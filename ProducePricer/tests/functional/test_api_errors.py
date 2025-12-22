import pytest
import json
import io
from producepricer import db
from producepricer.models import (
    Company, User, RawProduct, 
    BrandName, Seller, GrowerOrDistributor, ReceivingLog, ReceivingImage
)

class TestReceivingAPIErrors:
    
    @pytest.fixture
    def setup_companies(self, app):
        with app.app_context():
            # Company 1
            company1 = Company(name="Company 1", admin_email="admin1@co.com")
            db.session.add(company1)
            db.session.commit()
            
            user1 = User(first_name="User", last_name="One", email="user1@co.com", 
                        password="password", company_id=company1.id)
            db.session.add(user1)
            
            # Company 2
            company2 = Company(name="Company 2", admin_email="admin2@co.com")
            db.session.add(company2)
            db.session.commit()
            
            user2 = User(first_name="User", last_name="Two", email="user2@co.com", 
                        password="password", company_id=company2.id)
            db.session.add(user2)
            
            # Setup basic data for Company 1
            raw_product = RawProduct(name="Product 1", company_id=company1.id)
            db.session.add(raw_product)
            
            brand = BrandName(name="Brand 1", company_id=company1.id)
            db.session.add(brand)
            
            seller = Seller(name="Seller 1", company_id=company1.id)
            db.session.add(seller)
            
            grower = GrowerOrDistributor(name="Grower 1", company_id=company1.id, city="City", state="State")
            db.session.add(grower)
            
            db.session.commit()
            
            return {
                'c1': {'id': company1.id},
                'u1': {'email': 'user1@co.com', 'password': 'password'},
                'c2': {'id': company2.id},
                'u2': {'email': 'user2@co.com', 'password': 'password'},
                'data': {
                    'raw_product_id': raw_product.id,
                    'brand_name_id': brand.id,
                    'seller_id': seller.id,
                    'grower_or_distributor_id': grower.id
                }
            }

    def test_unauthorized_access(self, client):
        """Test accessing API without login"""
        response = client.get('/api/receiving_logs')
        assert response.status_code == 401

        response = client.post('/api/receiving_logs', json={})
        assert response.status_code == 401

    def test_cross_company_isolation(self, client, setup_companies, app):
        """Test that users can only see their own company's logs"""
        
        # Create log for Company 1
        with app.app_context():
            log = ReceivingLog(
                raw_product_id=setup_companies['data']['raw_product_id'],
                pack_size_unit="lbs",
                pack_size=50.0,
                brand_name_id=setup_companies['data']['brand_name_id'],
                quantity_received=100,
                seller_id=setup_companies['data']['seller_id'],
                temperature=34.5,
                hold_or_used="used",
                grower_or_distributor_id=setup_companies['data']['grower_or_distributor_id'],
                country_of_origin="USA",
                received_by="User One",
                company_id=setup_companies['c1']['id']
            )
            db.session.add(log)
            db.session.commit()
            log_id = log.id

        # Login as User 2 (Company 2)
        client.post('/login', data=setup_companies['u2'])
        
        # Should see empty list
        response = client.get('/api/receiving_logs')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) == 0
        
        # Try to upload image to Company 1's log
        data = {'images': (io.BytesIO(b"data"), 'test.jpg')}
        response = client.post(f'/api/receiving_logs/{log_id}/images', 
                             data=data,
                             content_type='multipart/form-data')
        assert response.status_code == 403

    def test_create_log_missing_fields(self, client, setup_companies):
        """Test creating log with missing required fields"""
        client.post('/login', data=setup_companies['u1'])
        
        payload = {
            'raw_product_id': setup_companies['data']['raw_product_id']
            # Missing other required fields
        }
        
        response = client.post('/api/receiving_logs', 
                             data=json.dumps(payload),
                             content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_upload_image_invalid_log(self, client, setup_companies):
        """Test uploading image to non-existent log"""
        client.post('/login', data=setup_companies['u1'])
        
        data = {'images': (io.BytesIO(b"data"), 'test.jpg')}
        response = client.post('/api/receiving_logs/99999/images', 
                             data=data,
                             content_type='multipart/form-data')
        
        assert response.status_code == 404

    def test_upload_no_images(self, client, setup_companies, app):
        """Test uploading without providing images"""
        client.post('/login', data=setup_companies['u1'])
        
        # Create log
        with app.app_context():
            log = ReceivingLog(
                raw_product_id=setup_companies['data']['raw_product_id'],
                pack_size_unit="lbs",
                pack_size=50.0,
                brand_name_id=setup_companies['data']['brand_name_id'],
                quantity_received=100,
                seller_id=setup_companies['data']['seller_id'],
                temperature=34.5,
                hold_or_used="used",
                grower_or_distributor_id=setup_companies['data']['grower_or_distributor_id'],
                country_of_origin="USA",
                received_by="User One",
                company_id=setup_companies['c1']['id']
            )
            db.session.add(log)
            db.session.commit()
            log_id = log.id

        response = client.post(f'/api/receiving_logs/{log_id}/images', 
                             data={},
                             content_type='multipart/form-data')
        
        assert response.status_code == 400
