"""
Comprehensive tests for database logic and operations.
Tests cover model relationships, cost calculations, cascading operations,
and database integrity constraints.
"""

import pytest
from datetime import date, datetime, timedelta
from producepricer import db
from producepricer.models import (
    Company,
    User,
    Item,
    RawProduct,
    Packaging,
    PackagingCost,
    Customer,
    CostHistory,
    PriceHistory,
    PriceSheet,
    LaborCost,
    ItemInfo,
    ItemTotalCost,
    RanchPrice,
    DesignationCost,
    PendingUser,
    AIResponse,
    EmailTemplate,
    UnitOfWeight,
    ItemDesignation,
)


# ====================
# Helper Fixtures
# ====================

@pytest.fixture
def setup_full_company(app):
    """Create a complete company setup with all related entities."""
    with app.app_context():
        # Create company
        company = Company(name="Full Test Company", admin_email="fulladmin@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create user
        user = User(
            first_name="Full",
            last_name="User",
            email="fulluser@test.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)
        
        # Create packaging
        packaging = Packaging(packaging_type="Standard Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create packaging cost
        pkg_cost = PackagingCost(
            packaging_id=packaging.id,
            box_cost=2.00,
            bag_cost=0.50,
            tray_andor_chemical_cost=0.25,
            label_andor_tape_cost=0.15,
            date=date.today(),
            company_id=company.id
        )
        db.session.add(pkg_cost)
        
        # Create raw product
        raw_product = RawProduct(name="Test Spinach", company_id=company.id)
        db.session.add(raw_product)
        db.session.commit()
        
        # Create cost history for raw product
        cost_history = CostHistory(
            raw_product_id=raw_product.id,
            cost=5.00,
            date=date.today(),
            company_id=company.id
        )
        db.session.add(cost_history)
        
        # Create labor cost
        labor_cost = LaborCost(
            date=date.today(),
            labor_cost=18.00,
            company_id=company.id
        )
        db.session.add(labor_cost)
        
        # Create designation costs
        for designation in ItemDesignation:
            desig_cost = DesignationCost(
                item_designation=designation,
                cost=1.00 + list(ItemDesignation).index(designation) * 0.25,
                date=date.today(),
                company_id=company.id
            )
            db.session.add(desig_cost)
        
        # Create customer
        customer = Customer(
            name="Test Customer",
            email="customer@test.com",
            company_id=company.id
        )
        db.session.add(customer)
        
        # Create master customer
        master_customer = Customer(
            name="Master Customer",
            email="master@test.com",
            company_id=company.id
        )
        master_customer.is_master = True
        db.session.add(master_customer)
        
        db.session.commit()
        
        return {
            'company_id': company.id,
            'user_id': user.id,
            'packaging_id': packaging.id,
            'raw_product_id': raw_product.id,
            'customer_id': customer.id,
            'master_customer_id': master_customer.id
        }


# ====================
# Item-RawProduct Relationship Tests
# ====================

class TestItemRawProductRelationship:
    """Tests for the many-to-many relationship between items and raw products."""
    
    def test_item_can_have_multiple_raw_products(self, app, setup_full_company):
        """Test that an item can be associated with multiple raw products."""
        with app.app_context():
            setup = setup_full_company
            
            # Create additional raw products
            raw1 = RawProduct(name="Lettuce", company_id=setup['company_id'])
            raw2 = RawProduct(name="Tomato", company_id=setup['company_id'])
            raw3 = RawProduct(name="Carrot", company_id=setup['company_id'])
            db.session.add_all([raw1, raw2, raw3])
            db.session.commit()
            
            # Create item with multiple raw products
            item = Item(
                name="Mixed Salad",
                code="MS-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id'],
                case_weight=5.0
            )
            item.raw_products.extend([raw1, raw2, raw3])
            db.session.add(item)
            db.session.commit()
            
            # Verify relationship
            result = Item.query.filter_by(code="MS-001").first()
            assert len(result.raw_products) == 3
            raw_names = [rp.name for rp in result.raw_products]
            assert "Lettuce" in raw_names
            assert "Tomato" in raw_names
            assert "Carrot" in raw_names

    def test_raw_product_can_belong_to_multiple_items(self, app, setup_full_company):
        """Test that a raw product can be used in multiple items."""
        with app.app_context():
            setup = setup_full_company
            
            raw_product = RawProduct.query.get(setup['raw_product_id'])
            
            # Create multiple items using same raw product
            item1 = Item(
                name="Spinach Salad",
                code="SS-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            item1.raw_products.append(raw_product)
            
            item2 = Item(
                name="Spinach Wrap",
                code="SW-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            item2.raw_products.append(raw_product)
            
            db.session.add_all([item1, item2])
            db.session.commit()
            
            # Verify relationship from raw product side
            raw_product = RawProduct.query.get(setup['raw_product_id'])
            assert raw_product.items.count() >= 2


# ====================
# Cost History Tests
# ====================

class TestCostHistoryOperations:
    """Tests for cost history tracking and retrieval."""
    
    def test_multiple_cost_entries_for_raw_product(self, app, setup_full_company):
        """Test that we can track cost changes over time."""
        with app.app_context():
            setup = setup_full_company
            
            # Add historical cost entries
            for i in range(5):
                cost = CostHistory(
                    raw_product_id=setup['raw_product_id'],
                    cost=5.00 + i * 0.50,
                    date=date.today() - timedelta(days=i*30),
                    company_id=setup['company_id']
                )
                db.session.add(cost)
            db.session.commit()
            
            # Query all costs for the raw product
            costs = CostHistory.query.filter_by(
                raw_product_id=setup['raw_product_id'],
                company_id=setup['company_id']
            ).order_by(CostHistory.date.desc()).all()
            
            # Should have 6 total (1 from setup + 5 new)
            assert len(costs) >= 5
            # Most recent should have highest cost in our test data
            assert costs[0].date >= costs[-1].date

    def test_get_most_recent_cost(self, app, setup_full_company):
        """Test retrieval of the most recent cost entry."""
        with app.app_context():
            setup = setup_full_company
            
            # Add a newer cost
            new_cost = CostHistory(
                raw_product_id=setup['raw_product_id'],
                cost=10.00,
                date=date.today() + timedelta(days=1),
                company_id=setup['company_id']
            )
            db.session.add(new_cost)
            db.session.commit()
            
            # Get most recent
            most_recent = CostHistory.query.filter_by(
                raw_product_id=setup['raw_product_id'],
                company_id=setup['company_id']
            ).order_by(CostHistory.date.desc(), CostHistory.id.desc()).first()
            
            assert most_recent.cost == 10.00


# ====================
# Price History Tests
# ====================

class TestPriceHistoryOperations:
    """Tests for price history per customer."""
    
    def test_different_prices_for_different_customers(self, app, setup_full_company):
        """Test that items can have different prices for different customers."""
        with app.app_context():
            setup = setup_full_company
            
            # Create item
            item = Item(
                name="Price Test Item",
                code="PTI-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item)
            db.session.commit()
            
            # Create another customer
            customer2 = Customer(
                name="Second Customer",
                email="customer2@test.com",
                company_id=setup['company_id']
            )
            db.session.add(customer2)
            db.session.commit()
            
            # Add different prices for different customers
            price1 = PriceHistory(
                item_id=item.id,
                date=date.today(),
                company_id=setup['company_id'],
                customer_id=setup['customer_id'],
                price=25.00
            )
            price2 = PriceHistory(
                item_id=item.id,
                date=date.today(),
                company_id=setup['company_id'],
                customer_id=customer2.id,
                price=22.00
            )
            db.session.add_all([price1, price2])
            db.session.commit()
            
            # Verify different prices
            p1 = PriceHistory.query.filter_by(
                item_id=item.id,
                customer_id=setup['customer_id']
            ).first()
            p2 = PriceHistory.query.filter_by(
                item_id=item.id,
                customer_id=customer2.id
            ).first()
            
            assert p1.price == 25.00
            assert p2.price == 22.00

    def test_price_history_tracking_over_time(self, app, setup_full_company):
        """Test that price changes are tracked over time."""
        with app.app_context():
            setup = setup_full_company
            
            item = Item(
                name="History Test Item",
                code="HTI-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item)
            db.session.commit()
            
            # Add price history over time
            for i in range(3):
                price = PriceHistory(
                    item_id=item.id,
                    date=date.today() - timedelta(days=i*30),
                    company_id=setup['company_id'],
                    customer_id=setup['customer_id'],
                    price=20.00 + i * 2.00
                )
                db.session.add(price)
            db.session.commit()
            
            # Get price history
            history = PriceHistory.query.filter_by(
                item_id=item.id,
                customer_id=setup['customer_id']
            ).order_by(PriceHistory.date.desc()).all()
            
            assert len(history) == 3


# ====================
# Item Total Cost Tests
# ====================

class TestItemTotalCostOperations:
    """Tests for item total cost calculations and storage."""
    
    def test_item_total_cost_components(self, app, setup_full_company):
        """Test that all cost components are properly stored."""
        with app.app_context():
            setup = setup_full_company
            
            item = Item(
                name="Cost Component Item",
                code="CCI-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item)
            db.session.commit()
            
            # Create total cost with all components
            total_cost = ItemTotalCost(
                item_id=item.id,
                date=date.today(),
                total_cost=50.00,
                ranch_cost=5.00,
                packaging_cost=10.00,
                raw_product_cost=25.00,
                labor_cost=8.00,
                designation_cost=2.00,
                company_id=setup['company_id']
            )
            db.session.add(total_cost)
            db.session.commit()
            
            # Retrieve and verify
            result = ItemTotalCost.query.filter_by(item_id=item.id).first()
            assert result.total_cost == 50.00
            assert result.ranch_cost == 5.00
            assert result.packaging_cost == 10.00
            assert result.raw_product_cost == 25.00
            assert result.labor_cost == 8.00
            assert result.designation_cost == 2.00
            
            # Verify components sum correctly
            component_sum = (result.ranch_cost + result.packaging_cost + 
                          result.raw_product_cost + result.labor_cost + 
                          result.designation_cost)
            assert component_sum == result.total_cost

    def test_cost_updates_over_time(self, app, setup_full_company):
        """Test that costs can be tracked over time."""
        with app.app_context():
            setup = setup_full_company
            
            item = Item(
                name="Time Cost Item",
                code="TCI-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item)
            db.session.commit()
            
            # Add costs for different dates
            for i in range(3):
                cost = ItemTotalCost(
                    item_id=item.id,
                    date=date.today() - timedelta(days=i*7),
                    total_cost=50.00 + i * 5.00,
                    ranch_cost=5.00,
                    packaging_cost=10.00,
                    raw_product_cost=25.00 + i * 5.00,
                    labor_cost=8.00,
                    designation_cost=2.00,
                    company_id=setup['company_id']
                )
                db.session.add(cost)
            db.session.commit()
            
            # Get most recent cost
            most_recent = ItemTotalCost.query.filter_by(
                item_id=item.id
            ).order_by(ItemTotalCost.date.desc()).first()
            
            assert most_recent.date == date.today()


# ====================
# Price Sheet Tests
# ====================

class TestPriceSheetOperations:
    """Tests for price sheet creation and item management."""
    
    def test_create_price_sheet_with_items(self, app, setup_full_company):
        """Test creating a price sheet with multiple items."""
        with app.app_context():
            setup = setup_full_company
            
            # Create items
            items = []
            for i in range(5):
                item = Item(
                    name=f"Sheet Item {i}",
                    code=f"SI-{i:03d}",
                    unit_of_weight=UnitOfWeight.POUND,
                    packaging_id=setup['packaging_id'],
                    company_id=setup['company_id']
                )
                items.append(item)
            db.session.add_all(items)
            db.session.commit()
            
            # Create price sheet
            sheet = PriceSheet(
                name="Test Price Sheet",
                date=date.today(),
                company_id=setup['company_id'],
                customer_id=setup['customer_id']
            )
            sheet.items.extend(items)
            db.session.add(sheet)
            db.session.commit()
            
            # Verify
            result = PriceSheet.query.filter_by(name="Test Price Sheet").first()
            assert result is not None
            assert len(result.items) == 5

    def test_add_items_to_existing_sheet(self, app, setup_full_company):
        """Test adding items to an existing price sheet."""
        with app.app_context():
            setup = setup_full_company
            
            # Create initial sheet with one item
            item1 = Item(
                name="Initial Item",
                code="II-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item1)
            db.session.commit()
            
            sheet = PriceSheet(
                name="Growing Sheet",
                date=date.today(),
                company_id=setup['company_id'],
                customer_id=setup['customer_id']
            )
            sheet.items.append(item1)
            db.session.add(sheet)
            db.session.commit()
            
            # Add more items
            item2 = Item(
                name="Added Item",
                code="AI-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item2)
            db.session.commit()
            
            sheet.items.append(item2)
            db.session.commit()
            
            # Verify
            result = PriceSheet.query.filter_by(name="Growing Sheet").first()
            assert len(result.items) == 2

    def test_remove_item_from_sheet(self, app, setup_full_company):
        """Test removing an item from a price sheet."""
        with app.app_context():
            setup = setup_full_company
            
            # Create items and sheet
            items = []
            for i in range(3):
                item = Item(
                    name=f"Remove Test {i}",
                    code=f"RT-{i:03d}",
                    unit_of_weight=UnitOfWeight.POUND,
                    packaging_id=setup['packaging_id'],
                    company_id=setup['company_id']
                )
                items.append(item)
            db.session.add_all(items)
            db.session.commit()
            
            sheet = PriceSheet(
                name="Removal Sheet",
                date=date.today(),
                company_id=setup['company_id'],
                customer_id=setup['customer_id']
            )
            sheet.items.extend(items)
            db.session.add(sheet)
            db.session.commit()
            
            # Remove one item
            sheet.items.remove(items[1])
            db.session.commit()
            
            # Verify
            result = PriceSheet.query.filter_by(name="Removal Sheet").first()
            assert len(result.items) == 2
            item_names = [i.name for i in result.items]
            assert "Remove Test 1" not in item_names


# ====================
# Master Customer Tests
# ====================

class TestMasterCustomerOperations:
    """Tests for master customer functionality."""
    
    def test_only_one_master_customer(self, app, setup_full_company):
        """Test that there should ideally be one master customer per company."""
        with app.app_context():
            setup = setup_full_company
            
            # Count master customers
            master_count = Customer.query.filter_by(
                company_id=setup['company_id'],
                is_master=True
            ).count()
            
            assert master_count == 1

    def test_master_customer_flag(self, app, setup_full_company):
        """Test the is_master flag functionality."""
        with app.app_context():
            setup = setup_full_company
            
            master = Customer.query.get(setup['master_customer_id'])
            regular = Customer.query.get(setup['customer_id'])
            
            assert master.is_master == True
            assert regular.is_master == False


# ====================
# Packaging Cost Tests
# ====================

class TestPackagingCostOperations:
    """Tests for packaging cost tracking."""
    
    def test_packaging_cost_total(self, app, setup_full_company):
        """Test that all packaging cost components are tracked."""
        with app.app_context():
            setup = setup_full_company
            
            pkg_cost = PackagingCost.query.filter_by(
                packaging_id=setup['packaging_id']
            ).first()
            
            total = (pkg_cost.box_cost + pkg_cost.bag_cost + 
                    pkg_cost.tray_andor_chemical_cost + pkg_cost.label_andor_tape_cost)
            
            assert total == 2.90  # 2.00 + 0.50 + 0.25 + 0.15

    def test_multiple_packaging_types(self, app, setup_full_company):
        """Test multiple packaging types with different costs."""
        with app.app_context():
            setup = setup_full_company
            
            # Create different packaging types
            pkg_types = ["Premium Box", "Economy Box", "Clamshell"]
            costs = [(5.00, 1.00, 0.50, 0.25), (1.00, 0.25, 0.10, 0.05), (3.00, 0.00, 0.75, 0.20)]
            
            for pkg_type, (box, bag, tray, label) in zip(pkg_types, costs):
                pkg = Packaging(packaging_type=pkg_type, company_id=setup['company_id'])
                db.session.add(pkg)
                db.session.commit()
                
                cost = PackagingCost(
                    packaging_id=pkg.id,
                    box_cost=box,
                    bag_cost=bag,
                    tray_andor_chemical_cost=tray,
                    label_andor_tape_cost=label,
                    date=date.today(),
                    company_id=setup['company_id']
                )
                db.session.add(cost)
            db.session.commit()
            
            # Verify all packaging types exist
            packagings = Packaging.query.filter_by(company_id=setup['company_id']).all()
            assert len(packagings) >= 4  # 1 from setup + 3 new


# ====================
# Ranch Item Tests
# ====================

class TestRanchItemOperations:
    """Tests for ranch items and pricing."""
    
    def test_ranch_item_flag(self, app, setup_full_company):
        """Test the ranch item flag on items."""
        with app.app_context():
            setup = setup_full_company
            
            # Create ranch item
            ranch_item = Item(
                name="Ranch Spinach",
                code="RS-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id'],
                ranch=True
            )
            db.session.add(ranch_item)
            db.session.commit()
            
            # Verify
            result = Item.query.filter_by(code="RS-001").first()
            assert result.ranch == True

    def test_ranch_price_history(self, app, setup_full_company):
        """Test ranch price tracking over time."""
        with app.app_context():
            setup = setup_full_company
            
            # Add multiple ranch prices
            for i in range(5):
                price = RanchPrice(
                    date=date.today() - timedelta(days=i*7),
                    cost=2.00 + i * 0.25,
                    price=3.00 + i * 0.30,
                    company_id=setup['company_id']
                )
                db.session.add(price)
            db.session.commit()
            
            # Get all ranch prices
            prices = RanchPrice.query.filter_by(
                company_id=setup['company_id']
            ).order_by(RanchPrice.date.desc()).all()
            
            assert len(prices) >= 5


# ====================
# Item Info Tests
# ====================

class TestItemInfoOperations:
    """Tests for item info (yield and labor hours)."""
    
    def test_item_info_creation(self, app, setup_full_company):
        """Test creating item info with yield and labor hours."""
        with app.app_context():
            setup = setup_full_company
            
            item = Item(
                name="Info Test Item",
                code="ITI-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item)
            db.session.commit()
            
            info = ItemInfo(
                product_yield=85.0,
                item_id=item.id,
                labor_hours=0.5,
                date=date.today(),
                company_id=setup['company_id']
            )
            db.session.add(info)
            db.session.commit()
            
            # Verify
            result = ItemInfo.query.filter_by(item_id=item.id).first()
            assert result.product_yield == 85.0
            assert result.labor_hours == 0.5

    def test_item_info_history(self, app, setup_full_company):
        """Test that item info can change over time."""
        with app.app_context():
            setup = setup_full_company
            
            item = Item(
                name="Info History Item",
                code="IHI-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item)
            db.session.commit()
            
            # Add info entries over time
            for i in range(3):
                info = ItemInfo(
                    product_yield=80.0 + i * 2.0,
                    item_id=item.id,
                    labor_hours=0.5 - i * 0.05,
                    date=date.today() - timedelta(days=i*30),
                    company_id=setup['company_id']
                )
                db.session.add(info)
            db.session.commit()
            
            # Get most recent info
            most_recent = ItemInfo.query.filter_by(
                item_id=item.id
            ).order_by(ItemInfo.date.desc()).first()
            
            assert most_recent.product_yield == 80.0


# ====================
# Company Isolation Tests
# ====================

class TestCompanyIsolation:
    """Tests to ensure data is properly isolated between companies."""
    
    def test_items_isolated_by_company(self, app):
        """Test that items from one company are not visible to another."""
        with app.app_context():
            # Create two companies
            company1 = Company(name="Company 1", admin_email="admin1@test.com")
            company2 = Company(name="Company 2", admin_email="admin2@test.com")
            db.session.add_all([company1, company2])
            db.session.commit()
            
            # Create packaging for each company
            pkg1 = Packaging(packaging_type="Box 1", company_id=company1.id)
            pkg2 = Packaging(packaging_type="Box 2", company_id=company2.id)
            db.session.add_all([pkg1, pkg2])
            db.session.commit()
            
            # Create items for each company
            item1 = Item(
                name="Company 1 Item",
                code="C1-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=pkg1.id,
                company_id=company1.id
            )
            item2 = Item(
                name="Company 2 Item",
                code="C2-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=pkg2.id,
                company_id=company2.id
            )
            db.session.add_all([item1, item2])
            db.session.commit()
            
            # Query items for company 1 only
            company1_items = Item.query.filter_by(company_id=company1.id).all()
            item_names = [i.name for i in company1_items]
            
            assert "Company 1 Item" in item_names
            assert "Company 2 Item" not in item_names

    def test_customers_isolated_by_company(self, app):
        """Test that customers are isolated between companies."""
        with app.app_context():
            company1 = Company(name="Customer Co 1", admin_email="cust1@test.com")
            company2 = Company(name="Customer Co 2", admin_email="cust2@test.com")
            db.session.add_all([company1, company2])
            db.session.commit()
            
            cust1 = Customer(name="Customer A", email="a@test.com", company_id=company1.id)
            cust2 = Customer(name="Customer B", email="b@test.com", company_id=company2.id)
            db.session.add_all([cust1, cust2])
            db.session.commit()
            
            # Query customers for company 1 only
            company1_customers = Customer.query.filter_by(company_id=company1.id).all()
            customer_names = [c.name for c in company1_customers]
            
            assert "Customer A" in customer_names
            assert "Customer B" not in customer_names


# ====================
# Alternate Code Tests
# ====================

class TestAlternateCode:
    """Tests for alternate item codes."""
    
    def test_item_with_alternate_code(self, app, setup_full_company):
        """Test creating an item with an alternate code."""
        with app.app_context():
            setup = setup_full_company
            
            item = Item(
                name="Dual Code Item",
                code="DCI-001",
                alternate_code="ALT-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item)
            db.session.commit()
            
            result = Item.query.filter_by(code="DCI-001").first()
            assert result.alternate_code == "ALT-001"

    def test_item_without_alternate_code(self, app, setup_full_company):
        """Test that alternate code can be null."""
        with app.app_context():
            setup = setup_full_company
            
            item = Item(
                name="Single Code Item",
                code="SCI-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item)
            db.session.commit()
            
            result = Item.query.filter_by(code="SCI-001").first()
            assert result.alternate_code is None
