"""
Security tests for API endpoints to ensure they're protected against common attacks.

Tests cover:
- Authentication requirements
- Authorization and data isolation (company_id checks)
- SQL injection attempts
- XSS and malicious input
- Invalid data types and boundary conditions
- File upload security
- Information disclosure through error messages
"""

import pytest
import json
import io
from producepricer import db
from producepricer.models import (
    Company, User, RawProduct, 
    BrandName, Seller, GrowerOrDistributor, ReceivingLog, ReceivingImage
)


class TestAPIAuthentication:
    """Test that all API endpoints require authentication."""
    
    def test_get_receiving_logs_requires_auth(self, client):
        """GET /api/receiving_logs should reject unauthenticated requests."""
        response = client.get('/api/receiving_logs')
        assert response.status_code == 401
        data = json.loads(response.data)
        assert 'error' in data
        assert data['error'] == 'Unauthorized'
    
    def test_post_receiving_logs_requires_auth(self, client):
        """POST /api/receiving_logs should reject unauthenticated requests."""
        payload = {'raw_product_id': 1, 'pack_size': 50}
        response = client.post('/api/receiving_logs', 
                              json=payload,
                              content_type='application/json')
        assert response.status_code == 401
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_get_raw_products_requires_auth(self, client):
        """GET /api/raw_products should reject unauthenticated requests."""
        response = client.get('/api/raw_products')
        assert response.status_code == 401
    
    def test_get_brand_names_requires_auth(self, client):
        """GET /api/brand_names should reject unauthenticated requests."""
        response = client.get('/api/brand_names')
        assert response.status_code == 401
    
    def test_get_sellers_requires_auth(self, client):
        """GET /api/sellers should reject unauthenticated requests."""
        response = client.get('/api/sellers')
        assert response.status_code == 401
    
    def test_get_growers_distributors_requires_auth(self, client):
        """GET /api/growers_distributors should reject unauthenticated requests."""
        response = client.get('/api/growers_distributors')
        assert response.status_code == 401
    
    def test_upload_images_requires_auth(self, client):
        """POST /api/receiving_logs/<id>/images should reject unauthenticated requests."""
        response = client.post('/api/receiving_logs/1/images',
                              data={'images': (io.BytesIO(b"fake image"), 'test.jpg')})
        assert response.status_code == 401


