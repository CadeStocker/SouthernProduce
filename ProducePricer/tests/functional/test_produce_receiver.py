"""
Comprehensive tests for Produce Receiver app features including:
- Brand Names management
- Sellers management
- Growers/Distributors management
- Receiving Logs display
"""
import pytest
from producepricer.models import (
    BrandName, 
    Seller, 
    GrowerOrDistributor, 
    ReceivingLog,
    RawProduct,
    ReceivingImage,
    Company,
    User
)
from datetime import datetime
from producepricer import db


@pytest.fixture
def auth_client(client, app):
    """Create an authenticated client with a company and user."""
    with app.app_context():
        # Create a company
        company = Company(name='Test Company', admin_email='admin@test.com')
        db.session.add(company)
        db.session.commit()
        
        # Create a user
        user = User(
            first_name='Test',
            last_name='User',
            email='test@test.com',
            password='password123',
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()
        
        # Store IDs for later use
        company_id = company.id
        user_id = user.id
    
    # Login (don't use 'with client' - client fixture already handles context)
    response = client.post('/login', data={
        'email': 'test@test.com',
        'password': 'password123'
    }, follow_redirects=True)
    assert response.status_code == 200
    
    yield client, company_id, user_id


class TestBrandNames:
    """Tests for Brand Name management."""
    
    def test_brand_names_page_loads(self, auth_client):
        """Test that the brand names page loads successfully."""
        client, company_id, user_id = auth_client
        
        response = client.get('/brand_names')
        assert response.status_code == 200
        assert b'Brand Names' in response.data
        assert b'Add New Brand Name' in response.data
    
    def test_add_brand_name(self, auth_client, app):
        """Test adding a new brand name."""
        client, company_id, user_id = auth_client
        
        response = client.post('/add_brand_name', data={
            'name': 'Test Brand'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Test Brand' in response.data
        assert b'successfully' in response.data
        
        # Verify in database
        with app.app_context():
            brand = BrandName.query.filter_by(name='Test Brand', company_id=company_id).first()
            assert brand is not None
            assert brand.name == 'Test Brand'
    
    def test_add_duplicate_brand_name_allowed(self, auth_client, app):
        """Test that duplicate brand names are allowed (no validation)."""
        client, company_id, user_id = auth_client
        
        # Add first brand
        client.post('/add_brand_name', data={'name': 'Duplicate Brand'})
        
        # Add duplicate
        response = client.post('/add_brand_name', data={
            'name': 'Duplicate Brand'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify both exist in database
        with app.app_context():
            brands = BrandName.query.filter_by(name='Duplicate Brand', company_id=company_id).all()
            assert len(brands) == 2
    
    def test_delete_brand_name(self, auth_client, app):
        """Test deleting a brand name."""
        client, company_id, user_id = auth_client
        
        # Create a brand
        with app.app_context():
            brand = BrandName(name='Delete Me', company_id=company_id)
            db.session.add(brand)
            db.session.commit()
            brand_id = brand.id
        
        # Delete it
        response = client.post(f'/delete_brand_name/{brand_id}', follow_redirects=True)
        assert response.status_code == 200
        assert b'deleted' in response.data
        
        # Verify deletion
        with app.app_context():
            brand = BrandName.query.get(brand_id)
            assert brand is None
    
    def test_search_brand_names(self, auth_client, app):
        """Test searching brand names."""
        client, company_id, user_id = auth_client
        
        # Create multiple brands
        with app.app_context():
            brands = [
                BrandName(name='Apple Brand', company_id=company_id),
                BrandName(name='Banana Brand', company_id=company_id),
                BrandName(name='Cherry Brand', company_id=company_id),
            ]
            for brand in brands:
                db.session.add(brand)
            db.session.commit()
        
        # Search for "Banana"
        response = client.get('/brand_names?q=Banana')
        assert response.status_code == 200
        assert b'Banana Brand' in response.data
        assert b'Apple Brand' not in response.data
        assert b'Cherry Brand' not in response.data
    
    def test_brand_names_pagination(self, auth_client, app):
        """Test pagination for brand names."""
        client, company_id, user_id = auth_client
        
        # Create 20 brands
        with app.app_context():
            for i in range(20):
                brand = BrandName(name=f'Brand {i:02d}', company_id=company_id)
                db.session.add(brand)
            db.session.commit()
        
        # Get first page
        response = client.get('/brand_names?paginate=1&page=1')
        assert response.status_code == 200
        assert b'Brand 00' in response.data
        
        # Get second page
        response = client.get('/brand_names?paginate=1&page=2')
        assert response.status_code == 200
        assert b'Brand 15' in response.data or b'Brand 16' in response.data


class TestSellers:
    """Tests for Seller management."""
    
    def test_sellers_page_loads(self, auth_client):
        """Test that the sellers page loads successfully."""
        client, company_id, user_id = auth_client
        
        response = client.get('/sellers')
        assert response.status_code == 200
        assert b'Sellers' in response.data
        assert b'Add New Seller' in response.data
    
    def test_add_seller(self, auth_client, app):
        """Test adding a new seller."""
        client, company_id, user_id = auth_client
        
        response = client.post('/add_seller', data={
            'name': 'Test Seller'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Test Seller' in response.data
        assert b'successfully' in response.data
        
        # Verify in database
        with app.app_context():
            seller = Seller.query.filter_by(name='Test Seller', company_id=company_id).first()
            assert seller is not None
            assert seller.name == 'Test Seller'
    
    def test_delete_seller(self, auth_client, app):
        """Test deleting a seller."""
        client, company_id, user_id = auth_client
        
        # Create a seller
        with app.app_context():
            seller = Seller(name='Delete Me', company_id=company_id)
            db.session.add(seller)
            db.session.commit()
            seller_id = seller.id
        
        # Delete it
        response = client.post(f'/delete_seller/{seller_id}', follow_redirects=True)
        assert response.status_code == 200
        assert b'deleted' in response.data
        
        # Verify deletion
        with app.app_context():
            seller = Seller.query.get(seller_id)
            assert seller is None
    
    def test_search_sellers(self, auth_client, app):
        """Test searching sellers."""
        client, company_id, user_id = auth_client
        
        # Create multiple sellers
        with app.app_context():
            sellers = [
                Seller(name='ABC Produce', company_id=company_id),
                Seller(name='XYZ Foods', company_id=company_id),
                Seller(name='ABC Foods', company_id=company_id),
            ]
            for seller in sellers:
                db.session.add(seller)
            db.session.commit()
        
        # Search for "ABC"
        response = client.get('/sellers?q=ABC')
        assert response.status_code == 200
        assert b'ABC Produce' in response.data
        assert b'ABC Foods' in response.data
        assert b'XYZ Foods' not in response.data


class TestGrowersDistributors:
    """Tests for Grower/Distributor management."""
    
    def test_growers_distributors_page_loads(self, auth_client):
        """Test that the growers/distributors page loads successfully."""
        client, company_id, user_id = auth_client
        
        response = client.get('/growers_distributors')
        assert response.status_code == 200
        assert b'Growers/Distributors' in response.data
        assert b'Add New Grower/Distributor' in response.data
    
    def test_add_grower_distributor(self, auth_client, app):
        """Test adding a new grower/distributor."""
        client, company_id, user_id = auth_client
        
        response = client.post('/add_grower_distributor', data={
            'name': 'Test Grower',
            'city': 'Los Angeles',
            'state': 'California'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Test Grower' in response.data
        assert b'Los Angeles' in response.data
        assert b'successfully' in response.data
        
        # Verify in database
        with app.app_context():
            grower = GrowerOrDistributor.query.filter_by(
                name='Test Grower', 
                company_id=company_id
            ).first()
            assert grower is not None
            assert grower.name == 'Test Grower'
            assert grower.city == 'Los Angeles'
            assert grower.state == 'California'
    
    def test_delete_grower_distributor(self, auth_client, app):
        """Test deleting a grower/distributor."""
        client, company_id, user_id = auth_client
        
        # Create a grower
        with app.app_context():
            grower = GrowerOrDistributor(
                name='Delete Me',
                city='Test City',
                state='Test State',
                company_id=company_id
            )
            db.session.add(grower)
            db.session.commit()
            grower_id = grower.id
        
        # Delete it
        response = client.post(f'/delete_grower_distributor/{grower_id}', follow_redirects=True)
        assert response.status_code == 200
        assert b'deleted' in response.data
        
        # Verify deletion
        with app.app_context():
            grower = GrowerOrDistributor.query.get(grower_id)
            assert grower is None
    
    def test_search_growers_distributors(self, auth_client, app):
        """Test searching growers/distributors by name, city, or state."""
        client, company_id, user_id = auth_client
        
        # Create multiple growers
        with app.app_context():
            growers = [
                GrowerOrDistributor(name='Farm A', city='Portland', state='Oregon', company_id=company_id),
                GrowerOrDistributor(name='Farm B', city='Seattle', state='Washington', company_id=company_id),
                GrowerOrDistributor(name='Farm C', city='Portland', state='Maine', company_id=company_id),
            ]
            for grower in growers:
                db.session.add(grower)
            db.session.commit()
        
        # Search by city "Portland"
        response = client.get('/growers_distributors?q=Portland')
        assert response.status_code == 200
        assert b'Farm A' in response.data
        assert b'Farm C' in response.data
        assert b'Farm B' not in response.data
        
        # Search by state "Washington"
        response = client.get('/growers_distributors?q=Washington')
        assert response.status_code == 200
        assert b'Farm B' in response.data
        assert b'Farm A' not in response.data


class TestReceivingLogs:
    """Tests for Receiving Logs display."""
    
    def test_receiving_logs_page_loads(self, auth_client):
        """Test that the receiving logs page loads successfully."""
        client, company_id, user_id = auth_client
        
        response = client.get('/receiving_logs')
        assert response.status_code == 200
        assert b'Receiving Logs' in response.data
    
    def test_display_receiving_logs(self, auth_client, app):
        """Test displaying receiving logs."""
        client, company_id, user_id = auth_client
        
        # Create necessary related data
        with app.app_context():
            raw_product = RawProduct(name='Test Product', company_id=company_id)
            brand = BrandName(name='Test Brand', company_id=company_id)
            seller = Seller(name='Test Seller', company_id=company_id)
            grower = GrowerOrDistributor(
                name='Test Grower',
                city='Test City',
                state='Test State',
                company_id=company_id
            )
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create receiving log
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit='lbs',
                pack_size=25.0,
                brand_name_id=brand.id,
                quantity_received=100,
                seller_id=seller.id,
                temperature=38.5,
                hold_or_used='used',
                grower_or_distributor_id=grower.id,
                country_of_origin='USA',
                received_by='John Doe',
                company_id=company_id,
                date_time=datetime(2026, 1, 8, 10, 30)
            )
            db.session.add(log)
            db.session.commit()
        
        # View receiving logs
        response = client.get('/receiving_logs')
        assert response.status_code == 200
        assert b'Test Product' in response.data
        assert b'Test Brand' in response.data
        assert b'Test Seller' in response.data
        assert b'Test Grower' in response.data
        assert b'100' in response.data
        assert b'38.5' in response.data
        assert b'USED' in response.data
        assert b'John Doe' in response.data
    
    def test_receiving_logs_search(self, auth_client, app):
        """Test searching receiving logs."""
        client, company_id, user_id = auth_client
        
        # Create test data
        with app.app_context():
            raw_product1 = RawProduct(name='Apples', company_id=company_id)
            raw_product2 = RawProduct(name='Bananas', company_id=company_id)
            brand = BrandName(name='Brand', company_id=company_id)
            seller = Seller(name='Seller', company_id=company_id)
            grower = GrowerOrDistributor(
                name='Grower',
                city='City',
                state='State',
                company_id=company_id
            )
            db.session.add_all([raw_product1, raw_product2, brand, seller, grower])
            db.session.commit()
            
            # Create logs
            log1 = ReceivingLog(
                raw_product_id=raw_product1.id,
                pack_size_unit='lbs',
                pack_size=25.0,
                brand_name_id=brand.id,
                quantity_received=50,
                seller_id=seller.id,
                temperature=38.0,
                hold_or_used='used',
                grower_or_distributor_id=grower.id,
                country_of_origin='USA',
                received_by='Alice',
                company_id=company_id
            )
            log2 = ReceivingLog(
                raw_product_id=raw_product2.id,
                pack_size_unit='lbs',
                pack_size=40.0,
                brand_name_id=brand.id,
                quantity_received=75,
                seller_id=seller.id,
                temperature=40.0,
                hold_or_used='hold',
                grower_or_distributor_id=grower.id,
                country_of_origin='Mexico',
                received_by='Bob',
                company_id=company_id
            )
            db.session.add_all([log1, log2])
            db.session.commit()
        
        # Search by raw product name
        response = client.get('/receiving_logs?q=Apples')
        assert response.status_code == 200
        assert b'Apples' in response.data
        assert b'Bananas' not in response.data
        
        # Search by received_by
        response = client.get('/receiving_logs?q=Bob')
        assert response.status_code == 200
        assert b'Bob' in response.data
        assert b'Alice' not in response.data
        
        # Search by country
        response = client.get('/receiving_logs?q=Mexico')
        assert response.status_code == 200
        assert b'Mexico' in response.data
        assert b'Bananas' in response.data
    
    def test_receiving_logs_pagination(self, auth_client, app):
        """Test pagination for receiving logs."""
        client, company_id, user_id = auth_client
        
        # Create test data
        with app.app_context():
            raw_product = RawProduct(name='Product', company_id=company_id)
            brand = BrandName(name='Brand', company_id=company_id)
            seller = Seller(name='Seller', company_id=company_id)
            grower = GrowerOrDistributor(
                name='Grower',
                city='City',
                state='State',
                company_id=company_id
            )
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create 20 logs
            for i in range(20):
                log = ReceivingLog(
                    raw_product_id=raw_product.id,
                    pack_size_unit='lbs',
                    pack_size=25.0,
                    brand_name_id=brand.id,
                    quantity_received=i,
                    seller_id=seller.id,
                    temperature=38.0,
                    hold_or_used='used',
                    grower_or_distributor_id=grower.id,
                    country_of_origin='USA',
                    received_by=f'Employee {i}',
                    company_id=company_id
                )
                db.session.add(log)
            db.session.commit()
        
        # Test pagination
        response = client.get('/receiving_logs?paginate=1&page=1')
        assert response.status_code == 200
        
        response = client.get('/receiving_logs?paginate=1&page=2')
        assert response.status_code == 200


class TestRawProductReceivingLogsIntegration:
    """Test integration of receiving logs with raw product detail page."""
    
    def test_raw_product_shows_receiving_logs(self, auth_client, app):
        """Test that raw product detail page shows associated receiving logs."""
        client, company_id, user_id = auth_client
        
        # Create test data
        with app.app_context():
            raw_product = RawProduct(name='Integration Test Product', company_id=company_id)
            brand = BrandName(name='Brand', company_id=company_id)
            seller = Seller(name='Seller', company_id=company_id)
            grower = GrowerOrDistributor(
                name='Grower',
                city='City',
                state='State',
                company_id=company_id
            )
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            raw_product_id = raw_product.id
            
            # Create receiving log
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit='lbs',
                pack_size=50.0,
                brand_name_id=brand.id,
                quantity_received=200,
                seller_id=seller.id,
                temperature=39.0,
                hold_or_used='hold',
                grower_or_distributor_id=grower.id,
                country_of_origin='Canada',
                received_by='Test Employee',
                company_id=company_id
            )
            db.session.add(log)
            db.session.commit()
        
        # View raw product page
        response = client.get(f'/raw_product/{raw_product_id}')
        assert response.status_code == 200
        assert b'Receiving Logs' in response.data
        assert b'200' in response.data  # quantity
        assert b'50.0' in response.data  # pack size
        assert b'39.0' in response.data  # temperature
        assert b'HOLD' in response.data
        assert b'Canada' in response.data
        assert b'Test Employee' in response.data


class TestCompanyIsolation:
    """Test that companies can only see their own data."""
    
    def test_brand_names_company_isolation(self, client, app):
        """Test that users only see brand names from their company."""
        # Create two companies with users
        with app.app_context():
            company1 = Company(name='Company 1', admin_email='admin1@test.com')
            company2 = Company(name='Company 2', admin_email='admin2@test.com')
            db.session.add_all([company1, company2])
            db.session.commit()
            
            user1 = User(
                first_name='User',
                last_name='One',
                email='user1@test.com',
                password='password',
                company_id=company1.id
            )
            user2 = User(
                first_name='User',
                last_name='Two',
                email='user2@test.com',
                password='password',
                company_id=company2.id
            )
            db.session.add_all([user1, user2])
            db.session.commit()
            
            # Create brands for each company
            brand1 = BrandName(name='Company 1 Brand', company_id=company1.id)
            brand2 = BrandName(name='Company 2 Brand', company_id=company2.id)
            db.session.add_all([brand1, brand2])
            db.session.commit()
        
        # Login as user1
        client.post('/login', data={
            'email': 'user1@test.com',
            'password': 'password'
        })
        
        # Check that user1 only sees their brand
        response = client.get('/brand_names')
        assert b'Company 1 Brand' in response.data
        assert b'Company 2 Brand' not in response.data
        
        # Logout and login as user2
        client.get('/logout')
        client.post('/login', data={
            'email': 'user2@test.com',
            'password': 'password'
        })
        
        # Check that user2 only sees their brand
        response = client.get('/brand_names')
        assert b'Company 2 Brand' in response.data
        assert b'Company 1 Brand' not in response.data


class TestNavigationLinks:
    """Test that navigation links to Produce Receiver pages work."""
    
    def test_produce_receiver_dropdown_exists(self, auth_client):
        """Test that Produce Receiver dropdown exists in navigation."""
        client, company_id, user_id = auth_client
        
        response = client.get('/home')
        assert response.status_code == 200
        assert b'Produce Receiver' in response.data
    
    def test_receiving_logs_link_works(self, auth_client):
        """Test that receiving logs link in nav works."""
        client, company_id, user_id = auth_client
        
        # Get home page to ensure we're logged in
        response = client.get('/home')
        assert b'Produce Receiver' in response.data
        
        # Follow link to receiving logs
        response = client.get('/receiving_logs')
        assert response.status_code == 200
        assert b'Receiving Logs' in response.data


class TestReceivingLogView:
    """Test individual receiving log view with print and email functionality."""
    
    def test_view_receiving_log_success(self, auth_client, app):
        """Test viewing a single receiving log."""
        client, company_id, user_id = auth_client
        
        with app.app_context():
            # Create necessary entities
            raw_product = RawProduct(name='Test Product', company_id=company_id)
            brand = BrandName(name='Test Brand', company_id=company_id)
            seller = Seller(name='Test Seller', company_id=company_id)
            grower = GrowerOrDistributor(name='Test Grower', company_id=company_id, city='Test City', state='CA')
            
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create receiving log
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit='lbs',
                pack_size=50.0,
                brand_name_id=brand.id,
                quantity_received=100,
                seller_id=seller.id,
                temperature=34.5,
                hold_or_used='used',
                grower_or_distributor_id=grower.id,
                country_of_origin='USA',
                received_by='Test Employee',
                company_id=company_id
            )
            db.session.add(log)
            db.session.commit()
            log_id = log.id
        
        # View the log
        response = client.get(f'/receiving_log/{log_id}')
        assert response.status_code == 200
        assert b'Receiving Log Details' in response.data
        assert b'Test Product' in response.data
        assert b'Test Brand' in response.data
        assert b'Test Seller' in response.data
        assert b'Test Grower' in response.data
        assert b'34.5' in response.data  # Temperature
        assert b'USA' in response.data
        assert b'Test Employee' in response.data
        assert b'Download PDF' in response.data
        assert b'Email' in response.data
    
    def test_view_receiving_log_with_images(self, auth_client, app):
        """Test viewing a receiving log that has images."""
        client, company_id, user_id = auth_client
        
        with app.app_context():
            # Create necessary entities
            raw_product = RawProduct(name='Test Product with Images', company_id=company_id)
            brand = BrandName(name='Test Brand', company_id=company_id)
            seller = Seller(name='Test Seller', company_id=company_id)
            grower = GrowerOrDistributor(name='Test Grower', company_id=company_id, city='Test City', state='CA')
            
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create receiving log
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit='count',
                pack_size=24.0,
                brand_name_id=brand.id,
                quantity_received=50,
                seller_id=seller.id,
                temperature=32.0,
                hold_or_used='hold',
                grower_or_distributor_id=grower.id,
                country_of_origin='Mexico',
                received_by='Another Employee',
                company_id=company_id
            )
            db.session.add(log)
            db.session.commit()
            
            # Add images
            image1 = ReceivingImage(filename='test_image1.jpg', receiving_log_id=log.id, company_id=company_id)
            image2 = ReceivingImage(filename='test_image2.jpg', receiving_log_id=log.id, company_id=company_id)
            db.session.add_all([image1, image2])
            db.session.commit()
            log_id = log.id
        
        # View the log
        response = client.get(f'/receiving_log/{log_id}')
        assert response.status_code == 200
        assert b'Product Images (2)' in response.data
        assert b'test_image1.jpg' in response.data
        assert b'test_image2.jpg' in response.data
    
    def test_view_receiving_log_not_found(self, auth_client, app):
        """Test viewing a non-existent receiving log returns 404."""
        client, company_id, user_id = auth_client
        
        response = client.get('/receiving_log/99999')
        assert response.status_code == 404
    
    def test_view_receiving_log_wrong_company(self, auth_client, app):
        """Test that users cannot view logs from other companies."""
        client, company_id, user_id = auth_client
        
        with app.app_context():
            # Create another company
            other_company = Company(name='Other Company', admin_email='other@test.com')
            db.session.add(other_company)
            db.session.commit()
            
            # Create entities for the other company
            raw_product = RawProduct(name='Other Product', company_id=other_company.id)
            brand = BrandName(name='Other Brand', company_id=other_company.id)
            seller = Seller(name='Other Seller', company_id=other_company.id)
            grower = GrowerOrDistributor(name='Other Grower', company_id=other_company.id, city='City', state='ST')
            
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create log for other company
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit='lbs',
                pack_size=50.0,
                brand_name_id=brand.id,
                quantity_received=100,
                seller_id=seller.id,
                temperature=34.5,
                hold_or_used='used',
                grower_or_distributor_id=grower.id,
                country_of_origin='USA',
                received_by='Other Employee',
                company_id=other_company.id
            )
            db.session.add(log)
            db.session.commit()
            log_id = log.id
        
        # Try to view the other company's log
        response = client.get(f'/receiving_log/{log_id}')
        assert response.status_code == 404
    
    def test_receiving_logs_table_has_view_details_link(self, auth_client, app):
        """Test that receiving logs table has a 'View Details' button."""
        client, company_id, user_id = auth_client
        
        with app.app_context():
            # Create necessary entities
            raw_product = RawProduct(name='Link Test Product', company_id=company_id)
            brand = BrandName(name='Link Test Brand', company_id=company_id)
            seller = Seller(name='Link Test Seller', company_id=company_id)
            grower = GrowerOrDistributor(name='Link Test Grower', company_id=company_id, city='Test City', state='CA')
            
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create receiving log
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit='lbs',
                pack_size=50.0,
                brand_name_id=brand.id,
                quantity_received=100,
                seller_id=seller.id,
                temperature=34.5,
                hold_or_used='used',
                grower_or_distributor_id=grower.id,
                country_of_origin='USA',
                received_by='Test Employee',
                company_id=company_id
            )
            db.session.add(log)
            db.session.commit()
            log_id = log.id
        
        # View receiving logs page
        response = client.get('/receiving_logs')
        assert response.status_code == 200
        assert b'View Details' in response.data
        assert f'/receiving_log/{log_id}'.encode() in response.data
    
    def test_email_receiving_log_missing_recipient(self, auth_client, app):
        """Test that emailing without a recipient shows an error."""
        client, company_id, user_id = auth_client
        
        with app.app_context():
            # Create necessary entities
            raw_product = RawProduct(name='Email Test Product', company_id=company_id)
            brand = BrandName(name='Email Test Brand', company_id=company_id)
            seller = Seller(name='Email Test Seller', company_id=company_id)
            grower = GrowerOrDistributor(name='Email Test Grower', company_id=company_id, city='Test City', state='CA')
            
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create receiving log
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit='lbs',
                pack_size=50.0,
                brand_name_id=brand.id,
                quantity_received=100,
                seller_id=seller.id,
                temperature=34.5,
                hold_or_used='used',
                grower_or_distributor_id=grower.id,
                country_of_origin='USA',
                received_by='Test Employee',
                company_id=company_id
            )
            db.session.add(log)
            db.session.commit()
            log_id = log.id
        
        # Try to email without recipient
        response = client.post(f'/email_receiving_log/{log_id}', data={
            'recipient': '',
            'subject': 'Test Subject',
            'message': 'Test message'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Recipient email address is required' in response.data

    def test_download_receiving_log_pdf(self, auth_client, app):
        """Test downloading a receiving log as PDF."""
        client, company_id, user_id = auth_client
        
        with app.app_context():
            # Create necessary entities
            raw_product = RawProduct(name='PDF Test Product', company_id=company_id)
            brand = BrandName(name='PDF Test Brand', company_id=company_id)
            seller = Seller(name='PDF Test Seller', company_id=company_id)
            grower = GrowerOrDistributor(name='PDF Test Grower', company_id=company_id, city='Test City', state='CA')
            
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create receiving log
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit='lbs',
                pack_size=50.0,
                brand_name_id=brand.id,
                quantity_received=100,
                seller_id=seller.id,
                temperature=34.5,
                hold_or_used='used',
                grower_or_distributor_id=grower.id,
                country_of_origin='USA',
                received_by='Test Employee',
                company_id=company_id
            )
            db.session.add(log)
            db.session.commit()
            log_id = log.id
        
        # Download PDF
        response = client.get(f'/receiving_log/{log_id}/pdf')
        assert response.status_code == 200
        assert response.headers['Content-Type'] == 'application/pdf'
        assert 'attachment' in response.headers['Content-Disposition']
        assert 'receiving_log_' in response.headers['Content-Disposition']
        assert '.pdf' in response.headers['Content-Disposition']
        # Check that we got actual PDF content
        assert response.data.startswith(b'%PDF')


