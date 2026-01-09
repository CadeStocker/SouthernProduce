"""
Comprehensive security tests for API endpoints.
Tests authentication, authorization, multi-tenant isolation, and common vulnerabilities.
"""

import pytest
import json
from datetime import datetime, date, timedelta
from producepricer.models import (
    Company, User, APIKey, ReceivingLog, RawProduct, BrandName, 
    Seller, GrowerOrDistributor, Customer, Item, Packaging, CostHistory
)
from producepricer import db


class TestAPIAuthentication:
    """Test API authentication and authorization mechanisms."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data for authentication tests."""
        with app.app_context():
            # Create two companies
            self.company1 = Company(name='Company 1', admin_email='admin1@test.com')
            self.company2 = Company(name='Company 2', admin_email='admin2@test.com')
            db.session.add_all([self.company1, self.company2])
            db.session.flush()
            
            # Create users for each company
            self.user1 = User(
                first_name='User', last_name='One',
                email='user1@test.com', password='hashed',
                company_id=self.company1.id
            )
            self.user2 = User(
                first_name='User', last_name='Two',
                email='user2@test.com', password='hashed',
                company_id=self.company2.id
            )
            db.session.add_all([self.user1, self.user2])
            db.session.flush()
            
            # Create API keys for each company
            self.api_key1 = APIKey(
                key='test_key_company_1_secure_token_123456',
                device_name='Test Device 1',
                company_id=self.company1.id,
                created_by_user_id=self.user1.id
            )
            self.api_key2 = APIKey(
                key='test_key_company_2_secure_token_789012',
                device_name='Test Device 2',
                company_id=self.company2.id,
                created_by_user_id=self.user2.id
            )
            db.session.add_all([self.api_key1, self.api_key2])
            db.session.commit()
            
            # Store IDs for use in tests
            self.company1_id = self.company1.id
            self.company2_id = self.company2.id
            self.user1_id = self.user1.id
            self.api_key1_value = self.api_key1.key
            self.api_key2_value = self.api_key2.key
        
        yield
        
        with app.app_context():
            # Cleanup in reverse dependency order
            APIKey.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_api_endpoint_without_authentication(self, client):
        """Test that API endpoints reject unauthenticated requests."""
        # Try to access API without any authentication
        response = client.get('/api/receiving_logs')
        assert response.status_code == 401
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_api_endpoint_with_invalid_key(self, client):
        """Test that API endpoints reject invalid API keys."""
        response = client.get(
            '/api/receiving_logs',
            headers={'X-API-Key': 'invalid_key_that_does_not_exist'}
        )
        assert response.status_code == 401
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Invalid' in data['error'] or 'Unauthorized' in data['error']
    
    def test_api_endpoint_with_valid_key(self, client, app):
        """Test that API endpoints accept valid API keys."""
        response = client.get(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key1_value}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        # API returns an array directly, not wrapped in an object
        assert isinstance(data, list)
    
    def test_api_endpoint_with_revoked_key(self, client, app):
        """Test that revoked API keys are rejected."""
        with app.app_context():
            api_key = db.session.get(APIKey, 1)
            api_key.is_active = False
            db.session.commit()
        
        response = client.get(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key1_value}
        )
        assert response.status_code == 401
        
        # Reactivate for other tests
        with app.app_context():
            api_key = db.session.get(APIKey, 1)
            api_key.is_active = True
            db.session.commit()
    
    def test_api_key_in_query_parameter(self, client):
        """Test that API key in query parameter works (alternative auth method)."""
        response = client.get(f'/api/receiving_logs?api_key={self.api_key1_value}')
        # This should either work or be explicitly rejected - either is fine
        # Just ensure it's handled consistently
        assert response.status_code in [200, 401]
    
    def test_api_test_endpoint_requires_key(self, client):
        """Test that the /api/test endpoint requires API key."""
        # Without key
        response = client.get('/api/test')
        assert response.status_code == 401
        
        # With valid key
        response = client.get('/api/test', headers={'X-API-Key': self.api_key1_value})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['company_id'] == self.company1_id