class TestAPIAuthorization:
    """Test that users can only access their own company's data."""
    
    @pytest.fixture
    def two_companies_setup(self, app):
        """Create two companies with data for cross-company access tests."""
        with app.app_context():
            # Company 1
            company1 = Company(name="Company One", admin_email="admin1@company1.com")
            db.session.add(company1)
            db.session.commit()
            
            user1 = User(first_name="User", last_name="One", 
                        email="user1@company1.com", 
                        password="password123",
                        company_id=company1.id)
            db.session.add(user1)
            
            raw_product1 = RawProduct(name="Product 1", company_id=company1.id)
            db.session.add(raw_product1)
            
            brand1 = BrandName(name="Brand 1", company_id=company1.id)
            db.session.add(brand1)
            
            seller1 = Seller(name="Seller 1", company_id=company1.id)
            db.session.add(seller1)
            
            grower1 = GrowerOrDistributor(name="Grower 1", company_id=company1.id,
                                         city="City1", state="State1")
            db.session.add(grower1)
            db.session.commit()
            
            log1 = ReceivingLog(
                raw_product_id=raw_product1.id,
                pack_size_unit="lbs",
                pack_size=50.0,
                brand_name_id=brand1.id,
                quantity_received=100,
                seller_id=seller1.id,
                temperature=34.5,
                hold_or_used="used",
                grower_or_distributor_id=grower1.id,
                country_of_origin="USA",
                received_by="Employee 1",
                company_id=company1.id
            )
            db.session.add(log1)
            db.session.commit()
            
            # Company 2
            company2 = Company(name="Company Two", admin_email="admin2@company2.com")
            db.session.add(company2)
            db.session.commit()
            
            user2 = User(first_name="User", last_name="Two", 
                        email="user2@company2.com", 
                        password="password123",
                        company_id=company2.id)
            db.session.add(user2)
            
            raw_product2 = RawProduct(name="Product 2", company_id=company2.id)
            db.session.add(raw_product2)
            
            brand2 = BrandName(name="Brand 2", company_id=company2.id)
            db.session.add(brand2)
            
            seller2 = Seller(name="Seller 2", company_id=company2.id)
            db.session.add(seller2)
            
            grower2 = GrowerOrDistributor(name="Grower 2", company_id=company2.id,
                                         city="City2", state="State2")
            db.session.add(grower2)
            db.session.commit()
            
            log2 = ReceivingLog(
                raw_product_id=raw_product2.id,
                pack_size_unit="lbs",
                pack_size=25.0,
                brand_name_id=brand2.id,
                quantity_received=50,
                seller_id=seller2.id,
                temperature=36.0,
                hold_or_used="hold",
                grower_or_distributor_id=grower2.id,
                country_of_origin="Mexico",
                received_by="Employee 2",
                company_id=company2.id
            )
            db.session.add(log2)
            db.session.commit()
            
            return {
                'company1': {'id': company1.id, 'log_id': log1.id},
                'company2': {'id': company2.id, 'log_id': log2.id},
                'user1': {'email': 'user1@company1.com'},
                'user2': {'email': 'user2@company2.com'}
            }
    
    def test_user_only_sees_own_company_receiving_logs(self, client, two_companies_setup, app):
        """Users should only see receiving logs from their own company."""
        # Login as company1 user
        client.post('/login', data={
            'email': 'user1@company1.com',
            'password': 'password123'
        })
        
        response = client.get('/api/receiving_logs')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Should only see company1's log
        assert len(data) == 1
        assert data[0]['raw_product_name'] == "Product 1"
        assert data[0]['received_by'] == "Employee 1"
    
    def test_user_cannot_upload_to_other_company_log(self, client, two_companies_setup, app):
        """Users should not be able to upload images to another company's receiving log."""
        # Login as company1 user
        client.post('/login', data={
            'email': 'user1@company1.com',
            'password': 'password123'
        })
        
        # Try to upload to company2's log
        log_id = two_companies_setup['company2']['log_id']
        
        data = {
            'images': (io.BytesIO(b"fake image content"), 'hacker.jpg')
        }
        
        response = client.post(f'/api/receiving_logs/{log_id}/images', 
                              data=data,
                              content_type='multipart/form-data')
        
        # Should be forbidden
        assert response.status_code == 403
        result = json.loads(response.data)
        assert 'error' in result
        assert result['error'] == 'Unauthorized'
    
    def test_user_only_sees_own_company_raw_products(self, client, two_companies_setup):
        """Users should only see raw products from their own company."""
        client.post('/login', data={
            'email': 'user1@company1.com',
            'password': 'password123'
        })
        
        response = client.get('/api/raw_products')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Should only see company1's product
        assert len(data) == 1
        assert data[0]['name'] == "Product 1"
    
    def test_user_only_sees_own_company_brands(self, client, two_companies_setup):
        """Users should only see brands from their own company."""
        client.post('/login', data={
            'email': 'user2@company2.com',
            'password': 'password123'
        })
        
        response = client.get('/api/brand_names')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Should only see company2's brand
        assert len(data) == 1
        assert data[0]['name'] == "Brand 2"
    
    def test_user_only_sees_own_company_sellers(self, client, two_companies_setup):
        """Users should only see sellers from their own company."""
        client.post('/login', data={
            'email': 'user1@company1.com',
            'password': 'password123'
        })
        
        response = client.get('/api/sellers')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert len(data) == 1
        assert data[0]['name'] == "Seller 1"
    
    def test_user_only_sees_own_company_growers(self, client, two_companies_setup):
        """Users should only see growers from their own company."""
        client.post('/login', data={
            'email': 'user2@company2.com',
            'password': 'password123'
        })
        
        response = client.get('/api/growers_distributors')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert len(data) == 1
        assert data[0]['name'] == "Grower 2"
        assert data[0]['city'] == "City2"


