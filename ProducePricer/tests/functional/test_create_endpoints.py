"""
Functional tests for API reference data creation endpoints.
Tests POST endpoints for creating raw products, brands, sellers, and growers.
"""

import pytest
from producepricer.models import RawProduct, BrandName, Seller, GrowerOrDistributor, APIKey, Company, User, db
from flask import json


@pytest.fixture
def setup_company_and_user(app):
    """Create a company and user for testing."""
    with app.app_context():
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
        
        return {
            'company_id': company.id,
            'user_id': user.id
        }


class TestCreateRawProducts:
    """Test POST /api/raw_products endpoint."""
    
    def test_create_raw_product_with_api_key(self, client, app, setup_company_and_user):
        """Test creating a raw product with valid API key."""
        # Create API key in app context
        with app.app_context():
            api_key = APIKey(
                key='test-key-raw-product-001',
                device_name='Test Device',
                company_id=setup_company_and_user['company_id'],
                created_by_user_id=setup_company_and_user['user_id']
            )
            db.session.add(api_key)
            db.session.commit()
        
        # Make request outside app context
        response = client.post(
            '/api/raw_products',
            json={'name': 'Test Apples'},
            headers={'X-API-Key': 'test-key-raw-product-001'}
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['message'] == 'Raw product created successfully'
        assert 'id' in data
        assert data['name'] == 'Test Apples'
    
    def test_create_raw_product_duplicate(self, client, app, setup_company_and_user):
        """Test creating a duplicate raw product returns 409."""
        with app.app_context():
            api_key = APIKey(
                key='test-key-raw-product-002',
                device_name='Test Device',
                company_id=setup_company_and_user['company_id'],
                created_by_user_id=setup_company_and_user['user_id']
            )
            db.session.add(api_key)
            
            product = RawProduct(name='Duplicate Product', company_id=setup_company_and_user['company_id'])
            db.session.add(product)
            db.session.commit()
        
        # Make request outside app context
        response = client.post(
            '/api/raw_products',
            json={'name': 'Duplicate Product'},
            headers={'X-API-Key': 'test-key-raw-product-002'}
        )
        
        assert response.status_code == 409
        data = json.loads(response.data)
        assert 'already exists' in data['error']
    
    def test_create_raw_product_empty_name(self, client, app, setup_company_and_user):
        """Test creating a raw product with empty name returns 400."""
        with app.app_context():
            api_key = APIKey(
                key='test-key-raw-product-003',
                device_name='Test Device',
                company_id=setup_company_and_user['company_id'],
                created_by_user_id=setup_company_and_user['user_id']
            )
            db.session.add(api_key)
            db.session.commit()
        
        response = client.post(
            '/api/raw_products',
            json={'name': '   '},
            headers={'X-API-Key': 'test-key-raw-product-003'}
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'cannot be empty' in data['error']


class TestCreateBrandNames:
    """Test POST /api/brand_names endpoint."""
    
    def test_create_brand_with_api_key(self, client, app, setup_company_and_user):
        """Test creating a brand name with valid API key."""
        with app.app_context():
            api_key = APIKey(
                key='test-key-brand-001',
                device_name='Test Device',
                company_id=setup_company_and_user['company_id'],
                created_by_user_id=setup_company_and_user['user_id']
            )
            db.session.add(api_key)
            db.session.commit()
        
        response = client.post(
            '/api/brand_names',
            json={'name': 'Test Brand Co'},
            headers={'X-API-Key': 'test-key-brand-001'}
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['message'] == 'Brand name created successfully'
        assert 'id' in data


class TestCreateSellers:
    """Test POST /api/sellers endpoint."""
    
    def test_create_seller_with_api_key(self, client, app, setup_company_and_user):
        """Test creating a seller with valid API key."""
        with app.app_context():
            api_key = APIKey(
                key='test-key-seller-001',
                device_name='Test Device',
                company_id=setup_company_and_user['company_id'],
                created_by_user_id=setup_company_and_user['user_id']
            )
            db.session.add(api_key)
            db.session.commit()
        
        response = client.post(
            '/api/sellers',
            json={'name': 'Test Seller Inc'},
            headers={'X-API-Key': 'test-key-seller-001'}
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['message'] == 'Seller created successfully'


class TestCreateGrowersDistributors:
    """Test POST /api/growers_distributors endpoint."""
    
    def test_create_grower_with_api_key(self, client, app, setup_company_and_user):
        """Test creating a grower/distributor with valid API key."""
        with app.app_context():
            api_key = APIKey(
                key='test-key-grower-001',
                device_name='Test Device',
                company_id=setup_company_and_user['company_id'],
                created_by_user_id=setup_company_and_user['user_id']
            )
            db.session.add(api_key)
            db.session.commit()
        
        response = client.post(
            '/api/growers_distributors',
            json={
                'name': 'Test Grower Farm',
                'city': 'Salinas',
                'state': 'CA'
            },
            headers={'X-API-Key': 'test-key-grower-001'}
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['message'] == 'Grower/distributor created successfully'
        assert data['city'] == 'Salinas'
    
    def test_create_grower_missing_city(self, client, app, setup_company_and_user):
        """Test creating a grower without city returns 400."""
        with app.app_context():
            api_key = APIKey(
                key='test-key-grower-002',
                device_name='Test Device',
                company_id=setup_company_and_user['company_id'],
                created_by_user_id=setup_company_and_user['user_id']
            )
            db.session.add(api_key)
            db.session.commit()
        
        response = client.post(
            '/api/growers_distributors',
            json={
                'name': 'Test Grower',
                'state': 'CA'
            },
            headers={'X-API-Key': 'test-key-grower-002'}
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'city' in data['error'].lower()
