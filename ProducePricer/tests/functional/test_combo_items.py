import pytest
from datetime import date
from producepricer import db
from producepricer.models import (
    Item, ItemInfo, RawProduct, Packaging, PackagingCost, 
    LaborCost, DesignationCost, RanchPrice, CostHistory, 
    ItemDesignation, UnitOfWeight
)
from producepricer.blueprints.items import calculate_item_cost

class TestComboItemPricing:

    @pytest.fixture(autouse=True)
    def setup_data(self, app, logged_in_user):
        """Setup common data for all tests in this class"""
        self.company_id = logged_in_user.company_id
        
        with app.app_context():
            # 1. Setup Labor Cost ($20/hr)
            # We'll set labor hours to 0 for simplicity unless testing labor specifically
            lc = LaborCost(date=date.today(), labor_cost=20.0, company_id=self.company_id)
            db.session.add(lc)

            # 2. Setup Designation Costs
            # We need a cost for COMBO designation, let's say $1.50
            dc_combo = DesignationCost(item_designation=ItemDesignation.COMBO, cost=1.50, date=date.today(), company_id=self.company_id)
            db.session.add(dc_combo)

            # 3. Setup Packaging ($2.00 total)
            self.pack = Packaging(packaging_type="Box", company_id=self.company_id)
            db.session.add(self.pack)
            db.session.flush()

            pc = PackagingCost(
                box_cost=1.00, bag_cost=0.50, 
                tray_andor_chemical_cost=0.25, label_andor_tape_cost=0.25,
                date=date.today(), company_id=self.company_id, packaging_id=self.pack.id
            )
            db.session.add(pc)

            # 4. Setup Raw Products with distinct costs
            self.raw1 = RawProduct(name="Raw1", company_id=self.company_id)
            self.raw2 = RawProduct(name="Raw2", company_id=self.company_id)
            self.raw3 = RawProduct(name="Raw3", company_id=self.company_id)
            db.session.add(self.raw1)
            db.session.add(self.raw2)
            db.session.add(self.raw3)
            db.session.flush()

            # Raw Product Costs
            # Raw1: $10.00
            ch1 = CostHistory(cost=10.00, date=date.today(), company_id=self.company_id, raw_product_id=self.raw1.id)
            # Raw2: $20.00
            ch2 = CostHistory(cost=20.00, date=date.today(), company_id=self.company_id, raw_product_id=self.raw2.id)
            # Raw3: $30.00
            ch3 = CostHistory(cost=30.00, date=date.today(), company_id=self.company_id, raw_product_id=self.raw3.id)
            
            db.session.add(ch1)
            db.session.add(ch2)
            db.session.add(ch3)

            db.session.commit()
            
            # Store IDs for tests
            self.pack_id = self.pack.id
            self.raw1_id = self.raw1.id
            self.raw2_id = self.raw2.id
            self.raw3_id = self.raw3.id

    def test_combo_item_two_raw_products(self, app, logged_in_user):
        """
        Test Scenario: Combo Item with 2 Raw Products
        - Raw1 Cost: $10.00
        - Raw2 Cost: $20.00
        - Yield: 1.0 (for simplicity)
        - Case Weight: 1.0 (for simplicity)
        
        Raw Product Calculation:
        - Raw1 Contribution: ($10.00 / 1.0) * 1.0 = $10.00
        - Raw2 Contribution: ($20.00 / 1.0) * 1.0 = $20.00
        - Average Raw Cost: ($10.00 + $20.00) / 2 = $15.00
        
        Total Cost:
        - Raw Average: $15.00
        - Packaging: $2.00
        - Designation (COMBO): $1.50
        - Labor (0 hrs): $0.00
        - Total: $18.50
        """
        with app.app_context():
            # Create Item
            item = Item(
                name="Combo Item 1", 
                code="C1", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=1.0,
                ranch=False,
                item_designation=ItemDesignation.COMBO
            )
            
            # Add raw products
            raw1 = db.session.get(RawProduct, self.raw1_id)
            raw2 = db.session.get(RawProduct, self.raw2_id)
            item.raw_products.append(raw1)
            item.raw_products.append(raw2)
            
            db.session.add(item)
            db.session.commit()

            # Create ItemInfo
            ii = ItemInfo(
                product_yield=1.0, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(ii)
            db.session.commit()

            # Calculate Cost
            from flask_login import login_user
            with app.test_request_context():
                user_obj = logged_in_user.get_user()
                login_user(user_obj)
                total, labor, designation, packaging, raw_prod, ranch = calculate_item_cost(item.id)

            assert raw_prod == 15.00
            assert packaging == 2.00
            assert designation == 1.50
            assert total == 18.50

    def test_combo_item_three_raw_products(self, app, logged_in_user):
        """
        Test Scenario: Combo Item with 3 Raw Products
        - Raw1 Cost: $10.00, Raw2: $20.00, Raw3: $30.00
        - Yield: 0.8
        - Case Weight: 5.0
        
        Raw Product Calculation (per product):
        - Cost / Yield * CaseWeight
        - Raw1: ($10.00 / 0.8) * 5.0 = $12.50 * 5.0 = $62.50
        - Raw2: ($20.00 / 0.8) * 5.0 = $25.00 * 5.0 = $125.00
        - Raw3: ($30.00 / 0.8) * 5.0 = $37.50 * 5.0 = $187.50
        
        Average: ($62.50 + $125.00 + $187.50) / 3 = $375.00 / 3 = $125.00
        
        Total Cost:
        - Raw Average: $125.00
        - Packaging: $2.00
        - Designation (COMBO): $1.50
        - Total: $128.50
        """
        with app.app_context():
            item = Item(
                name="Combo Item 2", 
                code="C2", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=5.0,
                ranch=False,
                item_designation=ItemDesignation.COMBO
            )
            raw1 = db.session.get(RawProduct, self.raw1_id)
            raw2 = db.session.get(RawProduct, self.raw2_id)
            raw3 = db.session.get(RawProduct, self.raw3_id)
            
            item.raw_products.extend([raw1, raw2, raw3])
            db.session.add(item)
            db.session.commit()

            ii = ItemInfo(
                product_yield=0.8, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(ii)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                user_obj = logged_in_user.get_user()
                login_user(user_obj)
                total, labor, designation, packaging, raw_prod, ranch = calculate_item_cost(item.id)

            # Check within small epsilon due to float arithmetic
            assert abs(raw_prod - 125.00) < 0.001
            assert abs(total - 128.50) < 0.001

    def test_combo_item_with_missing_cost(self, app, logged_in_user):
        """
        Test Scenario: Combo Item with 2 Raw Products, one has NO COST info.
        - Raw1 Cost: $10.00
        - RawProduct 4 (New) Cost: None/Missing
        - Yield: 1.0, Case Weight: 1.0
        
        Logic in routes.py skips items with no cost foundation.
        
        Expected Calculation:
        - Raw1: $10.00
        - NewRaw: Skipped (count=0 for this one)
        
        Average is calculated based on items WITH costs.
        - Total Raw Items with cost: 1
        - Sum: $10.00
        - Average: $10.00 / 1 = $10.00
        """
        with app.app_context():
            # Create a raw product with NO cost history
            raw_no_cost = RawProduct(name="RawNoCost", company_id=self.company_id)
            db.session.add(raw_no_cost)
            db.session.flush()
            
            item = Item(
                name="Combo Item Missing Cost", 
                code="C3", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=1.0,
                ranch=False,
                item_designation=ItemDesignation.COMBO
            )
            
            raw1 = db.session.get(RawProduct, self.raw1_id)
            item.raw_products.extend([raw1, raw_no_cost])
            
            db.session.add(item)
            db.session.commit()

            ii = ItemInfo(
                product_yield=1.0, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(ii)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                user_obj = logged_in_user.get_user()
                login_user(user_obj)
                total, labor, designation, packaging, raw_prod, ranch = calculate_item_cost(item.id)

            # verify it just used the one valid cost
            assert raw_prod == 10.00
            assert total == 13.50  # 10.00 + 2.00 + 1.50

    def test_combo_item_no_raw_products(self, app, logged_in_user):
        """Test combo with 0 raw products assigned. Cost should be 0."""
        with app.app_context():
            item = Item(
                name="Empty Combo", 
                code="C4", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=1.0,
                ranch=False,
                item_designation=ItemDesignation.COMBO
            )
            db.session.add(item)
            db.session.commit()
            
            ii = ItemInfo(
                product_yield=1.0, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(ii)
            db.session.commit()
            
            from flask_login import login_user
            with app.test_request_context():
                user_obj = logged_in_user.get_user()
                login_user(user_obj)
                total, labor, designation, packaging, raw_prod, ranch = calculate_item_cost(item.id)
            
            assert raw_prod == 0.0
            assert total == 3.50 # 0 + 2.00 (pack) + 1.50 (desig)

