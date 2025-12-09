import pytest
import math
from flask import url_for
from datetime import date
from producepricer import db
from producepricer.models import (
    User, Company, Item, ItemTotalCost, ItemInfo, Packaging, PackagingCost,
    RawProduct, CostHistory, LaborCost, DesignationCost, UnitOfWeight, ItemDesignation
)

@pytest.fixture
def logged_in_user_with_data(client, app):
    """Fixture to create a user, company, and basic cost data, and log the user in."""
    with app.app_context():
        company = Company(name="Test Price Co", admin_email="admin@price.com")
        db.session.add(company)
        db.session.commit()

        user = User(first_name="Price", last_name="Tester", email="price@test.com", password="pw", company_id=company.id)
        db.session.add(user)

        # Add base costs required for item cost calculation
        labor_cost = LaborCost(labor_cost=20.0, date=date.today(), company_id=company.id)
        
        # Create parent objects
        packaging = Packaging(packaging_type="Test Price Box", company_id=company.id)
        raw_product = RawProduct(name="Test Price Raw", company_id=company.id)
        db.session.add_all([packaging, raw_product])
        db.session.commit()

        # Use packaging_id and raw_product_id as required by the model constructors
        packaging_cost = PackagingCost(packaging_id=packaging.id, box_cost=1.50, bag_cost=0.50, tray_andor_chemical_cost=0.25, label_andor_tape_cost=0.10, date=date.today(), company_id=company.id)
        cost_history = CostHistory(raw_product_id=raw_product.id, cost=5.0, date=date.today(), company_id=company.id)
        
        designation_cost = DesignationCost(item_designation=ItemDesignation.RETAIL, cost=1.0, date=date.today(), company_id=company.id)

        db.session.add_all([labor_cost, packaging, raw_product, packaging_cost, cost_history, designation_cost])
        db.session.commit()
        
        user_id = user.id

    client.post(url_for('main.login'), data={'email': 'price@test.com', 'password': 'pw'}, follow_redirects=True)
    
    with app.app_context():
        return db.session.get(User, user_id)

class TestPricePage:
    def test_price_page_loads_successfully(self, client, logged_in_user_with_data):
        """
        GIVEN a logged-in user
        WHEN the '/price' page is requested (GET)
        THEN check that the response is valid and the title is correct
        """
        response = client.get(url_for('main.price'))
        assert response.status_code == 200
        assert b'Price' in response.data
        assert b'Items & Costs' in response.data # Part of the nav bar

    def test_price_page_displays_item_data(self, client, app, logged_in_user_with_data):
        """
        GIVEN a logged-in user with an item that has a pre-calculated cost
        WHEN the '/price' page is requested
        THEN check that the item and its calculated prices are displayed
        """
        with app.app_context():
            item = Item.query.filter_by(name="Test Item With Cost").first()
            if not item:
                packaging = Packaging.query.first()
                item = Item(name="Test Item With Cost", code="P-001", case_weight=10, packaging_id=packaging.id, company_id=logged_in_user_with_data.company_id, item_designation=ItemDesignation.RETAIL, unit_of_weight=UnitOfWeight.POUND)
                db.session.add(item)
                db.session.commit()
                item_cost = ItemTotalCost(item_id=item.id, total_cost=100.0, labor_cost=10, packaging_cost=20, ranch_cost=5, raw_product_cost=65, designation_cost=0, date=date.today(), company_id=logged_in_user_with_data.company_id)
                db.session.add(item_cost)
                db.session.commit()

        response = client.get(url_for('main.price'))
        
        assert response.status_code == 200
        assert b'Test Item With Cost' in response.data
        assert b'P-001' in response.data
        assert b'100.00' in response.data # Total cost
        
        # Check for a rounded price (100 * 1.25 = 125, rounded to nearest quarter is 125.00)
        assert b'125.00' in response.data

    def test_price_page_calculates_cost_if_missing(self, client, app, logged_in_user_with_data):
        """
        GIVEN a logged-in user with an item that has NO pre-calculated cost
        WHEN the '/price' page is requested
        THEN check that a cost is calculated and displayed correctly
        """
        with app.app_context():
            packaging = Packaging.query.first()
            raw_product = RawProduct.query.first()
            item = Item(name="Item Needs Cost", code="P-002", case_weight=10, packaging_id=packaging.id, company_id=logged_in_user_with_data.company_id, item_designation=ItemDesignation.RETAIL, ranch=False, unit_of_weight=UnitOfWeight.POUND)
            item.raw_products.append(raw_product)
            db.session.add(item)
            db.session.commit()  # Commit item first to get item.id
            
            item_info = ItemInfo(item_id=item.id, product_yield=80.0, labor_hours=0.5, date=date.today(), company_id=logged_in_user_with_data.company_id)
            db.session.add(item_info)
            db.session.commit()
            item_id = item.id

        response = client.get(url_for('main.price'))
        
        assert response.status_code == 200
        assert b'Item Needs Cost' in response.data
        
        # Verify a cost was calculated and added to the DB
        with app.app_context():
            new_cost = ItemTotalCost.query.filter_by(item_id=item_id).first()
            assert new_cost is not None
            # Verify each cost component was calculated
            assert new_cost.packaging_cost == 2.35  # 1.5 + 0.5 + 0.25 + 0.10
            assert new_cost.labor_cost == 10.0  # 0.5 * 20.0
            assert new_cost.designation_cost == 1.0
            # Raw product cost depends on actual calculation logic
            # Just verify total is reasonable and components add up
            expected_total = new_cost.raw_product_cost + new_cost.packaging_cost + new_cost.labor_cost + new_cost.designation_cost + (new_cost.ranch_cost or 0)
            assert math.isclose(new_cost.total_cost, expected_total, rel_tol=1e-9)

    def test_price_page_search(self, client, app, logged_in_user_with_data):
        """
        GIVEN a logged-in user with multiple items
        WHEN the '/price' page is searched
        THEN check that only matching items are displayed
        """
        with app.app_context():
            packaging = Packaging.query.first()
            item1 = Item(name="Search Apple", code="S-001", case_weight=10, packaging_id=packaging.id, company_id=logged_in_user_with_data.company_id, item_designation=ItemDesignation.RETAIL, unit_of_weight=UnitOfWeight.POUND)
            item2 = Item(name="Search Orange", code="S-002", case_weight=10, packaging_id=packaging.id, company_id=logged_in_user_with_data.company_id, item_designation=ItemDesignation.RETAIL, unit_of_weight=UnitOfWeight.POUND)
            db.session.add_all([item1, item2])
            db.session.commit()
            # Add costs so the page doesn't error
            db.session.add(ItemTotalCost(item_id=item1.id, total_cost=1, date=date.today(), company_id=logged_in_user_with_data.company_id, ranch_cost=0, packaging_cost=0, raw_product_cost=0, labor_cost=0, designation_cost=1))
            db.session.add(ItemTotalCost(item_id=item2.id, total_cost=1, date=date.today(), company_id=logged_in_user_with_data.company_id, ranch_cost=0, packaging_cost=0, raw_product_cost=0, labor_cost=0, designation_cost=1))
            db.session.commit()

        response = client.get(url_for('main.price', q='Apple'))
        
        assert response.status_code == 200
        assert b'Search Apple' in response.data
        assert b'Search Orange' not in response.data