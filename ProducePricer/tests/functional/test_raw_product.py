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


class TestEditRawProduct:
    """Tests for editing raw product names."""
    
    def test_edit_raw_product_name_success(self, client, app, logged_in_user):
        """Test successfully renaming a raw product."""
        with app.app_context():
            # Create a raw product
            raw_product = RawProduct(
                name="Original Name",
                company_id=logged_in_user.company_id
            )
            db.session.add(raw_product)
            db.session.commit()
            raw_product_id = raw_product.id
            url = url_for('main.edit_raw_product', raw_product_id=raw_product_id)
        
        # Submit the edit form
        response = client.post(url, data={
            'name': 'New Name'
        }, follow_redirects=True)
        
        # Verify success
        assert response.status_code == 200
        assert b'renamed' in response.data.lower() or b'successfully' in response.data.lower()
        
        # Verify the name was actually changed in the database
        with app.app_context():
            updated_product = db.session.get(RawProduct, raw_product_id)
            assert updated_product.name == 'New Name'
    
    def test_edit_raw_product_name_reflects_in_items(self, client, app, logged_in_user):
        """Test that renaming a raw product is reflected when viewing items that use it."""
        with app.app_context():
            # Create a raw product
            raw_product = RawProduct(
                name="Original Raw Product",
                company_id=logged_in_user.company_id
            )
            db.session.add(raw_product)
            db.session.commit()
            
            # Create an item that uses this raw product
            from producepricer.models import Packaging, ItemInfo, LaborCost
            packaging = Packaging(packaging_type="Test Package", company_id=logged_in_user.company_id)
            db.session.add(packaging)
            db.session.commit()
            
            # Create a labor cost (required for item cost calculation)
            labor_cost = LaborCost(
                date=date(2025, 1, 1),
                labor_cost=15.00,
                company_id=logged_in_user.company_id
            )
            db.session.add(labor_cost)
            db.session.commit()
            
            item = Item(
                name="Test Item",
                code="TST-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging.id,
                company_id=logged_in_user.company_id,
                item_designation=ItemDesignation.FOODSERVICE
            )
            item.raw_products.append(raw_product)
            db.session.add(item)
            db.session.commit()
            
            # Create ItemInfo (required for view_item to work)
            item_info = ItemInfo(
                product_yield=1.0,
                item_id=item.id,
                labor_hours=1.0,
                date=date(2025, 1, 1),
                company_id=logged_in_user.company_id
            )
            db.session.add(item_info)
            db.session.commit()
            
            raw_product_id = raw_product.id
            item_id = item.id
            edit_url = url_for('main.edit_raw_product', raw_product_id=raw_product_id)
            view_item_url = url_for('main.view_item', item_id=item_id)
        
        # Rename the raw product
        client.post(edit_url, data={'name': 'Renamed Raw Product'}, follow_redirects=True)
        
        # View the item and check the new raw product name appears
        response = client.get(view_item_url)
        assert response.status_code == 200
        assert b'Renamed Raw Product' in response.data
        assert b'Original Raw Product' not in response.data
    
    def test_edit_raw_product_duplicate_name_rejected(self, client, app, logged_in_user):
        """Test that renaming to an existing raw product name is rejected."""
        with app.app_context():
            # Create two raw products
            raw_product1 = RawProduct(name="Product One", company_id=logged_in_user.company_id)
            raw_product2 = RawProduct(name="Product Two", company_id=logged_in_user.company_id)
            db.session.add_all([raw_product1, raw_product2])
            db.session.commit()
            
            raw_product1_id = raw_product1.id
            url = url_for('main.edit_raw_product', raw_product_id=raw_product1_id)
        
        # Try to rename Product One to Product Two (should fail)
        response = client.post(url, data={'name': 'Product Two'}, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'already exists' in response.data.lower()
        
        # Verify the name was NOT changed
        with app.app_context():
            product = db.session.get(RawProduct, raw_product1_id)
            assert product.name == 'Product One'
    
    def test_edit_raw_product_preserves_cost_history(self, client, app, logged_in_user):
        """Test that renaming a raw product preserves its cost history."""
        with app.app_context():
            # Create a raw product with cost history
            raw_product = RawProduct(name="Old Name", company_id=logged_in_user.company_id)
            db.session.add(raw_product)
            db.session.commit()
            
            cost1 = CostHistory(
                cost=15.00,
                date=date(2025, 1, 1),
                company_id=logged_in_user.company_id,
                raw_product_id=raw_product.id
            )
            cost2 = CostHistory(
                cost=16.50,
                date=date(2025, 2, 1),
                company_id=logged_in_user.company_id,
                raw_product_id=raw_product.id
            )
            db.session.add_all([cost1, cost2])
            db.session.commit()
            
            raw_product_id = raw_product.id
            edit_url = url_for('main.edit_raw_product', raw_product_id=raw_product_id)
        
        # Rename the raw product
        client.post(edit_url, data={'name': 'New Name'}, follow_redirects=True)
        
        # Verify cost history is still there
        with app.app_context():
            costs = CostHistory.query.filter_by(raw_product_id=raw_product_id).all()
            assert len(costs) == 2
            assert costs[0].cost == 15.00
            assert costs[1].cost == 16.50
    
    def test_edit_other_company_raw_product_forbidden(self, client, app, logged_in_user):
        """Test that editing a raw product from another company is not allowed."""
        with app.app_context():
            # Create another company and raw product
            other_company = Company(name="Other Company", admin_email="other@example.com")
            db.session.add(other_company)
            db.session.commit()
            
            other_raw_product = RawProduct(name="Other Product", company_id=other_company.id)
            db.session.add(other_raw_product)
            db.session.commit()
            
            url = url_for('main.edit_raw_product', raw_product_id=other_raw_product.id)
        
        # Try to edit the other company's raw product
        response = client.post(url, data={'name': 'Hacked Name'}, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'not found' in response.data.lower() or b'permission' in response.data.lower()


class TestDeleteRawProduct:
    """Tests for deleting raw products and cleanup of associations."""
    
    def test_delete_raw_product_removes_item_associations(self, client, app, logged_in_user):
        """Test that deleting a raw product properly removes it from items."""
        with app.app_context():
            # Create a raw product
            raw_product = RawProduct(name="To Be Deleted", company_id=logged_in_user.company_id)
            db.session.add(raw_product)
            db.session.commit()
            
            # Create an item using this raw product
            from producepricer.models import Packaging, ItemInfo, LaborCost
            packaging = Packaging(packaging_type="Test Package", company_id=logged_in_user.company_id)
            db.session.add(packaging)
            db.session.commit()
            
            # Create a labor cost (required for item cost calculation)
            labor_cost = LaborCost(
                date=date(2025, 1, 1),
                labor_cost=15.00,
                company_id=logged_in_user.company_id
            )
            db.session.add(labor_cost)
            db.session.commit()
            
            item = Item(
                name="Item With Raw Product",
                code="ITM-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging.id,
                company_id=logged_in_user.company_id,
                item_designation=ItemDesignation.FOODSERVICE
            )
            item.raw_products.append(raw_product)
            db.session.add(item)
            db.session.commit()
            
            # Create ItemInfo (required for view_item to work)
            item_info = ItemInfo(
                product_yield=1.0,
                item_id=item.id,
                labor_hours=1.0,
                date=date(2025, 1, 1),
                company_id=logged_in_user.company_id
            )
            db.session.add(item_info)
            db.session.commit()
            
            raw_product_id = raw_product.id
            item_id = item.id
            delete_url = url_for('main.delete_raw_product', raw_product_id=raw_product_id)
            view_item_url = url_for('main.view_item', item_id=item_id)
        
        # Delete the raw product
        response = client.post(delete_url, follow_redirects=True)
        assert response.status_code == 200
        assert b'deleted' in response.data.lower()
        
        # Verify the item can still be viewed without errors
        response = client.get(view_item_url)
        assert response.status_code == 200
        # The deleted raw product should not appear
        assert b'To Be Deleted' not in response.data
    
    def test_delete_raw_product_item_list_no_errors(self, client, app, logged_in_user):
        """Test that the items list page works correctly after deleting a raw product."""
        with app.app_context():
            # Create a raw product
            raw_product = RawProduct(name="Delete Me", company_id=logged_in_user.company_id)
            db.session.add(raw_product)
            db.session.commit()
            
            # Create an item using this raw product
            from producepricer.models import Packaging
            packaging = Packaging(packaging_type="Test Package", company_id=logged_in_user.company_id)
            db.session.add(packaging)
            db.session.commit()
            
            item = Item(
                name="Test Item For Delete",
                code="DEL-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging.id,
                company_id=logged_in_user.company_id,
                item_designation=ItemDesignation.FOODSERVICE
            )
            item.raw_products.append(raw_product)
            db.session.add(item)
            db.session.commit()
            
            raw_product_id = raw_product.id
            delete_url = url_for('main.delete_raw_product', raw_product_id=raw_product_id)
            items_url = url_for('main.items')
        
        # Delete the raw product
        client.post(delete_url, follow_redirects=True)
        
        # View the items list - should not crash
        response = client.get(items_url)
        assert response.status_code == 200
        assert b'Test Item For Delete' in response.data
        # Deleted raw product should not appear
        assert b'Delete Me' not in response.data
    
    def test_delete_raw_product_deletes_cost_history(self, client, app, logged_in_user):
        """Test that deleting a raw product also deletes its cost history."""
        with app.app_context():
            # Create a raw product with cost history
            raw_product = RawProduct(name="Product With Costs", company_id=logged_in_user.company_id)
            db.session.add(raw_product)
            db.session.commit()
            
            cost = CostHistory(
                cost=20.00,
                date=date(2025, 1, 1),
                company_id=logged_in_user.company_id,
                raw_product_id=raw_product.id
            )
            db.session.add(cost)
            db.session.commit()
            
            raw_product_id = raw_product.id
            cost_id = cost.id
            delete_url = url_for('main.delete_raw_product', raw_product_id=raw_product_id)
        
        # Delete the raw product
        client.post(delete_url, follow_redirects=True)
        
        # Verify cost history was also deleted
        with app.app_context():
            remaining_cost = db.session.get(CostHistory, cost_id)
            assert remaining_cost is None
    
    def test_delete_raw_product_multiple_items_all_cleaned(self, client, app, logged_in_user):
        """Test that deleting a raw product cleans up associations from multiple items."""
        with app.app_context():
            # Create a raw product
            raw_product = RawProduct(name="Shared Raw Product", company_id=logged_in_user.company_id)
            db.session.add(raw_product)
            db.session.commit()
            
            # Create packaging
            from producepricer.models import Packaging
            packaging = Packaging(packaging_type="Test Package", company_id=logged_in_user.company_id)
            db.session.add(packaging)
            db.session.commit()
            
            # Create multiple items using this raw product
            item1 = Item(
                name="Item One",
                code="ONE-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging.id,
                company_id=logged_in_user.company_id,
                item_designation=ItemDesignation.FOODSERVICE
            )
            item1.raw_products.append(raw_product)
            
            item2 = Item(
                name="Item Two",
                code="TWO-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging.id,
                company_id=logged_in_user.company_id,
                item_designation=ItemDesignation.RETAIL
            )
            item2.raw_products.append(raw_product)
            
            db.session.add_all([item1, item2])
            db.session.commit()
            
            raw_product_id = raw_product.id
            item1_id = item1.id
            item2_id = item2.id
            delete_url = url_for('main.delete_raw_product', raw_product_id=raw_product_id)
        
        # Delete the raw product
        client.post(delete_url, follow_redirects=True)
        
        # Verify both items no longer have this raw product
        with app.app_context():
            item1 = db.session.get(Item, item1_id)
            item2 = db.session.get(Item, item2_id)
            
            assert len(item1.raw_products) == 0
            assert len(item2.raw_products) == 0


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