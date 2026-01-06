"""Unit tests for the APIKey model."""
import pytest
from datetime import datetime, timedelta
from producepricer.models import APIKey, User, Company
from producepricer import db


class TestAPIKeyModel:
    """Test suite for the APIKey model."""

    def test_api_key_creation(self, app):
        """Test creating a new API key."""
        with app.app_context():
            # Create company and user
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="hashed_password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Generate and create API key
            key = APIKey.generate_key()
            api_key = APIKey(
                key=key,
                device_name="iPad Pro 1",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(api_key)
            db.session.commit()
            
            # Verify the API key was created correctly
            assert api_key.id is not None
            assert api_key.key == key
            assert api_key.device_name == "iPad Pro 1"
            assert api_key.company_id == company.id
            assert api_key.created_by_user_id == user.id
            assert api_key.is_active is True
            assert api_key.created_at is not None
            assert api_key.last_used_at is None

    def test_generate_key_uniqueness(self, app):
        """Test that generate_key produces unique keys."""
        with app.app_context():
            keys = [APIKey.generate_key() for _ in range(100)]
            # All keys should be unique
            assert len(keys) == len(set(keys))

    def test_generate_key_length(self, app):
        """Test that generated keys are of sufficient length."""
        with app.app_context():
            key = APIKey.generate_key()
            # token_urlsafe(48) produces a string of approximately 64 characters
            assert len(key) >= 60  # Allow some variance

    def test_update_last_used(self, app):
        """Test updating the last_used_at timestamp."""
        with app.app_context():
            # Create company and user
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="hashed_password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Create API key
            api_key = APIKey(
                key=APIKey.generate_key(),
                device_name="iPad Pro 1",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(api_key)
            db.session.commit()
            
            assert api_key.last_used_at is None
            
            # Update last used
            before_update = datetime.utcnow()
            api_key.update_last_used()
            after_update = datetime.utcnow()
            
            # Refresh from database
            db.session.refresh(api_key)
            
            assert api_key.last_used_at is not None
            assert before_update <= api_key.last_used_at <= after_update

    def test_revoke_api_key(self, app):
        """Test revoking an API key."""
        with app.app_context():
            # Create company and user
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="hashed_password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Create API key
            api_key = APIKey(
                key=APIKey.generate_key(),
                device_name="iPad Pro 1",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(api_key)
            db.session.commit()
            
            assert api_key.is_active is True
            
            # Revoke the key
            api_key.revoke()
            
            # Refresh from database
            db.session.refresh(api_key)
            
            assert api_key.is_active is False

    def test_activate_api_key(self, app):
        """Test activating a previously revoked API key."""
        with app.app_context():
            # Create company and user
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="hashed_password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Create and revoke API key
            api_key = APIKey(
                key=APIKey.generate_key(),
                device_name="iPad Pro 1",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(api_key)
            db.session.commit()
            api_key.revoke()
            db.session.refresh(api_key)
            
            assert api_key.is_active is False
            
            # Reactivate the key
            api_key.activate()
            
            # Refresh from database
            db.session.refresh(api_key)
            
            assert api_key.is_active is True

    def test_api_key_relationships(self, app):
        """Test API key relationships with Company and User."""
        with app.app_context():
            # Create company and user
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="hashed_password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Create API key
            api_key = APIKey(
                key=APIKey.generate_key(),
                device_name="iPad Pro 1",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(api_key)
            db.session.commit()
            
            # Test relationships
            assert api_key.company == company
            assert api_key.created_by == user
            assert api_key in company.api_keys
            assert api_key in user.created_api_keys

    def test_multiple_api_keys_per_company(self, app):
        """Test that a company can have multiple API keys."""
        with app.app_context():
            # Create company and user
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="hashed_password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Create multiple API keys
            devices = ["iPad Pro 1", "iPad Air 2", "iPad Mini"]
            api_keys = []
            for device in devices:
                api_key = APIKey(
                    key=APIKey.generate_key(),
                    device_name=device,
                    company_id=company.id,
                    created_by_user_id=user.id
                )
                db.session.add(api_key)
                api_keys.append(api_key)
            
            db.session.commit()
            
            # Verify all keys are associated with the company
            assert len(company.api_keys) == 3
            for api_key in api_keys:
                assert api_key in company.api_keys

    def test_api_key_unique_constraint(self, app):
        """Test that API keys must be unique."""
        with app.app_context():
            # Create company and user
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="hashed_password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Create first API key
            key = APIKey.generate_key()
            api_key1 = APIKey(
                key=key,
                device_name="iPad Pro 1",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(api_key1)
            db.session.commit()
            
            # Try to create second API key with same key
            api_key2 = APIKey(
                key=key,  # Same key!
                device_name="iPad Pro 2",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(api_key2)
            
            # Should raise an integrity error
            with pytest.raises(Exception):  # SQLAlchemy IntegrityError
                db.session.commit()

    def test_api_key_repr(self, app):
        """Test the string representation of APIKey."""
        with app.app_context():
            # Create company and user
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="hashed_password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Create API key
            api_key = APIKey(
                key=APIKey.generate_key(),
                device_name="iPad Pro 1",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(api_key)
            db.session.commit()
            
            repr_str = repr(api_key)
            assert "iPad Pro 1" in repr_str
            assert "active=True" in repr_str
            
            # Revoke and test again
            api_key.revoke()
            repr_str = repr(api_key)
            assert "active=False" in repr_str

    def test_api_key_query_by_key(self, app):
        """Test querying API key by key value."""
        with app.app_context():
            # Create company and user
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="hashed_password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Create API key
            key_value = APIKey.generate_key()
            api_key = APIKey(
                key=key_value,
                device_name="iPad Pro 1",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(api_key)
            db.session.commit()
            
            # Query by key
            found_key = APIKey.query.filter_by(key=key_value).first()
            assert found_key is not None
            assert found_key.id == api_key.id
            assert found_key.device_name == "iPad Pro 1"

    def test_api_key_filter_by_company(self, app):
        """Test filtering API keys by company."""
        with app.app_context():
            # Create two companies
            company1 = Company(name="Company 1", admin_email="admin1@test.com")
            company2 = Company(name="Company 2", admin_email="admin2@test.com")
            db.session.add(company1)
            db.session.add(company2)
            db.session.commit()
            
            user1 = User(
                first_name="Test",
                last_name="User1",
                email="test1@test.com",
                password="hashed_password",
                company_id=company1.id
            )
            user2 = User(
                first_name="Test",
                last_name="User2",
                email="test2@test.com",
                password="hashed_password",
                company_id=company2.id
            )
            db.session.add(user1)
            db.session.add(user2)
            db.session.commit()
            
            # Create API keys for both companies
            api_key1 = APIKey(
                key=APIKey.generate_key(),
                device_name="Company 1 iPad",
                company_id=company1.id,
                created_by_user_id=user1.id
            )
            api_key2 = APIKey(
                key=APIKey.generate_key(),
                device_name="Company 2 iPad",
                company_id=company2.id,
                created_by_user_id=user2.id
            )
            db.session.add(api_key1)
            db.session.add(api_key2)
            db.session.commit()
            
            # Query keys for company 1
            company1_keys = APIKey.query.filter_by(company_id=company1.id).all()
            assert len(company1_keys) == 1
            assert company1_keys[0].device_name == "Company 1 iPad"
            
            # Query keys for company 2
            company2_keys = APIKey.query.filter_by(company_id=company2.id).all()
            assert len(company2_keys) == 1
            assert company2_keys[0].device_name == "Company 2 iPad"

    def test_api_key_filter_active_only(self, app):
        """Test filtering only active API keys."""
        with app.app_context():
            # Create company and user
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="hashed_password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Create multiple API keys
            active_key = APIKey(
                key=APIKey.generate_key(),
                device_name="Active iPad",
                company_id=company.id,
                created_by_user_id=user.id
            )
            inactive_key = APIKey(
                key=APIKey.generate_key(),
                device_name="Inactive iPad",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(active_key)
            db.session.add(inactive_key)
            db.session.commit()
            
            # Revoke one key
            inactive_key.revoke()
            
            # Query only active keys
            active_keys = APIKey.query.filter_by(
                company_id=company.id,
                is_active=True
            ).all()
            
            assert len(active_keys) == 1
            assert active_keys[0].device_name == "Active iPad"
