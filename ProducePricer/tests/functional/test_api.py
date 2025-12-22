import pytest
import json
import io
from producepricer import db
from producepricer.models import (
    Company, User, RawProduct, 
    BrandName, Seller, GrowerOrDistributor, ReceivingLog, ReceivingImage
)

class TestReceivingAPI:
    
    @pytest.fixture
    def setup_data(self, app):
        with app.app_context():
            company = Company(name="Test Co", admin_email="test@co.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(first_name="Test", last_name="User", email="test@example.com", 
                        password="password", company_id=company.id)
            db.session.add(user)
            
            raw_product = RawProduct(name="Test Product", company_id=company.id)
            db.session.add(raw_product)
            
            brand = BrandName(name="Test Brand", company_id=company.id)
            db.session.add(brand)
            
            seller = Seller(name="Test Seller", company_id=company.id)
            db.session.add(seller)
            
            grower = GrowerOrDistributor(name="Test Grower", company_id=company.id, city="Test City", state="Test State")
            db.session.add(grower)
            
            db.session.commit()
            
            return {
                'company': {'id': company.id},
                'user': {'id': user.id},
                'raw_product': {'id': raw_product.id},
                'brand': {'id': brand.id},
                'seller': {'id': seller.id},
                'grower': {'id': grower.id}
            }

    def test_get_receiving_logs(self, client, setup_data, app):
        """Test GET /api/receiving_logs"""
        # Login
        client.post('/login', data={'email': 'test@example.com', 'password': 'password'})
        
        with app.app_context():
            # Create a log
            log = ReceivingLog(
                raw_product_id=setup_data['raw_product']['id'],
                pack_size_unit="lbs",
                pack_size=50.0,
                brand_name_id=setup_data['brand']['id'],
                quantity_received=100,
                seller_id=setup_data['seller']['id'],
                temperature=34.5,
                hold_or_used="used",
                grower_or_distributor_id=setup_data['grower']['id'],
                country_of_origin="USA",
                received_by="Test Employee",
                company_id=setup_data['company']['id']
            )
            db.session.add(log)
            db.session.commit()
            
            # Add an image
            image = ReceivingImage(
                filename="test.jpg",
                receiving_log_id=log.id,
                company_id=setup_data['company']['id']
            )
            db.session.add(image)
            db.session.commit()

        response = client.get('/api/receiving_logs')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert len(data) == 1
        assert data[0]['raw_product_name'] == "Test Product"
        assert len(data[0]['images']) == 1
        assert "test.jpg" in data[0]['images'][0]

    def test_create_receiving_log(self, client, setup_data):
        """Test POST /api/receiving_logs"""
        client.post('/login', data={'email': 'test@example.com', 'password': 'password'})
        
        payload = {
            'raw_product_id': setup_data['raw_product']['id'],
            'pack_size_unit': 'lbs',
            'pack_size': 50.0,
            'brand_name_id': setup_data['brand']['id'],
            'quantity_received': 100,
            'seller_id': setup_data['seller']['id'],
            'temperature': 34.5,
            'hold_or_used': 'used',
            'grower_or_distributor_id': setup_data['grower']['id'],
            'country_of_origin': 'USA',
            'received_by': 'Test Employee',
            'returned': 'No'
        }
        
        response = client.post('/api/receiving_logs', 
                             data=json.dumps(payload),
                             content_type='application/json')
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert 'id' in data
        assert data['message'] == 'Receiving log created successfully'

    def test_upload_receiving_images(self, client, setup_data, app):
        """Test POST /api/receiving_logs/<id>/images"""
        client.post('/login', data={'email': 'test@example.com', 'password': 'password'})
        
        # Create a log first
        with app.app_context():
            log = ReceivingLog(
                raw_product_id=setup_data['raw_product']['id'],
                pack_size_unit="lbs",
                pack_size=50.0,
                brand_name_id=setup_data['brand']['id'],
                quantity_received=100,
                seller_id=setup_data['seller']['id'],
                temperature=34.5,
                hold_or_used="used",
                grower_or_distributor_id=setup_data['grower']['id'],
                country_of_origin="USA",
                received_by="Test Employee",
                company_id=setup_data['company']['id']
            )
            db.session.add(log)
            db.session.commit()
            log_id = log.id

        # Prepare image file
        data = {
            'images': (io.BytesIO(b"fake image data"), 'test_image.jpg')
        }
        
        response = client.post(f'/api/receiving_logs/{log_id}/images', 
                             data=data,
                             content_type='multipart/form-data')
        
        assert response.status_code == 201
        response_data = json.loads(response.data)
        assert response_data['message'] == '1 images uploaded successfully'
        assert len(response_data['images']) == 1
        
        # Verify db record
        with app.app_context():
            images = ReceivingImage.query.filter_by(receiving_log_id=log_id).all()
            assert len(images) == 1
            assert "test_image.jpg" in images[0].filename

    def test_get_auxiliary_data(self, client, setup_data):
        """Test GET endpoints for auxiliary data"""
        client.post('/login', data={'email': 'test@example.com', 'password': 'password'})
        
        # Test raw products
        response = client.get('/api/raw_products')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) == 1
        assert data[0]['name'] == "Test Product"
        
        # Test brand names
        response = client.get('/api/brand_names')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) == 1
        assert data[0]['name'] == "Test Brand"
        
        # Test sellers
        response = client.get('/api/sellers')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) == 1
        assert data[0]['name'] == "Test Seller"
        
        # Test growers
        response = client.get('/api/growers_distributors')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) == 1
        assert data[0]['name'] == "Test Grower"