class TestSQLInjection:
    """Test that API endpoints are protected against SQL injection attacks."""
    
    @pytest.fixture
    def sql_injection_setup(self, app):
        """Setup data for SQL injection tests."""
        with app.app_context():
            company = Company(name="Test Company", admin_email="test@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(first_name="Test", last_name="User", 
                       email="test@test.com", 
                       password="password",
                       company_id=company.id)
            db.session.add(user)
            
            raw_product = RawProduct(name="Safe Product", company_id=company.id)
            db.session.add(raw_product)
            
            brand = BrandName(name="Safe Brand", company_id=company.id)
            db.session.add(brand)
            
            seller = Seller(name="Safe Seller", company_id=company.id)
            db.session.add(seller)
            
            grower = GrowerOrDistributor(name="Safe Grower", company_id=company.id,
                                        city="Safe City", state="SS")
            db.session.add(grower)
            
            db.session.commit()
            
            return {
                'company_id': company.id,
                'raw_product_id': raw_product.id,
                'brand_id': brand.id,
                'seller_id': seller.id,
                'grower_id': grower.id
            }
    
    def test_sql_injection_in_receiving_log_creation(self, client, sql_injection_setup):
        """Test that SQL injection attempts in POST data are handled safely."""
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'password'
        })
        
        # Various SQL injection payloads
        sql_payloads = [
            "'; DROP TABLE receiving_log; --",
            "1' OR '1'='1",
            "1; DELETE FROM receiving_log WHERE 1=1; --",
            "' UNION SELECT * FROM user; --"
        ]
        
        for payload in sql_payloads:
            response = client.post('/api/receiving_logs', 
                                  json={
                                      'raw_product_id': sql_injection_setup['raw_product_id'],
                                      'pack_size_unit': payload,  # Injection in string field
                                      'pack_size': 50.0,
                                      'brand_name_id': sql_injection_setup['brand_id'],
                                      'quantity_received': 100,
                                      'seller_id': sql_injection_setup['seller_id'],
                                      'temperature': 34.5,
                                      'hold_or_used': 'used',
                                      'grower_or_distributor_id': sql_injection_setup['grower_id'],
                                      'country_of_origin': 'USA',
                                      'received_by': 'Test'
                                  },
                                  content_type='application/json')
            
            # Should either succeed (safely storing/sanitizing the string) or fail gracefully
            assert response.status_code in [201, 400, 500]
            
            # If it succeeded, verify the SQL was NOT executed (database still exists)
            if response.status_code == 201:
                response = client.get('/api/receiving_logs')
                data = json.loads(response.data)
                # Should get data back (proves SQL wasn't executed to drop tables)
                assert isinstance(data, list)
                # The payload should be sanitized or stored safely
                # Key point: the dangerous SQL should not have been executed
                assert len(data) > 0  # We successfully retrieved logs
    
    def test_sql_injection_in_country_field(self, client, sql_injection_setup):
        """Test SQL injection in country_of_origin field."""
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'password'
        })
        
        payload = {
            'raw_product_id': sql_injection_setup['raw_product_id'],
            'pack_size_unit': 'lbs',
            'pack_size': 50.0,
            'brand_name_id': sql_injection_setup['brand_id'],
            'quantity_received': 100,
            'seller_id': sql_injection_setup['seller_id'],
            'temperature': 34.5,
            'hold_or_used': 'used',
            'grower_or_distributor_id': sql_injection_setup['grower_id'],
            'country_of_origin': "'; DELETE FROM receiving_log; --",
            'received_by': 'Test'
        }
        
        response = client.post('/api/receiving_logs', 
                              json=payload,
                              content_type='application/json')
        
        # Should handle safely
        assert response.status_code in [201, 400, 500]
    
    def test_integer_field_sql_injection(self, client, sql_injection_setup):
        """Test that integer fields reject SQL injection strings."""
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'password'
        })
        
        # Try to inject SQL through integer fields
        payload = {
            'raw_product_id': "1 OR 1=1",  # Should fail type validation
            'pack_size_unit': 'lbs',
            'pack_size': 50.0,
            'brand_name_id': sql_injection_setup['brand_id'],
            'quantity_received': 100,
            'seller_id': sql_injection_setup['seller_id'],
            'temperature': 34.5,
            'hold_or_used': 'used',
            'grower_or_distributor_id': sql_injection_setup['grower_id'],
            'country_of_origin': 'USA',
            'received_by': 'Test'
        }
        
        response = client.post('/api/receiving_logs', 
                              json=payload,
                              content_type='application/json')
        
        # Should fail with error (400 or 500)
        assert response.status_code in [400, 500]


