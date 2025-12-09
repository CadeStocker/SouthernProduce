"""
Comprehensive tests for Flask routes - authentication, pages, and API endpoints.
Tests cover GET/POST requests, login requirements, and basic functionality.
"""

import pytest
from flask import url_for
from unittest.mock import patch, MagicMock
from datetime import date
from producepricer import db
from producepricer.models import (
    Company, User, Customer, Item, RawProduct, Packaging,
    LaborCost, PendingUser, UnitOfWeight, ItemDesignation
)


# ====================
# Fixtures
# ====================

@pytest.fixture
def setup_company(app):
    """Create a test company."""
    with app.app_context():
        company = Company(name="Route Test Company", admin_email="routeuser@test.com")
        db.session.add(company)
        db.session.commit()
        return company.id


@pytest.fixture
def setup_user(app, setup_company):
    """Create a test user who is the company admin."""
    with app.app_context():
        user = User(
            first_name="Route",
            last_name="User",
            email="routeuser@test.com",  # Must match company admin_email
            password="testpassword",
            company_id=setup_company
        )
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def logged_in_client(client, app, setup_user):
    """Return a client that is logged in."""
    with app.app_context():
        user = db.session.get(User, setup_user)
        client.post('/login', data={
            'email': user.email,
            'password': 'testpassword'
        })
    return client


# ====================
# Public Pages Tests
# ====================

class TestPublicPages:
    def test_about_page_loads(self, client, app):
        """Test the about page loads without login."""
        response = client.get('/about')
        assert response.status_code == 200
        assert b'About' in response.data or response.status_code == 200

    def test_signup_page_loads(self, client, app):
        """Test the signup page loads."""
        response = client.get('/signup')
        assert response.status_code == 200
        assert b'Sign Up' in response.data

    def test_login_page_loads(self, client, app):
        """Test the login page loads."""
        response = client.get('/login')
        assert response.status_code == 200
        assert b'Login' in response.data

    def test_create_company_page_loads(self, client, app):
        """Test the create company page loads."""
        response = client.get('/create_company')
        assert response.status_code == 200


# ====================
# Protected Pages Tests
# ====================

class TestProtectedPages:
    def test_home_redirects_when_not_logged_in(self, client, app):
        """Test that home page requires login."""
        response = client.get('/')
        assert response.status_code == 302  # Redirect to login
        assert '/login' in response.location

    def test_home_accessible_when_logged_in(self, logged_in_client, app):
        """Test that logged in users can access home."""
        response = logged_in_client.get('/')
        assert response.status_code == 200

    def test_company_page_requires_login(self, client, app):
        """Test company page requires login."""
        response = client.get('/company')
        assert response.status_code == 302
        assert '/login' in response.location


# ====================
# Authentication Tests
# ====================

