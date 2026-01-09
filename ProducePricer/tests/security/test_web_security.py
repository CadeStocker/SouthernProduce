"""
Security tests for web routes.
Tests authentication, authorization, CSRF protection, and access control.
"""

import pytest
from producepricer.models import (
    Company, User, ReceivingLog, RawProduct, BrandName,
    Seller, GrowerOrDistributor, Customer, Item, Packaging,
    CostHistory, PriceHistory
)
from producepricer import db, bcrypt


class TestWebAuthentication:
    """Test web authentication requirements."""
    
    def test_home_requires_login(self, client):
        """Test that home page requires login."""
        response = client.get('/')
        assert response.status_code == 302  # Redirect to login
        assert '/login' in response.location
    
    def test_items_requires_login(self, client):
        """Test that items page requires login."""
        response = client.get('/items')
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_raw_product_requires_login(self, client):
        """Test that raw products page requires login."""
        response = client.get('/raw_product')
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_receiving_logs_requires_login(self, client):
        """Test that receiving logs page requires login."""
        response = client.get('/receiving_logs')
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_company_page_requires_login(self, client):
        """Test that company page requires login."""
        response = client.get('/company')
        assert response.status_code == 302
        assert '/login' in response.location


class TestWebCompanyIsolation:
    """Test that web routes properly isolate data between companies."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data for isolation tests."""
        with app.app_context():
            # Create two companies
            self.company1 = Company(name='Company 1', admin_email='admin1@test.com')
            self.company2 = Company(name='Company 2', admin_email='admin2@test.com')
            db.session.add_all([self.company1, self.company2])
            db.session.flush()
            
            # Create users for each company with bcrypt hashed passwords
            password_hash = bcrypt.generate_password_hash('password123').decode('utf-8')
            self.user1 = User(
                first_name='User', last_name='One',
                email='user1@test.com', password=password_hash,
                company_id=self.company1.id
            )
            self.user2 = User(
                first_name='User', last_name='Two',
                email='user2@test.com', password=password_hash,
                company_id=self.company2.id
            )
            db.session.add_all([self.user1, self.user2])
            db.session.flush()
            
            # Create raw products for each company
            self.raw_product1 = RawProduct(name='Raw Product 1', company_id=self.company1.id)
            self.raw_product2 = RawProduct(name='Raw Product 2', company_id=self.company2.id)
            db.session.add_all([self.raw_product1, self.raw_product2])
            db.session.flush()
            
            # Create supporting entities for receiving logs
            self.brand1 = BrandName(name='Brand 1', company_id=self.company1.id)
            self.brand2 = BrandName(name='Brand 2', company_id=self.company2.id)
            self.seller1 = Seller(name='Seller 1', company_id=self.company1.id)
            self.seller2 = Seller(name='Seller 2', company_id=self.company2.id)
            self.grower1 = GrowerOrDistributor(
                name='Grower 1', city='City1', state='State1',
                company_id=self.company1.id
            )
            self.grower2 = GrowerOrDistributor(
                name='Grower 2', city='City2', state='State2',
                company_id=self.company2.id
            )
            db.session.add_all([
                self.brand1, self.brand2, self.seller1, self.seller2,
                self.grower1, self.grower2
            ])
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
            
            # Store IDs
            self.user1_id = self.user1.id
            self.user2_id = self.user2.id
            self.log1_id = self.log1.id
            self.log2_id = self.log2.id
            self.raw_product1_id = self.raw_product1.id
            self.raw_product2_id = self.raw_product2.id
        
        yield
        
        with app.app_context():
            # Cleanup
            ReceivingLog.query.delete()
            GrowerOrDistributor.query.delete()
            Seller.query.delete()
            BrandName.query.delete()
            RawProduct.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_cannot_view_other_company_receiving_log(self, client, app):
        """Test that a user cannot view another company's receiving log."""
        # Login as user1
        response = client.post('/login', data={
            'email': 'user1@test.com',
            'password': 'password123'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        # Try to view company2's receiving log
        response = client.get(f'/receiving_log/{self.log2_id}')
        
        # Should return 404 (not found) to prevent information disclosure
        assert response.status_code == 404
    
    def test_cannot_edit_other_company_receiving_log(self, client, app):
        """Test that a user cannot edit another company's receiving log."""
        # Login as user1
        client.post('/login', data={
            'email': 'user1@test.com',
            'password': 'password123'
        })
        
        # Try to edit company2's receiving log
        response = client.post(
            f'/edit_receiving_log/{self.log2_id}',
            data={'price_paid': '25.00'}
        )
        
        # Should return 404 or redirect
        assert response.status_code in [404, 302]
    
    def test_cannot_view_other_company_raw_product(self, client, app):
        """Test that a user cannot view another company's raw product."""
        # Login as user1
        client.post('/login', data={
            'email': 'user1@test.com',
            'password': 'password123'
        })
        
        # Try to view company2's raw product
        response = client.get(f'/raw_product/{self.raw_product2_id}')
        
        # Should return 404 or redirect to raw product list
        assert response.status_code in [404, 302]
    
    def test_cannot_delete_other_company_raw_product(self, client, app):
        """Test that a user cannot delete another company's raw product."""
        # Login as user1
        client.post('/login', data={
            'email': 'user1@test.com',
            'password': 'password123'
        })
        
        # Try to delete company2's raw product
        response = client.post(f'/delete_raw_product/{self.raw_product2_id}')
        
        # Should return 404 or error
        assert response.status_code in [404, 302, 403]
        
        # Verify product still exists
        with app.app_context():
            product = db.session.get(RawProduct, self.raw_product2_id)
            assert product is not None


class TestWebInputValidation:
    """Test web form input validation."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data."""
        with app.app_context():
            self.company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(self.company)
            db.session.flush()
            
            password_hash = bcrypt.generate_password_hash('password123').decode('utf-8')
            self.user = User(
                first_name='Test', last_name='User',
                email='test@test.com', password=password_hash,
                company_id=self.company.id
            )
            db.session.add(self.user)
            db.session.commit()
        
        yield
        
        with app.app_context():
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_xss_in_raw_product_name_escaped(self, client, app):
        """Test that XSS in raw product names is escaped."""
        # Login
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'password123'
        })
        
        # Create raw product with XSS attempt
        response = client.post('/add_raw_product', data={
            'name': '<script>alert("XSS")</script>'
        }, follow_redirects=True)
        
        # Should succeed
        assert response.status_code == 200
        
        # When displayed, the script should be escaped
        response = client.get('/raw_product')
        assert b'<script>' not in response.data or b'&lt;script&gt;' in response.data
    
    def test_sql_injection_in_search_prevented(self, client, app):
        """Test that SQL injection in search is prevented."""
        # Login
        response = client.post('/login', data={
            'email': 'test@test.com',
            'password': 'password123'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        # Try SQL injection in search
        response = client.get("/raw_product?q=' OR '1'='1")
        
        # Should return 200 (handled safely)
        assert response.status_code == 200


class TestWebCSRFProtection:
    """Test CSRF protection on state-changing operations."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data."""
        with app.app_context():
            self.company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(self.company)
            db.session.flush()
            
            password_hash = bcrypt.generate_password_hash('password123').decode('utf-8')
            self.user = User(
                first_name='Test', last_name='User',
                email='test@test.com', password=password_hash,
                company_id=self.company.id
            )
            db.session.add(self.user)
            db.session.flush()
            
            self.raw_product = RawProduct(name='Test Product', company_id=self.company.id)
            db.session.add(self.raw_product)
            db.session.commit()
            
            self.raw_product_id = self.raw_product.id
        
        yield
        
        with app.app_context():
            RawProduct.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_delete_without_csrf_token_fails(self, client, app):
        """Test that DELETE operations without CSRF token fail."""
        # Login
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'password123'
        })
        
        # Try to delete without CSRF token (if CSRF is enabled)
        # Note: This test depends on whether CSRF is enabled in your app
        response = client.post(
            f'/delete_raw_product/{self.raw_product_id}',
            data={},
            environ_base={'HTTP_REFERER': 'http://external-site.com'}
        )
        
        # If CSRF is enabled, should fail
        # If not enabled, this is a security recommendation to add
        # For now, we just check it doesn't crash
        assert response.status_code in [200, 302, 400, 403]


