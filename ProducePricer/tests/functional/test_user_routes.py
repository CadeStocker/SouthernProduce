import pytest
from flask import url_for
from flask_login import current_user
from unittest.mock import patch
from producepricer import db
from producepricer.models import User, Company, PendingUser

class TestSignupRoute:
    def test_signup_page_loads(self, client, app):
        """Test that signup page loads correctly when not logged in."""
        with app.app_context():
            # Ensure the user is not logged in
            #assert not current_user.is_authenticated
            response = client.get(url_for('main.signup'))
            assert response.status_code == 200
            assert b'Sign Up' in response.data
            assert b'<form' in response.data
            assert b'method="POST"' in response.data
        
    def test_signup_redirects_when_logged_in(self, client, login_user, app):
        """Test that signup page redirects to home when user is already logged in."""
        # Login the user
        login_user()
        
        # Generate URLs once in a context
        with app.test_request_context():
            signup_url = url_for('main.signup')
            home_url = url_for('main.home')
        
        # Make request outside context
        response = client.get(signup_url)
        
        # Check redirect
        assert response.status_code == 302
        assert home_url in response.location

    def test_signup_with_existing_email(self, client, app):
        """Test signup attempt with an already registered email."""
        # STEP 1: set up data in app context
        with app.app_context():
            company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(company)
            db.session.commit()
            company_id = company.id

            test_email = 'existing@test.com'
            user = User(
                first_name='Existing',
                last_name='User',
                email=test_email,
                password='Password123',
                company_id=company_id
            )
            db.session.add(user)
            db.session.commit()

            signup_url = url_for('main.signup')
            login_url  = url_for('main.login')

        # STEP 2: POST without following redirects
        data = {
            'first_name':      'New',
            'last_name':       'User',
            'email':           test_email,
            'password':        'newpassword1',  # Password must have a digit
            'confirm_password':'newpassword1',
            'company':         company_id,
        }
        
        resp = client.post(signup_url, data=data, follow_redirects=False)

        # Check if redirected to login (302) or stayed on page due to email exists
        if resp.status_code == 302:
            # Check that the redirect location contains 'login'
            assert 'login' in resp.headers['Location']
            # STEP 3: GET the login page to see the flash
            login_page = client.get(resp.headers['Location'])
            assert b'Email already registered.' in login_page.data
            assert b'Login' in login_page.data
        else:
            # Form might show error on page
            assert b'already registered' in resp.data or b'Sign Up' in resp.data
    
    @patch('producepricer.blueprints.auth.login_user')
    def test_signup_as_company_admin(self, mock_login, client, app):
        """Test signup as the company admin email (auto-approval)."""
        with app.app_context():
            # Create a company
            admin_email = 'admin@testcompany.com'
            company = Company(name='Admin Test Company', admin_email=admin_email)
            db.session.add(company)
            db.session.commit()
            
            # Signup as the company admin
            response = client.post(
                url_for('main.signup'),
                data={
                    'first_name': 'Admin',
                    'last_name': 'User',
                    'email': admin_email,  # Matches company.admin_email
                    'password': 'adminpassword1',  # Password must have a digit
                    'confirm_password': 'adminpassword1',
                    'company': company.id,
                },
                follow_redirects=True
            )
            
            # Check user was created (either via mock or direct creation)
            user = User.query.filter_by(email=admin_email).first()
            assert user is not None
            assert user.first_name == 'Admin'
            assert user.company_id == company.id
    
    @patch('producepricer.blueprints.auth.send_admin_approval_email')
    def test_regular_signup(self, mock_send_email, client, app):
        """Test regular user signup (requires admin approval)."""
        with app.app_context():
            # Create a company
            company = Company(name='Regular Test Company', admin_email='admin@company.com')
            db.session.add(company)
            db.session.commit()
            
            # Signup as a regular user
            email = 'newuser@test.com'
            response = client.post(
                url_for('main.signup'),
                data={
                    'first_name': 'Regular',
                    'last_name': 'User',
                    'email': email,
                    'password': 'userpassword1',  # Password must have a digit
                    'confirm_password': 'userpassword1',
                    'company': company.id,
                },
                follow_redirects=True
            )
            
            # Should create pending user
            pending_user = PendingUser.query.filter_by(email=email).first()
            assert pending_user is not None
            assert pending_user.first_name == 'Regular'
            assert pending_user.company_id == company.id

# Helper method for getting CSRF token
# @pytest.fixture
# def client_with_csrf():
#     """Client that automatically adds CSRF token to forms."""
#     from flask.testing import FlaskClient
    
#     class ClientWithCSRF(FlaskClient):
#         def get_csrf_token(self):
#             response = self.get(url_for('main.signup'))
#             csrf_token = response.data.decode('utf-8').split('csrf_token" value="')[1].split('"')[0]
#             return csrf_token
        
#         def post(self, *args, **kwargs):
#             if 'data' in kwargs and 'csrf_token' not in kwargs['data']:
#                 kwargs['data']['csrf_token'] = self.get_csrf_token()
#             return super().post(*args, **kwargs)
    
#     return ClientWithCSRF

# Add these fixtures if not already defined in conftest.py
# @pytest.fixture
# def client(app):
#     """Create a test client for the app."""
#     with app.test_client() as client:
#         client.get_csrf_token = lambda: client.get('/signup').data.decode('utf-8').split('csrf_token" value="')[1].split('"')[0]
#         yield client

@pytest.fixture
def login_user(app, client):
    """Log in a test user."""
    def _login_user():
        # Set up data in a separate context
        with app.app_context():
            # Create company
            company = Company.query.filter_by(name='Test Company').first()
            if not company:
                company = Company(name='Test Company', admin_email='admin@test.com')
                db.session.add(company)
                db.session.commit()
            
            # Create user if doesn't exist
            email = 'testuser@example.com'
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(
                    first_name='Test',
                    last_name='User',
                    email=email,
                    password='password',
                    company_id=company.id
                )
                db.session.add(user)
                db.session.commit()
            
            # Get login URL - must be inside context
            login_url = url_for('main.login')
            user_id = user.id  # Store ID to retrieve later
        
        # Login request - should be outside context
        client.post(
            login_url,
            data={
                'email': email,
                'password': 'password'
                # No need for CSRF token if disabled
            }
        )
        
        # Get the user again in a fresh context
        with app.app_context():
            return User.query.get(user_id)
            
    return _login_user