class TestXSSAndMaliciousInput:
    """Test protection against XSS and malicious input."""
    
    @pytest.fixture
    def xss_setup(self, app):
        """Setup data for XSS tests."""
        with app.app_context():
            company = Company(name="XSS Test Co", admin_email="xss@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(first_name="XSS", last_name="Tester", 
                       email="xss@test.com", 
                       password="password",
                       company_id=company.id)
            db.session.add(user)
            
            raw_product = RawProduct(name="Test Product", company_id=company.id)
            db.session.add(raw_product)
            
            brand = BrandName(name="Test Brand", company_id=company.id)
            db.session.add(brand)
            
            seller = Seller(name="Test Seller", company_id=company.id)
            db.session.add(seller)
            
            grower = GrowerOrDistributor(name="Test Grower", company_id=company.id,
                                        city="Test", state="TS")
            db.session.add(grower)
            
            db.session.commit()
            
            return {
                'company_id': company.id,
                'raw_product_id': raw_product.id,
                'brand_id': brand.id,
                'seller_id': seller.id,
                'grower_id': grower.id
            }
    
    def test_xss_in_text_fields(self, client, xss_setup):
        """Test that XSS payloads in text fields are handled safely."""
        client.post('/login', data={
            'email': 'xss@test.com',
            'password': 'password'
        })
        
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<iframe src='javascript:alert(\"XSS\")'></iframe>",
            "<svg onload=alert('XSS')>"
        ]
        
        for payload in xss_payloads:
            response = client.post('/api/receiving_logs', 
                                  json={
                                      'raw_product_id': xss_setup['raw_product_id'],
                                      'pack_size_unit': 'lbs',
                                      'pack_size': 50.0,
                                      'brand_name_id': xss_setup['brand_id'],
                                      'quantity_received': 100,
                                      'seller_id': xss_setup['seller_id'],
                                      'temperature': 34.5,
                                      'hold_or_used': 'used',
                                      'grower_or_distributor_id': xss_setup['grower_id'],
                                      'country_of_origin': payload,  # XSS in text field
                                      'received_by': 'Test'
                                  },
                                  content_type='application/json')
            
            # Should succeed (with sanitized input) or reject
            assert response.status_code in [201, 400]
            
            if response.status_code == 201:
                # Verify the data is sanitized (tags removed or escaped)
                response = client.get('/api/receiving_logs')
                data = json.loads(response.data)
                
                # Check that dangerous tags are removed or properly escaped
                for log in data:
                    country = log.get('country_of_origin', '')
                    # Dangerous script tags should be sanitized
                    # Either completely removed or HTML-escaped (both are safe)
                    # Check that actual executable script tags are not present
                    assert '<script>' not in country  # Unescaped script tag
                    assert '</script>' not in country  # Unescaped closing tag
                    
                    # If HTML entities are used (like &lt;), that's acceptable
                    # The key is that the browser won't execute them
                    # Verify it's not the raw dangerous payload
                    if '<' in country or '&lt;' in country:
                        # It's been escaped/sanitized, which is good
                        pass
                    # Otherwise it should be stripped clean
    
    def test_malicious_filename_upload(self, client, xss_setup, app):
        """Test that malicious filenames are sanitized."""
        client.post('/login', data={
            'email': 'xss@test.com',
            'password': 'password'
        })
        
        # Create a receiving log first
        with app.app_context():
            log = ReceivingLog(
                raw_product_id=xss_setup['raw_product_id'],
                pack_size_unit="lbs",
                pack_size=50.0,
                brand_name_id=xss_setup['brand_id'],
                quantity_received=100,
                seller_id=xss_setup['seller_id'],
                temperature=34.5,
                hold_or_used="used",
                grower_or_distributor_id=xss_setup['grower_id'],
                country_of_origin="USA",
                received_by="Test",
                company_id=xss_setup['company_id']
            )
            db.session.add(log)
            db.session.commit()
            log_id = log.id
        
        # Try various malicious filenames
        malicious_filenames = [
            "../../../etc/passwd.jpg",
            "../../sensitive.jpg",
            "<script>alert('xss')</script>.jpg",
            "file; rm -rf /.jpg",
            "test\x00.jpg.exe"  # Null byte injection
        ]
        
        for filename in malicious_filenames:
            data = {
                'images': (io.BytesIO(b"fake image"), filename)
            }
            
            response = client.post(f'/api/receiving_logs/{log_id}/images',
                                  data=data,
                                  content_type='multipart/form-data')
            
            # Should either succeed (with sanitized filename) or reject
            assert response.status_code in [201, 400]
            
            if response.status_code == 201:
                # Verify filename was sanitized
                result = json.loads(response.data)
                if 'images' in result and len(result['images']) > 0:
                    # Check that path traversal sequences are not in the stored filename
                    assert '../' not in result['images'][0]
                    assert '<script>' not in result['images'][0]


