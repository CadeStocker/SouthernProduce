"""
Additional unit tests for models not fully covered in other test files.
Includes CustomerEmail, User password tokens, and other specific scenarios.
"""

import pytest
from datetime import date, datetime, timedelta
from producepricer import db
from producepricer.models import (
    Company,
    User,
    Customer,
    CustomerEmail,
    AIResponse,
    Item,
    UnitOfWeight,
    Packaging,
    ItemDesignation
)

# ====================
# CustomerEmail Model Tests
# ====================

class TestCustomerEmailModel:
    def test_customer_email_creation(self):
        """Test creating a customer email object."""
        email = CustomerEmail(email="billing@test.com", customer_id=1, label="Billing")
        assert email.email == "billing@test.com"
        assert email.customer_id == 1
        assert email.label == "Billing"

    def test_customer_email_relationship(self, app):
        """Test relationship between Customer and CustomerEmail."""
        with app.app_context():
            company = Company(name="Email Rel Co", admin_email="emailrel@test.com")
            db.session.add(company)
            db.session.commit()
            
            customer = Customer(name="Email Customer", email="primary@test.com", company_id=company.id)
            db.session.add(customer)
            db.session.commit()
            
            email1 = CustomerEmail(email="secondary@test.com", customer_id=customer.id, label="Secondary")
            email2 = CustomerEmail(email="billing@test.com", customer_id=customer.id, label="Billing")
            db.session.add_all([email1, email2])
            db.session.commit()
            
            # Reload customer
            customer = Customer.query.get(customer.id)
            assert len(customer.emails) == 2
            emails = [e.email for e in customer.emails]
            assert "secondary@test.com" in emails
            assert "billing@test.com" in emails

    def test_get_all_emails(self, app):
        """Test Customer.get_all_emails method."""
        with app.app_context():
            company = Company(name="All Emails Co", admin_email="allemails@test.com")
            db.session.add(company)
            db.session.commit()
            
            customer = Customer(name="Multi Email Customer", email="primary@test.com", company_id=company.id)
            db.session.add(customer)
            db.session.commit()
            
            # Add additional emails
            email1 = CustomerEmail(email="secondary@test.com", customer_id=customer.id)
            email2 = CustomerEmail(email="tertiary@test.com", customer_id=customer.id)
            # Add duplicate to check uniqueness logic if any (though model doesn't enforce unique across table, get_all_emails might filter)
            email3 = CustomerEmail(email="primary@test.com", customer_id=customer.id) # Same as primary
            
            db.session.add_all([email1, email2, email3])
            db.session.commit()
            
            all_emails = customer.get_all_emails()
            assert "primary@test.com" in all_emails
            assert "secondary@test.com" in all_emails
            assert "tertiary@test.com" in all_emails
            # Check for duplicates
            assert all_emails.count("primary@test.com") == 1

    def test_cascade_delete_customer_emails(self, app):
        """Test that deleting a customer deletes their emails."""
        with app.app_context():
            company = Company(name="Cascade Co", admin_email="cascade@test.com")
            db.session.add(company)
            db.session.commit()
            
            customer = Customer(name="Delete Me", email="del@test.com", company_id=company.id)
            db.session.add(customer)
            db.session.commit()
            
            email = CustomerEmail(email="child@test.com", customer_id=customer.id)
            db.session.add(email)
            db.session.commit()
            
            email_id = email.id
            
            # Delete customer
            db.session.delete(customer)
            db.session.commit()
            
            # Verify email is gone
            assert db.session.get(CustomerEmail, email_id) is None


# ====================
# User Password Token Tests
# ====================

class TestUserPasswordTokens:
    def test_generate_reset_token(self, app):
        """Test generating a password reset token."""
        with app.app_context():
            company = Company(name="Token Co", admin_email="token@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Token",
                last_name="User",
                email="token@user.com",
                password="password123",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            token = user.generate_reset_password_token()
            assert token is not None
            assert isinstance(token, str)

    def test_verify_reset_token(self, app):
        """Test verifying a valid password reset token."""
        with app.app_context():
            company = Company(name="Verify Co", admin_email="verify@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Verify",
                last_name="User",
                email="verify@user.com",
                password="password123",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            token = user.generate_reset_password_token()
            
            verified_user = User.verify_reset_password_token(token, user.id)
            assert verified_user is not None
            assert verified_user.id == user.id
            assert verified_user.email == user.email

    def test_verify_invalid_token(self, app):
        """Test verifying an invalid token."""
        with app.app_context():
            company = Company(name="Invalid Co", admin_email="invalid@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Invalid",
                last_name="User",
                email="invalid@user.com",
                password="password123",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Use a fake token
            verified_user = User.verify_reset_password_token("invalid_token", user.id)
            assert verified_user is None

    def test_verify_token_wrong_user(self, app):
        """Test verifying a token with the wrong user ID."""
        with app.app_context():
            company = Company(name="Wrong User Co", admin_email="wrong@test.com")
            db.session.add(company)
            db.session.commit()
            
            user1 = User(first_name="U1", last_name="1", email="u1@test.com", password="pw", company_id=company.id)
            user2 = User(first_name="U2", last_name="2", email="u2@test.com", password="pw", company_id=company.id)
            db.session.add_all([user1, user2])
            db.session.commit()
            
            token = user1.generate_reset_password_token()
            
            # Try to verify with user2's ID
            verified_user = User.verify_reset_password_token(token, user2.id)
            # Should fail because token payload email won't match user2's email
            assert verified_user is None


# ====================
# Item Alternate Code Tests
# ====================

class TestItemAlternateCode:
    def test_item_alternate_code(self, app):
        """Test item with alternate code."""
        with app.app_context():
            company = Company(name="Alt Code Co", admin_email="alt@test.com")
            db.session.add(company)
            db.session.commit()
            
            pkg = Packaging(packaging_type="Alt Pkg", company_id=company.id)
            db.session.add(pkg)
            db.session.commit()
            
            item = Item(
                name="Alt Item",
                code="MAIN001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=pkg.id,
                company_id=company.id,
                alternate_code="ALT001"
            )
            db.session.add(item)
            db.session.commit()
            
            result = Item.query.filter_by(alternate_code="ALT001").first()
            assert result is not None
            assert result.code == "MAIN001"
            assert result.name == "Alt Item"

