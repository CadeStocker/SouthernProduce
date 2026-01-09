import pytest
from datetime import date
from flask import url_for
from producepricer import db
from producepricer.models import User, Company, Customer, CustomerEmail


class TestCustomerPage:
    """Tests for the customer list page."""

    def test_view_customer_page_success(self, client, app, logged_in_user):
        """Test successful display of customer page when logged in."""
        with app.app_context():
            url = url_for('main.customer')
        
        response = client.get(url)
        assert response.status_code == 200
        assert b'Customers' in response.data
        assert b'Customer List' in response.data

    def test_view_customer_page_requires_login(self, client, app):
        """Test that customer page requires login."""
        with app.app_context():
            customer_url = url_for('main.customer')
            login_url = url_for('main.login', _external=False)
        
        response = client.get(customer_url, follow_redirects=False)
        assert response.status_code == 302
        assert login_url in response.location

    def test_view_customers_displays_all_customers(self, client, app, logged_in_user):
        """Test that all customers for the company are displayed."""
        with app.app_context():
            # Create some test customers
            customer1 = Customer(
                name="Customer One",
                email="one@test.com",
                company_id=logged_in_user.company_id
            )
            customer2 = Customer(
                name="Customer Two",
                email="two@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add_all([customer1, customer2])
            db.session.commit()
            
            url = url_for('main.customer')
        
        response = client.get(url)
        assert response.status_code == 200
        assert b'Customer One' in response.data
        assert b'Customer Two' in response.data
        assert b'one@test.com' in response.data
        assert b'two@test.com' in response.data

    def test_view_customers_does_not_show_other_company_customers(self, client, app, logged_in_user):
        """Test that customers from other companies are not shown."""
        with app.app_context():
            # Create another company
            other_company = Company(name="Other Company", admin_email="other@company.com")
            db.session.add(other_company)
            db.session.commit()
            
            # Create a customer for the other company
            other_customer = Customer(
                name="Other Company Customer",
                email="other@customer.com",
                company_id=other_company.id
            )
            db.session.add(other_customer)
            db.session.commit()
            
            url = url_for('main.customer')
        
        response = client.get(url)
        assert response.status_code == 200
        assert b'Other Company Customer' not in response.data


class TestAddCustomer:
    """Tests for adding new customers."""

    def test_add_customer_success(self, client, app, logged_in_user):
        """Test successfully adding a new customer."""
        with app.app_context():
            url = url_for('main.add_customer')
        
        response = client.post(url, data={
            'name': 'New Customer',
            'email': 'new@customer.com'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'added successfully' in response.data.lower() or b'success' in response.data.lower()
        
        # Verify customer was actually created
        with app.app_context():
            customer = Customer.query.filter_by(email='new@customer.com').first()
            assert customer is not None
            assert customer.name == 'New Customer'

    def test_add_customer_duplicate_email_rejected(self, client, app, logged_in_user):
        """Test that adding a customer with duplicate email is rejected."""
        with app.app_context():
            # Create an existing customer
            existing = Customer(
                name="Existing Customer",
                email="existing@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(existing)
            db.session.commit()
            
            url = url_for('main.add_customer')
        
        # Try to add another customer with the same email
        response = client.post(url, data={
            'name': 'Another Customer',
            'email': 'existing@test.com'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'unique' in response.data.lower() or b'already exists' in response.data.lower()

    def test_add_customer_duplicate_name_and_email_rejected(self, client, app, logged_in_user):
        """Test that adding a customer with duplicate name and email is rejected."""
        with app.app_context():
            # Create an existing customer
            existing = Customer(
                name="Duplicate Name",
                email="duplicate@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(existing)
            db.session.commit()
            
            url = url_for('main.add_customer')
        
        # Try to add another customer with the same name and email
        response = client.post(url, data={
            'name': 'Duplicate Name',
            'email': 'duplicate@test.com'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'already exists' in response.data.lower()


class TestEditCustomer:
    """Tests for editing customer information."""

    def test_edit_customer_name_success(self, client, app, logged_in_user):
        """Test successfully editing a customer's name."""
        with app.app_context():
            customer = Customer(
                name="Original Name",
                email="customer@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            customer_id = customer.id
            url = url_for('main.edit_customer', customer_id=customer_id)
        
        response = client.post(url, data={
            'name': 'Updated Name',
            'email': 'customer@test.com'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'updated successfully' in response.data.lower()
        
        # Verify the name was changed
        with app.app_context():
            customer = db.session.get(Customer, customer_id)
            assert customer.name == 'Updated Name'

    def test_edit_customer_email_success(self, client, app, logged_in_user):
        """Test successfully editing a customer's email."""
        with app.app_context():
            customer = Customer(
                name="Test Customer",
                email="old@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            customer_id = customer.id
            url = url_for('main.edit_customer', customer_id=customer_id)
        
        response = client.post(url, data={
            'name': 'Test Customer',
            'email': 'new@test.com'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'updated successfully' in response.data.lower()
        
        # Verify the email was changed
        with app.app_context():
            customer = db.session.get(Customer, customer_id)
            assert customer.email == 'new@test.com'

    def test_edit_customer_set_master(self, client, app, logged_in_user):
        """Test setting a customer as master."""
        with app.app_context():
            customer = Customer(
                name="Test Customer",
                email="test@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            customer_id = customer.id
            url = url_for('main.edit_customer', customer_id=customer_id)
        
        response = client.post(url, data={
            'name': 'Test Customer',
            'email': 'test@test.com',
            'is_master': 'on'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify is_master was set
        with app.app_context():
            customer = db.session.get(Customer, customer_id)
            assert customer.is_master == True

    def test_edit_customer_change_master_unmarks_previous(self, client, app, logged_in_user):
        """Test that setting a new master customer unmarks the previous one."""
        with app.app_context():
            # Create first customer as master
            customer1 = Customer(
                name="First Master",
                email="first@test.com",
                company_id=logged_in_user.company_id
            )
            customer1.is_master = True
            
            customer2 = Customer(
                name="Second Customer",
                email="second@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add_all([customer1, customer2])
            db.session.commit()
            
            customer1_id = customer1.id
            customer2_id = customer2.id
            url = url_for('main.edit_customer', customer_id=customer2_id)
        
        # Set customer2 as master
        response = client.post(url, data={
            'name': 'Second Customer',
            'email': 'second@test.com',
            'is_master': 'on'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify customer2 is now master and customer1 is not
        with app.app_context():
            customer1 = db.session.get(Customer, customer1_id)
            customer2 = db.session.get(Customer, customer2_id)
            assert customer1.is_master == False
            assert customer2.is_master == True

    def test_edit_other_company_customer_forbidden(self, client, app, logged_in_user):
        """Test that editing a customer from another company is not allowed."""
        with app.app_context():
            # Create another company and customer
            other_company = Company(name="Other Company", admin_email="other@company.com")
            db.session.add(other_company)
            db.session.commit()
            
            other_customer = Customer(
                name="Other Customer",
                email="other@customer.com",
                company_id=other_company.id
            )
            db.session.add(other_customer)
            db.session.commit()
            
            url = url_for('main.edit_customer', customer_id=other_customer.id)
        
        response = client.post(url, data={
            'name': 'Hacked Name',
            'email': 'hacked@email.com'
        }, follow_redirects=True)
        
        assert response.status_code == 404
        # assert b'not found' in response.data.lower() or b'permission' in response.data.lower()


class TestDeleteCustomer:
    """Tests for deleting customers."""

    def test_delete_customer_success(self, client, app, logged_in_user):
        """Test successfully deleting a customer."""
        with app.app_context():
            customer = Customer(
                name="To Be Deleted",
                email="delete@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            customer_id = customer.id
            url = url_for('main.delete_customer', customer_id=customer_id)
        
        response = client.post(url, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'deleted successfully' in response.data.lower()
        
        # Verify customer was deleted
        with app.app_context():
            customer = db.session.get(Customer, customer_id)
            assert customer is None

    def test_delete_customer_also_deletes_emails(self, client, app, logged_in_user):
        """Test that deleting a customer also deletes associated emails."""
        with app.app_context():
            customer = Customer(
                name="Customer With Emails",
                email="main@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            # Add additional emails
            email1 = CustomerEmail(email="extra1@test.com", customer_id=customer.id, label="Billing")
            email2 = CustomerEmail(email="extra2@test.com", customer_id=customer.id, label="Sales")
            db.session.add_all([email1, email2])
            db.session.commit()
            
            customer_id = customer.id
            email1_id = email1.id
            email2_id = email2.id
            url = url_for('main.delete_customer', customer_id=customer_id)
        
        response = client.post(url, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify customer and all emails were deleted
        with app.app_context():
            assert db.session.get(Customer, customer_id) is None
            assert db.session.get(CustomerEmail, email1_id) is None
            assert db.session.get(CustomerEmail, email2_id) is None

    def test_delete_other_company_customer_forbidden(self, client, app, logged_in_user):
        """Test that deleting a customer from another company is not allowed."""
        with app.app_context():
            # Create another company and customer
            other_company = Company(name="Other Company", admin_email="other@company.com")
            db.session.add(other_company)
            db.session.commit()
            
            other_customer = Customer(
                name="Other Customer",
                email="other@customer.com",
                company_id=other_company.id
            )
            db.session.add(other_customer)
            db.session.commit()
            
            customer_id = other_customer.id
            url = url_for('main.delete_customer', customer_id=customer_id)
        
        response = client.post(url, follow_redirects=True)
        
        assert response.status_code == 404
        # assert b'not found' in response.data.lower() or b'permission' in response.data.lower()
        
        # Verify customer was NOT deleted
        with app.app_context():
            customer = db.session.get(Customer, customer_id)
            assert customer is not None


class TestCustomerEmails:
    """Tests for managing customer email addresses."""

    def test_view_customer_emails_page(self, client, app, logged_in_user):
        """Test viewing the customer emails management page."""
        with app.app_context():
            customer = Customer(
                name="Test Customer",
                email="main@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            url = url_for('main.manage_customer_emails', customer_id=customer.id)
        
        response = client.get(url)
        assert response.status_code == 200
        assert b'Test Customer' in response.data
        assert b'main@test.com' in response.data

    def test_add_customer_email_success(self, client, app, logged_in_user):
        """Test successfully adding an email to a customer."""
        with app.app_context():
            customer = Customer(
                name="Test Customer",
                email="main@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            customer_id = customer.id
            url = url_for('main.add_customer_email', customer_id=customer_id)
        
        response = client.post(url, data={
            'email': 'additional@test.com',
            'label': 'Billing'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'added successfully' in response.data.lower()
        
        # Verify email was added
        with app.app_context():
            email = CustomerEmail.query.filter_by(
                customer_id=customer_id,
                email='additional@test.com'
            ).first()
            assert email is not None
            assert email.label == 'Billing'

    def test_add_duplicate_customer_email_rejected(self, client, app, logged_in_user):
        """Test that adding a duplicate email is rejected."""
        with app.app_context():
            customer = Customer(
                name="Test Customer",
                email="main@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            # Add an additional email
            email = CustomerEmail(email="extra@test.com", customer_id=customer.id)
            db.session.add(email)
            db.session.commit()
            
            customer_id = customer.id
            url = url_for('main.add_customer_email', customer_id=customer_id)
        
        # Try to add the same email again
        response = client.post(url, data={
            'email': 'extra@test.com',
            'label': 'Duplicate'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'already added' in response.data.lower()

    def test_add_primary_email_as_additional_rejected(self, client, app, logged_in_user):
        """Test that adding the primary email as additional is rejected."""
        with app.app_context():
            customer = Customer(
                name="Test Customer",
                email="main@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            customer_id = customer.id
            url = url_for('main.add_customer_email', customer_id=customer_id)
        
        # Try to add the primary email as additional
        response = client.post(url, data={
            'email': 'main@test.com',
            'label': 'Duplicate'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'already' in response.data.lower()

    def test_delete_customer_email_success(self, client, app, logged_in_user):
        """Test successfully deleting a customer email."""
        with app.app_context():
            customer = Customer(
                name="Test Customer",
                email="main@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            email = CustomerEmail(email="to-delete@test.com", customer_id=customer.id)
            db.session.add(email)
            db.session.commit()
            
            customer_id = customer.id
            email_id = email.id
            url = url_for('main.delete_customer_email', customer_id=customer_id, email_id=email_id)
        
        response = client.post(url, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'removed successfully' in response.data.lower()
        
        # Verify email was deleted
        with app.app_context():
            email = db.session.get(CustomerEmail, email_id)
            assert email is None

    def test_update_customer_email_label(self, client, app, logged_in_user):
        """Test updating a customer email label."""
        with app.app_context():
            customer = Customer(
                name="Test Customer",
                email="main@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            email = CustomerEmail(email="extra@test.com", customer_id=customer.id, label="Old Label")
            db.session.add(email)
            db.session.commit()
            
            customer_id = customer.id
            email_id = email.id
            url = url_for('main.update_customer_email', customer_id=customer_id, email_id=email_id)
        
        response = client.post(url, data={
            'label': 'New Label'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'updated successfully' in response.data.lower()
        
        # Verify label was updated
        with app.app_context():
            email = db.session.get(CustomerEmail, email_id)
            assert email.label == 'New Label'


class TestCustomerGetAllEmails:
    """Tests for the get_all_emails method on Customer model."""

    def test_get_all_emails_primary_only(self, app, logged_in_user):
        """Test get_all_emails with only primary email."""
        with app.app_context():
            customer = Customer(
                name="Test Customer",
                email="primary@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            emails = customer.get_all_emails()
            assert emails == ['primary@test.com']

    def test_get_all_emails_with_additional(self, app, logged_in_user):
        """Test get_all_emails with primary and additional emails."""
        with app.app_context():
            customer = Customer(
                name="Test Customer",
                email="primary@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            email1 = CustomerEmail(email="extra1@test.com", customer_id=customer.id)
            email2 = CustomerEmail(email="extra2@test.com", customer_id=customer.id)
            db.session.add_all([email1, email2])
            db.session.commit()
            
            emails = customer.get_all_emails()
            assert 'primary@test.com' in emails
            assert 'extra1@test.com' in emails
            assert 'extra2@test.com' in emails
            assert len(emails) == 3

    def test_get_all_emails_no_duplicates(self, app, logged_in_user):
        """Test that get_all_emails does not return duplicates."""
        with app.app_context():
            customer = Customer(
                name="Test Customer",
                email="primary@test.com",
                company_id=logged_in_user.company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            # Note: This shouldn't happen normally, but test the logic
            emails = customer.get_all_emails()
            assert len(emails) == len(set(emails))


@pytest.fixture
def logged_in_user(client, app):
    """Fixture to create and log in a test user."""
    with app.app_context():
        # Create a test company
        company = Company(name="Test Company", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()
        app.test_company_id = company.id
        
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
        
        # Store the user ID and company ID for later retrieval
        user_id = user.id
        company_id = company.id
        login_url = url_for('main.login')
    
    # Log in the user (outside app context is fine for client.post)
    client.post(
        login_url,
        data={'email': 'user@test.com', 'password': 'password'},
        follow_redirects=True
    )
    
    # Return a helper object similar to conftest.py
    class LoggedInUserHelper:
        def __init__(self, user_id, company_id, app):
            self.id = user_id
            self.company_id = company_id
            self._app = app
            self.email = "user@test.com"
            self.first_name = "Test"
            self.last_name = "User"
            # Add Flask-Login required attributes
            self.is_active = True
            self.is_authenticated = True
            self.is_anonymous = False
            
        def get_id(self):
            """Flask-Login required method."""
            return str(self.id)
            
        def get_user(self):
            """Get the actual User object within an app context."""
            with self._app.app_context():
                return db.session.get(User, self.id)
    
    return LoggedInUserHelper(user_id, company_id, app)