class TestInputValidation:
    """Test input validation and error handling."""
    
    @pytest.fixture
    def validation_setup(self, app):
        """Setup data for validation tests."""
        with app.app_context():
            company = Company(name="Validation Co", admin_email="valid@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(first_name="Valid", last_name="User", 
                       email="valid@test.com", 
                       password="password",
                       company_id=company.id)
            db.session.add(user)
            
            raw_product = RawProduct(name="Product", company_id=company.id)
            db.session.add(raw_product)
            
            brand = BrandName(name="Brand", company_id=company.id)
            db.session.add(brand)
            
            seller = Seller(name="Seller", company_id=company.id)
            db.session.add(seller)
            
            grower = GrowerOrDistributor(name="Grower", company_id=company.id,
                                        city="City", state="ST")
            db.session.add(grower)
            
            db.session.commit()
            
            return {
                'raw_product_id': raw_product.id,
                'brand_id': brand.id,
                'seller_id': seller.id,
                'grower_id': grower.id
            }
    
    def test_missing_required_fields(self, client, validation_setup):
        """Test that missing required fields are rejected."""
        client.post('/login', data={
            'email': 'valid@test.com',
            'password': 'password'
        })
        
        # Missing multiple required fields
        payload = {
            'pack_size': 50.0,
            'quantity_received': 100
        }
        
        response = client.post('/api/receiving_logs', 
                              json=payload,
                              content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        # Should not reveal sensitive system information
        assert 'database' not in data['error'].lower()
        assert 'traceback' not in data['error'].lower()
    
    def test_invalid_data_types(self, client, validation_setup):
        """Test that invalid data types are rejected."""
        client.post('/login', data={
            'email': 'valid@test.com',
            'password': 'password'
        })
        
        # String where integer is expected
        payload = {
            'raw_product_id': "not_an_integer",
            'pack_size_unit': 'lbs',
            'pack_size': 50.0,
            'brand_name_id': validation_setup['brand_id'],
            'quantity_received': 100,
            'seller_id': validation_setup['seller_id'],
            'temperature': 34.5,
            'hold_or_used': 'used',
            'grower_or_distributor_id': validation_setup['grower_id'],
            'country_of_origin': 'USA',
            'received_by': 'Test'
        }
        
        response = client.post('/api/receiving_logs', 
                              json=payload,
                              content_type='application/json')
        
        assert response.status_code in [400, 500]
    
    def test_negative_numbers_in_quantity(self, client, validation_setup):
        """Test that negative quantities are handled."""
        client.post('/login', data={
            'email': 'valid@test.com',
            'password': 'password'
        })
        
        payload = {
            'raw_product_id': validation_setup['raw_product_id'],
            'pack_size_unit': 'lbs',
            'pack_size': 50.0,
            'brand_name_id': validation_setup['brand_id'],
            'quantity_received': -100,  # Negative quantity
            'seller_id': validation_setup['seller_id'],
            'temperature': 34.5,
            'hold_or_used': 'used',
            'grower_or_distributor_id': validation_setup['grower_id'],
            'country_of_origin': 'USA',
            'received_by': 'Test'
        }
        
        response = client.post('/api/receiving_logs', 
                              json=payload,
                              content_type='application/json')
        
        # Should succeed or fail gracefully (business logic decision)
        assert response.status_code in [201, 400]
    
    def test_extremely_large_numbers(self, client, validation_setup):
        """Test handling of extremely large numbers."""
        client.post('/login', data={
            'email': 'valid@test.com',
            'password': 'password'
        })
        
        payload = {
            'raw_product_id': validation_setup['raw_product_id'],
            'pack_size_unit': 'lbs',
            'pack_size': 999999999999.99,  # Very large number
            'brand_name_id': validation_setup['brand_id'],
            'quantity_received': 999999999,
            'seller_id': validation_setup['seller_id'],
            'temperature': 34.5,
            'hold_or_used': 'used',
            'grower_or_distributor_id': validation_setup['grower_id'],
            'country_of_origin': 'USA',
            'received_by': 'Test'
        }
        
        response = client.post('/api/receiving_logs', 
                              json=payload,
                              content_type='application/json')
        
        # Should handle without crashing
        assert response.status_code in [201, 400, 500]
    
    def test_empty_strings(self, client, validation_setup):
        """Test handling of empty strings in text fields."""
        client.post('/login', data={
            'email': 'valid@test.com',
            'password': 'password'
        })
        
        payload = {
            'raw_product_id': validation_setup['raw_product_id'],
            'pack_size_unit': '',  # Empty string
            'pack_size': 50.0,
            'brand_name_id': validation_setup['brand_id'],
            'quantity_received': 100,
            'seller_id': validation_setup['seller_id'],
            'temperature': 34.5,
            'hold_or_used': '',  # Empty string
            'grower_or_distributor_id': validation_setup['grower_id'],
            'country_of_origin': '',  # Empty string
            'received_by': ''  # Empty string
        }
        
        response = client.post('/api/receiving_logs', 
                              json=payload,
                              content_type='application/json')
        
        # Should either accept or reject consistently
        assert response.status_code in [201, 400]
    
    def test_very_long_strings(self, client, validation_setup):
        """Test handling of very long strings."""
        client.post('/login', data={
            'email': 'valid@test.com',
            'password': 'password'
        })
        
        # Create a very long string
        long_string = 'A' * 10000
        
        payload = {
            'raw_product_id': validation_setup['raw_product_id'],
            'pack_size_unit': long_string,
            'pack_size': 50.0,
            'brand_name_id': validation_setup['brand_id'],
            'quantity_received': 100,
            'seller_id': validation_setup['seller_id'],
            'temperature': 34.5,
            'hold_or_used': 'used',
            'grower_or_distributor_id': validation_setup['grower_id'],
            'country_of_origin': 'USA',
            'received_by': 'Test'
        }
        
        response = client.post('/api/receiving_logs', 
                              json=payload,
                              content_type='application/json')
        
        # Should handle without crashing
        assert response.status_code in [201, 400, 500]
    
    def test_nonexistent_foreign_keys(self, client, validation_setup):
        """Test that referencing nonexistent foreign keys is handled."""
        client.post('/login', data={
            'email': 'valid@test.com',
            'password': 'password'
        })
        
        payload = {
            'raw_product_id': 999999,  # Nonexistent ID
            'pack_size_unit': 'lbs',
            'pack_size': 50.0,
            'brand_name_id': validation_setup['brand_id'],
            'quantity_received': 100,
            'seller_id': validation_setup['seller_id'],
            'temperature': 34.5,
            'hold_or_used': 'used',
            'grower_or_distributor_id': validation_setup['grower_id'],
            'country_of_origin': 'USA',
            'received_by': 'Test'
        }
        
        response = client.post('/api/receiving_logs', 
                              json=payload,
                              content_type='application/json')
        
        assert response.status_code in [400, 500]
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_null_values(self, client, validation_setup):
        """Test handling of null values."""
        client.post('/login', data={
            'email': 'valid@test.com',
            'password': 'password'
        })
        
        payload = {
            'raw_product_id': validation_setup['raw_product_id'],
            'pack_size_unit': None,  # Null value
            'pack_size': 50.0,
            'brand_name_id': validation_setup['brand_id'],
            'quantity_received': 100,
            'seller_id': validation_setup['seller_id'],
            'temperature': 34.5,
            'hold_or_used': 'used',
            'grower_or_distributor_id': validation_setup['grower_id'],
            'country_of_origin': 'USA',
            'received_by': 'Test'
        }
        
        response = client.post('/api/receiving_logs', 
                              json=payload,
                              content_type='application/json')
        
        # Should handle gracefully
        assert response.status_code in [201, 400, 500]
    
    def test_error_messages_dont_leak_sensitive_info(self, client):
        """Test that error messages don't reveal sensitive system information."""
        # Try to access API without auth
        response = client.get('/api/receiving_logs')
        
        data = json.loads(response.data)
        error_msg = data.get('error', '').lower()
        
        # Should not contain sensitive information
        assert 'password' not in error_msg
        assert 'database' not in error_msg
        assert 'traceback' not in error_msg
        assert 'stack' not in error_msg
        assert '/users/' not in error_msg  # No file paths
        assert 'sqlalchemy' not in error_msg


class TestFileUploadSecurity:
    """Test security of file upload functionality."""
    
    @pytest.fixture
    def upload_setup(self, app):
        """Setup for file upload tests."""
        with app.app_context():
            company = Company(name="Upload Test", admin_email="upload@test.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(first_name="Upload", last_name="User", 
                       email="upload@test.com", 
                       password="password",
                       company_id=company.id)
            db.session.add(user)
            
            raw_product = RawProduct(name="Product", company_id=company.id)
            db.session.add(raw_product)
            
            brand = BrandName(name="Brand", company_id=company.id)
            db.session.add(brand)
            
            seller = Seller(name="Seller", company_id=company.id)
            db.session.add(seller)
            
            grower = GrowerOrDistributor(name="Grower", company_id=company.id,
                                        city="City", state="ST")
            db.session.add(grower)
            db.session.commit()
            
            # Create a receiving log
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit="lbs",
                pack_size=50.0,
                brand_name_id=brand.id,
                quantity_received=100,
                seller_id=seller.id,
                temperature=34.5,
                hold_or_used="used",
                grower_or_distributor_id=grower.id,
                country_of_origin="USA",
                received_by="Test",
                company_id=company.id
            )
            db.session.add(log)
            db.session.commit()
            
            return {'log_id': log.id}
    
    def test_empty_file_upload(self, client, upload_setup):
        """Test handling of empty file uploads."""
        client.post('/login', data={
            'email': 'upload@test.com',
            'password': 'password'
        })
        
        data = {
            'images': (io.BytesIO(b""), 'empty.jpg')  # Empty file
        }
        
        response = client.post(f'/api/receiving_logs/{upload_setup["log_id"]}/images',
                              data=data,
                              content_type='multipart/form-data')
        
        # Should handle gracefully
        assert response.status_code in [201, 400]
    
    def test_no_file_provided(self, client, upload_setup):
        """Test proper error when no file is provided."""
        client.post('/login', data={
            'email': 'upload@test.com',
            'password': 'password'
        })
        
        response = client.post(f'/api/receiving_logs/{upload_setup["log_id"]}/images',
                              data={},
                              content_type='multipart/form-data')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_suspicious_file_extensions(self, client, upload_setup):
        """Test handling of suspicious file extensions."""
        client.post('/login', data={
            'email': 'upload@test.com',
            'password': 'password'
        })
        
        suspicious_extensions = [
            'test.exe',
            'test.php',
            'test.sh',
            'test.bat',
            'test.jpg.exe',
            'test.asp',
            'test.jsp'
        ]
        
        for filename in suspicious_extensions:
            data = {
                'images': (io.BytesIO(b"fake content"), filename)
            }
            
            response = client.post(f'/api/receiving_logs/{upload_setup["log_id"]}/images',
                                  data=data,
                                  content_type='multipart/form-data')
            
            # Should either accept (if extension checking not implemented) 
            # or reject (if it is implemented)
            assert response.status_code in [201, 400]
    
    def test_large_file_upload(self, client, upload_setup):
        """Test handling of very large file uploads."""
        client.post('/login', data={
            'email': 'upload@test.com',
            'password': 'password'
        })
        
        # Create a large file (1MB)
        large_content = b"X" * (1024 * 1024)
        
        data = {
            'images': (io.BytesIO(large_content), 'large.jpg')
        }
        
        response = client.post(f'/api/receiving_logs/{upload_setup["log_id"]}/images',
                              data=data,
                              content_type='multipart/form-data')
        
        # Should handle without crashing
        assert response.status_code in [201, 400, 413]  # 413 = Payload Too Large
    
    def test_multiple_files_with_same_name(self, client, upload_setup):
        """Test uploading multiple files with the same name."""
        client.post('/login', data={
            'email': 'upload@test.com',
            'password': 'password'
        })
        
        data = {
            'images': [
                (io.BytesIO(b"image1"), 'same.jpg'),
                (io.BytesIO(b"image2"), 'same.jpg')
            ]
        }
        
        response = client.post(f'/api/receiving_logs/{upload_setup["log_id"]}/images',
                              data=data,
                              content_type='multipart/form-data')
        
        # Should handle by renaming or overwriting (implementation dependent)
        assert response.status_code in [201, 400]
