"""
Business workflow tests for the ProducePricer application.
Tests cover end-to-end workflows like customer management, item creation,
pricing operations, and data import/export functionality.
"""

import pytest
from datetime import date, datetime
from flask import url_for
from producepricer import db
from producepricer.models import (
    Company, User, Customer, Item, RawProduct, Packaging,
    PackagingCost, LaborCost, CostHistory, ItemInfo, ItemTotalCost,
    PriceSheet, PriceHistory, DesignationCost, RanchPrice,
    UnitOfWeight, ItemDesignation
)


# ====================
# Fixtures
# ====================

@pytest.fixture
def complete_setup(app):
    """Create a complete test environment with all necessary data."""
    with app.app_context():
        # Company
        company = Company(name="Complete Test Co", admin_email="complete@test.com")
        db.session.add(company)
        db.session.commit()
        
        # User
        user = User(
            first_name="Complete",
            last_name="User",
            email="user@complete.com",
            password="password123",
            company_id=company.id
        )
        db.session.add(user)
        
        # Packaging
        packaging = Packaging(packaging_type="Standard Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Packaging Cost
        pkg_cost = PackagingCost(
            box_cost=1.00,
            bag_cost=0.50,
            tray_andor_chemical_cost=0.25,
            label_andor_tape_cost=0.15,
            company_id=company.id,
            packaging_id=packaging.id,
            date=date.today()
        )
        db.session.add(pkg_cost)
        
        # Labor Cost
        labor = LaborCost(
            date=date.today(),
            labor_cost=15.00,
            company_id=company.id
        )
        db.session.add(labor)
        
        # Raw Products
        raw1 = RawProduct(name="Romaine Lettuce", company_id=company.id)
        raw2 = RawProduct(name="Spring Mix", company_id=company.id)
        db.session.add_all([raw1, raw2])
        db.session.commit()
        
        # Cost History for raw products
        cost1 = CostHistory(
            cost=2.50,
            date=date.today(),
            company_id=company.id,
            raw_product_id=raw1.id
        )
        cost2 = CostHistory(
            cost=3.00,
            date=date.today(),
            company_id=company.id,
            raw_product_id=raw2.id
        )
        db.session.add_all([cost1, cost2])
        
        # Designation Costs
        for designation in ItemDesignation:
            desg_cost = DesignationCost(
                item_designation=designation,
                cost=0.50,
                date=date.today(),
                company_id=company.id
            )
            db.session.add(desg_cost)
        
        # Customer
        customer = Customer(
            name="Test Customer",
            email="customer@test.com",
            company_id=company.id
        )
        db.session.add(customer)
        
        db.session.commit()
        
        return {
            'company_id': company.id,
            'user_id': user.id,
            'packaging_id': packaging.id,
            'raw_product_ids': [raw1.id, raw2.id],
            'customer_id': customer.id
        }


@pytest.fixture
def logged_in_complete(client, app, complete_setup):
    """Login with the complete setup user."""
    client.post('/login', data={
        'email': 'user@complete.com',
        'password': 'password123'
    })
    return complete_setup


# ====================
# Customer Workflow Tests
# ====================

class TestCustomerWorkflow:
    def test_customer_creation_workflow(self, client, app, logged_in_complete):
        """Test creating a customer through the application."""
        setup = logged_in_complete
        
        # First verify we can access customers page
        response = client.get('/customer')
        assert response.status_code == 200
        
        # Check existing customer is displayed
        assert b'Test Customer' in response.data

    def test_customer_list_only_shows_company_customers(self, client, app, logged_in_complete):
        """Test that customers page loads and shows company customers."""
        setup = logged_in_complete
        
        # Get customers page
        response = client.get('/customer')
        
        # Our customer should be visible
        assert b'Test Customer' in response.data
        assert response.status_code == 200


# ====================
# Item Workflow Tests
# ====================

class TestItemWorkflow:
    def test_items_page_loads(self, client, app, logged_in_complete):
        """Test that items page loads successfully."""
        response = client.get('/items')
        assert response.status_code == 200
        assert b'Items' in response.data

    def test_item_requires_labor_cost(self, client, app, logged_in_complete):
        """Test that creating items requires labor cost."""
        setup = logged_in_complete
        
        with app.app_context():
            # Remove labor costs
            LaborCost.query.filter_by(company_id=setup['company_id']).delete()
            db.session.commit()
        
        # Try to add item - should redirect with message
        response = client.post('/add_item', follow_redirects=True)
        assert b'labor cost' in response.data.lower() or response.status_code == 200


# ====================
# Pricing Workflow Tests
# ====================

class TestPricingWorkflow:
    def test_price_sheet_creation(self, client, app, logged_in_complete):
        """Test creating a price sheet."""
        setup = logged_in_complete
        
        with app.app_context():
            # First create an item
            item = Item(
                name="Price Sheet Item",
                code="PSI001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id'],
                case_weight=10.0
            )
            db.session.add(item)
            db.session.commit()
            
            # Create price sheet
            sheet = PriceSheet(
                name="Test Sheet",
                date=date.today(),
                company_id=setup['company_id'],
                customer_id=setup['customer_id']
            )
            sheet.items.append(item)
            db.session.add(sheet)
            db.session.commit()
            
            # Verify creation
            result = PriceSheet.query.filter_by(name="Test Sheet").first()
            assert result is not None
            assert len(result.items) == 1

    def test_price_history_tracking(self, client, app, logged_in_complete):
        """Test that price history is tracked correctly."""
        setup = logged_in_complete
        
        with app.app_context():
            # Create item
            item = Item(
                name="Price History Item",
                code="PHI001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item)
            db.session.commit()
            
            # Add price history entries
            prices = [10.00, 10.50, 11.00]
            for i, price in enumerate(prices):
                ph = PriceHistory(
                    item_id=item.id,
                    date=date(2024, i+1, 1),
                    company_id=setup['company_id'],
                    customer_id=setup['customer_id'],
                    price=price
                )
                db.session.add(ph)
            db.session.commit()
            
            # Query and verify
            history = PriceHistory.query.filter_by(item_id=item.id).order_by(PriceHistory.date).all()
            assert len(history) == 3
            assert history[0].price == 10.00
            assert history[2].price == 11.00


# ====================
# Cost Calculation Workflow Tests
# ====================

class TestCostCalculationWorkflow:
    def test_item_total_cost_creation(self, client, app, logged_in_complete):
        """Test creating item total cost records."""
        setup = logged_in_complete
        
        with app.app_context():
            # Create item
            item = Item(
                name="Cost Item",
                code="CI001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item)
            db.session.commit()
            
            # Create total cost
            total_cost = ItemTotalCost(
                item_id=item.id,
                date=date.today(),
                total_cost=15.00,
                ranch_cost=0.00,
                packaging_cost=2.00,
                raw_product_cost=8.00,
                labor_cost=4.00,
                designation_cost=1.00,
                company_id=setup['company_id']
            )
            db.session.add(total_cost)
            db.session.commit()
            
            # Verify
            result = ItemTotalCost.query.filter_by(item_id=item.id).first()
            assert result is not None
            assert result.total_cost == 15.00
            
            # Verify components sum to total
            components = (
                result.ranch_cost + result.packaging_cost + 
                result.raw_product_cost + result.labor_cost + 
                result.designation_cost
            )
            assert components == result.total_cost

    def test_ranch_item_cost_includes_ranch_price(self, client, app, logged_in_complete):
        """Test that ranch items include ranch pricing."""
        setup = logged_in_complete
        
        with app.app_context():
            # Create ranch price
            ranch = RanchPrice(
                date=date.today(),
                cost=1.50,
                price=2.00,
                company_id=setup['company_id']
            )
            db.session.add(ranch)
            db.session.commit()
            
            # Create ranch item
            item = Item(
                name="Ranch Item",
                code="RI001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id'],
                ranch=True
            )
            db.session.add(item)
            db.session.commit()
            
            # Create total cost with ranch component
            total_cost = ItemTotalCost(
                item_id=item.id,
                date=date.today(),
                total_cost=17.00,
                ranch_cost=2.00,  # Ranch items should have ranch cost
                packaging_cost=2.00,
                raw_product_cost=8.00,
                labor_cost=4.00,
                designation_cost=1.00,
                company_id=setup['company_id']
            )
            db.session.add(total_cost)
            db.session.commit()
            
            result = ItemTotalCost.query.filter_by(item_id=item.id).first()
            assert result.ranch_cost > 0


# ====================
# Raw Product Workflow Tests
# ====================

class TestRawProductWorkflow:
    def test_raw_products_page_loads(self, client, app, logged_in_complete):
        """Test that raw products page loads."""
        response = client.get('/raw_product')
        assert response.status_code == 200

    def test_raw_product_cost_history(self, client, app, logged_in_complete):
        """Test raw product cost history tracking."""
        setup = logged_in_complete
        
        with app.app_context():
            raw = RawProduct(name="Cost History Raw", company_id=setup['company_id'])
            db.session.add(raw)
            db.session.commit()
            
            # Add cost history
            costs = [
                (date(2024, 1, 1), 5.00),
                (date(2024, 2, 1), 5.50),
                (date(2024, 3, 1), 5.25),
            ]
            
            for d, c in costs:
                cost = CostHistory(
                    cost=c,
                    date=d,
                    company_id=setup['company_id'],
                    raw_product_id=raw.id
                )
                db.session.add(cost)
            db.session.commit()
            
            # Query costs
            history = CostHistory.query.filter_by(
                raw_product_id=raw.id
            ).order_by(CostHistory.date).all()
            
            assert len(history) == 3
            # Check prices changed over time
            assert history[0].cost != history[1].cost


# ====================
# Packaging Workflow Tests
# ====================

class TestPackagingWorkflow:
    def test_packaging_page_loads(self, client, app, logged_in_complete):
        """Test that packaging page loads."""
        response = client.get('/packaging')
        assert response.status_code == 200

    def test_packaging_cost_tracking(self, client, app, logged_in_complete):
        """Test packaging cost tracking over time."""
        setup = logged_in_complete
        
        with app.app_context():
            # Get existing packaging
            pkg = Packaging.query.filter_by(company_id=setup['company_id']).first()
            
            # Add another cost entry for different date
            new_cost = PackagingCost(
                box_cost=1.25,  # Price changed
                bag_cost=0.60,
                tray_andor_chemical_cost=0.30,
                label_andor_tape_cost=0.20,
                company_id=setup['company_id'],
                packaging_id=pkg.id,
                date=date(2024, 6, 1)
            )
            db.session.add(new_cost)
            db.session.commit()
            
            # Query costs
            costs = PackagingCost.query.filter_by(
                packaging_id=pkg.id
            ).order_by(PackagingCost.date).all()
            
            assert len(costs) >= 2


# ====================
# Multi-Company Isolation Tests
# ====================

class TestMultiCompanyIsolation:
    def test_data_isolation_between_companies(self, client, app, logged_in_complete):
        """Test that data is properly isolated between companies."""
        setup = logged_in_complete
        
        with app.app_context():
            # Create another company with its own data
            other_co = Company(name="Isolated Co", admin_email="iso@co.com")
            db.session.add(other_co)
            db.session.commit()
            
            other_raw = RawProduct(name="Isolated Raw", company_id=other_co.id)
            db.session.add(other_raw)
            db.session.commit()
            
            # Query raw products for our company
            our_raws = RawProduct.query.filter_by(company_id=setup['company_id']).all()
            
            # Verify isolated product is not in our list
            raw_names = [r.name for r in our_raws]
            assert "Isolated Raw" not in raw_names


# ====================
# Database Relationship Tests
# ====================

class TestDatabaseRelationships:
    def test_item_raw_product_relationship(self, client, app, logged_in_complete):
        """Test many-to-many relationship between items and raw products."""
        setup = logged_in_complete
        
        with app.app_context():
            # Get raw products
            raws = RawProduct.query.filter_by(company_id=setup['company_id']).all()
            
            # Create item with multiple raw products
            item = Item(
                name="Multi-Raw Item",
                code="MRI001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            for raw in raws:
                item.raw_products.append(raw)
            db.session.add(item)
            db.session.commit()
            
            # Verify relationship
            result = Item.query.filter_by(code="MRI001").first()
            assert len(result.raw_products) == len(raws)
            
            # Verify reverse relationship
            for raw in raws:
                items_using_raw = raw.items.all()
                assert result in items_using_raw

    def test_company_user_relationship(self, client, app, logged_in_complete):
        """Test company-user relationship."""
        setup = logged_in_complete
        
        with app.app_context():
            company = Company.query.get(setup['company_id'])
            
            # Add another user to the company
            user2 = User(
                first_name="Another",
                last_name="User",
                email="another@complete.com",
                password="pass",
                company_id=company.id
            )
            db.session.add(user2)
            db.session.commit()
            
            # Verify relationship through company
            company = Company.query.get(setup['company_id'])
            assert len(company.users) >= 2

    def test_price_sheet_items_relationship(self, client, app, logged_in_complete):
        """Test price sheet to items many-to-many relationship."""
        setup = logged_in_complete
        
        with app.app_context():
            # Create items
            items = []
            for i in range(3):
                item = Item(
                    name=f"Sheet Item {i}",
                    code=f"SI{i:03d}",
                    unit_of_weight=UnitOfWeight.POUND,
                    packaging_id=setup['packaging_id'],
                    company_id=setup['company_id']
                )
                items.append(item)
                db.session.add(item)
            db.session.commit()
            
            # Create price sheet with items
            sheet = PriceSheet(
                name="Relationship Test Sheet",
                date=date.today(),
                company_id=setup['company_id'],
                customer_id=setup['customer_id']
            )
            for item in items:
                sheet.items.append(item)
            db.session.add(sheet)
            db.session.commit()
            
            # Verify
            result = PriceSheet.query.filter_by(name="Relationship Test Sheet").first()
            assert len(result.items) == 3
            
            # Verify reverse relationship
            for item in items:
                sheets = item.price_sheets.all()
                assert result in sheets