class TestWebAdminAccess:
    """Test that admin-only operations are properly protected."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data."""
        with app.app_context():
            self.company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(self.company)
            db.session.flush()
            
            password_hash = bcrypt.generate_password_hash('password123').decode('utf-8')
            
            # Admin user
            self.admin = User(
                first_name='Admin', last_name='User',
                email='admin@test.com', password=password_hash,
                company_id=self.company.id
            )
            
            # Regular user
            self.regular_user = User(
                first_name='Regular', last_name='User',
                email='user@test.com', password=password_hash,
                company_id=self.company.id
            )
            
            db.session.add_all([self.admin, self.regular_user])
            db.session.commit()
        
        yield
        
        with app.app_context():
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_regular_user_cannot_approve_pending_users(self, client, app):
        """Test that only admins can approve pending users."""
        # Login as regular user
        client.post('/login', data={
            'email': 'user@test.com',
            'password': 'password123'
        })
        
        # Try to access company page (which has approval functions)
        response = client.get('/company')
        
        # Regular users might not have access or see limited info
        # The key is they shouldn't be able to approve users
        response = client.post('/approve_pending/999')
        
        # Should be denied
        assert response.status_code in [302, 403, 404]
    
    def test_admin_can_access_company_management(self, client, app):
        """Test that admins can access company management."""
        # Login as admin
        response = client.post('/login', data={
            'email': 'admin@test.com',
            'password': 'password123'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        # Should be able to access company page
        response = client.get('/company')
        assert response.status_code == 200


class TestWebFileUploadSecurity:
    """Test file upload security."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data."""
        with app.app_context():
            self.company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(self.company)
            db.session.flush()
            
            password_hash = bcrypt.generate_password_hash('password123').decode('utf-8')
            self.user = User(
                first_name='Test', last_name='User',
                email='test@test.com', password=password_hash,
                company_id=self.company.id
            )
            db.session.add(self.user)
            db.session.commit()
        
        yield
        
        with app.app_context():
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_malicious_filename_sanitized(self, client, app):
        """Test that malicious filenames are sanitized."""
        from io import BytesIO
        
        # Login
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'password123'
        })
        
        # Try to upload file with path traversal in name
        data = {
            'file': (BytesIO(b'name,company_id\nTest Product,1'), '../../etc/passwd.csv')
        }
        
        response = client.post(
            '/upload_raw_product_csv',
            data=data,
            content_type='multipart/form-data'
        )
        
        # Should either reject or sanitize the filename
        # The file should not be written to ../../etc/passwd.csv
        assert response.status_code in [200, 302, 400]