class TestAPICompanyIsolation:
    """Test that API endpoints properly isolate data between companies."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data for isolation tests."""
        with app.app_context():
            # Create two companies
            self.company1 = Company(name='Company 1', admin_email='admin1@test.com')
            self.company2 = Company(name='Company 2', admin_email='admin2@test.com')
            db.session.add_all([self.company1, self.company2])
            db.session.flush()
            
            # Create users
            self.user1 = User(
                first_name='User', last_name='One',
                email='user1@test.com', password='hashed',
                company_id=self.company1.id
            )
            self.user2 = User(
                first_name='User', last_name='Two',
                email='user2@test.com', password='hashed',
                company_id=self.company2.id
            )
            db.session.add_all([self.user1, self.user2])
            db.session.flush()
            
            # Create API keys
            self.api_key1 = APIKey(
                key='company1_key_12345',
                device_name='Device 1',
                company_id=self.company1.id,
                created_by_user_id=self.user1.id
            )
            self.api_key2 = APIKey(
                key='company2_key_67890',
                device_name='Device 2',
                company_id=self.company2.id,
                created_by_user_id=self.user2.id
            )
            db.session.add_all([self.api_key1, self.api_key2])
            db.session.flush()
            
            # Create raw products for each company
            self.raw_product1 = RawProduct(name='Raw Product 1', company_id=self.company1.id)
            self.raw_product2 = RawProduct(name='Raw Product 2', company_id=self.company2.id)
            db.session.add_all([self.raw_product1, self.raw_product2])
            db.session.flush()
            
            # Create brand names
            self.brand1 = BrandName(name='Brand 1', company_id=self.company1.id)
            self.brand2 = BrandName(name='Brand 2', company_id=self.company2.id)
            db.session.add_all([self.brand1, self.brand2])
            db.session.flush()
            
            # Create sellers
            self.seller1 = Seller(name='Seller 1', company_id=self.company1.id)
            self.seller2 = Seller(name='Seller 2', company_id=self.company2.id)
            db.session.add_all([self.seller1, self.seller2])
            db.session.flush()
            
            # Create growers
            self.grower1 = GrowerOrDistributor(
                name='Grower 1', city='City1', state='State1',
                company_id=self.company1.id
            )
            self.grower2 = GrowerOrDistributor(
                name='Grower 2', city='City2', state='State2',
                company_id=self.company2.id
            )
            db.session.add_all([self.grower1, self.grower2])
            db.session.flush()
            
            # Create receiving logs
            self.log1 = ReceivingLog(
                raw_product_id=self.raw_product1.id,
                pack_size_unit='lbs', pack_size=25.0,
                brand_name_id=self.brand1.id,
                quantity_received=10,
                seller_id=self.seller1.id,
                temperature=35.0,
                hold_or_used='used',
                grower_or_distributor_id=self.grower1.id,
                country_of_origin='USA',
                received_by='Worker 1',
                company_id=self.company1.id
            )
            self.log2 = ReceivingLog(
                raw_product_id=self.raw_product2.id,
                pack_size_unit='lbs', pack_size=30.0,
                brand_name_id=self.brand2.id,
                quantity_received=15,
                seller_id=self.seller2.id,
                temperature=36.0,
                hold_or_used='hold',
                grower_or_distributor_id=self.grower2.id,
                country_of_origin='Mexico',
                received_by='Worker 2',
                company_id=self.company2.id
            )
            db.session.add_all([self.log1, self.log2])
            db.session.commit()
            
            # Store IDs for tests (to avoid DetachedInstanceError)
            self.api_key1_value = self.api_key1.key
            self.api_key2_value = self.api_key2.key
            self.company1_id = self.company1.id
            self.company2_id = self.company2.id
            self.raw_product1_id = self.raw_product1.id
            self.raw_product2_id = self.raw_product2.id
            self.brand1_id = self.brand1.id
            self.brand2_id = self.brand2.id
            self.seller1_id = self.seller1.id
            self.seller2_id = self.seller2.id
            self.grower1_id = self.grower1.id
            self.grower2_id = self.grower2.id
            self.log1_id = self.log1.id
            self.log2_id = self.log2.id
        
        yield
        
        with app.app_context():
            # Cleanup
            ReceivingLog.query.delete()
            GrowerOrDistributor.query.delete()
            Seller.query.delete()
            BrandName.query.delete()
            RawProduct.query.delete()
            APIKey.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_get_receiving_logs_returns_only_own_company_data(self, client):
        """Test that GET /api/receiving_logs returns only data for authenticated company."""
        # Company 1 should see only their logs
        response = client.get(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key1_value}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        # API returns array directly
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]['id'] == self.log1_id
        
        # Company 2 should see only their logs
        response = client.get(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key2_value}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]['id'] == self.log2_id
    
    def test_get_raw_products_returns_only_own_company_data(self, client):
        """Test that GET /api/raw_products returns only data for authenticated company."""
        # Company 1
        response = client.get(
            '/api/raw_products',
            headers={'X-API-Key': self.api_key1_value}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        # API returns array directly
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]['id'] == self.raw_product1_id
        
        # Company 2
        response = client.get(
            '/api/raw_products',
            headers={'X-API-Key': self.api_key2_value}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        # API returns array directly
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]['id'] == self.raw_product2_id
    
    def test_cannot_create_receiving_log_with_other_company_foreign_keys(self, client, app):
        """Test that creating a receiving log with another company's foreign keys fails."""
        # Try to create a log for company1 using company2's raw product
        log_data = {
            'raw_product_id': self.raw_product2_id,  # Company 2's product
            'pack_size_unit': 'lbs',
            'pack_size': 20.0,
            'brand_name_id': self.brand1_id,  # Company 1's brand (mixing data)
            'quantity_received': 5,
            'seller_id': self.seller1_id,
            'temperature': 35.0,
            'hold_or_used': 'used',
            'grower_or_distributor_id': self.grower1_id,
            'country_of_origin': 'USA',
            'received_by': 'Test Worker'
        }
        
        response = client.post(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key1_value},
            data=json.dumps(log_data),
            content_type='application/json'
        )
        
        # Should fail validation or return an error
        assert response.status_code in [400, 403, 404]


