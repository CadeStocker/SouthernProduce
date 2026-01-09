"""
Functional tests for receiving log pricing routes.

These tests verify the web interface for viewing and editing receiving log prices.
"""
import pytest
from datetime import datetime, timedelta, date
from producepricer.models import (
    Company, User, RawProduct, ReceivingLog, CostHistory,
    BrandName, Seller, GrowerOrDistributor
)
from producepricer import db


class TestReceivingLogPricingRoutes:
    """Test suite for receiving log pricing web routes."""
    
    @pytest.fixture(autouse=True)
    def setup(self, app, client):
        """Set up test data and login before each test."""
        with app.app_context():
            # Create company
            self.company = Company(name="Test Company", admin_email="admin@test.com")
            db.session.add(self.company)
            db.session.flush()
            
            # Create user
            self.user = User(
                first_name="Test",
                last_name="User",
                email="admin@test.com",
                password="password123",
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
            
            # Create supporting entities
            self.brand_name = BrandName(name="Test Brand", company_id=self.company.id)
            self.seller = Seller(name="Test Seller", company_id=self.company.id)
            self.grower = GrowerOrDistributor(
                name="Test Grower",
                city="Test City",
                state="CA",
                company_id=self.company.id
            )
            db.session.add_all([self.brand_name, self.seller, self.grower])
            db.session.commit()
            
            # Store IDs
            self.company_id = self.company.id
            self.raw_product_id = self.raw_product.id
            self.brand_name_id = self.brand_name.id
            self.seller_id = self.seller.id
            self.grower_id = self.grower.id
        
        # Login
        response = client.post('/login', data={
            'email': 'admin@test.com',
            'password': 'password123'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        yield
        
        # Cleanup
        with app.app_context():
            db.session.rollback()
            ReceivingLog.query.delete()
            CostHistory.query.delete()
            GrowerOrDistributor.query.delete()
            Seller.query.delete()
            BrandName.query.delete()
            RawProduct.query.delete()
            User.query.delete()
            Company.query.delete()
            db.session.commit()
    
    def test_view_receiving_log_with_price_comparison(self, app, client):
        """Test viewing a receiving log that has price comparison data."""
        with app.app_context():
            # Create receiving log with price
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
                price_paid=22.00
            )
            db.session.add(log)
            db.session.flush()
            
            # Create market cost
            cost = CostHistory(
                cost=25.00,
                date=date.today() - timedelta(days=2),
                company_id=self.company_id,
                raw_product_id=self.raw_product_id
            )
            db.session.add(cost)
            db.session.commit()
            log_id = log.id
        
        # View the log
        response = client.get(f'/receiving_log/{log_id}')
        assert response.status_code == 200
        
        html = response.data.decode('utf-8')
        
        # Check that pricing information is displayed
        assert '$22.00' in html  # Price paid
        assert '$25.00' in html  # Market cost
        assert 'BELOW Market' in html or 'below' in html.lower()
        assert 'Pricing Analysis' in html
        
        # Check that the date is shown
        cost_date_str = (date.today() - timedelta(days=2)).strftime('%b %d, %Y')
        assert cost_date_str in html or 'as of' in html.lower()
    
    def test_view_receiving_log_without_price(self, app, client):
        """Test viewing a receiving log that has no price entered."""
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
                price_paid=None
            )
            db.session.add(log)
            db.session.commit()
            log_id = log.id
        
        response = client.get(f'/receiving_log/{log_id}')
        assert response.status_code == 200
        
        html = response.data.decode('utf-8')
        
        # Check for "no price entered" messaging
        assert 'No Price Entered' in html or 'Not entered' in html
        assert 'Add Price' in html
    
    def test_view_receiving_log_shows_market_reference_in_modal(self, app, client):
        """Test that the edit price modal shows market cost reference."""
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
                price_paid=None
            )
            db.session.add(log)
            db.session.flush()
            
            # Create market cost
            cost = CostHistory(
                cost=25.00,
                date=date.today() - timedelta(days=1),
                company_id=self.company_id,
                raw_product_id=self.raw_product_id
            )
            db.session.add(cost)
            db.session.commit()
            log_id = log.id
        
        response = client.get(f'/receiving_log/{log_id}')
        assert response.status_code == 200
        
        html = response.data.decode('utf-8')
        
        # Check that market reference is shown in modal
        assert 'Market Cost Reference' in html
        assert '$25.00' in html
    
    def test_edit_receiving_log_price(self, app, client):
        """Test editing the price of a receiving log."""
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
                price_paid=None
            )
            db.session.add(log)
            db.session.commit()
            log_id = log.id
        
        # Edit the price
        response = client.post(f'/edit_receiving_log/{log_id}', data={
            'price_paid': '28.50'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify price was saved
        with app.app_context():
            log = db.session.get(ReceivingLog, log_id)
            assert log.price_paid == 28.50
    
    def test_edit_receiving_log_price_validation(self, app, client):
        """Test that negative prices are rejected."""
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
            log_id = log.id
        
        # Try to set negative price
        response = client.post(f'/edit_receiving_log/{log_id}', data={
            'price_paid': '-10.00'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify price was NOT changed
        with app.app_context():
            log = db.session.get(ReceivingLog, log_id)
            assert log.price_paid == 25.00  # Original price unchanged
    
    def test_edit_receiving_log_remove_price(self, app, client):
        """Test removing a price by submitting empty value."""
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
            log_id = log.id
        
        # Remove the price (empty string)
        response = client.post(f'/edit_receiving_log/{log_id}', data={
            'price_paid': ''
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify price was removed
        with app.app_context():
            log = db.session.get(ReceivingLog, log_id)
            assert log.price_paid is None
    
    def test_debug_route_shows_cost_history(self, app, client):
        """Test the debug route shows cost history information."""
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
                price_paid=22.00
            )
            db.session.add(log)
            db.session.flush()
            
            # Create cost history
            cost = CostHistory(
                cost=25.00,
                date=date.today() - timedelta(days=2),
                company_id=self.company_id,
                raw_product_id=self.raw_product_id
            )
            db.session.add(cost)
            db.session.commit()
            log_id = log.id
        
        # Access debug route
        response = client.get(f'/debug_receiving_log/{log_id}')
        assert response.status_code == 200
        
        # Parse JSON response
        data = response.get_json()
        
        # Verify debug information
        assert data['log_id'] == log_id
        assert data['raw_product'] == 'Test Strawberries'
        assert data['price_paid'] == 22.00
        assert 'all_cost_history' in data
        assert len(data['all_cost_history']) > 0
        assert data['market_cost_used'] == 25.00
        assert 'market_cost_date' in data
    
    def test_receiving_logs_table_shows_price_comparison(self, app, client):
        """Test that the receiving logs table shows price comparison badges."""
        with app.app_context():
            # Create log with price below market
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
                price_paid=20.00
            )
            db.session.add(log)
            db.session.flush()
            
            # Create market cost
            cost = CostHistory(
                cost=25.00,
                date=date.today() - timedelta(days=2),
                company_id=self.company_id,
                raw_product_id=self.raw_product_id
            )
            db.session.add(cost)
            db.session.commit()
        
        # View receiving logs list
        response = client.get('/receiving_logs')
        assert response.status_code == 200
        
        html = response.data.decode('utf-8')
        
        # Check that price is shown
        assert 'Paid:' in html or '$20.00' in html
        assert 'Market:' in html or '$25.00' in html
        
        # Check for badge indicators
        assert 'badge' in html.lower()
    
    def test_company_isolation_in_routes(self, app, client):
        """Test that users can only view logs from their own company."""
        with app.app_context():
            # Create another company and log
            company2 = Company(name="Other Company", admin_email="other@test.com")
            db.session.add(company2)
            db.session.flush()
            
            raw_product2 = RawProduct(name="Other Product", company_id=company2.id)
            brand2 = BrandName(name="Other Brand", company_id=company2.id)
            seller2 = Seller(name="Other Seller", company_id=company2.id)
            grower2 = GrowerOrDistributor(
                name="Other Grower",
                city="Other City",
                state="NY",
                company_id=company2.id
            )
            db.session.add_all([raw_product2, brand2, seller2, grower2])
            db.session.flush()
            
            other_log = ReceivingLog(
                raw_product_id=raw_product2.id,
                pack_size_unit="lbs",
                pack_size=10.0,
                brand_name_id=brand2.id,
                quantity_received=5,
                seller_id=seller2.id,
                temperature=35.0,
                hold_or_used="used",
                grower_or_distributor_id=grower2.id,
                country_of_origin="USA",
                received_by="Other User",
                company_id=company2.id,
                date_time=datetime.utcnow(),
                price_paid=30.00
            )
            db.session.add(other_log)
            db.session.commit()
            other_log_id = other_log.id
        
        # Try to view the other company's log (should get 404)
        response = client.get(f'/receiving_log/{other_log_id}')
        assert response.status_code == 404
        
        # Try to edit the other company's log (should get 404)
        response = client.post(f'/edit_receiving_log/{other_log_id}', data={
            'price_paid': '100.00'
        })
        assert response.status_code == 404
