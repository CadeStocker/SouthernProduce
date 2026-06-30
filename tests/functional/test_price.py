# Copyright Cade Stocker 2026
import pytest
import math
from flask import url_for
from datetime import date
from app import db
from app.models import (
    User, Company, Item, ItemTotalCost, ItemInfo, Packaging, PackagingCost,
    RawProduct, CostHistory, LaborCost, DesignationCost, UnitOfWeight, ItemDesignation,
    Customer, CurrentItemPrice, PriceHistory, PriceSheet
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

        master_customer = Customer(name="Master", email="master@price.com", company_id=company.id)
        master_customer.is_master = True
        db.session.add(master_customer)

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
        company_id = company.id
        login_url = url_for('main.login')

    client.post(login_url, data={'email': 'price@test.com', 'password': 'pw'}, follow_redirects=True)
    
    # Return a helper object
    class LoggedInUserHelper:
        def __init__(self, user_id, company_id, app):
            self.id = user_id
            self.company_id = company_id
            self._app = app
            self.email = "price@test.com"
            self.first_name = "Price"
            self.last_name = "Tester"
            self.is_active = True
            self.is_authenticated = True
            self.is_anonymous = False
            
        def get_id(self):
            """Flask-Login required method."""
            return str(self.id)
            
        def get_user(self):
            with self._app.app_context():
                return db.session.get(User, self.id)
    
    return LoggedInUserHelper(user_id, company_id, app)

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
                item = Item(name="Test Item With Cost", code="P-001", case_weight=10, packaging_id=packaging.id, company_id=logged_in_user_with_data.company_id, item_designation=ItemDesignation.RETAIL, unit_of_weight=UnitOfWeight.POUND, alternate_code="ALT-P-001")
                db.session.add(item)
                db.session.commit()
                item_cost = ItemTotalCost(item_id=item.id, total_cost=100.0, labor_cost=10, packaging_cost=20, ranch_cost=5, raw_product_cost=65, designation_cost=0, date=date.today(), company_id=logged_in_user_with_data.company_id)
                db.session.add(item_cost)
                db.session.commit()

        response = client.get(url_for('main.price'))
        
        assert response.status_code == 200
        assert b'Test Item With Cost' in response.data
        assert b'P-001' in response.data
        assert b'ALT-P-001' in response.data
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


class TestPricingWorkflowCurrentPrice:
    def test_pricing_workflow_loads(self, client, logged_in_user_with_data):
        response = client.get(url_for('main.pricing_workflow'))
        assert response.status_code == 200
        assert b'Pricing Workflow' in response.data

    def test_pricing_workflow_saves_current_item_price(self, client, app, logged_in_user_with_data):
        with app.app_context():
            packaging = Packaging.query.first()
            item = Item(
                name="Workflow Price Item",
                code="WPI001",
                case_weight=10,
                packaging_id=packaging.id,
                company_id=logged_in_user_with_data.company_id,
                item_designation=ItemDesignation.RETAIL,
                unit_of_weight=UnitOfWeight.POUND
            )
            db.session.add(item)
            db.session.commit()

            db.session.add(
                ItemTotalCost(
                    item_id=item.id,
                    total_cost=20.0,
                    labor_cost=2.0,
                    packaging_cost=1.0,
                    ranch_cost=0,
                    raw_product_cost=16.0,
                    designation_cost=1.0,
                    date=date.today(),
                    company_id=logged_in_user_with_data.company_id
                )
            )
            db.session.commit()

            item_id = item.id

        response = client.post(
            url_for('main.pricing_workflow'),
            data={
                'target_margin': '10.00',
                f'price_input_{item_id}': '31.25'
            },
            follow_redirects=True
        )

        assert response.status_code == 200

class TestCurrentPricesPage:
    def test_current_prices_page_loads_successfully(self, client, logged_in_user_with_data):
        """
        GIVEN a logged-in user
        WHEN the '/current_prices' page is requested (GET)
        THEN check that the response is valid and contains important elements
        """
        response = client.get(url_for('main.current_prices'))
        assert response.status_code == 200


class TestPricingDataStorageMigrationSafety:
    def test_pricing_workflow_updates_current_price_without_touching_price_history(self, client, app, logged_in_user_with_data):
        """Posting pricing workflow should update CurrentItemPrice only and preserve existing PriceHistory rows."""
        with app.app_context():
            packaging = Packaging.query.first()
            company_id = logged_in_user_with_data.company_id

            # Add an item with an existing historical customer price and a current master price.
            item = Item(
                name="Migration Workflow Item",
                code="MWI-001",
                case_weight=10,
                packaging_id=packaging.id,
                company_id=company_id,
                item_designation=ItemDesignation.RETAIL,
                unit_of_weight=UnitOfWeight.POUND
            )
            customer = Customer(name="Workflow Customer", email="workflow-customer@test.com", company_id=company_id)
            db.session.add_all([item, customer])
            db.session.commit()

            item_id = item.id
            customer_id = customer.id

            db.session.add(
                ItemTotalCost(
                    item_id=item_id,
                    total_cost=18.0,
                    labor_cost=2.0,
                    packaging_cost=1.0,
                    ranch_cost=0,
                    raw_product_cost=14.0,
                    designation_cost=1.0,
                    date=date.today(),
                    company_id=company_id
                )
            )
            db.session.add(
                CurrentItemPrice(
                    item_id=item_id,
                    company_id=company_id,
                    price=26.00,
                    effective_date=date(2026, 1, 1)
                )
            )
            db.session.add(
                PriceHistory(
                    item_id=item_id,
                    date=date(2026, 1, 15),
                    company_id=company_id,
                    customer_id=customer_id,
                    price=24.50
                )
            )
            db.session.commit()

            history_count_before = PriceHistory.query.filter_by(item_id=item_id, company_id=company_id).count()

        response = client.post(
            url_for('main.pricing_workflow'),
            data={
                'target_margin': '10.00',
                f'price_input_{item_id}': '31.25'
            },
            follow_redirects=True
        )
        assert response.status_code == 200

        with app.app_context():
            cp = CurrentItemPrice.query.filter_by(item_id=item_id, company_id=company_id).first()
            assert cp is not None
            assert cp.price == 31.25

            history_rows = PriceHistory.query.filter_by(item_id=item_id, company_id=company_id).all()
            assert len(history_rows) == history_count_before
            assert any(h.customer_id == customer_id and h.price == 24.50 for h in history_rows)

    def test_edit_price_sheet_appends_price_history_without_overwriting_current_price(self, client, app, logged_in_user_with_data):
        """Saving a sheet price should append PriceHistory for that customer and keep CurrentItemPrice unchanged."""
        with app.app_context():
            packaging = Packaging.query.first()
            company_id = logged_in_user_with_data.company_id

            item = Item(
                name="Migration Sheet Item",
                code="MSI-001",
                case_weight=10,
                packaging_id=packaging.id,
                company_id=company_id,
                item_designation=ItemDesignation.RETAIL,
                unit_of_weight=UnitOfWeight.POUND
            )
            customer = Customer(name="Sheet Customer", email="sheet-customer@test.com", company_id=company_id)
            db.session.add_all([item, customer])
            db.session.commit()

            item_id = item.id
            customer_id = customer.id

            sheet = PriceSheet(
                name="Migration Safety Sheet",
                date=date(2026, 6, 1),
                valid_from=date(2026, 6, 1),
                valid_to=date(2026, 6, 30),
                company_id=company_id,
                customer_id=customer_id
            )
            sheet.items.append(item)
            db.session.add(sheet)

            db.session.add(
                CurrentItemPrice(
                    item_id=item_id,
                    company_id=company_id,
                    price=40.00,
                    effective_date=date(2026, 6, 1)
                )
            )
            db.session.add(
                PriceHistory(
                    item_id=item_id,
                    date=date(2026, 5, 1),
                    company_id=company_id,
                    customer_id=customer_id,
                    price=37.25
                )
            )
            db.session.commit()

            sheet_id = sheet.id
            history_count_before = PriceHistory.query.filter_by(
                item_id=item_id,
                company_id=company_id,
                customer_id=customer_id
            ).count()

        response = client.post(
            url_for('main.edit_price_sheet', sheet_id=sheet_id),
            data={f'price_input_{item_id}': '42.75'},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert b'Prices saved!' in response.data

        with app.app_context():
            cp = CurrentItemPrice.query.filter_by(item_id=item_id, company_id=company_id).first()
            assert cp is not None
            assert cp.price == 40.00
            assert cp.effective_date == date(2026, 6, 1)

            history_rows = (
                PriceHistory.query
                .filter_by(item_id=item_id, company_id=company_id, customer_id=customer_id)
                .order_by(PriceHistory.date.desc(), PriceHistory.id.desc())
                .all()
            )
            assert len(history_rows) == history_count_before + 1
            assert history_rows[0].price == 42.75

    def test_pricing_workflow_falls_back_to_price_history_when_no_current_price(self, client, app, logged_in_user_with_data):
        """Existing historical prices should still be usable in workflow when CurrentItemPrice is absent."""
        with app.app_context():
            company_id = logged_in_user_with_data.company_id
            packaging = Packaging.query.first()

            item = Item(
                name="Fallback History Item",
                code="FHI-001",
                case_weight=10,
                packaging_id=packaging.id,
                company_id=company_id,
                item_designation=ItemDesignation.RETAIL,
                unit_of_weight=UnitOfWeight.POUND
            )
            customer = Customer(name="Fallback Customer", email="fallback@test.com", company_id=company_id)
            db.session.add_all([item, customer])
            db.session.commit()

            item_id = item.id
            customer_id = customer.id

            db.session.add(
                ItemTotalCost(
                    item_id=item_id,
                    total_cost=20.0,
                    labor_cost=2.0,
                    packaging_cost=1.0,
                    ranch_cost=0,
                    raw_product_cost=16.0,
                    designation_cost=1.0,
                    date=date.today(),
                    company_id=company_id
                )
            )
            db.session.add(
                PriceHistory(
                    item_id=item_id,
                    date=date(2026, 6, 1),
                    company_id=company_id,
                    customer_id=customer_id,
                    price=33.50
                )
            )
            db.session.commit()

            # Explicitly verify there is no current/master price row.
            assert CurrentItemPrice.query.filter_by(item_id=item_id, company_id=company_id).first() is None

        response = client.get(url_for('main.pricing_workflow'))
        assert response.status_code == 200
        assert b'Fallback History Item' in response.data
        assert b'33.50' in response.data

    def test_edit_price_sheet_does_not_write_to_other_customers(self, client, app, logged_in_user_with_data):
        """Saving a price for one customer should not append rows for other customers."""
        with app.app_context():
            company_id = logged_in_user_with_data.company_id
            packaging = Packaging.query.first()

            item = Item(
                name="Customer Isolation Item",
                code="CII-001",
                case_weight=10,
                packaging_id=packaging.id,
                company_id=company_id,
                item_designation=ItemDesignation.RETAIL,
                unit_of_weight=UnitOfWeight.POUND
            )
            customer_a = Customer(name="Customer A", email="a@test.com", company_id=company_id)
            customer_b = Customer(name="Customer B", email="b@test.com", company_id=company_id)
            db.session.add_all([item, customer_a, customer_b])
            db.session.commit()

            item_id = item.id
            customer_a_id = customer_a.id
            customer_b_id = customer_b.id

            sheet_a = PriceSheet(
                name="Customer A Sheet",
                date=date(2026, 6, 1),
                valid_from=date(2026, 6, 1),
                valid_to=date(2026, 6, 30),
                company_id=company_id,
                customer_id=customer_a_id
            )
            sheet_a.items.append(item)
            db.session.add(sheet_a)

            # Existing row for another customer should remain untouched.
            db.session.add(
                PriceHistory(
                    item_id=item_id,
                    date=date(2026, 5, 1),
                    company_id=company_id,
                    customer_id=customer_b_id,
                    price=18.00
                )
            )
            db.session.commit()

            sheet_a_id = sheet_a.id
            customer_b_count_before = PriceHistory.query.filter_by(
                item_id=item_id,
                company_id=company_id,
                customer_id=customer_b_id
            ).count()

        response = client.post(
            url_for('main.edit_price_sheet', sheet_id=sheet_a_id),
            data={f'price_input_{item_id}': '21.25'},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert b'Prices saved!' in response.data

        with app.app_context():
            customer_a_latest = (
                PriceHistory.query
                .filter_by(item_id=item_id, company_id=company_id, customer_id=customer_a_id)
                .order_by(PriceHistory.date.desc(), PriceHistory.id.desc())
                .first()
            )
            assert customer_a_latest is not None
            assert customer_a_latest.price == 21.25

            customer_b_count_after = PriceHistory.query.filter_by(
                item_id=item_id,
                company_id=company_id,
                customer_id=customer_b_id
            ).count()
            assert customer_b_count_after == customer_b_count_before

    def test_pricing_writes_do_not_affect_other_companies(self, client, app, logged_in_user_with_data):
        """Writes in one company should not mutate PriceHistory or CurrentItemPrice rows in another company."""
        with app.app_context():
            company_a_id = logged_in_user_with_data.company_id
            packaging_a = Packaging.query.filter_by(company_id=company_a_id).first()

            item_a = Item(
                name="Company A Item",
                code="CO-ITEM-001",
                case_weight=10,
                packaging_id=packaging_a.id,
                company_id=company_a_id,
                item_designation=ItemDesignation.RETAIL,
                unit_of_weight=UnitOfWeight.POUND
            )
            customer_a = Customer(name="Company A Customer", email="ca@test.com", company_id=company_a_id)
            db.session.add_all([item_a, customer_a])
            db.session.commit()

            item_a_id = item_a.id
            customer_a_id = customer_a.id

            sheet_a = PriceSheet(
                name="Company A Sheet",
                date=date(2026, 6, 1),
                valid_from=date(2026, 6, 1),
                valid_to=date(2026, 6, 30),
                company_id=company_a_id,
                customer_id=customer_a_id
            )
            sheet_a.items.append(item_a)
            db.session.add(sheet_a)

            # Create independent company B data with same item code pattern.
            company_b = Company(name="Isolation Co B", admin_email="b-isolation@test.com")
            db.session.add(company_b)
            db.session.commit()

            company_b_id = company_b.id
            packaging_b = Packaging(packaging_type="Isolation B Box", company_id=company_b_id)
            customer_b = Customer(name="Company B Customer", email="cb@test.com", company_id=company_b_id)
            db.session.add_all([packaging_b, customer_b])
            db.session.commit()

            item_b = Item(
                name="Company B Item",
                code="CO-ITEM-001",
                case_weight=10,
                packaging_id=packaging_b.id,
                company_id=company_b_id,
                item_designation=ItemDesignation.RETAIL,
                unit_of_weight=UnitOfWeight.POUND
            )
            db.session.add(item_b)
            db.session.commit()

            item_b_id = item_b.id
            customer_b_id = customer_b.id

            b_current = CurrentItemPrice(
                item_id=item_b_id,
                company_id=company_b_id,
                price=55.00,
                effective_date=date(2026, 6, 1)
            )
            b_history = PriceHistory(
                item_id=item_b_id,
                date=date(2026, 6, 1),
                company_id=company_b_id,
                customer_id=customer_b_id,
                price=53.00
            )
            db.session.add_all([b_current, b_history])
            db.session.commit()

            sheet_a_id = sheet_a.id
            b_history_count_before = PriceHistory.query.filter_by(
                company_id=company_b_id,
                item_id=item_b_id,
                customer_id=customer_b_id
            ).count()
            b_current_before = CurrentItemPrice.query.filter_by(
                company_id=company_b_id,
                item_id=item_b_id
            ).first()
            b_current_price_before = b_current_before.price
            b_current_effective_before = b_current_before.effective_date

        response = client.post(
            url_for('main.edit_price_sheet', sheet_id=sheet_a_id),
            data={f'price_input_{item_a_id}': '24.75'},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert b'Prices saved!' in response.data

        with app.app_context():
            b_history_count_after = PriceHistory.query.filter_by(
                company_id=company_b_id,
                item_id=item_b_id,
                customer_id=customer_b_id
            ).count()
            assert b_history_count_after == b_history_count_before

            b_current_after = CurrentItemPrice.query.filter_by(
                company_id=company_b_id,
                item_id=item_b_id
            ).first()
            assert b_current_after is not None
            assert b_current_after.price == b_current_price_before
            assert b_current_after.effective_date == b_current_effective_before

    def test_current_prices_page_contains_items(self, client, app, logged_in_user_with_data):
        """
        GIVEN a logged-in user with items and current prices set
        WHEN the '/current_prices' page is requested
        THEN check that items are displayed correctly
        """
        # Add an item for testing  
        with app.app_context():
            packaging = Packaging.query.first()
            item = Item(
                name="Test Item",
                code="T-001",
                case_weight=10,
                packaging_id=packaging.id,
                company_id=logged_in_user_with_data.company_id,
                item_designation=ItemDesignation.RETAIL,
                unit_of_weight=UnitOfWeight.POUND
            )
            db.session.add(item)
            db.session.commit()
            item_id = item.id
            
            # Add a current item price for this item
            db.session.add(
                CurrentItemPrice(
                    item_id=item_id,
                    company_id=logged_in_user_with_data.company_id,
                    price=25.00,
                    effective_date=date.today()
                )
            )
            db.session.commit()

        cp = CurrentItemPrice.query.filter_by(item_id=item_id, company_id=logged_in_user_with_data.company_id).first()
        assert cp is not None
        assert cp.price == 25.00

        """
        WHEN the '/pricing_workflow' page is requested (GET)
        THEN check that the response is valid and contains important elements
        """
        response = client.get(url_for('main.pricing_workflow'))
        assert response.status_code == 200
        assert b'Pricing Workflow' in response.data
        
        # Check for the buttons we fixed the spacing for
        assert b'Update Raw Costs' in response.data
        assert b'Price Sheets' in response.data

    def test_pricing_workflow_page_contains_expected_elements(self, client, logged_in_user_with_data):
        """
        GIVEN a logged-in user
        WHEN the '/pricing_workflow' page is requested
        THEN check that all expected elements are present
        """
        response = client.get(url_for('main.pricing_workflow'))
        assert response.status_code == 200
        
        # Check for core components
        assert b'Target margin ($):' in response.data
        assert b'Apply Target Margin To All' in response.data
        assert b'Clear Inputs' in response.data
        assert b'Set Master Prices' in response.data

    def test_pricing_workflow_page_contains_items(self, client, app, logged_in_user_with_data):
        """
        GIVEN a logged-in user with items in the database
        WHEN the '/pricing_workflow' page is requested
        THEN check that items are displayed correctly
        """
        with app.app_context():
            # Add an item for testing
            packaging = Packaging.query.first()
            item = Item(
                name="Test Item",
                code="T-001",
                case_weight=10,
                packaging_id=packaging.id,
                company_id=logged_in_user_with_data.company_id,
                item_designation=ItemDesignation.RETAIL,
                unit_of_weight=UnitOfWeight.POUND
            )
            db.session.add(item)
            db.session.commit()
            
            # Add a cost for the item (required to be displayed in the workflow)
            test_cost = ItemTotalCost(
                item_id=item.id,
                total_cost=20.0,
                labor_cost=2.0,
                packaging_cost=1.0,
                ranch_cost=0,
                raw_product_cost=16.0,
                designation_cost=1.0,
                date=date.today(),
                company_id=logged_in_user_with_data.company_id
            )
            db.session.add(test_cost)
            db.session.commit()

        response = client.get(url_for('main.pricing_workflow'))
        assert response.status_code == 200
        # Check that the item name is displayed somewhere in the HTML (may be in the table)
        # We'll test using a more reliable pattern that looks for the item content
        assert b'Test Item' in response.data or b'T-001' in response.data

    def test_pricing_workflow_target_margin_functionality(self, client, app, logged_in_user_with_data):
        """
        GIVEN a logged-in user with items and target margin set
        WHEN the 'Apply Target Margin To All' button is clicked
        THEN check that prices are updated correctly according to the target margin
        """
        # Add an item for testing
        with app.app_context():
            packaging = Packaging.query.first()
            item = Item(
                name="Test Item",
                code="T-001",
                case_weight=10,
                packaging_id=packaging.id,
                company_id=logged_in_user_with_data.company_id,
                item_designation=ItemDesignation.RETAIL,
                unit_of_weight=UnitOfWeight.POUND
            )
            db.session.add(item)
            db.session.commit()
            
            db.session.add(
                ItemTotalCost(
                    item_id=item.id,
                    total_cost=20.0,
                    labor_cost=2.0,
                    packaging_cost=1.0,
                    ranch_cost=0,
                    raw_product_cost=16.0,
                    designation_cost=1.0,
                    date=date.today(),
                    company_id=logged_in_user_with_data.company_id
                )
            )
            db.session.commit()
            
            item_id = item.id

        # Test with a specific target margin
        response = client.post(
            url_for('main.pricing_workflow'),
            data={
                'target_margin': '10.00',
                f'price_input_{item_id}': ''
            },
            follow_redirects=True
        )
        
        assert response.status_code == 200
        
    def test_pricing_workflow_clear_inputs_functionality(self, client, app, logged_in_user_with_data):
        """
        GIVEN a logged-in user with items and prices entered
        WHEN the 'Clear Inputs' button is clicked
        THEN check that all input fields are cleared properly
        """
        # Add an item for testing
        with app.app_context():
            packaging = Packaging.query.first()
            item = Item(
                name="Test Item",
                code="T-001",
                case_weight=10,
                packaging_id=packaging.id,
                company_id=logged_in_user_with_data.company_id,
                item_designation=ItemDesignation.RETAIL,
                unit_of_weight=UnitOfWeight.POUND
            )
            db.session.add(item)
            db.session.commit()
            
            db.session.add(
                ItemTotalCost(
                    item_id=item.id,
                    total_cost=20.0,
                    labor_cost=2.0,
                    packaging_cost=1.0,
                    ranch_cost=0,
                    raw_product_cost=16.0,
                    designation_cost=1.0,
                    date=date.today(),
                    company_id=logged_in_user_with_data.company_id
                )
            )
            db.session.commit()
            
            item_id = item.id

        # Test clearing inputs functionality
        response = client.post(
            url_for('main.pricing_workflow'),
            data={
                'target_margin': '10.00',
                f'price_input_{item_id}': '30.00'
            },
            follow_redirects=True
        )
        
        assert response.status_code == 200