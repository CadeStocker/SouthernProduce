"""
Comprehensive unit tests for all models in the ProducePricer application.
These tests verify model creation, relationships, and basic database operations.
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
# Company Model Tests
# ====================

class TestCompanyModel:
    def test_company_creation_simple(self):
        """Test creating a company object without database."""
        company = Company(name="Test Company", admin_email="admin@test.com")
        assert company.name == "Test Company"
        assert company.admin_email == "admin@test.com"

    def test_company_repr(self):
        """Test company string representation."""
        company = Company(name="Acme Corp", admin_email="admin@acme.com")
        assert "Acme Corp" in repr(company)

    def test_company_db_creation(self, app):
        """Test creating a company in the database."""
        with app.app_context():
            company = Company(name="DB Test Company", admin_email="dbtest@test.com")
            db.session.add(company)
            db.session.commit()
            
            result = Company.query.filter_by(name="DB Test Company").first()
            assert result is not None
            assert result.admin_email == "dbtest@test.com"
            assert result.id is not None


# ====================
# User Model Tests
# ====================

class TestUserModel:
    def test_user_creation_simple(self):
        """Test creating a user object without database."""
        user = User(
            first_name="John",
            last_name="Doe",
            email="john@test.com",
            password="hashedpassword",
            company_id=1
        )
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.email == "john@test.com"

    def test_user_repr(self):
        """Test user string representation."""
        user = User(
            first_name="Jane",
            last_name="Smith",
            email="jane@test.com",
            password="password",
            company_id=1
        )
        assert "Jane" in repr(user)
        assert "Smith" in repr(user)
        assert "jane@test.com" in repr(user)

    def test_user_db_creation(self, app):
        """Test creating a user in the database with company relationship."""
        with app.app_context():
            company = Company(name="User Test Co", admin_email="admin@usertest.com")
            db.session.add(company)
            db.session.commit()
            
            user = User(
                first_name="Test",
                last_name="User",
                email="test@usertest.com",
                password="password123",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            result = User.query.filter_by(email="test@usertest.com").first()
            assert result is not None
            assert result.company_id == company.id
            assert result.company.name == "User Test Co"

    def test_user_company_relationship(self, app):
        """Test that users are properly linked to companies."""
        with app.app_context():
            company = Company(name="Relationship Test", admin_email="rel@test.com")
            db.session.add(company)
            db.session.commit()
            
            user1 = User(
                first_name="User", last_name="One",
                email="user1@test.com", password="pass",
                company_id=company.id
            )
            user2 = User(
                first_name="User", last_name="Two",
                email="user2@test.com", password="pass",
                company_id=company.id
            )
            db.session.add_all([user1, user2])
            db.session.commit()
            
            # Verify relationship through company
            company = Company.query.filter_by(name="Relationship Test").first()
            assert len(company.users) == 2


# ====================
# PendingUser Model Tests
# ====================

class TestPendingUserModel:
    def test_pending_user_creation(self):
        """Test creating a pending user object."""
        pending = PendingUser(
            first_name="Pending",
            last_name="User",
            email="pending@test.com",
            password="password",
            company_id=1
        )
        assert pending.first_name == "Pending"
        assert pending.email == "pending@test.com"

    def test_pending_user_db(self, app):
        """Test pending user database operations."""
        with app.app_context():
            company = Company(name="Pending Co", admin_email="pending@admin.com")
            db.session.add(company)
            db.session.commit()
            
            pending = PendingUser(
                first_name="New",
                last_name="User",
                email="new@pending.com",
                password="pass123",
                company_id=company.id
            )
            db.session.add(pending)
            db.session.commit()
            
            result = PendingUser.query.filter_by(email="new@pending.com").first()
            assert result is not None
            assert result.company_id == company.id


# ====================
# RawProduct Model Tests
# ====================

class TestRawProductModel:
    def test_raw_product_creation(self):
        """Test creating a raw product."""
        raw = RawProduct(name="Tomatoes", company_id=1)
        assert raw.name == "Tomatoes"
        assert raw.company_id == 1

    def test_raw_product_db(self, app):
        """Test raw product database operations."""
        with app.app_context():
            company = Company(name="Raw Test Co", admin_email="raw@test.com")
            db.session.add(company)
            db.session.commit()
            
            raw1 = RawProduct(name="Lettuce", company_id=company.id)
            raw2 = RawProduct(name="Carrots", company_id=company.id)
            db.session.add_all([raw1, raw2])
            db.session.commit()
            
            products = RawProduct.query.filter_by(company_id=company.id).all()
            assert len(products) == 2
            names = [p.name for p in products]
            assert "Lettuce" in names
            assert "Carrots" in names


# ====================
# Packaging Model Tests
# ====================

class TestPackagingModel:
    def test_packaging_creation(self):
        """Test creating packaging."""
        pkg = Packaging(packaging_type="Box", company_id=1)
        assert pkg.packaging_type == "Box"

    def test_packaging_db(self, app):
        """Test packaging database operations."""
        with app.app_context():
            company = Company(name="Pkg Co", admin_email="pkg@test.com")
            db.session.add(company)
            db.session.commit()
            
            pkg = Packaging(packaging_type="Clamshell", company_id=company.id)
            db.session.add(pkg)
            db.session.commit()
            
            result = Packaging.query.filter_by(packaging_type="Clamshell").first()
            assert result is not None
            assert result.company_id == company.id


# ====================
# PackagingCost Model Tests
# ====================

class TestPackagingCostModel:
    def test_packaging_cost_creation(self, app):
        """Test creating packaging cost."""
        with app.app_context():
            company = Company(name="Pkg Cost Co", admin_email="pkgcost@test.com")
            db.session.add(company)
            db.session.commit()
            
            pkg = Packaging(packaging_type="Test Pkg", company_id=company.id)
            db.session.add(pkg)
            db.session.commit()
            
            cost = PackagingCost(
                box_cost=1.50,
                bag_cost=0.75,
                tray_andor_chemical_cost=0.50,
                label_andor_tape_cost=0.25,
                company_id=company.id,
                packaging_id=pkg.id,
                date=date.today()
            )
            db.session.add(cost)
            db.session.commit()
            
            result = PackagingCost.query.filter_by(packaging_id=pkg.id).first()
            assert result is not None
            assert result.box_cost == 1.50
            assert result.bag_cost == 0.75

    def test_packaging_cost_total(self, app):
        """Test total packaging cost calculation."""
        with app.app_context():
            company = Company(name="Cost Calc Co", admin_email="calc@test.com")
            db.session.add(company)
            db.session.commit()
            
            pkg = Packaging(packaging_type="Calc Pkg", company_id=company.id)
            db.session.add(pkg)
            db.session.commit()
            
            cost = PackagingCost(
                box_cost=1.00,
                bag_cost=0.50,
                tray_andor_chemical_cost=0.30,
                label_andor_tape_cost=0.20,
                company_id=company.id,
                packaging_id=pkg.id,
                date=date.today()
            )
            db.session.add(cost)
            db.session.commit()
            
            # Calculate total manually
            total = cost.box_cost + cost.bag_cost + cost.tray_andor_chemical_cost + cost.label_andor_tape_cost
            assert total == 2.00


# ====================
# Customer Model Tests
# ====================

class TestCustomerModel:
    def test_customer_creation(self):
        """Test creating a customer."""
        customer = Customer(name="Walmart", email="buyer@walmart.com", company_id=1)
        assert customer.name == "Walmart"
        assert customer.email == "buyer@walmart.com"

    def test_customer_db(self, app):
        """Test customer database operations."""
        with app.app_context():
            company = Company(name="Cust Co", admin_email="cust@test.com")
            db.session.add(company)
            db.session.commit()
            
            customer = Customer(
                name="Test Customer",
                email="customer@test.com",
                company_id=company.id
            )
            db.session.add(customer)
            db.session.commit()
            
            result = Customer.query.filter_by(name="Test Customer").first()
            assert result is not None
            assert result.is_master == False  # Default value


# ====================
# Item Model Tests
# ====================

class TestItemModel:
    def test_item_creation(self):
        """Test creating an item."""
        item = Item(
            name="Salad Mix",
            code="SM001",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=1,
            company_id=1,
            item_designation=ItemDesignation.RETAIL
        )
        assert item.name == "Salad Mix"
        assert item.code == "SM001"
        assert item.ranch == False

    def test_item_with_ranch(self):
        """Test creating a ranch item."""
        item = Item(
            name="Ranch Item",
            code="RI001",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=1,
            company_id=1,
            ranch=True
        )
        assert item.ranch == True

    def test_item_db_with_raw_products(self, app):
        """Test item with raw products relationship."""
        with app.app_context():
            company = Company(name="Item Co", admin_email="item@test.com")
            db.session.add(company)
            db.session.commit()
            
            pkg = Packaging(packaging_type="Item Pkg", company_id=company.id)
            db.session.add(pkg)
            
            raw1 = RawProduct(name="Spinach", company_id=company.id)
            raw2 = RawProduct(name="Arugula", company_id=company.id)
            db.session.add_all([raw1, raw2])
            db.session.commit()
            
            item = Item(
                name="Mixed Greens",
                code="MG001",
                unit_of_weight=UnitOfWeight.OUNCE,
                packaging_id=pkg.id,
                company_id=company.id,
                item_designation=ItemDesignation.FOODSERVICE
            )
            item.raw_products.append(raw1)
            item.raw_products.append(raw2)
            db.session.add(item)
            db.session.commit()
            
            result = Item.query.filter_by(code="MG001").first()
            assert result is not None
            assert len(result.raw_products) == 2

    def test_item_designations(self):
        """Test all item designations."""
        for designation in ItemDesignation:
            item = Item(
                name=f"{designation.value} Item",
                code=f"{designation.value}001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=1,
                company_id=1,
                item_designation=designation
            )
            assert item.item_designation == designation


# ====================
# CostHistory Model Tests
# ====================

class TestCostHistoryModel:
    def test_cost_history_creation(self, app):
        """Test creating cost history."""
        with app.app_context():
            company = Company(name="Cost Co", admin_email="cost@test.com")
            db.session.add(company)
            db.session.commit()
            
            raw = RawProduct(name="Cost Raw", company_id=company.id)
            db.session.add(raw)
            db.session.commit()
            
            cost = CostHistory(
                cost=5.50,
                date=date(2024, 1, 1),
                company_id=company.id,
                raw_product_id=raw.id
            )
            db.session.add(cost)
            db.session.commit()
            
            result = CostHistory.query.filter_by(raw_product_id=raw.id).first()
            assert result is not None
            assert result.cost == 5.50

    def test_cost_history_timeline(self, app):
        """Test cost history over time."""
        with app.app_context():
            company = Company(name="Timeline Co", admin_email="time@test.com")
            db.session.add(company)
            db.session.commit()
            
            raw = RawProduct(name="Timeline Raw", company_id=company.id)
            db.session.add(raw)
            db.session.commit()
            
            # Add costs for different dates
            dates_costs = [
                (date(2024, 1, 1), 5.00),
                (date(2024, 2, 1), 5.50),
                (date(2024, 3, 1), 5.25),
            ]
            
            for d, c in dates_costs:
                cost = CostHistory(
                    cost=c,
                    date=d,
                    company_id=company.id,
                    raw_product_id=raw.id
                )
                db.session.add(cost)
            db.session.commit()
            
            costs = CostHistory.query.filter_by(raw_product_id=raw.id).order_by(CostHistory.date).all()
            assert len(costs) == 3
            assert costs[0].cost == 5.00
            assert costs[2].cost == 5.25


# ====================
# LaborCost Model Tests
# ====================

class TestLaborCostModel:
    def test_labor_cost_creation(self, app):
        """Test creating labor cost."""
        with app.app_context():
            company = Company(name="Labor Co", admin_email="labor@test.com")
            db.session.add(company)
            db.session.commit()
            
            labor = LaborCost(
                date=date(2024, 1, 1),
                labor_cost=15.00,
                company_id=company.id
            )
            db.session.add(labor)
            db.session.commit()
            
            result = LaborCost.query.filter_by(company_id=company.id).first()
            assert result is not None
            assert result.labor_cost == 15.00


# ====================
# ItemInfo Model Tests
# ====================

class TestItemInfoModel:
    def test_item_info_creation(self, app):
        """Test creating item info."""
        with app.app_context():
            company = Company(name="Info Co", admin_email="info@test.com")
            db.session.add(company)
            db.session.commit()
            
            pkg = Packaging(packaging_type="Info Pkg", company_id=company.id)
            db.session.add(pkg)
            db.session.commit()
            
            item = Item(
                name="Info Item",
                code="II001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=pkg.id,
                company_id=company.id
            )
            db.session.add(item)
            db.session.commit()
            
            info = ItemInfo(
                product_yield=95.0,
                item_id=item.id,
                labor_hours=2.5,
                date=date.today(),
                company_id=company.id
            )
            db.session.add(info)
            db.session.commit()
            
            result = ItemInfo.query.filter_by(item_id=item.id).first()
            assert result is not None
            assert result.product_yield == 95.0
            assert result.labor_hours == 2.5


# ====================
# ItemTotalCost Model Tests
# ====================

class TestItemTotalCostModel:
    def test_item_total_cost_creation(self, app):
        """Test creating item total cost."""
        with app.app_context():
            company = Company(name="Total Cost Co", admin_email="total@test.com")
            db.session.add(company)
            db.session.commit()
            
            pkg = Packaging(packaging_type="Total Pkg", company_id=company.id)
            db.session.add(pkg)
            db.session.commit()
            
            item = Item(
                name="Total Item",
                code="TI001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=pkg.id,
                company_id=company.id
            )
            db.session.add(item)
            db.session.commit()
            
            total_cost = ItemTotalCost(
                item_id=item.id,
                date=date.today(),
                total_cost=10.00,
                ranch_cost=1.00,
                packaging_cost=2.00,
                raw_product_cost=5.00,
                labor_cost=1.50,
                designation_cost=0.50,
                company_id=company.id
            )
            db.session.add(total_cost)
            db.session.commit()
            
            result = ItemTotalCost.query.filter_by(item_id=item.id).first()
            assert result is not None
            assert result.total_cost == 10.00
            # Verify components add up
            component_sum = (
                result.ranch_cost + result.packaging_cost + 
                result.raw_product_cost + result.labor_cost + 
                result.designation_cost
            )
            assert component_sum == result.total_cost


# ====================
# PriceHistory Model Tests
# ====================

class TestPriceHistoryModel:
    def test_price_history_creation(self, app):
        """Test creating price history."""
        with app.app_context():
            company = Company(name="Price Co", admin_email="price@test.com")
            db.session.add(company)
            db.session.commit()
            
            customer = Customer(name="Price Customer", email="pc@test.com", company_id=company.id)
            pkg = Packaging(packaging_type="Price Pkg", company_id=company.id)
            db.session.add_all([customer, pkg])
            db.session.commit()
            
            item = Item(
                name="Price Item",
                code="PI001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=pkg.id,
                company_id=company.id
            )
            db.session.add(item)
            db.session.commit()
            
            price = PriceHistory(
                item_id=item.id,
                date=date.today(),
                company_id=company.id,
                customer_id=customer.id,
                price=12.99
            )
            db.session.add(price)
            db.session.commit()
            
            result = PriceHistory.query.filter_by(item_id=item.id).first()
            assert result is not None
            assert result.price == 12.99


# ====================
# PriceSheet Model Tests
# ====================

class TestPriceSheetModel:
    def test_price_sheet_creation(self, app):
        """Test creating a price sheet with items."""
        with app.app_context():
            company = Company(name="Sheet Co", admin_email="sheet@test.com")
            db.session.add(company)
            db.session.commit()
            
            customer = Customer(name="Sheet Customer", email="sc@test.com", company_id=company.id)
            pkg = Packaging(packaging_type="Sheet Pkg", company_id=company.id)
            db.session.add_all([customer, pkg])
            db.session.commit()
            
            items = []
            for i in range(3):
                item = Item(
                    name=f"Sheet Item {i}",
                    code=f"SI00{i}",
                    unit_of_weight=UnitOfWeight.POUND,
                    packaging_id=pkg.id,
                    company_id=company.id
                )
                items.append(item)
                db.session.add(item)
            db.session.commit()
            
            sheet = PriceSheet(
                name="Test Price Sheet",
                date=date.today(),
                company_id=company.id,
                customer_id=customer.id
            )
            for item in items:
                sheet.items.append(item)
            db.session.add(sheet)
            db.session.commit()
            
            result = PriceSheet.query.filter_by(name="Test Price Sheet").first()
            assert result is not None
            assert len(result.items) == 3


# ====================
# RanchPrice Model Tests
# ====================

class TestRanchPriceModel:
    def test_ranch_price_creation(self, app):
        """Test creating ranch price."""
        with app.app_context():
            company = Company(name="Ranch Co", admin_email="ranch@test.com")
            db.session.add(company)
            db.session.commit()
            
            ranch = RanchPrice(
                date=date.today(),
                cost=2.50,
                price=3.50,
                company_id=company.id
            )
            db.session.add(ranch)
            db.session.commit()
            
            result = RanchPrice.query.filter_by(company_id=company.id).first()
            assert result is not None
            assert result.cost == 2.50
            assert result.price == 3.50


# ====================
# DesignationCost Model Tests
# ====================

class TestDesignationCostModel:
    def test_designation_cost_creation(self, app):
        """Test creating designation costs."""
        with app.app_context():
            company = Company(name="Desig Co", admin_email="desig@test.com")
            db.session.add(company)
            db.session.commit()
            
            for designation in ItemDesignation:
                cost = DesignationCost(
                    item_designation=designation,
                    cost=1.00 + list(ItemDesignation).index(designation) * 0.5,
                    date=date.today(),
                    company_id=company.id
                )
                db.session.add(cost)
            db.session.commit()
            
            costs = DesignationCost.query.filter_by(company_id=company.id).all()
            assert len(costs) == len(ItemDesignation)


# ====================
# AIResponse Model Tests
# ====================

class TestAIResponseModel:
    def test_ai_response_creation(self, app):
        """Test creating AI response."""
        with app.app_context():
            company = Company(name="AI Co", admin_email="ai@test.com")
            db.session.add(company)
            db.session.commit()
            
            response = AIResponse(
                content="This is a test AI response",
                date=datetime.now(),
                company_id=company.id,
                name="Test Summary"
            )
            db.session.add(response)
            db.session.commit()
            
            result = AIResponse.query.filter_by(company_id=company.id).first()
            assert result is not None
            assert "test AI response" in result.content
            assert result.name == "Test Summary"


# ====================
# EmailTemplate Model Tests
# ====================

class TestEmailTemplateModel:
    def test_email_template_creation(self, app):
        """Test creating email template."""
        with app.app_context():
            company = Company(name="Email Co", admin_email="email@test.com")
            db.session.add(company)
            db.session.commit()
            
            template = EmailTemplate(
                name="Welcome Email",
                subject="Welcome to our service",
                body="Hello {{ customer_name }}, welcome!",
                company_id=company.id,
                is_default=True
            )
            db.session.add(template)
            db.session.commit()
            
            result = EmailTemplate.query.filter_by(company_id=company.id).first()
            assert result is not None
            assert result.name == "Welcome Email"
            assert result.is_default == True


# ====================
# Enum Tests
# ====================

class TestEnums:
    def test_unit_of_weight_enum(self):
        """Test all weight units exist."""
        expected_units = ['gram', 'kilogram', 'pound', 'ounce', 'pint', 'liter']
        for unit_value in expected_units:
            unit = UnitOfWeight(unit_value)
            assert unit.value == unit_value

    def test_item_designation_enum(self):
        """Test all item designations exist."""
        expected_designations = ['snakpak', 'retail', 'foodservice']
        for desig_value in expected_designations:
            desig = ItemDesignation(desig_value)
            assert desig.value == desig_value
