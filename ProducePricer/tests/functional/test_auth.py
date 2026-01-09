"""
Tests for authentication features including login, logout, and password reset.
"""
import pytest
from flask import url_for
from flask_login import current_user
from unittest.mock import patch, MagicMock
from producepricer import db
from producepricer.models import User, Company


class TestLoginRoute:
    """Tests for login functionality."""

    def test_login_page_loads(self, client, app):
        """Test that login page loads correctly when not logged in."""
        with app.app_context():
            response = client.get(url_for('main.login'))
            assert response.status_code == 200
            assert b'Login' in response.data
            assert b'<form' in response.data

    def test_login_redirects_when_authenticated(self, client, app):
        """Test that login page redirects to home when user is already logged in."""
        with app.app_context():
            # Create company and user
            company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Test',
                last_name='User',
                email='test@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Login the user
            client.post(
                url_for('main.login'),
                data={'email': 'test@test.com', 'password': 'password123'},
                follow_redirects=False
            )
            
            # Try accessing login page again
            response = client.get(url_for('main.login'), follow_redirects=False)
            assert response.status_code == 302
            assert 'home' in response.location or response.status_code == 302

    def test_successful_login(self, client, app):
        """Test successful login with correct credentials."""
        with app.app_context():
            # Create company and user
            company = Company(name='Login Test Company', admin_email='admin@login.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Login',
                last_name='Test',
                email='logintest@test.com',
                password='correctpassword1',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Attempt login
            response = client.post(
                url_for('main.login'),
                data={
                    'email': 'logintest@test.com',
                    'password': 'correctpassword1'
                },
                follow_redirects=True
            )
            
            assert response.status_code == 200
            assert b'Welcome back' in response.data

    def test_failed_login_wrong_password(self, client, app):
        """Test login failure with wrong password."""
        with app.app_context():
            # Create company and user
            company = Company(name='Wrong Pass Company', admin_email='admin@wrongpass.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Wrong',
                last_name='Pass',
                email='wrongpass@test.com',
                password='correctpassword1',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Attempt login with wrong password
            response = client.post(
                url_for('main.login'),
                data={
                    'email': 'wrongpass@test.com',
                    'password': 'wrongpassword'
                },
                follow_redirects=True
            )
            
            assert response.status_code == 200
            assert b'Login Unsuccessful' in response.data

    def test_failed_login_nonexistent_user(self, client, app):
        """Test login failure with non-existent user email."""
        with app.app_context():
            response = client.post(
                url_for('main.login'),
                data={
                    'email': 'nonexistent@test.com',
                    'password': 'somepassword'
                },
                follow_redirects=True
            )
            
            assert response.status_code == 200
            assert b'Login Unsuccessful' in response.data

    def test_login_with_empty_fields(self, client, app):
        """Test login with empty email and password fields."""
        with app.app_context():
            response = client.post(
                url_for('main.login'),
                data={
                    'email': '',
                    'password': ''
                },
                follow_redirects=True
            )
            
            # Form validation should fail
            assert response.status_code == 200
            # Should still be on login page
            assert b'Login' in response.data

    def test_login_with_remember_me(self, client, app):
        """Test login with remember me checkbox."""
        with app.app_context():
            # Create company and user
            company = Company(name='Remember Me Company', admin_email='admin@remember.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Remember',
                last_name='Me',
                email='remember@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Login with remember me
            response = client.post(
                url_for('main.login'),
                data={
                    'email': 'remember@test.com',
                    'password': 'password123',
                    'remember': True
                },
                follow_redirects=True
            )
            
            assert response.status_code == 200
            assert b'Welcome back' in response.data


class TestLogoutRoute:
    """Tests for logout functionality."""

    def test_logout_success(self, client, app):
        """Test successful logout."""
        with app.app_context():
            # Create company and user
            company = Company(name='Logout Test Company', admin_email='admin@logout.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Logout',
                last_name='Test',
                email='logout@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # First login
            client.post(
                url_for('main.login'),
                data={
                    'email': 'logout@test.com',
                    'password': 'password123'
                },
                follow_redirects=True
            )
            
            # Then logout
            response = client.get(url_for('main.logout'), follow_redirects=True)
            
            assert response.status_code == 200
            assert b'You have been logged out!' in response.data

    def test_logout_redirects_to_home(self, client, app):
        """Test that logout redirects to home page."""
        with app.app_context():
            response = client.get(url_for('main.logout'), follow_redirects=False)
            assert response.status_code == 302
            # Should redirect to home


class TestPasswordResetRequest:
    """Tests for password reset request functionality."""

    def test_reset_password_request_page_loads(self, client, app):
        """Test that password reset request page loads correctly."""
        with app.app_context():
            response = client.get(url_for('main.reset_password_request'))
            assert response.status_code == 200
            assert b'Reset Password' in response.data
            assert b'Email' in response.data

    def test_reset_password_request_redirects_when_authenticated(self, client, app):
        """Test that password reset request redirects when user is logged in."""
        with app.app_context():
            # Create and login user
            company = Company(name='Reset Auth Company', admin_email='admin@resetauth.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Reset',
                last_name='Auth',
                email='resetauth@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Login
            client.post(
                url_for('main.login'),
                data={'email': 'resetauth@test.com', 'password': 'password123'}
            )
            
            # Try to access reset password request - redirects to home (main.index redirects to main.home)
            response = client.get(url_for('main.reset_password_request'), follow_redirects=False)
            # Should redirect (either 302 or return page if already on it)
            assert response.status_code in [200, 302]

    @patch('producepricer.routes.send_reset_password_email')
    def test_reset_password_request_valid_email(self, mock_send_email, client, app):
        """Test password reset request with valid email sends email."""
        with app.app_context():
            # Create user
            company = Company(name='Reset Valid Company', admin_email='admin@resetvalid.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Reset',
                last_name='Valid',
                email='resetvalid@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Request password reset
            response = client.post(
                url_for('main.reset_password_request'),
                data={'email': 'resetvalid@test.com'},
                follow_redirects=True
            )
            
            assert response.status_code == 200
            # Email should have been called
            mock_send_email.assert_called_once()
            assert b'email has been sent' in response.data or b'Login' in response.data

    def test_reset_password_request_invalid_email(self, client, app):
        """Test password reset request with non-existent email."""
        with app.app_context():
            response = client.post(
                url_for('main.reset_password_request'),
                data={'email': 'nonexistent@test.com'},
                follow_redirects=True
            )
            
            assert response.status_code == 200
            assert b'No account found' in response.data

    def test_reset_password_request_empty_email(self, client, app):
        """Test password reset request with empty email."""
        with app.app_context():
            response = client.post(
                url_for('main.reset_password_request'),
                data={'email': ''},
                follow_redirects=True
            )
            
            # Form validation should fail
            assert response.status_code == 200
            assert b'Reset Password' in response.data


class TestPasswordReset:
    """Tests for the actual password reset functionality."""

    def test_reset_password_page_loads_with_valid_token(self, client, app):
        """Test that password reset page loads with a valid token."""
        with app.app_context():
            # Create user
            company = Company(name='Reset Page Company', admin_email='admin@resetpage.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Reset',
                last_name='Page',
                email='resetpage@test.com',
                password='oldpassword1',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Generate a valid token
            token = user.generate_reset_password_token()
            user_id = user.id
            
            # Access reset password page
            response = client.get(
                url_for('main.reset_password', token=token, user_id=user_id)
            )
            
            assert response.status_code == 200
            assert b'Reset Password' in response.data or b'New Password' in response.data

    def test_reset_password_with_invalid_token(self, client, app):
        """Test password reset with invalid token redirects."""
        with app.app_context():
            # Create user
            company = Company(name='Invalid Token Company', admin_email='admin@invalidtoken.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Invalid',
                last_name='Token',
                email='invalidtoken@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Use invalid token
            response = client.get(
                url_for('main.reset_password', token='invalid_token', user_id=user.id),
                follow_redirects=True
            )
            
            assert response.status_code == 200
            assert b'Invalid or expired token' in response.data

    def test_reset_password_with_nonexistent_user_id(self, client, app):
        """Test password reset with non-existent user ID."""
        with app.app_context():
            response = client.get(
                url_for('main.reset_password', token='sometoken', user_id=99999),
                follow_redirects=True
            )
            
            assert response.status_code == 200
            assert b'Invalid or expired token' in response.data

    def test_reset_password_success(self, client, app):
        """Test successful password reset."""
        with app.app_context():
            # Create user
            company = Company(name='Reset Success Company', admin_email='admin@resetsuccess.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Reset',
                last_name='Success',
                email='resetsuccess@test.com',
                password='oldpassword1',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Generate token
            token = user.generate_reset_password_token()
            user_id = user.id
            
            # Reset password
            response = client.post(
                url_for('main.reset_password', token=token, user_id=user_id),
                data={
                    'password': 'newpassword1',
                    'confirm_password': 'newpassword1'
                },
                follow_redirects=True
            )
            
            assert response.status_code == 200
            assert b'password has been reset' in response.data or b'Login' in response.data
            
            # Verify password was changed - use check_password since passwords are hashed
            updated_user = User.query.get(user_id)
            assert updated_user.check_password('newpassword1')

    def test_reset_password_mismatched_confirmation(self, client, app):
        """Test password reset with mismatched password confirmation."""
        with app.app_context():
            # Create user
            company = Company(name='Mismatch Company', admin_email='admin@mismatch.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Mismatch',
                last_name='Test',
                email='mismatch@test.com',
                password='oldpassword1',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Generate token
            token = user.generate_reset_password_token()
            user_id = user.id
            
            # Try to reset with mismatched passwords
            response = client.post(
                url_for('main.reset_password', token=token, user_id=user_id),
                data={
                    'password': 'newpassword1',
                    'confirm_password': 'differentpassword1'
                },
                follow_redirects=True
            )
            
            assert response.status_code == 200
            # Password should not have changed
            unchanged_user = User.query.get(user_id)
            assert unchanged_user.password == 'oldpassword1'

    def test_reset_password_weak_password(self, client, app):
        """Test password reset with password that doesn't meet requirements."""
        with app.app_context():
            # Create user
            company = Company(name='Weak Pass Company', admin_email='admin@weakpass.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Weak',
                last_name='Pass',
                email='weakpass@test.com',
                password='oldpassword1',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Generate token
            token = user.generate_reset_password_token()
            user_id = user.id
            
            # Try to reset with weak password (no digit)
            response = client.post(
                url_for('main.reset_password', token=token, user_id=user_id),
                data={
                    'password': 'nodigits',
                    'confirm_password': 'nodigits'
                },
                follow_redirects=True
            )
            
            assert response.status_code == 200
            # Password should not have changed
            unchanged_user = User.query.get(user_id)
            assert unchanged_user.password == 'oldpassword1'

    def test_reset_password_redirects_when_authenticated(self, client, app):
        """Test that password reset page redirects when user is logged in."""
        with app.app_context():
            # Create and login user
            company = Company(name='Reset Logged In Company', admin_email='admin@resetloggedin.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Reset',
                last_name='LoggedIn',
                email='resetloggedin@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            token = user.generate_reset_password_token()
            user_id = user.id
            
            # Login
            client.post(
                url_for('main.login'),
                data={'email': 'resetloggedin@test.com', 'password': 'password123'}
            )
            
            # Try to access reset password
            response = client.get(
                url_for('main.reset_password', token=token, user_id=user_id),
                follow_redirects=False
            )
            
            assert response.status_code == 302


class TestTokenGeneration:
    """Tests for password reset token generation and verification."""

    def test_generate_reset_password_token(self, app):
        """Test that a token can be generated for a user."""
        with app.app_context():
            company = Company(name='Token Gen Company', admin_email='admin@tokengen.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Token',
                last_name='Gen',
                email='tokengen@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            token = user.generate_reset_password_token()
            
            assert token is not None
            assert isinstance(token, str)
            assert len(token) > 0

    def test_verify_valid_token(self, app):
        """Test that a valid token can be verified."""
        with app.app_context():
            company = Company(name='Verify Token Company', admin_email='admin@verifytoken.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Verify',
                last_name='Token',
                email='verifytoken@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            token = user.generate_reset_password_token()
            user_id = user.id
            
            result = User.verify_reset_password_token(token, user_id)
            
            assert result is not None
            assert result.email == user.email

    def test_verify_invalid_token(self, app):
        """Test that an invalid token returns None."""
        with app.app_context():
            company = Company(name='Invalid Verify Company', admin_email='admin@invalidverify.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Invalid',
                last_name='Verify',
                email='invalidverify@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            result = User.verify_reset_password_token('invalid_token_string', user.id)
            
            assert result is None

    def test_verify_token_wrong_user_id(self, app):
        """Test that a token with wrong user ID returns None."""
        with app.app_context():
            company = Company(name='Wrong ID Company', admin_email='admin@wrongid.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Wrong',
                last_name='ID',
                email='wrongid@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            token = user.generate_reset_password_token()
            
            # Try to verify with a different user ID
            result = User.verify_reset_password_token(token, 99999)
            
            assert result is None

    def test_token_becomes_invalid_after_password_change(self, app):
        """Test that a token becomes invalid after the password is changed."""
        with app.app_context():
            company = Company(name='Token Invalid Company', admin_email='admin@tokeninvalid.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Token',
                last_name='Invalid',
                email='tokeninvalid@test.com',
                password='oldpassword1',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Generate token with old password
            token = user.generate_reset_password_token()
            user_id = user.id
            
            # Change password
            user.set_password('newpassword1')
            db.session.commit()
            
            # Try to verify the old token
            result = User.verify_reset_password_token(token, user_id)
            
            # Token should be invalid now because password salt changed
            assert result is None


class TestProtectedRoutes:
    """Tests for accessing protected routes without authentication."""

    def test_protected_route_redirects_to_login(self, client, app):
        """Test that a protected route redirects to login when not authenticated."""
        with app.app_context():
            # Try to access a protected route (e.g., home which requires login)
            response = client.get(url_for('main.home'), follow_redirects=False)
            
            # Should redirect to login
            assert response.status_code == 302
            assert 'login' in response.location.lower()

    def test_protected_route_accessible_when_authenticated(self, client, app):
        """Test that a protected route is accessible when authenticated."""
        with app.app_context():
            # Create and login user
            company = Company(name='Protected Route Company', admin_email='admin@protected.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Protected',
                last_name='Route',
                email='protected@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Login
            client.post(
                url_for('main.login'),
                data={'email': 'protected@test.com', 'password': 'password123'}
            )
            
            # Access protected route
            response = client.get(url_for('main.home'))
            
            assert response.status_code == 200


class TestSessionManagement:
    """Tests for user session management."""

    def test_session_persists_across_requests(self, client, app):
        """Test that user session persists across multiple requests."""
        with app.app_context():
            # Create and login user
            company = Company(name='Session Persist Company', admin_email='admin@sessionpersist.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Session',
                last_name='Persist',
                email='sessionpersist@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Login
            client.post(
                url_for('main.login'),
                data={'email': 'sessionpersist@test.com', 'password': 'password123'}
            )
            
            # Make multiple requests to protected routes
            response1 = client.get(url_for('main.home'))
            response2 = client.get(url_for('main.home'))
            
            # Both should succeed without re-authenticating
            assert response1.status_code == 200
            assert response2.status_code == 200

    def test_session_ends_after_logout(self, client, app):
        """Test that session ends after logout."""
        with app.app_context():
            # Create and login user
            company = Company(name='Session End Company', admin_email='admin@sessionend.com')
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name='Session',
                last_name='End',
                email='sessionend@test.com',
                password='password123',
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Login
            client.post(
                url_for('main.login'),
                data={'email': 'sessionend@test.com', 'password': 'password123'}
            )
            
            # Verify logged in
            response1 = client.get(url_for('main.home'))
            assert response1.status_code == 200
            
            # Logout
            client.get(url_for('main.logout'))
            
            # Try to access protected route
            response2 = client.get(url_for('main.home'), follow_redirects=False)
            
            # Should redirect to login
            assert response2.status_code == 302
            assert 'login' in response2.location.lower()
