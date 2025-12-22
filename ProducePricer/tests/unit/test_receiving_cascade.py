import pytest
from producepricer import db
from producepricer.models import (
    Company, User, RawProduct, 
    BrandName, Seller, GrowerOrDistributor, ReceivingLog, ReceivingImage
)

class TestReceivingCascade:
    
    def test_cascade_delete_images(self, app):
        """Test that deleting a ReceivingLog deletes associated ReceivingImages."""
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
            
            # Create ReceivingImages
            image1 = ReceivingImage(filename="img1.jpg", receiving_log_id=log.id, company_id=company.id)
            image2 = ReceivingImage(filename="img2.jpg", receiving_log_id=log.id, company_id=company.id)
            db.session.add(image1)
            db.session.add(image2)
            db.session.commit()
            
            # Verify creation
            assert ReceivingLog.query.count() == 1
            assert ReceivingImage.query.count() == 2
            
            # Delete Log
            db.session.delete(log)
            db.session.commit()
            
            # Verify cascade delete
            assert ReceivingLog.query.count() == 0
            assert ReceivingImage.query.count() == 0
