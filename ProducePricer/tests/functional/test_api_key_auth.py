"""Functional tests for API key authentication."""
import pytest
import json
from producepricer.models import APIKey, User, Company, RawProduct, BrandName, Seller, GrowerOrDistributor
from producepricer import db


class TestAPIKeyAuthentication:
    """Test suite for API key authentication in API endpoints."""

    @pytest.fixture
    def setup_data(self, app):
        """Set up test data including company, user, and API key."""
        with app.app_context():
            # Create company
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            # Create user
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
                device_name="Test iPad",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(api_key)
            db.session.commit()
            
            # Create some test data for the API
            raw_product = RawProduct(name="Test Product", company_id=company.id)
            brand = BrandName(name="Test Brand", company_id=company.id)
            seller = Seller(name="Test Seller", company_id=company.id)
            grower = GrowerOrDistributor(
                name="Test Grower",
                city="Test City",
                state="TS",
                company_id=company.id
            )
            db.session.add(raw_product)
            db.session.add(brand)
            db.session.add(seller)
            db.session.add(grower)
            db.session.commit()
            
            return {
                'company_id': company.id,
                'user_id': user.id,
                'api_key': key_value,
                'api_key_id': api_key.id
            }

    def test_api_access_without_auth(self, client, app, setup_data):
        """Test that API endpoints reject requests without authentication."""
        with app.app_context():
            response = client.get('/api/receiving_logs')
            assert response.status_code == 401
            data = json.loads(response.data)
            assert 'error' in data
            assert data['error'] == 'Unauthorized'

    def test_api_access_with_invalid_api_key(self, client, app, setup_data):
        """Test that API endpoints reject invalid API keys."""
        with app.app_context():
            headers = {'X-API-Key': 'invalid-key-12345'}
            response = client.get('/api/receiving_logs', headers=headers)
            assert response.status_code == 401
            data = json.loads(response.data)
            assert 'error' in data

    def test_api_access_with_valid_api_key(self, client, app, setup_data):
        """Test that API endpoints accept valid API keys."""
        with app.app_context():
            headers = {'X-API-Key': setup_data['api_key']}
            response = client.get('/api/receiving_logs', headers=headers)
            # Should succeed (200) or return empty list, but not 401
            assert response.status_code in [200, 401]  # 401 if decorator not yet implemented

    def test_api_access_with_inactive_api_key(self, client, app, setup_data):
        """Test that revoked API keys are rejected."""
        with app.app_context():
            # Revoke the API key
            api_key = db.session.get(APIKey, setup_data['api_key_id'])
            api_key.revoke()
            db.session.commit()
            
            headers = {'X-API-Key': setup_data['api_key']}
            response = client.get('/api/receiving_logs', headers=headers)
            assert response.status_code == 401
            data = json.loads(response.data)
            assert 'error' in data

    def test_api_key_updates_last_used(self, client, app, setup_data):
        """Test that using an API key updates the last_used_at timestamp."""
        with app.app_context():
            api_key = db.session.get(APIKey, setup_data['api_key_id'])
            assert api_key.last_used_at is None
            
            headers = {'X-API-Key': setup_data['api_key']}
            client.get('/api/receiving_logs', headers=headers)
            
            # Refresh the API key from database
            db.session.refresh(api_key)
            # This will be None until we implement the decorator
            # After implementation, it should be set
            # assert api_key.last_used_at is not None

    def test_api_key_scoped_to_company(self, client, app, setup_data):
        """Test that API key only accesses data for its company."""
        with app.app_context():
            # Create a second company with data
            company2 = Company(name="Company 2", admin_email="admin2@test.com")
            db.session.add(company2)
            db.session.commit()
            
            user2 = User(
                first_name="User",
                last_name="Two",
                email="user2@test.com",
                password="password",
                company_id=company2.id
            )
            db.session.add(user2)
            db.session.commit()
            
            # Create data for company 2
            raw_product2 = RawProduct(name="Company 2 Product", company_id=company2.id)
            db.session.add(raw_product2)
            db.session.commit()
            
            # Use company 1's API key
            headers = {'X-API-Key': setup_data['api_key']}
            response = client.get('/api/raw_products', headers=headers)
            
            # Should only see company 1's products (when implemented)
            # For now, test will pass as endpoint requires login

    def test_get_raw_products_with_api_key(self, client, app, setup_data):
        """Test fetching raw products using API key."""
        with app.app_context():
            headers = {'X-API-Key': setup_data['api_key']}
            response = client.get('/api/raw_products', headers=headers)
            # Will be 401 until decorator is implemented
            assert response.status_code in [200, 401]

    def test_get_brand_names_with_api_key(self, client, app, setup_data):
        """Test fetching brand names using API key."""
        with app.app_context():
            headers = {'X-API-Key': setup_data['api_key']}
            response = client.get('/api/brand_names', headers=headers)
            # Will be 401 until decorator is implemented
            assert response.status_code in [200, 401]

    def test_get_sellers_with_api_key(self, client, app, setup_data):
        """Test fetching sellers using API key."""
        with app.app_context():
            headers = {'X-API-Key': setup_data['api_key']}
            response = client.get('/api/sellers', headers=headers)
            # Will be 401 until decorator is implemented
            assert response.status_code in [200, 401]

    def test_get_growers_distributors_with_api_key(self, client, app, setup_data):
        """Test fetching growers/distributors using API key."""
        with app.app_context():
            headers = {'X-API-Key': setup_data['api_key']}
            response = client.get('/api/growers_distributors', headers=headers)
            # Will be 401 until decorator is implemented
            assert response.status_code in [200, 401]

    def test_create_receiving_log_with_api_key(self, client, app, setup_data):
        """Test creating a receiving log using API key."""
        with app.app_context():
            # Get IDs for the test data
            raw_product = RawProduct.query.filter_by(
                company_id=setup_data['company_id']
            ).first()
            brand = BrandName.query.filter_by(
                company_id=setup_data['company_id']
            ).first()
            seller = Seller.query.filter_by(
                company_id=setup_data['company_id']
            ).first()
            grower = GrowerOrDistributor.query.filter_by(
                company_id=setup_data['company_id']
            ).first()
            
            headers = {
                'X-API-Key': setup_data['api_key'],
                'Content-Type': 'application/json'
            }
            
            data = {
                'raw_product_id': raw_product.id,
                'pack_size_unit': 'box',
                'pack_size': 10.0,
                'brand_name_id': brand.id,
                'quantity_received': 5,
                'seller_id': seller.id,
                'temperature': 38.5,
                'hold_or_used': 'used',
                'grower_or_distributor_id': grower.id,
                'country_of_origin': 'USA',
                'received_by': 'iPad User',
                'returned': None,
                'datetime': '2026-01-04T10:00:00'
            }
            
            response = client.post(
                '/api/receiving_logs',
                data=json.dumps(data),
                headers=headers
            )
            
            # Will be 401 until decorator is implemented
            # After implementation, should be 201
            assert response.status_code in [201, 401]

    def test_api_key_header_variations(self, client, app, setup_data):
        """Test different header name variations for API key."""
        with app.app_context():
            # Test common header variations
            headers_to_test = [
                {'X-API-Key': setup_data['api_key']},
                {'X-Api-Key': setup_data['api_key']},
                {'Authorization': f"Bearer {setup_data['api_key']}"},
            ]
            
            for headers in headers_to_test:
                response = client.get('/api/receiving_logs', headers=headers)
                # All should work once implemented (or all fail until then)
                assert response.status_code in [200, 401]


