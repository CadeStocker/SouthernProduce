import pytest
from datetime import datetime
from producepricer import db
from producepricer.models import (
    Company, User, RawProduct, 
    BrandName, Seller, GrowerOrDistributor, ReceivingLog, ReceivingImage
)

class TestReceivingImageModel:
    
    def test_receiving_image_creation(self, app):
        """Test creating a ReceivingImage."""
        with app.app_context():
            # Setup dependencies
            company = Company(name="Test Co", admin_email="test@co.com")
            db.session.add(company)
            db.session.commit()
            
            raw_product = RawProduct(name="Test Product", company_id=company.id)
            db.session.add(raw_product)
            
            brand = BrandName(name="Test Brand", company_id=company.id)
            db.session.add(brand)
            
            seller = Seller(name="Test Seller", company_id=company.id)
            db.session.add(seller)
            
            grower = GrowerOrDistributor(name="Test Grower", company_id=company.id, city="Test City", state="Test State")
            db.session.add(grower)
            
            db.session.commit()
            
            # Create ReceivingLog
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
                received_by="Test Employee",
                company_id=company.id
            )
            db.session.add(log)
            db.session.commit()
            
            # Create ReceivingImage
            image = ReceivingImage(
                filename="test_image.jpg",
                receiving_log_id=log.id,
                company_id=company.id
            )
            db.session.add(image)
            db.session.commit()
            
            assert image.id is not None
            assert image.filename == "test_image.jpg"
            assert image.receiving_log_id == log.id
            assert image.company_id == company.id
            assert image.uploaded_at is not None
            
            # Test relationship
            assert image in log.images
            assert image.receiving_log == log

    def test_receiving_image_repr(self, app):
        """Test the __repr__ method of ReceivingImage."""
        with app.app_context():
            image = ReceivingImage(
                filename="test_image.jpg",
                receiving_log_id=1,
                company_id=1
            )
            assert repr(image) == "ReceivingImage('test_image.jpg', '1')"
