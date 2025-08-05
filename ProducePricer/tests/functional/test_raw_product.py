import pytest
from datetime import date
from flask import url_for
from flask_login import current_user
from producepricer import db
from producepricer.models import User, Company, RawProduct, CostHistory, Item, UnitOfWeight, ItemDesignation


class TestViewRawProduct:
    def test_view_raw_product_success(self, client, app, logged_in_user):
        """Test successful display of raw product details when logged in."""
        with app.app_context():
            # Create a raw product for the logged-in user's company
            raw_product = RawProduct(
                name="Test Raw Product",
                company_id=logged_in_user.company_id
            )
            db.session.add(raw_product)
            db.session.commit()
            
            # Add some cost history
            cost1 = CostHistory(
                cost=10.50,
                date=date(2025, 1, 1),
                company_id=logged_in_user.company_id,
                raw_product_id=raw_product.id
            )
            cost2 = CostHistory(
                cost=11.25,
                date=date(2025, 2, 1),
                company_id=logged_in_user.company_id,
                raw_product_id=raw_product.id
            )
            db.session.add_all([cost1, cost2])
            
            # Create an item that uses this raw product
            from producepricer.models import Packaging
            packaging_id = app.test_packaging_id  # Use the ID instead of the object
            item = Item(
                name="Test Item",
                code="TST-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging_id,  # Use the ID directly
                company_id=logged_in_user.company_id,
                item_designation=ItemDesignation.FOODSERVICE
            )
            # Link the item to the raw product
            item.raw_products.append(raw_product)
            db.session.add(item)
            db.session.commit()
            
            # Get the URL for viewing this raw product
            url = url_for('main.view_raw_product', raw_product_id=raw_product.id)

    def test_view_nonexistent_raw_product(self, client, app, logged_in_user):
        """Test redirect when trying to view a raw product that doesn't exist."""
        with app.app_context():
            # Use a raw product ID that doesn't exist
            url = url_for('main.view_raw_product', raw_product_id=9999)
            
        # Make the request
        response = client.get(url, follow_redirects=True)
        
        # Check for redirect to raw products list
        assert response.status_code == 200  # After redirect
        assert b"Raw product not found" in response.data
        
        # Make sure we're on the raw products listing page
        assert b"Raw Products" in response.data

    def test_view_other_company_raw_product(self, client, app, logged_in_user):
        """Test redirect when trying to view a raw product from another company."""
        with app.app_context():
            # Create another company
            other_company = Company(name="Other Company", admin_email="other@example.com")
            db.session.add(other_company)
            db.session.commit()
            
            # Create a raw product for the other company
            other_raw_product = RawProduct(
                name="Other Company's Raw Product",
                company_id=other_company.id
            )
            db.session.add(other_raw_product)
            db.session.commit()
            
            # Get URL for viewing the other company's raw product
            url = url_for('main.view_raw_product', raw_product_id=other_raw_product.id)
            
        # Make the request
        response = client.get(url, follow_redirects=True)
        
        # Should redirect with a "not found" message (security through obscurity)
        assert response.status_code == 200  # After redirect
        assert b"Raw product not found" in response.data

    def test_unauthorized_access(self, client, app):
        """Test redirect to login when not logged in."""
        with app.app_context():
            # Create a company and raw product
            company = Company(name="Test Company", admin_email="admin@example.com")
            db.session.add(company)
            db.session.commit()
            
            raw_product = RawProduct(
                name="Test Raw Product",
                company_id=company.id
            )
            db.session.add(raw_product)
            db.session.commit()
            
            # Get URL for viewing the raw product
            raw_product_url = url_for('main.view_raw_product', raw_product_id=raw_product.id)
            login_url = url_for('main.login', _external=False)
            
        # Make the request without being logged in
        response = client.get(raw_product_url, follow_redirects=False)
        
        # Should redirect to login
        assert response.status_code == 302
        assert login_url in response.location
    
    def test_cost_history_chart(self, client, app, logged_in_user):
        """Test that the cost history chart data is correctly included."""
        with app.app_context():
            # Create raw product with multiple cost entries
            raw_product = RawProduct(
                name="Chart Test Product",
                company_id=logged_in_user.company_id
            )
            db.session.add(raw_product)
            db.session.commit()
            
            # Create several cost history entries
            costs = [
                CostHistory(cost=10.00, date=date(2025, 1, 1), company_id=logged_in_user.company_id, raw_product_id=raw_product.id),
                CostHistory(cost=10.50, date=date(2025, 2, 1), company_id=logged_in_user.company_id, raw_product_id=raw_product.id),
                CostHistory(cost=11.00, date=date(2025, 3, 1), company_id=logged_in_user.company_id, raw_product_id=raw_product.id),
            ]
            db.session.add_all(costs)
            db.session.commit()
            
            url = url_for('main.view_raw_product', raw_product_id=raw_product.id)
            
        # Make the request
        response = client.get(url)
        
        # Check that the chart data is included in the HTML
        html = response.data.decode('utf-8')
        
        # Check for chart elements
        assert 'id="costTrendChart"' in html
        
        # Check for the JavaScript data structure with our costs
        assert "costData" in html
        assert '"2025-01-01"' in html
        assert '"2025-02-01"' in html
        assert '"2025-03-01"' in html
        assert "10.00" in html
        assert "10.50" in html
        assert "11.00" in html


@pytest.fixture
def logged_in_user(client, app):
    """Fixture to create and log in a test user."""
    with app.app_context():
        # Create a test company
        company = Company(name="Test Company", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()
        app.test_company_id = company.id
        
        # Create test packaging for items
        from producepricer.models import Packaging
        packaging = Packaging(packaging_type="Test Packaging", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        app.test_packaging_id = packaging.id  # Store the ID, not the object
        
        # Create a test user
        user = User(
            first_name="Test",
            last_name="User",
            email="user@test.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()
        
        # Store the user ID for later retrieval
        user_id = user.id
    
    # Log in the user
    client.post(
        url_for('main.login'),
        data={'email': 'user@test.com', 'password': 'password'},
        follow_redirects=True
    )
    
    # Return a function that gets a fresh user object
    def get_user():
        with app.app_context():
            return db.session.get(User, user_id)
            
    return get_user()