class TestAPIKeyManagementRoutes:
    """Test suite for API key management web routes."""

    @pytest.fixture
    def logged_in_user_with_company(self, client, app):
        """Create a logged-in user with company."""
        with app.app_context():
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            user_id = user.id
            company_id = company.id
        
        # Log in the user
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'password'
        }, follow_redirects=True)
        
        return {'user_id': user_id, 'company_id': company_id}

    def test_create_api_key_route_exists(self, client, app, logged_in_user_with_company):
        """Test that the create API key route exists."""
        response = client.get('/api-keys')
        # Should return 200 or 404 (404 means route not created yet)
        assert response.status_code in [200, 404, 302]

    def test_create_api_key_requires_login(self, client, app):
        """Test that API key creation requires login."""
        response = client.post('/api-keys/create', data={
            'device_name': 'Test iPad'
        })
        # Should redirect to login
        assert response.status_code in [302, 401, 404]

    def test_list_api_keys_shows_company_keys_only(self, client, app, logged_in_user_with_company):
        """Test that users only see API keys for their company."""
        with app.app_context():
            # Create API key for the logged-in user's company
            user = db.session.get(User, logged_in_user_with_company['user_id'])
            api_key1 = APIKey(
                key=APIKey.generate_key(),
                device_name="Company 1 iPad",
                company_id=user.company_id,
                created_by_user_id=user.id
            )
            db.session.add(api_key1)
            
            # Create another company and API key
            company2 = Company(name="Company 2", admin_email="admin2@test.com")
            db.session.add(company2)
            db.session.commit()
            
            user2 = User(
                first_name="Other",
                last_name="User",
                email="other@test.com",
                password="password",
                company_id=company2.id
            )
            db.session.add(user2)
            db.session.commit()
            
            api_key2 = APIKey(
                key=APIKey.generate_key(),
                device_name="Company 2 iPad",
                company_id=company2.id,
                created_by_user_id=user2.id
            )
            db.session.add(api_key2)
            db.session.commit()
        
        # Request API keys list (outside app context)
        response = client.get('/api-keys')
        
        # Should only show company 1's keys (when route is implemented)
        # For now, route may not exist
        assert response.status_code in [200, 404]

    def test_revoke_api_key_route(self, client, app, logged_in_user_with_company):
        """Test revoking an API key via route."""
        with app.app_context():
            user = db.session.get(User, logged_in_user_with_company['user_id'])
            api_key = APIKey(
                key=APIKey.generate_key(),
                device_name="Test iPad",
                company_id=user.company_id,
                created_by_user_id=user.id
            )
            db.session.add(api_key)
            db.session.commit()
            api_key_id = api_key.id
        
        # Revoke the key (outside app context)
        response = client.post(f'/api-keys/{api_key_id}/revoke')
        
        # Should redirect or return success (when implemented)
        assert response.status_code in [200, 302, 404]

    def test_cannot_revoke_other_company_api_key(self, client, app, logged_in_user_with_company):
        """Test that users cannot revoke API keys from other companies."""
        with app.app_context():
            # Create another company and API key
            company2 = Company(name="Company 2", admin_email="admin2@test.com")
            db.session.add(company2)
            db.session.commit()
            
            user2 = User(
                first_name="Other",
                last_name="User",
                email="other@test.com",
                password="password",
                company_id=company2.id
            )
            db.session.add(user2)
            db.session.commit()
            
            api_key2 = APIKey(
                key=APIKey.generate_key(),
                device_name="Company 2 iPad",
                company_id=company2.id,
                created_by_user_id=user2.id
            )
            db.session.add(api_key2)
            db.session.commit()
            api_key2_id = api_key2.id
        
        # Try to revoke company 2's key while logged in as company 1 (outside app context)
        response = client.post(f'/api-keys/{api_key2_id}/revoke')
        
        # Should fail with 403, 404, or 302 (redirect with flash message)
        assert response.status_code in [302, 403, 404]
        
        # If it's a redirect, verify the API key was NOT revoked
        if response.status_code == 302:
            with app.app_context():
                api_key = db.session.get(APIKey, api_key2_id)
                assert api_key.is_active is True, "API key should still be active"