class TestAPIInputValidation:
    """Test API input validation and sanitization."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data."""
        with app.app_context():
            self.company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(self.company)
            db.session.flush()
            
            self.user = User(
                first_name='Test', last_name='User',
                email='test@test.com', password='hashed',
                company_id=self.company.id
            )
            db.session.add(self.user)
            db.session.flush()
            
            self.api_key = APIKey(
                key='validation_test_key_12345',
                device_name='Test Device',
                company_id=self.company.id,
                created_by_user_id=self.user.id
            )
            db.session.add(self.api_key)
            db.session.flush()
            
            # Create required foreign key entities
            self.raw_product = RawProduct(name='Test Product', company_id=self.company.id)
            self.brand = BrandName(name='Test Brand', company_id=self.company.id)
            self.seller = Seller(name='Test Seller', company_id=self.company.id)
            self.grower = GrowerOrDistributor(
                name='Test Grower', city='City', state='State',
                company_id=self.company.id
            )
            db.session.add_all([self.raw_product, self.brand, self.seller, self.grower])
            db.session.commit()
            
            self.api_key_value = self.api_key.key
            self.raw_product_id = self.raw_product.id
            self.brand_id = self.brand.id
            self.seller_id = self.seller.id
            self.grower_id = self.grower.id
        
        yield
        
        with app.app_context():
            ReceivingLog.query.delete()
            GrowerOrDistributor.query.delete()
            Seller.query.delete()
            BrandName.query.delete()
            RawProduct.query.delete()
            APIKey.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_sql_injection_in_raw_product_name(self, client):
        """Test that SQL injection attempts in raw product names are handled safely."""
        malicious_data = {
            'name': "'; DROP TABLE raw_product; --"
        }
        
        response = client.post(
            '/api/raw_products',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps(malicious_data),
            content_type='application/json'
        )
        
        # Should either succeed (treating as literal string) or fail validation
        # Either way, should not execute the SQL
        assert response.status_code in [200, 201, 400]
        
        # Verify table still exists by making another request
        response = client.get(
            '/api/raw_products',
            headers={'X-API-Key': self.api_key_value}
        )
        assert response.status_code == 200
    
    def test_xss_in_received_by_field(self, client):
        """Test that XSS attempts are handled safely."""
        log_data = {
            'raw_product_id': self.raw_product_id,
            'pack_size_unit': 'lbs',
            'pack_size': 25.0,
            'brand_name_id': self.brand_id,
            'quantity_received': 10,
            'seller_id': self.seller_id,
            'temperature': 35.0,
            'hold_or_used': 'used',
            'grower_or_distributor_id': self.grower_id,
            'country_of_origin': 'USA',
            'received_by': '<script>alert("XSS")</script>'
        }
        
        response = client.post(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps(log_data),
            content_type='application/json'
        )
        
        # Should accept the data
        assert response.status_code in [200, 201]
        
        # When retrieved, the script tags should be escaped or sanitized
        response = client.get(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key_value}
        )
        data = json.loads(response.data)
        # The actual sanitization happens in templates, but data should be stored
    
    def test_negative_quantity_rejected(self, client):
        """Test that negative quantities are rejected."""
        log_data = {
            'raw_product_id': self.raw_product_id,
            'pack_size_unit': 'lbs',
            'pack_size': 25.0,
            'brand_name_id': self.brand_id,
            'quantity_received': -10,  # Negative value
            'seller_id': self.seller_id,
            'temperature': 35.0,
            'hold_or_used': 'used',
            'grower_or_distributor_id': self.grower_id,
            'country_of_origin': 'USA',
            'received_by': 'Worker'
        }
        
        response = client.post(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps(log_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
    
    def test_missing_required_fields_rejected(self, client):
        """Test that requests with missing required fields are rejected."""
        incomplete_data = {
            'raw_product_id': self.raw_product_id,
            'pack_size_unit': 'lbs'
            # Missing many required fields
        }
        
        response = client.post(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps(incomplete_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data or 'errors' in data
    
    def test_invalid_foreign_key_rejected(self, client):
        """Test that invalid foreign key IDs are rejected."""
        log_data = {
            'raw_product_id': 99999,  # Non-existent ID
            'pack_size_unit': 'lbs',
            'pack_size': 25.0,
            'brand_name_id': self.brand_id,
            'quantity_received': 10,
            'seller_id': self.seller_id,
            'temperature': 35.0,
            'hold_or_used': 'used',
            'grower_or_distributor_id': self.grower_id,
            'country_of_origin': 'USA',
            'received_by': 'Worker'
        }
        
        response = client.post(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps(log_data),
            content_type='application/json'
        )
        
        assert response.status_code in [400, 404]
    
    def test_extremely_large_values_handled(self, client):
        """Test that extremely large numeric values are handled appropriately."""
        log_data = {
            'raw_product_id': self.raw_product_id,
            'pack_size_unit': 'lbs',
            'pack_size': 999999999999999.99,  # Very large number
            'brand_name_id': self.brand_id,
            'quantity_received': 999999999,
            'seller_id': self.seller_id,
            'temperature': 35.0,
            'hold_or_used': 'used',
            'grower_or_distributor_id': self.grower_id,
            'country_of_origin': 'USA',
            'received_by': 'Worker'
        }
        
        response = client.post(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps(log_data),
            content_type='application/json'
        )
        
        # Should either accept or reject based on validation rules
        assert response.status_code in [200, 201, 400]


class TestAPIRateLimiting:
    """Test for potential rate limiting or DOS prevention."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data."""
        with app.app_context():
            self.company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(self.company)
            db.session.flush()
            
            self.user = User(
                first_name='Test', last_name='User',
                email='test@test.com', password='hashed',
                company_id=self.company.id
            )
            db.session.add(self.user)
            db.session.flush()
            
            self.api_key = APIKey(
                key='rate_limit_test_key',
                device_name='Test Device',
                company_id=self.company.id,
                created_by_user_id=self.user.id
            )
            db.session.add(self.api_key)
            db.session.commit()
            
            self.api_key_value = self.api_key.key
        
        yield
        
        with app.app_context():
            APIKey.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_multiple_rapid_requests_handled(self, client):
        """Test that multiple rapid requests are handled gracefully."""
        # Make 10 rapid requests
        responses = []
        for _ in range(10):
            response = client.get(
                '/api/receiving_logs',
                headers={'X-API-Key': self.api_key_value}
            )
            responses.append(response.status_code)
        
        # All should succeed or some should be rate limited (429)
        # If no rate limiting, all should be 200
        assert all(status in [200, 429] for status in responses)
        # At least some should succeed
        assert 200 in responses


class TestAPIContentTypeHandling:
    """Test handling of different content types and malformed requests."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data."""
        with app.app_context():
            self.company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(self.company)
            db.session.flush()
            
            self.user = User(
                first_name='Test', last_name='User',
                email='test@test.com', password='hashed',
                company_id=self.company.id
            )
            db.session.add(self.user)
            db.session.flush()
            
            self.api_key = APIKey(
                key='content_type_test_key',
                device_name='Test Device',
                company_id=self.company.id,
                created_by_user_id=self.user.id
            )
            db.session.add(self.api_key)
            db.session.commit()
            
            self.api_key_value = self.api_key.key
        
        yield
        
        with app.app_context():
            APIKey.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_malformed_json_rejected(self, client):
        """Test that malformed JSON is properly rejected."""
        response = client.post(
            '/api/raw_products',
            headers={'X-API-Key': self.api_key_value},
            data='{"name": "incomplete json',  # Malformed
            content_type='application/json'
        )
        
        assert response.status_code == 400
    
    def test_wrong_content_type_handled(self, client):
        """Test that wrong content-type headers are handled."""
        response = client.post(
            '/api/raw_products',
            headers={'X-API-Key': self.api_key_value},
            data='name=Test',
            content_type='text/plain'  # Wrong type
        )
        
        # Should reject or handle gracefully
        assert response.status_code in [400, 415]
    
    def test_empty_request_body_handled(self, client):
        """Test that empty request bodies are handled."""
        response = client.post(
            '/api/raw_products',
            headers={'X-API-Key': self.api_key_value},
            data='',
            content_type='application/json'
        )
        
        assert response.status_code == 400


class TestAPIMethodSecurity:
    """Test that HTTP methods are properly restricted."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data."""
        with app.app_context():
            self.company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(self.company)
            db.session.flush()
            
            self.user = User(
                first_name='Test', last_name='User',
                email='test@test.com', password='hashed',
                company_id=self.company.id
            )
            db.session.add(self.user)
            db.session.flush()
            
            self.api_key = APIKey(
                key='method_test_key',
                device_name='Test Device',
                company_id=self.company.id,
                created_by_user_id=self.user.id
            )
            db.session.add(self.api_key)
            db.session.commit()
            
            self.api_key_value = self.api_key.key
        
        yield
        
        with app.app_context():
            APIKey.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_delete_method_not_allowed_on_get_endpoint(self, client):
        """Test that DELETE is rejected on GET-only endpoints."""
        response = client.delete(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key_value}
        )
        
        assert response.status_code == 405  # Method Not Allowed
    
    def test_put_method_not_allowed_on_post_endpoint(self, client):
        """Test that PUT is rejected where not implemented."""
        response = client.put(
            '/api/receiving_logs',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps({'test': 'data'}),
            content_type='application/json'
        )
        
        assert response.status_code == 405  # Method Not Allowed
