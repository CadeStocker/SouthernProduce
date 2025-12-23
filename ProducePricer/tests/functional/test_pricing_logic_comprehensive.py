import pytest
from datetime import date
from producepricer import db
from producepricer.models import (
    Item, ItemInfo, RawProduct, Packaging, PackagingCost, 
    LaborCost, DesignationCost, RanchPrice, CostHistory, 
    ItemDesignation, UnitOfWeight
)
from producepricer.routes import calculate_item_cost, calculate_item_cost_with_info

class TestPricingLogic:

    @pytest.fixture(autouse=True)
    def setup_data(self, app, logged_in_user):
        """Setup common data for all tests in this class"""
        self.company_id = logged_in_user.company_id
        
        with app.app_context():
            # 1. Setup Labor Cost ($20/hr)
            lc = LaborCost(date=date.today(), labor_cost=20.0, company_id=self.company_id)
            db.session.add(lc)

            # 2. Setup Designation Costs
            dc_retail = DesignationCost(item_designation=ItemDesignation.RETAIL, cost=1.00, date=date.today(), company_id=self.company_id)
            dc_snakpak = DesignationCost(item_designation=ItemDesignation.SNAKPAK, cost=2.25, date=date.today(), company_id=self.company_id)
            db.session.add(dc_retail)
            db.session.add(dc_snakpak)

            # 3. Setup Ranch Price (Cost $5.00)
            rp = RanchPrice(date=date.today(), cost=5.00, price=10.00, company_id=self.company_id)
            db.session.add(rp)

            # 4. Setup Packaging
            self.pack = Packaging(packaging_type="Box", company_id=self.company_id)
            db.session.add(self.pack)
            db.session.flush() # get ID

            # Packaging Cost ($2.00 total)
            pc = PackagingCost(
                box_cost=1.00, bag_cost=0.50, 
                tray_andor_chemical_cost=0.25, label_andor_tape_cost=0.25,
                date=date.today(), company_id=self.company_id, packaging_id=self.pack.id
            )
            db.session.add(pc)

            # 5. Setup Raw Product
            self.raw1 = RawProduct(name="Raw1", company_id=self.company_id)
            self.raw2 = RawProduct(name="Raw2", company_id=self.company_id)
            db.session.add(self.raw1)
            db.session.add(self.raw2)
            db.session.flush()

            # Raw Product Costs
            # Raw1: $10.00
            ch1 = CostHistory(cost=10.00, date=date.today(), company_id=self.company_id, raw_product_id=self.raw1.id)
            # Raw2: $5.00
            ch2 = CostHistory(cost=5.00, date=date.today(), company_id=self.company_id, raw_product_id=self.raw2.id)
            db.session.add(ch1)
            db.session.add(ch2)

            db.session.commit()
            
            # Store IDs for tests
            self.pack_id = self.pack.id
            self.raw1_id = self.raw1.id
            self.raw2_id = self.raw2.id

    def test_basic_item_cost_calculation(self, app, logged_in_user):
        """
        Test Scenario 1: Basic Item Cost
        - Raw Product Cost: $10.00
        - Yield: 0.80
        - Case Weight: 10 lbs
        - Packaging Cost: $2.00
        - Labor: 0.5 hours @ $20/hr = $10.00
        - Designation: RETAIL ($1.00)
        - Ranch: False
        
        Expected Calculation:
        - Raw Component: ($10.00 / 0.80) * 10 = $12.50 * 10 = $125.00
        - Packaging: $2.00
        - Labor: $10.00
        - Designation: $1.00
        - Total: $138.00
        """
        with app.app_context():
            # Create Item
            item = Item(
                name="Test Item 1", 
                code="TI1", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=10.0,
                ranch=False,
                item_designation=ItemDesignation.RETAIL
            )
            # Add raw product
            raw1 = db.session.get(RawProduct, self.raw1_id)
            item.raw_products.append(raw1)
            db.session.add(item)
            db.session.flush()

            # Create ItemInfo (Yield 0.8, Labor 0.5)
            info = ItemInfo(
                product_yield=0.8, 
                item_id=item.id, 
                labor_hours=0.5, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            # Calculate Cost
            # We need to mock current_user or ensure logged_in_user is active
            # Since we are in app_context but not request context with login, 
            # calculate_item_cost relies on current_user.
            # However, the test client session handles login. 
            # But calling the function directly requires `current_user` proxy to work.
            # We can use `app.test_request_context` and `login_user` from flask_login.
            
            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                total, labor, designation, packaging, raw, ranch = calculate_item_cost(item.id)
                
                assert labor == 10.00
                assert designation == 1.00
                assert packaging == 2.00
                assert raw == 125.00
                assert ranch == 0.00
                assert total == 138.00

    def test_multiple_raw_products_sum(self, app, logged_in_user):
        """
        Test Scenario 2: Multiple Raw Products
        - Raw1: $10.00
        - Raw2: $5.00
        - Yield: 1.0
        - Case Weight: 10 lbs
        
        If SUM logic is used:
        - Raw1 Cost: ($10 / 1) * 10 = $100
        - Raw2 Cost: ($5 / 1) * 10 = $50
        - Total Raw: $150
        """
        with app.app_context():
            item = Item(
                name="Multi Raw Item", 
                code="MRI", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=10.0,
                ranch=False,
                item_designation=ItemDesignation.RETAIL
            )
            raw1 = db.session.get(RawProduct, self.raw1_id)
            raw2 = db.session.get(RawProduct, self.raw2_id)
            item.raw_products.append(raw1)
            item.raw_products.append(raw2)
            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                product_yield=1.0, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                total, labor, designation, packaging, raw, ranch = calculate_item_cost(item.id)
                
                # Based on code reading, it sums them
                assert raw == 150.00
                assert total == 150.00 + 2.00 + 1.00 # Raw + Packaging + Designation (Labor is 0)

    def test_ranch_cost_addition(self, app, logged_in_user):
        """
        Test Scenario 3: Ranch Cost
        - Ranch Price Cost: $5.00
        - Item.ranch = True
        """
        with app.app_context():
            item = Item(
                name="Ranch Item", 
                code="RI", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=10.0,
                ranch=True, # Enable Ranch
                item_designation=ItemDesignation.RETAIL
            )
            # No raw products for simplicity, or one
            raw1 = db.session.get(RawProduct, self.raw1_id)
            item.raw_products.append(raw1)
            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                product_yield=1.0, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                total, labor, designation, packaging, raw, ranch = calculate_item_cost(item.id)
                
                assert ranch == 5.00
                # Raw: ($10 / 1) * 10 = 100
                # Pack: 2
                # Desig: 1
                # Ranch: 5
                # Total: 108
                assert total == 100.00 + 2.00 + 1.00 + 5.00

    def test_yield_impact(self, app, logged_in_user):
        """
        Test Scenario 4: Yield Impact
        - Yield 0.5
        - Raw Cost $10
        - Case Weight 10
        - Expected Raw: ($10 / 0.5) * 10 = $20 * 10 = $200
        """
        with app.app_context():
            item = Item(
                name="Low Yield Item", 
                code="LYI", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=10.0,
                ranch=False,
                item_designation=ItemDesignation.RETAIL
            )
            raw1 = db.session.get(RawProduct, self.raw1_id)
            item.raw_products.append(raw1)
            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                product_yield=0.5, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                total, labor, designation, packaging, raw, ranch = calculate_item_cost(item.id)
                
                assert raw == 200.00

    def test_snakpak_designation(self, app, logged_in_user):
        """
        Test Scenario 6: Designation SNAKPAK
        - Should add $2.25 instead of $1.00
        """
        with app.app_context():
            item = Item(
                name="Snakpak Item", 
                code="SPI", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=10.0,
                ranch=False,
                item_designation=ItemDesignation.SNAKPAK
            )
            raw1 = db.session.get(RawProduct, self.raw1_id)
            item.raw_products.append(raw1)
            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                product_yield=1.0, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                total, labor, designation, packaging, raw, ranch = calculate_item_cost(item.id)
                
                assert designation == 2.25
                # Raw: 100
                # Pack: 2
                # Total: 104.25
                assert total == 100.00 + 2.00 + 2.25

    def test_calculate_item_cost_with_info_function(self, app, logged_in_user):
        """
        Test the standalone function `calculate_item_cost_with_info`
        This function takes arguments directly instead of looking up ItemInfo.
        """
        with app.app_context():
            raw1 = db.session.get(RawProduct, self.raw1_id)
            raw_products = [raw1]
            
            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                # Args: packaging_id, product_yield, labor_hours, case_weight, ranch, item_designation, raw_products
                total, labor, designation, packaging, raw, ranch_cost = calculate_item_cost_with_info(
                    self.pack_id, 
                    0.8, # Yield
                    0.5, # Labor Hours
                    10.0, # Case Weight
                    False, # Ranch
                    ItemDesignation.RETAIL,
                    raw_products
                )
                
                # Same expectations as test_basic_item_cost_calculation
                assert labor == 10.00
                assert designation == 1.00
                assert packaging == 2.00
                assert raw == 125.00
                assert ranch_cost == 0.00
                assert total == 138.00

    def test_zero_yield_handling(self, app, logged_in_user):
        """
        Test Scenario: Zero Yield
        - Yield = 0.0
        - Should default to 1.0 to avoid DivisionByZero
        - Raw Cost: ($10 / 1) * 10 = $100 (instead of infinity)
        """
        with app.app_context():
            item = Item(
                name="Zero Yield Item", 
                code="ZYI", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=10.0,
                ranch=False,
                item_designation=ItemDesignation.RETAIL
            )
            raw1 = db.session.get(RawProduct, self.raw1_id)
            item.raw_products.append(raw1)
            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                product_yield=0.0, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                total, labor, designation, packaging, raw, ranch = calculate_item_cost(item.id)
                
                # Expect yield to be treated as 1.0
                assert raw == 100.00

    def test_missing_labor_and_packaging_costs(self, app, logged_in_user):
        """
        Test Scenario: Missing Labor and Packaging Costs
        - Should default to 0.0
        """
        with app.app_context():
            # Create a new packaging with NO cost
            empty_pack = Packaging(packaging_type="Empty Box", company_id=self.company_id)
            db.session.add(empty_pack)
            db.session.flush()

            # Delete all labor costs for this test context
            LaborCost.query.filter_by(company_id=self.company_id).delete()
            
            item = Item(
                name="No Cost Item", 
                code="NCI", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=empty_pack.id, 
                company_id=self.company_id,
                case_weight=10.0,
                ranch=False,
                item_designation=ItemDesignation.RETAIL
            )
            # No raw products to isolate labor/packaging
            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                product_yield=1.0, 
                item_id=item.id, 
                labor_hours=1.0, # 1 hour, but cost is missing
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                total, labor, designation, packaging, raw, ranch = calculate_item_cost(item.id)
                
                assert labor == 0.00
                assert packaging == 0.00
                assert designation == 1.00 # Default
                assert total == 1.00

    def test_historical_cost_selection(self, app, logged_in_user):
        """
        Test Scenario: Historical Cost Selection
        - Ensure the MOST RECENT cost is used.
        - Old Cost: $5.00 (Yesterday)
        - New Cost: $10.00 (Today)
        - Should use $10.00
        """
        from datetime import timedelta
        with app.app_context():
            # Create Raw Product
            raw_hist = RawProduct(name="Historical Raw", company_id=self.company_id)
            db.session.add(raw_hist)
            db.session.flush()

            # Old Cost
            ch_old = CostHistory(
                cost=5.00, 
                date=date.today() - timedelta(days=1), 
                company_id=self.company_id, 
                raw_product_id=raw_hist.id
            )
            # New Cost
            ch_new = CostHistory(
                cost=10.00, 
                date=date.today(), 
                company_id=self.company_id, 
                raw_product_id=raw_hist.id
            )
            db.session.add(ch_old)
            db.session.add(ch_new)
            
            item = Item(
                name="Historical Item", 
                code="HI", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=10.0,
                ranch=False,
                item_designation=ItemDesignation.RETAIL
            )
            item.raw_products.append(raw_hist)
            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                product_yield=1.0, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                total, labor, designation, packaging, raw, ranch = calculate_item_cost(item.id)
                
                # Should use $10.00
                # ($10 / 1) * 10 = 100
                assert raw == 100.00

    def test_cost_update_impact(self, app, logged_in_user):
        """
        Test Scenario: Update Cost and Recalculate
        - Initial Raw Cost: $10.00
        - Calculate -> $100
        - Add New Cost: $20.00
        - Calculate -> $200
        """
        from datetime import timedelta
        with app.app_context():
            item = Item(
                name="Update Item", 
                code="UI", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=10.0,
                ranch=False,
                item_designation=ItemDesignation.RETAIL
            )
            raw1 = db.session.get(RawProduct, self.raw1_id)
            item.raw_products.append(raw1)
            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                product_yield=1.0, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                # First Calculation (Raw1 is $10 from setup)
                total1, _, _, _, raw1_cost, _ = calculate_item_cost(item.id)
                assert raw1_cost == 100.00

                # Add new cost for Raw1
                ch_new = CostHistory(
                    cost=20.00, 
                    date=date.today() + timedelta(days=1), # Future date to ensure it's newest
                    company_id=self.company_id, 
                    raw_product_id=self.raw1_id
                )
                db.session.add(ch_new)
                db.session.commit()

                # Second Calculation
                total2, _, _, _, raw2_cost, _ = calculate_item_cost(item.id)
                assert raw2_cost == 200.00

    def test_no_raw_products(self, app, logged_in_user):
        """
        Test Scenario: Item with NO Raw Products
        - Should calculate Packaging + Labor + Designation only.
        """
        with app.app_context():
            item = Item(
                name="Service Item", 
                code="SVC", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=10.0,
                ranch=False,
                item_designation=ItemDesignation.RETAIL
            )
            # No raw products appended
            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                product_yield=1.0, 
                item_id=item.id, 
                labor_hours=1.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                total, labor, designation, packaging, raw, ranch = calculate_item_cost(item.id)
                
                assert raw == 0.00
                assert labor == 20.00 # 1 hr * $20
                assert packaging == 2.00
                assert designation == 1.00
                assert total == 23.00

    def test_cross_company_isolation(self, app, logged_in_user):
        """
        Test Scenario: Cross-Company Isolation
        - Ensure costs from another company are not used.
        """
        from producepricer.models import Company
        with app.app_context():
            # Create Company B
            company_b = Company(name="Company B", admin_email="b@example.com")
            db.session.add(company_b)
            db.session.flush()

            # Create Raw Product for Company B
            raw_b = RawProduct(name="Raw B", company_id=company_b.id)
            db.session.add(raw_b)
            db.session.flush()

            # Add Cost for Raw B (High Value)
            ch_b = CostHistory(cost=1000.00, date=date.today(), company_id=company_b.id, raw_product_id=raw_b.id)
            db.session.add(ch_b)
            
            # Create Item for Company A (logged_in_user)
            # Using Raw1 (Cost $10) from setup
            item = Item(
                name="Company A Item", 
                code="CAI", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=10.0,
                ranch=False,
                item_designation=ItemDesignation.RETAIL
            )
            raw1 = db.session.get(RawProduct, self.raw1_id)
            item.raw_products.append(raw1)
            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                product_yield=1.0, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                total, labor, designation, packaging, raw, ranch = calculate_item_cost(item.id)
                
                # Should use Company A's cost ($10), not Company B's ($1000)
                # ($10 / 1) * 10 = 100
                assert raw == 100.00

    def test_future_dated_costs(self, app, logged_in_user):
        """
        Test Scenario: Future Dated Costs
        - System should pick up future dated costs if they are the most recent entry.
        """
        from datetime import timedelta
        with app.app_context():
            # Add Future Cost for Raw1
            ch_future = CostHistory(
                cost=50.00, 
                date=date.today() + timedelta(days=30), 
                company_id=self.company_id, 
                raw_product_id=self.raw1_id
            )
            db.session.add(ch_future)
            
            item = Item(
                name="Future Item", 
                code="FI", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=10.0,
                ranch=False,
                item_designation=ItemDesignation.RETAIL
            )
            raw1 = db.session.get(RawProduct, self.raw1_id)
            item.raw_products.append(raw1)
            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                product_yield=1.0, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                total, labor, designation, packaging, raw, ranch = calculate_item_cost(item.id)
                
                # Should use Future Cost ($50)
                # ($50 / 1) * 10 = 500
                assert raw == 500.00

    def test_floating_point_precision(self, app, logged_in_user):
        """
        Test Scenario: Floating Point Precision
        - Use weird numbers to check for stability.
        """
        with app.app_context():
            # Raw Cost: $0.3333
            raw_weird = RawProduct(name="Weird Raw", company_id=self.company_id)
            db.session.add(raw_weird)
            db.session.flush()
            
            ch_weird = CostHistory(cost=0.3333, date=date.today(), company_id=self.company_id, raw_product_id=raw_weird.id)
            db.session.add(ch_weird)

            item = Item(
                name="Precision Item", 
                code="PI", 
                unit_of_weight=UnitOfWeight.POUND, 
                packaging_id=self.pack_id, 
                company_id=self.company_id,
                case_weight=1.0,
                ranch=False,
                item_designation=ItemDesignation.RETAIL
            )
            item.raw_products.append(raw_weird)
            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                product_yield=0.3333, 
                item_id=item.id, 
                labor_hours=0.0, 
                date=date.today(), 
                company_id=self.company_id
            )
            db.session.add(info)
            db.session.commit()

            from flask_login import login_user
            with app.test_request_context():
                login_user(logged_in_user)
                
                total, labor, designation, packaging, raw, ranch = calculate_item_cost(item.id)
                
                # Raw: (0.3333 / 0.3333) * 1.0 = 1.0
                assert abs(raw - 1.0) < 0.0001

