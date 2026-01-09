"""
Tests for item inventory API endpoints.
Tests authentication, data isolation, input validation, and inventory counting functionality.
"""

import pytest
import json
from datetime import datetime, timedelta
from producepricer.models import (
    Company, User, APIKey, Item, ItemInventory, Packaging,
    UnitOfWeight, ItemDesignation
)
from producepricer import db


class TestGetItems:
    """Test GET /api/items endpoint for retrieving items for inventory."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data."""
        with app.app_context():
            # Create companies
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
                key='inventory_test_key_company1',
                device_name='iPad 1',
                company_id=self.company1.id,
                created_by_user_id=self.user1.id
            )
            self.api_key2 = APIKey(
                key='inventory_test_key_company2',
                device_name='iPad 2',
                company_id=self.company2.id,
                created_by_user_id=self.user2.id
            )
            db.session.add_all([self.api_key1, self.api_key2])
            db.session.flush()
            
            # Create packaging
            self.packaging1 = Packaging(packaging_type='Box', company_id=self.company1.id)
            self.packaging2 = Packaging(packaging_type='Bag', company_id=self.company2.id)
            db.session.add_all([self.packaging1, self.packaging2])
            db.session.flush()
            
            # Create items for company 1
            self.item1 = Item(
                name='Apples - Sliced',
                code='APL001',
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=self.packaging1.id,
                company_id=self.company1.id,
                case_weight=25.0,
                item_designation=ItemDesignation.RETAIL
            )
            self.item2 = Item(
                name='Carrots - Diced',
                code='CAR001',
                alternate_code='CAR-ALT',
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=self.packaging1.id,
                company_id=self.company1.id,
                case_weight=30.0,
                item_designation=ItemDesignation.FOODSERVICE
            )
            
            # Create items for company 2
            self.item3 = Item(
                name='Bananas',
                code='BAN001',
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=self.packaging2.id,
                company_id=self.company2.id,
                case_weight=40.0
            )
            db.session.add_all([self.item1, self.item2, self.item3])
            db.session.flush()
            
            # Add inventory count to item1
            self.count1 = ItemInventory(
                item_id=self.item1.id,
                quantity=50,
                company_id=self.company1.id,
                counted_by='John Doe',
                count_date=datetime.utcnow() - timedelta(days=1)
            )
            db.session.add(self.count1)
            db.session.commit()
            
            # Store IDs
            self.api_key1_value = self.api_key1.key
            self.api_key2_value = self.api_key2.key
            self.item1_id = self.item1.id
            self.item2_id = self.item2.id
            self.item3_id = self.item3.id
        
        yield
        
        with app.app_context():
            # Cleanup
            ItemInventory.query.delete()
            Item.query.delete()
            Packaging.query.delete()
            APIKey.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_get_items_requires_authentication(self, client):
        """Test that GET /api/items requires authentication."""
        response = client.get('/api/items')
        assert response.status_code == 401
    
    def test_get_items_returns_company_items(self, client):
        """Test that GET /api/items returns only company's items."""
        response = client.get(
            '/api/items',
            headers={'X-API-Key': self.api_key1_value}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Should return 2 items for company 1
        assert len(data) == 2
        
        # Check item details
        item_names = [item['name'] for item in data]
        assert 'Apples - Sliced' in item_names
        assert 'Carrots - Diced' in item_names
        assert 'Bananas' not in item_names  # Company 2's item
    
    def test_get_items_includes_last_count(self, client):
        """Test that items include their last inventory count."""
        response = client.get(
            '/api/items',
            headers={'X-API-Key': self.api_key1_value}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Find the apple item
        apple_item = next(item for item in data if item['name'] == 'Apples - Sliced')
        
        # Should have last_count data
        assert apple_item['last_count'] is not None
        assert apple_item['last_count']['quantity'] == 50
        assert apple_item['last_count']['counted_by'] == 'John Doe'
    
    def test_get_items_company_isolation(self, client):
        """Test that companies only see their own items."""
        # Company 2 should only see their item
        response = client.get(
            '/api/items',
            headers={'X-API-Key': self.api_key2_value}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert len(data) == 1
        assert data[0]['name'] == 'Bananas'
        assert data[0]['id'] == self.item3_id


class TestCreateInventoryCount:
    """Test POST /api/inventory_counts endpoint for recording inventory counts."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data."""
        with app.app_context():
            # Create company
            self.company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(self.company)
            db.session.flush()
            
            # Create user
            self.user = User(
                first_name='Test', last_name='User',
                email='test@test.com', password='hashed',
                company_id=self.company.id
            )
            db.session.add(self.user)
            db.session.flush()
            
            # Create API key
            self.api_key = APIKey(
                key='inventory_create_test_key',
                device_name='Test iPad',
                company_id=self.company.id,
                created_by_user_id=self.user.id
            )
            db.session.add(self.api_key)
            db.session.flush()
            
            # Create packaging and item
            self.packaging = Packaging(packaging_type='Box', company_id=self.company.id)
            db.session.add(self.packaging)
            db.session.flush()
            
            self.item = Item(
                name='Test Item',
                code='TEST001',
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=self.packaging.id,
                company_id=self.company.id,
                case_weight=25.0
            )
            db.session.add(self.item)
            db.session.commit()
            
            # Store IDs
            self.api_key_value = self.api_key.key
            self.item_id = self.item.id
            self.company_id = self.company.id
        
        yield
        
        with app.app_context():
            # Cleanup
            ItemInventory.query.delete()
            Item.query.delete()
            Packaging.query.delete()
            APIKey.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_create_inventory_count_requires_authentication(self, client):
        """Test that POST /api/inventory_counts requires authentication."""
        response = client.post(
            '/api/inventory_counts',
            data=json.dumps({'item_id': 1, 'quantity': 50}),
            content_type='application/json'
        )
        assert response.status_code == 401
    
    def test_create_inventory_count_success(self, client, app):
        """Test successful inventory count creation."""
        count_data = {
            'item_id': self.item_id,
            'quantity': 75,
            'counted_by': 'Jane Smith',
            'notes': 'Regular weekly count'
        }
        
        response = client.post(
            '/api/inventory_counts',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps(count_data),
            content_type='application/json'
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        
        assert data['success'] is True
        assert data['inventory_count']['quantity'] == 75
        assert data['inventory_count']['counted_by'] == 'Jane Smith'
        assert data['inventory_count']['notes'] == 'Regular weekly count'
        assert data['inventory_count']['item_name'] == 'Test Item'
        
        # Verify it was saved to database
        with app.app_context():
            count = ItemInventory.query.filter_by(item_id=self.item_id).first()
            assert count is not None
            assert count.quantity == 75
    
    def test_create_inventory_count_missing_item_id(self, client):
        """Test that item_id is required."""
        count_data = {'quantity': 50}
        
        response = client.post(
            '/api/inventory_counts',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps(count_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'item_id' in data['error']
    
    def test_create_inventory_count_missing_quantity(self, client):
        """Test that quantity is required."""
        count_data = {'item_id': self.item_id}
        
        response = client.post(
            '/api/inventory_counts',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps(count_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'quantity' in data['error']
    
    def test_create_inventory_count_invalid_item_id(self, client):
        """Test that non-existent item ID is rejected."""
        count_data = {
            'item_id': 99999,  # Non-existent
            'quantity': 50
        }
        
        response = client.post(
            '/api/inventory_counts',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps(count_data),
            content_type='application/json'
        )
        
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'not found' in data['error'].lower()
    
    def test_create_inventory_count_negative_quantity(self, client):
        """Test that negative quantities are rejected."""
        count_data = {
            'item_id': self.item_id,
            'quantity': -10
        }
        
        response = client.post(
            '/api/inventory_counts',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps(count_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'non-negative' in data['error']
    
    def test_create_inventory_count_with_custom_date(self, client, app):
        """Test creating count with custom date."""
        custom_date = datetime(2026, 1, 5, 14, 30, 0)
        count_data = {
            'item_id': self.item_id,
            'quantity': 100,
            'count_date': custom_date.isoformat()
        }
        
        response = client.post(
            '/api/inventory_counts',
            headers={'X-API-Key': self.api_key_value},
            data=json.dumps(count_data),
            content_type='application/json'
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        
        # Check date was set correctly
        returned_date = datetime.fromisoformat(data['inventory_count']['count_date'].replace('Z', '+00:00'))
        assert returned_date.date() == custom_date.date()
    
    def test_create_inventory_count_malformed_json(self, client):
        """Test that malformed JSON is rejected."""
        response = client.post(
            '/api/inventory_counts',
            headers={'X-API-Key': self.api_key_value},
            data='{"item_id": "invalid json',
            content_type='application/json'
        )
        
        assert response.status_code == 400
    
    def test_create_inventory_count_company_isolation(self, client, app):
        """Test that users cannot create counts for other company's items."""
        # Store IDs before closing context
        with app.app_context():
            # Create another company and item
            company2 = Company(name='Other Company', admin_email='other@test.com')
            db.session.add(company2)
            db.session.flush()
            
            company2_id = company2.id
            
            packaging2 = Packaging(packaging_type='Bag', company_id=company2_id)
            db.session.add(packaging2)
            db.session.flush()
            
            packaging2_id = packaging2.id
            
            item2 = Item(
                name='Other Item',
                code='OTHER001',
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging2_id,
                company_id=company2_id,
                case_weight=20.0
            )
            db.session.add(item2)
            db.session.commit()
            item2_id = item2.id
        
        try:
            # Try to create count for other company's item
            count_data = {
                'item_id': item2_id,
                'quantity': 50
            }
            
            response = client.post(
                '/api/inventory_counts',
                headers={'X-API-Key': self.api_key_value},
                data=json.dumps(count_data),
                content_type='application/json'
            )
            
            assert response.status_code == 404  # Should not be found
        finally:
            with app.app_context():
                Item.query.filter_by(id=item2_id).delete()
                Packaging.query.filter_by(id=packaging2_id).delete()
                Company.query.filter_by(id=company2_id).delete()
                db.session.commit()


class TestGetInventoryCounts:
    """Test GET /api/inventory_counts endpoint for retrieving count history."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Create test data."""
        with app.app_context():
            # Create company
            self.company = Company(name='Test Company', admin_email='admin@test.com')
            db.session.add(self.company)
            db.session.flush()
            
            # Create user
            self.user = User(
                first_name='Test', last_name='User',
                email='test@test.com', password='hashed',
                company_id=self.company.id
            )
            db.session.add(self.user)
            db.session.flush()
            
            # Create API key
            self.api_key = APIKey(
                key='inventory_get_test_key',
                device_name='Test iPad',
                company_id=self.company.id,
                created_by_user_id=self.user.id
            )
            db.session.add(self.api_key)
            db.session.flush()
            
            # Create packaging and items
            self.packaging = Packaging(packaging_type='Box', company_id=self.company.id)
            db.session.add(self.packaging)
            db.session.flush()
            
            self.item1 = Item(
                name='Item 1',
                code='ITEM001',
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=self.packaging.id,
                company_id=self.company.id,
                case_weight=25.0
            )
            self.item2 = Item(
                name='Item 2',
                code='ITEM002',
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=self.packaging.id,
                company_id=self.company.id,
                case_weight=30.0
            )
            db.session.add_all([self.item1, self.item2])
            db.session.flush()
            
            # Create multiple inventory counts
            now = datetime.utcnow()
            self.count1 = ItemInventory(
                item_id=self.item1.id,
                quantity=50,
                company_id=self.company.id,
                counted_by='John',
                count_date=now - timedelta(days=2)
            )
            self.count2 = ItemInventory(
                item_id=self.item1.id,
                quantity=45,
                company_id=self.company.id,
                counted_by='Jane',
                count_date=now - timedelta(days=1)
            )
            self.count3 = ItemInventory(
                item_id=self.item2.id,
                quantity=100,
                company_id=self.company.id,
                counted_by='Bob',
                count_date=now
            )
            db.session.add_all([self.count1, self.count2, self.count3])
            db.session.commit()
            
            # Store IDs
            self.api_key_value = self.api_key.key
            self.item1_id = self.item1.id
            self.item2_id = self.item2.id
        
        yield
        
        with app.app_context():
            # Cleanup
            ItemInventory.query.delete()
            Item.query.delete()
            Packaging.query.delete()
            APIKey.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_get_inventory_counts_requires_authentication(self, client):
        """Test that GET /api/inventory_counts requires authentication."""
        response = client.get('/api/inventory_counts')
        assert response.status_code == 401
    
    def test_get_inventory_counts_returns_all(self, client):
        """Test that GET /api/inventory_counts returns all counts."""
        response = client.get(
            '/api/inventory_counts',
            headers={'X-API-Key': self.api_key_value}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Should return 3 counts
        assert len(data) == 3
        
        # Check they're ordered by date descending
        dates = [datetime.fromisoformat(c['count_date'].replace('Z', '+00:00')) for c in data]
        assert dates == sorted(dates, reverse=True)
    
    def test_get_inventory_counts_filter_by_item(self, client):
        """Test filtering counts by item_id."""
        response = client.get(
            f'/api/inventory_counts?item_id={self.item1_id}',
            headers={'X-API-Key': self.api_key_value}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Should only return counts for item1
        assert len(data) == 2
        assert all(c['item_id'] == self.item1_id for c in data)
    
    def test_get_inventory_counts_filter_by_date_range(self, client):
        """Test filtering counts by date range."""
        now = datetime.utcnow()
        start_date = (now - timedelta(days=1, hours=12)).isoformat()
        
        response = client.get(
            f'/api/inventory_counts?start_date={start_date}',
            headers={'X-API-Key': self.api_key_value}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Should return only recent counts (last 2)
        assert len(data) == 2
    
    def test_get_inventory_counts_limit(self, client):
        """Test limit parameter."""
        response = client.get(
            '/api/inventory_counts?limit=1',
            headers={'X-API-Key': self.api_key_value}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Should only return 1 count
        assert len(data) == 1
    
    def test_get_inventory_counts_includes_item_details(self, client):
        """Test that counts include item details."""
        response = client.get(
            '/api/inventory_counts',
            headers={'X-API-Key': self.api_key_value}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Check first count has item details
        count = data[0]
        assert 'item_name' in count
        assert 'item_code' in count
        assert count['item_name'] in ['Item 1', 'Item 2']
