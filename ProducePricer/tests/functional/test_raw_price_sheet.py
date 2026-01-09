import pytest
from datetime import date
from flask import url_for
from producepricer import db
from producepricer.models import RawProduct, CostHistory, User, Company

@pytest.fixture
def logged_in_user(client, app):
    """Fixture to create and log in a test user."""
    with app.app_context():
        # Create a test company
        company = Company(name="Test Company", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()
        
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
        
        # Store necessary data
        user_id = user.id
        company_id = company.id
        login_url = url_for('main.login')
    
    # Log in the user
    client.post(
        login_url,
        data={'email': 'user@test.com', 'password': 'password'},
        follow_redirects=True
    )
    
    # Return a helper object
    class LoggedInUserHelper:
        def __init__(self, user_id, company_id, app):
            self.id = user_id
            self.company_id = company_id
            self._app = app
            self.email = "user@test.com"
            self.first_name = "Test"
            self.last_name = "User"
            self.is_active = True
            self.is_authenticated = True
            self.is_anonymous = False
            
        def get_id(self):
            """Flask-Login required method."""
            return str(self.id)
            
        def get_user(self):
            with self._app.app_context():
                return db.session.get(User, self.id)
    
    return LoggedInUserHelper(user_id, company_id, app)

def test_raw_price_sheet_page(client, app, logged_in_user):
    """Test the raw price sheet page loads correctly with data."""
    with app.app_context():
        # Create raw products
        rp1 = RawProduct(name="Carrots", company_id=logged_in_user.company_id)
        rp2 = RawProduct(name="Potatoes", company_id=logged_in_user.company_id)
        db.session.add_all([rp1, rp2])
        db.session.commit()

        # Add cost history for Carrots
        # Oldest (should be ignored as we only show latest and previous)
        ch1_old = CostHistory(
            cost=5.00,
            date=date(2023, 1, 1),
            raw_product_id=rp1.id,
            company_id=logged_in_user.company_id
        )
        # Previous
        ch1_prev = CostHistory(
            cost=6.00,
            date=date(2023, 2, 1),
            raw_product_id=rp1.id,
            company_id=logged_in_user.company_id
        )
        # Latest
        ch1_latest = CostHistory(
            cost=7.50,
            date=date(2023, 3, 1),
            raw_product_id=rp1.id,
            company_id=logged_in_user.company_id
        )
        
        # Add cost history for Potatoes (only one entry)
        ch2_latest = CostHistory(
            cost=12.00,
            date=date(2023, 3, 1),
            raw_product_id=rp2.id,
            company_id=logged_in_user.company_id
        )

        db.session.add_all([ch1_old, ch1_prev, ch1_latest, ch2_latest])
        db.session.commit()

        # Get URL inside context
        url = url_for('main.raw_price_sheet')

    # Access the page
    response = client.get(url)
    
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    
    # Check title
    assert "Raw Product Price Sheet" in html
    
    # Check Carrots data
    assert "Carrots" in html
    assert "$7.50" in html  # Latest
    assert "2023-03-01" in html
    assert "$6.00" in html  # Previous
    assert "2023-02-01" in html
    
    # Check Potatoes data
    assert "Potatoes" in html
    assert "$12.00" in html
    
    # Verify export button exists
    # We need to get the URL for export button to check if it is in html
    # Since we are outside context, we can't use url_for easily unless we push context again
    # or rely on the fact that conftest keeps it open?
    # If conftest keeps it open, then why did I need to move client.get out?
    # Because client.get pops the context it creates, which might interfere with the nested context.
    
    # Let's just check for the text "Export PDF"
    assert "Export PDF" in html
    assert "Email PDF" in html

def test_raw_price_sheet_empty(client, app, logged_in_user):
    """Test the raw price sheet page when there are no raw products."""
    # Assuming the logged_in_user has no raw products initially
    response = client.get(url_for('main.raw_price_sheet'))
    assert response.status_code == 200
    assert "No raw products found" in response.data.decode('utf-8')

def test_raw_price_sheet_requires_login(client):
    """Test that the page requires login."""
    response = client.get(url_for('main.raw_price_sheet'), follow_redirects=True)
    # Should redirect to login page
    assert "Login" in response.data.decode('utf-8')
