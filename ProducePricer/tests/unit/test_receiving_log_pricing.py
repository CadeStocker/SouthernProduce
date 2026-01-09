"""
Unit tests for ReceivingLog pricing comparison features.

These tests verify the price comparison functionality between received goods
and market costs from CostHistory.
"""
import pytest
from datetime import datetime, timedelta, date
from producepricer.models import (
    Company, User, RawProduct, ReceivingLog, CostHistory,
    BrandName, Seller, GrowerOrDistributor
)
from producepricer import db


class TestReceivingLogPricing:
    """Test suite for receiving log pricing comparison functionality."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Set up test data before each test."""
        with app.app_context():
            # Create company
            self.company = Company(name="Test Company", admin_email="test@example.com")
            db.session.add(self.company)
            db.session.flush()
            
            # Create user
            self.user = User(
                first_name="Test",
                last_name="User",
                email="test@example.com",
                password="password",
                company_id=self.company.id
            )
            db.session.add(self.user)
            db.session.flush()
            
            # Create raw product
            self.raw_product = RawProduct(
                name="Test Strawberries",
                company_id=self.company.id
            )
            db.session.add(self.raw_product)
            db.session.flush()
            
            # Create brand name
            self.brand_name = BrandName(
                name="Test Brand",
                company_id=self.company.id
            )
            db.session.add(self.brand_name)
            db.session.flush()
            
            # Create seller
            self.seller = Seller(
                name="Test Seller",
                company_id=self.company.id
            )
            db.session.add(self.seller)
            db.session.flush()
            
            # Create grower
            self.grower = GrowerOrDistributor(
                name="Test Grower",
                city="Test City",
                state="CA",
                company_id=self.company.id
            )
            db.session.add(self.grower)
            db.session.commit()
            
            # Store IDs for use in tests
            self.company_id = self.company.id
            self.raw_product_id = self.raw_product.id
            self.brand_name_id = self.brand_name.id
            self.seller_id = self.seller.id
            self.grower_id = self.grower.id
            
        yield
        
        # Cleanup after each test
        with app.app_context():
            db.session.rollback()
            # Delete in reverse order of dependencies
            ReceivingLog.query.delete()
            CostHistory.query.delete()
            GrowerOrDistributor.query.delete()
            Seller.query.delete()
            BrandName.query.delete()
            RawProduct.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_get_master_customer_price_with_recent_cost(self, app):
        """Test getting market cost when recent cost history exists."""
        with app.app_context():
            # Create a receiving log from today
            log = ReceivingLog(
                raw_product_id=self.raw_product_id,
                pack_size_unit="lbs",
                pack_size=10.0,
                brand_name_id=self.brand_name_id,
                quantity_received=5,
                seller_id=self.seller_id,
                temperature=35.0,
                hold_or_used="used",
                grower_or_distributor_id=self.grower_id,
                country_of_origin="USA",
                received_by="Test User",
                company_id=self.company_id,
                date_time=datetime.utcnow()
            )
            db.session.add(log)
            db.session.flush()
            
            # Create cost history from 2 days ago
            cost_date = date.today() - timedelta(days=2)
            cost = CostHistory(
                cost=25.50,
                date=cost_date,
                company_id=self.company_id,
                raw_product_id=self.raw_product_id
            )
            db.session.add(cost)
            db.session.commit()
            
            # Get the log again to ensure it's attached to session
            log = db.session.get(ReceivingLog, log.id)
            
            # Test the method
            result = log.get_master_customer_price()
            
            assert result is not None
            assert len(result) == 2
            assert result[0] == 25.50
            assert result[1] == cost_date
    
    def test_get_master_customer_price_no_cost_history(self, app):
        """Test getting market cost when no cost history exists."""
        with app.app_context():
            log = ReceivingLog(
                raw_product_id=self.raw_product_id,
                pack_size_unit="lbs",
                pack_size=10.0,
                brand_name_id=self.brand_name_id,
                quantity_received=5,
                seller_id=self.seller_id,
                temperature=35.0,
                hold_or_used="used",
                grower_or_distributor_id=self.grower_id,
                country_of_origin="USA",
                received_by="Test User",
                company_id=self.company_id,
                date_time=datetime.utcnow()
            )
            db.session.add(log)
            db.session.commit()
            
            log = db.session.get(ReceivingLog, log.id)
            result = log.get_master_customer_price()
            
            assert result is None
    
    def test_get_master_customer_price_old_cost_outside_window(self, app):
        """Test that costs older than 30 days are not returned."""
        with app.app_context():
            log = ReceivingLog(
                raw_product_id=self.raw_product_id,
                pack_size_unit="lbs",
                pack_size=10.0,
                brand_name_id=self.brand_name_id,
                quantity_received=5,
                seller_id=self.seller_id,
                temperature=35.0,
                hold_or_used="used",
                grower_or_distributor_id=self.grower_id,
                country_of_origin="USA",
                received_by="Test User",
                company_id=self.company_id,
                date_time=datetime.utcnow()
            )
            db.session.add(log)
            db.session.flush()
            
            # Create cost history from 40 days ago (outside 30-day window)
            old_cost_date = date.today() - timedelta(days=40)
            cost = CostHistory(
                cost=20.00,
                date=old_cost_date,
                company_id=self.company_id,
                raw_product_id=self.raw_product_id
            )
            db.session.add(cost)
            db.session.commit()
            
            log = db.session.get(ReceivingLog, log.id)
            result = log.get_master_customer_price()
            
            assert result is None
    
    def test_get_master_customer_price_selects_most_recent(self, app):
        """Test that the most recent cost within window is selected."""
        with app.app_context():
            log = ReceivingLog(
                raw_product_id=self.raw_product_id,
                pack_size_unit="lbs",
                pack_size=10.0,
                brand_name_id=self.brand_name_id,
                quantity_received=5,
                seller_id=self.seller_id,
                temperature=35.0,
                hold_or_used="used",
                grower_or_distributor_id=self.grower_id,
                country_of_origin="USA",
                received_by="Test User",
                company_id=self.company_id,
                date_time=datetime.utcnow()
            )
            db.session.add(log)
            db.session.flush()
            
            # Create multiple cost entries
            cost1 = CostHistory(
                cost=20.00,
                date=date.today() - timedelta(days=10),
                company_id=self.company_id,
                raw_product_id=self.raw_product_id
            )
            cost2 = CostHistory(
                cost=25.00,
                date=date.today() - timedelta(days=5),
                company_id=self.company_id,
                raw_product_id=self.raw_product_id
            )
            cost3 = CostHistory(
                cost=30.00,
                date=date.today() - timedelta(days=2),
                company_id=self.company_id,
                raw_product_id=self.raw_product_id
            )
            db.session.add_all([cost1, cost2, cost3])
            db.session.commit()
            
            log = db.session.get(ReceivingLog, log.id)
            result = log.get_master_customer_price()
            
            assert result is not None
            assert result[0] == 30.00  # Most recent cost
            assert result[1] == date.today() - timedelta(days=2)
    
    def test_get_price_comparison_below_market(self, app):
        """Test price comparison when paid price is below market."""
        with app.app_context():
            log = ReceivingLog(
                raw_product_id=self.raw_product_id,
                pack_size_unit="lbs",
                pack_size=10.0,
                brand_name_id=self.brand_name_id,
                quantity_received=5,
                seller_id=self.seller_id,
                temperature=35.0,
                hold_or_used="used",
                grower_or_distributor_id=self.grower_id,
                country_of_origin="USA",
                received_by="Test User",
                company_id=self.company_id,
                date_time=datetime.utcnow(),
                price_paid=20.00  # Below market
            )
            db.session.add(log)
            db.session.flush()
            
            # Market cost is $25
            cost = CostHistory(
                cost=25.00,
                date=date.today() - timedelta(days=2),
                company_id=self.company_id,
                raw_product_id=self.raw_product_id
            )
            db.session.add(cost)
            db.session.commit()
            
            log = db.session.get(ReceivingLog, log.id)
            result = log.get_price_comparison()
            
            assert result is not None
            assert result['price_paid'] == 20.00
            assert result['master_price'] == 25.00
            assert result['market_date'] is not None
            assert result['difference'] == -5.00
            assert result['percentage'] == -20.0
            assert result['status'] == 'below_market'
    
    def test_get_price_comparison_above_market(self, app):
        """Test price comparison when paid price is above market."""
        with app.app_context():
            log = ReceivingLog(
                raw_product_id=self.raw_product_id,
                pack_size_unit="lbs",
                pack_size=10.0,
                brand_name_id=self.brand_name_id,
                quantity_received=5,
                seller_id=self.seller_id,
                temperature=35.0,
                hold_or_used="used",
                grower_or_distributor_id=self.grower_id,
                country_of_origin="USA",
                received_by="Test User",
                company_id=self.company_id,
                date_time=datetime.utcnow(),
                price_paid=30.00  # Above market
            )
            db.session.add(log)
            db.session.flush()
            
            # Market cost is $25
            cost = CostHistory(
                cost=25.00,
                date=date.today() - timedelta(days=2),
                company_id=self.company_id,
                raw_product_id=self.raw_product_id
            )
            db.session.add(cost)
            db.session.commit()
            
            log = db.session.get(ReceivingLog, log.id)
            result = log.get_price_comparison()
            
            assert result is not None
            assert result['price_paid'] == 30.00
            assert result['master_price'] == 25.00
            assert result['market_date'] is not None
            assert result['difference'] == 5.00
            assert result['percentage'] == 20.0
            assert result['status'] == 'above_market'
    
    def test_get_price_comparison_at_market(self, app):
        """Test price comparison when paid price equals market."""
        with app.app_context():
            log = ReceivingLog(
                raw_product_id=self.raw_product_id,
                pack_size_unit="lbs",
                pack_size=10.0,
                brand_name_id=self.brand_name_id,
                quantity_received=5,
                seller_id=self.seller_id,
                temperature=35.0,
                hold_or_used="used",
                grower_or_distributor_id=self.grower_id,
                country_of_origin="USA",
                received_by="Test User",
                company_id=self.company_id,
                date_time=datetime.utcnow(),
                price_paid=25.00  # At market
            )
            db.session.add(log)
            db.session.flush()
            
            # Market cost is $25
            cost = CostHistory(
                cost=25.00,
                date=date.today() - timedelta(days=2),
                company_id=self.company_id,
                raw_product_id=self.raw_product_id
            )
            db.session.add(cost)
            db.session.commit()
            
            log = db.session.get(ReceivingLog, log.id)
            result = log.get_price_comparison()
            
            assert result is not None
            assert result['price_paid'] == 25.00
            assert result['master_price'] == 25.00
            assert result['market_date'] is not None
            assert abs(result['difference']) < 0.01
            assert result['status'] == 'at_market'
    
    def test_get_price_comparison_no_price_paid(self, app):
        """Test price comparison when no price has been entered."""
        with app.app_context():
            log = ReceivingLog(
                raw_product_id=self.raw_product_id,
                pack_size_unit="lbs",
                pack_size=10.0,
                brand_name_id=self.brand_name_id,
                quantity_received=5,
                seller_id=self.seller_id,
                temperature=35.0,
                hold_or_used="used",
                grower_or_distributor_id=self.grower_id,
                country_of_origin="USA",
                received_by="Test User",
                company_id=self.company_id,
                date_time=datetime.utcnow(),
                price_paid=None  # No price entered
            )
            db.session.add(log)
            db.session.commit()
            
            log = db.session.get(ReceivingLog, log.id)
            result = log.get_price_comparison()
            
            assert result is None
    
    def test_get_price_comparison_no_market_data(self, app):
        """Test price comparison when no market cost data exists."""
        with app.app_context():
            log = ReceivingLog(
                raw_product_id=self.raw_product_id,
                pack_size_unit="lbs",
                pack_size=10.0,
                brand_name_id=self.brand_name_id,
                quantity_received=5,
                seller_id=self.seller_id,
                temperature=35.0,
                hold_or_used="used",
                grower_or_distributor_id=self.grower_id,
                country_of_origin="USA",
                received_by="Test User",
                company_id=self.company_id,
                date_time=datetime.utcnow(),
                price_paid=25.00
            )
            db.session.add(log)
            db.session.commit()
            
            # No cost history created
            log = db.session.get(ReceivingLog, log.id)
            result = log.get_price_comparison()
            
            assert result is not None
            assert result['price_paid'] == 25.00
            assert result['master_price'] is None
            assert result['market_date'] is None
            assert result['status'] == 'no_market_data'
    
    def test_company_isolation(self, app):
        """Test that cost history from other companies is not used."""
        with app.app_context():
            # Create a second company
            company2 = Company(name="Other Company", admin_email="other@example.com")
            db.session.add(company2)
            db.session.flush()
            
            # Create raw product for second company
            raw_product2 = RawProduct(
                name="Test Strawberries",
                company_id=company2.id
            )
            db.session.add(raw_product2)
            db.session.flush()
            
            # Create receiving log for first company
            log = ReceivingLog(
                raw_product_id=self.raw_product_id,
                pack_size_unit="lbs",
                pack_size=10.0,
                brand_name_id=self.brand_name_id,
                quantity_received=5,
                seller_id=self.seller_id,
                temperature=35.0,
                hold_or_used="used",
                grower_or_distributor_id=self.grower_id,
                country_of_origin="USA",
                received_by="Test User",
                company_id=self.company_id,
                date_time=datetime.utcnow(),
                price_paid=25.00
            )
            db.session.add(log)
            db.session.flush()
            
            # Create cost history for SECOND company (should not be used)
            cost = CostHistory(
                cost=30.00,
                date=date.today() - timedelta(days=2),
                company_id=company2.id,
                raw_product_id=raw_product2.id
            )
            db.session.add(cost)
            db.session.commit()
            
            log = db.session.get(ReceivingLog, log.id)
            result = log.get_price_comparison()
            
            # Should not find market data from other company
            assert result is not None
            assert result['status'] == 'no_market_data'
            assert result['master_price'] is None