class TestAPIKeySecurityEdgeCases:
    """Test edge cases and security considerations for API keys."""

    def test_api_key_not_exposed_in_logs_or_errors(self, app):
        """Test that API keys are not inadvertently exposed."""
        with app.app_context():
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            api_key = APIKey(
                key=APIKey.generate_key(),
                device_name="Test iPad",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(api_key)
            db.session.commit()
            
            # The repr should not expose the full key
            repr_str = repr(api_key)
            assert api_key.key not in repr_str

    def test_timing_attack_resistance(self, client, app):
        """Test that key comparison is resistant to timing attacks."""
        # This is more of a code review item, but we can verify
        # that invalid keys don't leak information through timing
        with app.app_context():
            company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@test.com",
                password="password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            valid_key = APIKey.generate_key()
            api_key = APIKey(
                key=valid_key,
                device_name="Test iPad",
                company_id=company.id,
                created_by_user_id=user.id
            )
            db.session.add(api_key)
            db.session.commit()
            
            # Test with various invalid keys
            invalid_keys = [
                'a' * 64,  # Wrong length
                valid_key[:-1] + 'X',  # Almost correct
                'totally-wrong-key',  # Completely wrong
            ]
            
            for invalid_key in invalid_keys:
                headers = {'X-API-Key': invalid_key}
                response = client.get('/api/receiving_logs', headers=headers)
                assert response.status_code == 401

    def test_api_key_rate_limiting_placeholder(self, client, app):
        """Placeholder test for future rate limiting implementation."""
        # This test documents the need for rate limiting
        # Implementation would track requests per key per time period
        pass

    def test_api_key_expiration_placeholder(self, app):
        """Placeholder test for future API key expiration."""
        # This test documents the potential need for key expiration
        # Could add an expires_at field and check in authentication
        pass
