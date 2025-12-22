import pytest
from datetime import datetime
from producepricer import db
from producepricer.models import (
    Company, User, RawProduct, 
    BrandName, Seller, GrowerOrDistributor, ReceivingLog
)

class TestReceivingModels:
    
    def test_brand_name_creation(self, app):
        """Test creating a BrandName."""
        with app.app_context():
            company = Company(name="Test Co", admin_email="test@co.com")
            db.session.add(company)
            db.session.commit()
            
            brand = BrandName(name="Test Brand", company_id=company.id)
            db.session.add(brand)
            db.session.commit()
            
            assert brand.id is not None
            assert brand.name == "Test Brand"
            assert brand.company_id == company.id

    def test_seller_creation(self, app):
        """Test creating a Seller."""
        with app.app_context():
            company = Company(name="Test Co", admin_email="test@co.com")
            db.session.add(company)
            db.session.commit()
            
            seller = Seller(name="Test Seller", company_id=company.id)
            db.session.add(seller)
            db.session.commit()
            
            assert seller.id is not None
            assert seller.name == "Test Seller"

    def test_grower_distributor_creation(self, app):
        """Test creating a GrowerOrDistributor."""
        with app.app_context():
            company = Company(name="Test Co", admin_email="test@co.com")
            db.session.add(company)
            db.session.commit()
            
            grower = GrowerOrDistributor(name="Test Grower", company_id=company.id, city="Test City", state="Test State")
            db.session.add(grower)
            db.session.commit()
            
            assert grower.id is not None
            assert grower.name == "Test Grower"
            assert grower.city == "Test City"
            assert grower.state == "Test State"

    def test_receiving_log_creation(self, app):
        """Test creating a ReceivingLog with all relationships."""
        with app.app_context():
            # Setup dependencies
            company = Company(name="Test Co", admin_email="test@co.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(first_name="Test", last_name="User", email="user@test.com", 
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
                company_id=company.id,
                returned="No"
            )
            db.session.add(log)
            db.session.commit()
            
            # Verify
            assert log.id is not None
            assert log.raw_product.name == "Test Product"
            assert log.brand_name.name == "Test Brand"
            assert log.seller.name == "Test Seller"
            assert log.grower_or_distributor.name == "Test Grower"
            assert log.company_id == company.id
            assert isinstance(log.datetime, datetime)

    def test_receiving_log_relationships(self, app):
        """Test backrefs work correctly."""
        with app.app_context():
            # Setup dependencies
            company = Company(name="Test Co", admin_email="test@co.com")
            db.session.add(company)
            db.session.commit()
            
            raw_product = RawProduct(name="Test Product", company_id=company.id)
            brand = BrandName(name="Test Brand", company_id=company.id)
            seller = Seller(name="Test Seller", company_id=company.id)
            grower = GrowerOrDistributor(name="Test Grower", company_id=company.id, city="Test City", state="Test State")
            
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create Log
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
            
            # Check backrefs
            assert log in raw_product.receiving_logs
            assert log in brand.receiving_logs
            assert log in seller.receiving_logs
            assert log in grower.receiving_logs

    def test_receiving_log_required_fields(self, app):
        """Test that missing required fields raises an IntegrityError."""
        from sqlalchemy.exc import IntegrityError
        
        with app.app_context():
            company = Company(name="Test Co", admin_email="test@co.com")
            db.session.add(company)
            db.session.commit()
            
            # Create minimal dependencies
            raw_product = RawProduct(name="Test Product", company_id=company.id)
            db.session.add(raw_product)
            db.session.commit()
            
            # Try to create log without required fields (e.g. missing seller_id, brand_name_id etc)
            # We'll just pass the bare minimum to get past python args, but miss database constraints if possible
            # Since __init__ requires arguments, we might need to pass None to trigger DB constraint
            
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit="lbs",
                pack_size=50.0,
                brand_name_id=None, # Missing required FK
                quantity_received=100,
                seller_id=None, # Missing required FK
                temperature=34.5,
                hold_or_used="used",
                grower_or_distributor_id=None, # Missing required FK
                country_of_origin="USA",
                received_by="Test Employee",
                company_id=company.id
            )
            db.session.add(log)
            
            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_receiving_log_default_datetime(self, app):
        """Test that datetime defaults to now if not provided."""
        with app.app_context():
            # Setup dependencies
            company = Company(name="Test Co", admin_email="test@co.com")
            db.session.add(company)
            db.session.commit()
            
            raw_product = RawProduct(name="Test Product", company_id=company.id)
            brand = BrandName(name="Test Brand", company_id=company.id)
            seller = Seller(name="Test Seller", company_id=company.id)
            grower = GrowerOrDistributor(name="Test Grower", company_id=company.id, city="Test City", state="Test State")
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create Log without date_time
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
                # date_time is omitted
            )
            db.session.add(log)
            db.session.commit()
            
            assert log.datetime is not None
            assert isinstance(log.datetime, datetime)
            # Check it's recent (within last minute)
            assert (datetime.utcnow() - log.datetime).total_seconds() < 60

    def test_receiving_log_update(self, app):
        """Test updating a receiving log entry."""
        with app.app_context():
            # Setup
            company = Company(name="Test Co", admin_email="test@co.com")
            db.session.add(company)
            db.session.commit()
            
            raw_product = RawProduct(name="Test Product", company_id=company.id)
            brand = BrandName(name="Test Brand", company_id=company.id)
            seller = Seller(name="Test Seller", company_id=company.id)
            grower = GrowerOrDistributor(name="Test Grower", company_id=company.id, city="Test City", state="Test State")
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
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
            
            # Update
            log.quantity_received = 200
            log.hold_or_used = "hold"
            db.session.commit()
            
            # Verify
            updated_log = db.session.get(ReceivingLog, log.id)
            assert updated_log.quantity_received == 200
            assert updated_log.hold_or_used == "hold"

    def test_receiving_log_delete(self, app):
        """Test deleting a receiving log entry."""
        with app.app_context():
            # Setup
            company = Company(name="Test Co", admin_email="test@co.com")
            db.session.add(company)
            db.session.commit()
            
            raw_product = RawProduct(name="Test Product", company_id=company.id)
            brand = BrandName(name="Test Brand", company_id=company.id)
            seller = Seller(name="Test Seller", company_id=company.id)
            grower = GrowerOrDistributor(name="Test Grower", company_id=company.id, city="Test City", state="Test State")
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
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
            
            log_id = log.id
            
            # Delete
            db.session.delete(log)
            db.session.commit()
            
            # Verify
            assert db.session.get(ReceivingLog, log_id) is None

    def test_query_filtering(self, app):
        """Test filtering receiving logs."""
        with app.app_context():
            # Setup
            company = Company(name="Test Co", admin_email="test@co.com")
            db.session.add(company)
            db.session.commit()
            
            p1 = RawProduct(name="Product 1", company_id=company.id)
            p2 = RawProduct(name="Product 2", company_id=company.id)
            brand = BrandName(name="Brand", company_id=company.id)
            seller = Seller(name="Seller", company_id=company.id)
            grower = GrowerOrDistributor(name="Grower", company_id=company.id, city="Test City", state="Test State")
            db.session.add_all([p1, p2, brand, seller, grower])
            db.session.commit()
            
            # Create logs for different products
            log1 = ReceivingLog(
                raw_product_id=p1.id, pack_size_unit="lbs", pack_size=50, brand_name_id=brand.id,
                quantity_received=100, seller_id=seller.id, temperature=34, hold_or_used="used",
                grower_or_distributor_id=grower.id, country_of_origin="USA", received_by="Emp", company_id=company.id
            )
            log2 = ReceivingLog(
                raw_product_id=p2.id, pack_size_unit="lbs", pack_size=50, brand_name_id=brand.id,
                quantity_received=100, seller_id=seller.id, temperature=34, hold_or_used="used",
                grower_or_distributor_id=grower.id, country_of_origin="USA", received_by="Emp", company_id=company.id
            )
            db.session.add_all([log1, log2])
            db.session.commit()
            
            # Filter by product 1
            results = ReceivingLog.query.filter_by(raw_product_id=p1.id).all()
            assert len(results) == 1
            assert results[0].id == log1.id