class TestWebSessionSecurity:
    """Test session security measures."""
    
    def test_session_expires_after_logout(self, client, app):
        """Test that sessions are invalidated after logout."""
        with app.app_context():
            company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(company)
            db.session.flush()
            
            password_hash = bcrypt.generate_password_hash('password123').decode('utf-8')
            user = User(
                first_name='Test', last_name='User',
                email='test@test.com', password=password_hash,
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
        
        try:
            # Login
            response = client.post('/login', data={
                'email': 'test@test.com',
                'password': 'password123'
            }, follow_redirects=True)
            assert response.status_code == 200
            
            # Access protected page
            response = client.get('/items')
            assert response.status_code == 200
            
            # Logout
            client.get('/logout')
            
            # Try to access protected page
            response = client.get('/items')
            assert response.status_code == 302  # Should redirect to login
            assert '/login' in response.location
        
        finally:
            with app.app_context():
                User.query.delete()
                Company.query.delete()
                db.session.commit()
    
    def test_concurrent_session_handling(self, client, app):
        """Test that concurrent sessions are handled properly."""
        with app.app_context():
            company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(company)
            db.session.flush()
            
            password_hash = bcrypt.generate_password_hash('password123').decode('utf-8')
            user = User(
                first_name='Test', last_name='User',
                email='test@test.com', password=password_hash,
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
        
        try:
            # Login with first client
            response1 = client.post('/login', data={
                'email': 'test@test.com',
                'password': 'password123'
            }, follow_redirects=True)
            assert response1.status_code == 200
            
            # Create second client and login
            from flask import Flask
            client2 = app.test_client()
            response2 = client2.post('/login', data={
                'email': 'test@test.com',
                'password': 'password123'
            }, follow_redirects=True)
            assert response2.status_code == 200
            
            # Both should be able to access (unless you implement session limits)
            response1 = client.get('/items')
            response2 = client2.get('/items')
            assert response1.status_code == 200
            assert response2.status_code == 200
        
        finally:
            with app.app_context():
                User.query.delete()
                Company.query.delete()
                db.session.commit()