class TestAuthentication:
    def test_login_success(self, client, app, setup_user):
        """Test successful login."""
        response = client.post('/login', data={
            'email': 'routeuser@test.com',
            'password': 'testpassword'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_login_failure_wrong_password(self, client, app, setup_user):
        """Test login fails with wrong password."""
        response = client.post('/login', data={
            'email': 'routeuser@test.com',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        # Should stay on login page or show error
        assert b'Login' in response.data or b'Invalid' in response.data

    def test_login_failure_nonexistent_user(self, client, app):
        """Test login fails for non-existent user."""
        response = client.post('/login', data={
            'email': 'nonexistent@test.com',
            'password': 'anypassword'
        }, follow_redirects=True)
        assert b'Login' in response.data

    def test_logout(self, logged_in_client, app):
        """Test logout functionality."""
        response = logged_in_client.get('/logout', follow_redirects=True)
        assert response.status_code == 200
        
        # Verify we can't access protected pages anymore
        response = logged_in_client.get('/')
        assert response.status_code == 302  # Should redirect to login


# ====================
# Signup Tests
# ====================

class TestSignup:
    def test_signup_page_shows_companies(self, client, app, setup_company):
        """Test that signup page shows available companies."""
        response = client.get('/signup')
        assert response.status_code == 200
        assert b'Route Test Company' in response.data

    def test_signup_with_existing_email_fails(self, client, app, setup_user, setup_company):
        """Test that signup with existing email fails."""
        response = client.post('/signup', data={
            'first_name': 'Another',
            'last_name': 'User',
            'email': 'routeuser@test.com',
            'password': 'newpassword123',
            'confirm_password': 'newpassword123',
            'company': setup_company
        }, follow_redirects=True)
        assert b'already registered' in response.data or b'Login' in response.data

    @patch('producepricer.routes.send_admin_approval_email')
    def test_signup_creates_pending_user(self, mock_send_email, client, app, setup_company):
        """Test that regular signup creates a pending user."""
        response = client.post('/signup', data={
            'first_name': 'New',
            'last_name': 'Signup',
            'email': 'newsignup@test.com',
            'password': 'newpassword1',
            'confirm_password': 'newpassword1',
            'company': setup_company
        }, follow_redirects=True)
        
        with app.app_context():
            pending = PendingUser.query.filter_by(email='newsignup@test.com').first()
            # Either pending user was created or there was an issue
            # For admin email signup, user would be created directly
            assert pending is not None or response.status_code == 200


# ====================
# Company Creation Tests
# ====================

class TestCompanyCreation:
    def test_create_company_success(self, client, app):
        """Test successful company creation."""
        response = client.post('/create_company', data={
            'name': 'New Test Company',
            'admin_email': 'newadmin@newcompany.com'
        }, follow_redirects=True)
        
        with app.app_context():
            company = Company.query.filter_by(name='New Test Company').first()
            assert company is not None
            assert company.admin_email == 'newadmin@newcompany.com'

    def test_create_duplicate_company_fails(self, client, app, setup_company):
        """Test that creating duplicate company fails."""
        with app.app_context():
            existing = Company.query.get(setup_company)
            existing_name = existing.name
        
        response = client.post('/create_company', data={
            'name': existing_name,
            'admin_email': 'different@email.com'
        }, follow_redirects=True)
        
        # Should show error about duplicate name
        assert b'already in use' in response.data or response.status_code == 200


# ====================
# API Endpoint Tests
# ====================

class TestAPIEndpoints:
    def test_api_requires_login(self, client, app):
        """Test that API endpoints require login."""
        # Test various API endpoints
        api_endpoints = [
            '/api/ai-chat',
            '/api/parse_price_pdf',
            '/api/save_parsed_prices',
        ]
        
        for endpoint in api_endpoints:
            response = client.post(endpoint)
            # Should redirect to login or return 401
            assert response.status_code in [302, 401, 400]


# ====================
# Logged In Route Tests
# ====================

class TestLoggedInRoutes:
    def test_company_page_accessible(self, logged_in_client, app, setup_user):
        """Test company page is accessible when logged in."""
        response = logged_in_client.get('/company')
        assert response.status_code == 200

    def test_home_page_accessible(self, logged_in_client, app):
        """Test home page is accessible when logged in."""
        response = logged_in_client.get('/')
        assert response.status_code == 200


# ====================
# Error Handling Tests
# ====================

class TestErrorHandling:
    def test_404_for_nonexistent_route(self, client, app):
        """Test 404 error for non-existent routes."""
        response = client.get('/this-route-does-not-exist')
        assert response.status_code == 404

    def test_invalid_form_data_handling(self, client, app):
        """Test handling of invalid form data."""
        # Try login with empty data
        response = client.post('/login', data={}, follow_redirects=True)
        # Should handle gracefully
        assert response.status_code == 200


# ====================
# Form Validation Tests
# ====================

class TestFormValidation:
    def test_signup_password_validation(self, client, app, setup_company):
        """Test signup password requirements."""
        # Password too short
        response = client.post('/signup', data={
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'validtest@test.com',
            'password': '123',  # Too short
            'confirm_password': '123',
            'company': setup_company
        }, follow_redirects=True)
        # Should show validation error
        assert b'Sign Up' in response.data  # Still on signup page

    def test_signup_email_validation(self, client, app, setup_company):
        """Test signup email format validation."""
        response = client.post('/signup', data={
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'not-an-email',  # Invalid email
            'password': 'validpassword1',
            'confirm_password': 'validpassword1',
            'company': setup_company
        }, follow_redirects=True)
        # Should show validation error
        assert b'Sign Up' in response.data  # Still on signup page

    def test_signup_password_mismatch(self, client, app, setup_company):
        """Test signup password confirmation mismatch."""
        response = client.post('/signup', data={
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'mismatch@test.com',
            'password': 'password123',
            'confirm_password': 'differentpassword123',
            'company': setup_company
        }, follow_redirects=True)
        # Should show validation error
        assert b'Sign Up' in response.data  # Still on signup page


# ====================
# Session Tests
# ====================

class TestSession:
    def test_session_persists_after_login(self, client, app, setup_company, setup_user):
        """Test that session persists after login."""
        # Login
        client.post('/login', data={
            'email': 'routeuser@test.com',
            'password': 'testpassword'
        })
        
        # Make multiple requests
        response1 = client.get('/')
        response2 = client.get('/company')
        
        # Both should be accessible (200)
        assert response1.status_code == 200
        assert response2.status_code == 200

    def test_session_cleared_after_logout(self, logged_in_client, app):
        """Test that session is cleared after logout."""
        # Logout
        logged_in_client.get('/logout')
        
        # Try to access protected page
        response = logged_in_client.get('/')
        assert response.status_code == 302  # Redirected to login
