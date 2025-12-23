import pytest
import io
import os
import datetime
from flask import url_for
from producepricer import db
from producepricer.models import Item, ItemInfo, LaborCost, Packaging, RawProduct, ItemDesignation, UnitOfWeight

class TestItemUpload:
    
    @pytest.fixture(autouse=True)
    def setup_labor_cost(self, app, logged_in_user):
        """Ensure a labor cost exists for the user."""
        with app.app_context():
            lc = LaborCost(
                labor_cost=15.0,
                date=datetime.date.today(),
                company_id=logged_in_user.company_id
            )
            db.session.add(lc)
            db.session.commit()

    def test_upload_item_csv_success(self, client, app, logged_in_user, tmp_path):
        """Test successfully uploading an item CSV."""
        # Configure upload folder
        app.config['UPLOAD_FOLDER'] = str(tmp_path)
        
        csv_content = (
            "name,item_code,alternate_code,raw_product,ranch,item_designation,packaging_type,yield,case_weight,labor\n"
            "Test Item 1,TI1,ALT1,Raw1,yes,FOODSERVICE,Box1,0.85,10.0,0.5\n"
            "Test Item 2,TI2,,Raw2,no,RETAIL,Box2,0.90,5.0,0.2"
        )
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'items.csv')
        }
        
        with app.app_context():
            url = url_for('main.upload_item_csv')
            
        response = client.post(url, data=data, content_type='multipart/form-data', follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Items imported successfully!' in response.data
        
        with app.app_context():
            # Check Item 1
            item1 = Item.query.filter_by(name='Test Item 1').first()
            assert item1 is not None
            assert item1.code == 'TI1'
            assert item1.alternate_code == 'ALT1'
            assert item1.ranch is True
            assert item1.item_designation == ItemDesignation.FOODSERVICE
            assert item1.case_weight == 10.0
            
            # Check Packaging
            pack1 = Packaging.query.get(item1.packaging_id)
            assert pack1.packaging_type == 'BOX1' # It gets upper-cased
            
            # Check Raw Product
            assert len(item1.raw_products) == 1
            assert item1.raw_products[0].name == 'Raw1'
            
            # Check ItemInfo
            info1 = ItemInfo.query.filter_by(item_id=item1.id).first()
            assert info1 is not None
            assert info1.product_yield == 0.85
            assert info1.labor_hours == 0.5

            # Check Item 2
            item2 = Item.query.filter_by(name='Test Item 2').first()
            assert item2 is not None
            assert item2.code == 'TI2'
            assert item2.alternate_code is None # Route logic results in None for empty CSV values
            assert item2.ranch is False
            assert item2.item_designation == ItemDesignation.RETAIL
            
            # Check Packaging
            pack2 = Packaging.query.get(item2.packaging_id)
            assert pack2.packaging_type == 'BOX2'

    def test_upload_item_csv_missing_columns(self, client, app, logged_in_user, tmp_path):
        """Test uploading CSV with missing columns."""
        app.config['UPLOAD_FOLDER'] = str(tmp_path)
        
        csv_content = "name,item_code\nTest Item 1,TI1"
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'items.csv')
        }
        
        with app.app_context():
            url = url_for('main.upload_item_csv')
            
        response = client.post(url, data=data, content_type='multipart/form-data', follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Invalid CSV format. Missing columns' in response.data

    def test_upload_item_csv_no_labor_cost(self, client, app, logged_in_user):
        """Test uploading when no labor cost exists."""
        # Remove the labor cost created by the fixture
        with app.app_context():
            LaborCost.query.delete()
            db.session.commit()
            
            url = url_for('main.upload_item_csv')
            
        # GET request should redirect
        response = client.get(url, follow_redirects=True)
        assert b'Please add a labor cost before uploading items.' in response.data

    def test_upload_item_csv_update_existing(self, client, app, logged_in_user, tmp_path):
        """Test updating an existing item via CSV."""
        app.config['UPLOAD_FOLDER'] = str(tmp_path)
        
        # Create an existing item
        with app.app_context():
            pack = Packaging(packaging_type='BOX1', company_id=logged_in_user.company_id)
            db.session.add(pack)
            db.session.commit()
            
            item = Item(
                name='Test Item 1',
                code='TI1',
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=pack.id,
                company_id=logged_in_user.company_id,
                ranch=False,
                item_designation=ItemDesignation.FOODSERVICE
            )
            db.session.add(item)
            db.session.commit()
            
            info = ItemInfo(
                product_yield=0.80,
                labor_hours=0.4,
                date=datetime.date.today(),
                item_id=item.id,
                company_id=logged_in_user.company_id
            )
            db.session.add(info)
            db.session.commit()

        # CSV with updated info for the same item
        csv_content = (
            "name,item_code,alternate_code,raw_product,ranch,item_designation,packaging_type,yield,case_weight,labor\n"
            "Test Item 1,TI1,ALT_NEW,Raw1,yes,FOODSERVICE,BOX1,0.95,10.0,0.6"
        )
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'items.csv')
        }
        
        with app.app_context():
            url = url_for('main.upload_item_csv')
            
        response = client.post(url, data=data, content_type='multipart/form-data', follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Items imported successfully!' in response.data # Or "Item ... already exists" depending on logic
        
        with app.app_context():
            item = Item.query.filter_by(name='Test Item 1').first()
            assert item.alternate_code == 'ALT_NEW'
            
            # Check that a new ItemInfo was added
            infos = ItemInfo.query.filter_by(item_id=item.id).order_by(ItemInfo.id.desc()).all()
            assert len(infos) >= 2
            assert infos[0].product_yield == 0.95
            assert infos[0].labor_hours == 0.6

    def test_upload_item_csv_invalid_data(self, client, app, logged_in_user, tmp_path):
        """Test uploading CSV with invalid data (e.g. bad yield)."""
        app.config['UPLOAD_FOLDER'] = str(tmp_path)
        
        csv_content = (
            "name,item_code,alternate_code,raw_product,ranch,item_designation,packaging_type,yield,case_weight,labor\n"
            "Bad Item,BI1,,Raw1,yes,FOODSERVICE,Box1,not_a_number,10.0,0.5"
        )
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'items.csv')
        }
        
        with app.app_context():
            url = url_for('main.upload_item_csv')
            
        response = client.post(url, data=data, content_type='multipart/form-data', follow_redirects=True)
        
        assert response.status_code == 200
        # Should skip the item or show a warning
        assert b'Invalid yield value' in response.data or b'Skipping item' in response.data
        
        with app.app_context():
            item = Item.query.filter_by(name='Bad Item').first()
            assert item is None
