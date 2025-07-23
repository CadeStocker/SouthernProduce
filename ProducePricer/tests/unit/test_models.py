import pytest
from datetime import date
from producepricer import db  # Add this import
from producepricer.models import (
    Company, 
    User, 
    Item, 
    RawProduct, 
    ItemDesignation, 
    UnitOfWeight, 
    Packaging,
    Customer,
    PriceSheet,
    PriceHistory,
    LaborCost,
    ItemInfo,
    PackagingCost
)

def test_company_creation():
    """Test creating a new company."""
    company = Company(name="Test Company", admin_email="admin@test.com")
    assert company.name == "Test Company"
    assert company.admin_email == "admin@test.com"

def test_user_creation():
    """Test creating a new user."""
    user = User(first_name="John", last_name="Doe", email="john@test.com", 
                password="hashed_password", company_id=1)
    assert user.first_name == "John"
    assert user.last_name == "Doe"
    assert user.email == "john@test.com"
    assert user.password == "hashed_password"
    assert user.company_id == 1

def test_packaging_creation():
    """Test creating new packaging."""
    packaging = Packaging(packaging_type="Box", company_id=1)
    assert packaging.packaging_type == "Box"
    assert packaging.company_id == 1

def test_raw_product_creation():
    """Test creating a new raw product."""
    raw_product = RawProduct(name="Tomatoes", company_id=1)
    assert raw_product.name == "Tomatoes"
    assert raw_product.company_id == 1

def test_db_company_creation(app):
    """Test creating a company in the database."""
    with app.app_context():
        # Create a new company
        company = Company(name="Test DB Company", admin_email="db@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Query the company
        queried_company = Company.query.filter_by(name="Test DB Company").first()
        
        # Check if the company was created correctly
        assert queried_company is not None
        assert queried_company.name == "Test DB Company"
        assert queried_company.admin_email == "db@test.com"

def test_db_user_creation(app):
    """Test creating a user in the database."""
    with app.app_context():
        # Create a new company
        company = Company(name="User Test Company", admin_email="user@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create a new user
        user = User(
            first_name="Jane", 
            last_name="Smith", 
            email="jane@test.com",
            password="hashed_password", 
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()
        
        # Query the user
        queried_user = User.query.filter_by(email="jane@test.com").first()
        
        # Check if the user was created correctly
        assert queried_user is not None
        assert queried_user.first_name == "Jane"
        assert queried_user.last_name == "Smith"
        assert queried_user.email == "jane@test.com"
        assert queried_user.company_id == company.id

def test_customer_creation(app):
    """Test creating a customer in the database."""
    with app.app_context():
        # Create a company first
        company = Company(name="Test Customer Company", admin_email="customer@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create a customer
        customer = Customer(
            name="Test Customer",
            email="test@customer.com",
            company_id=company.id
        )
        db.session.add(customer)
        db.session.commit()
        
        # Query the customer
        queried_customer = Customer.query.filter_by(email="test@customer.com").first()
        
        # Check if the customer was created correctly
        assert queried_customer is not None
        assert queried_customer.name == "Test Customer"
        assert queried_customer.email == "test@customer.com"
        assert queried_customer.company_id == company.id

def test_price_sheet_creation(app):
    """Test creating a price sheet with items."""
    with app.app_context():
        # Create required objects first
        company = Company(name="Price Sheet Company", admin_email="pricesheet@test.com")
        db.session.add(company)
        db.session.commit()
        
        customer = Customer(name="Price Sheet Customer", email="customer@pricesheet.com", company_id=company.id)
        db.session.add(customer)
        
        packaging = Packaging(packaging_type="Price Sheet Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create items
        item1 = Item(
            name="Price Sheet Item 1", 
            code="PS001", 
            unit_of_weight=UnitOfWeight.POUND, 
            packaging_id=packaging.id, 
            company_id=company.id,
            item_designation=ItemDesignation.RETAIL
        )
        
        item2 = Item(
            name="Price Sheet Item 2", 
            code="PS002", 
            unit_of_weight=UnitOfWeight.POUND, 
            packaging_id=packaging.id, 
            company_id=company.id,
            item_designation=ItemDesignation.FOODSERVICE
        )
        
        db.session.add(item1)
        db.session.add(item2)
        db.session.commit()
        
        # Create price sheet
        price_sheet = PriceSheet(
            name="Test Price Sheet",
            date=date.today(),
            company_id=company.id,
            customer_id=customer.id
        )
        
        # Add items to price sheet
        price_sheet.items.append(item1)
        price_sheet.items.append(item2)
        
        db.session.add(price_sheet)
        db.session.commit()
        
        # Query the price sheet
        queried_price_sheet = PriceSheet.query.filter_by(name="Test Price Sheet").first()
        
        # Verify the price sheet was created correctly
        assert queried_price_sheet is not None
        assert queried_price_sheet.name == "Test Price Sheet"
        assert queried_price_sheet.customer_id == customer.id
        assert len(queried_price_sheet.items) == 2
        
        # Check that the items are associated with the price sheet
        assert item1 in queried_price_sheet.items
        assert item2 in queried_price_sheet.items

def test_price_history(app):
    """Test creating and retrieving price history."""
    with app.app_context():
        # Create required objects
        company = Company(name="Price History Company", admin_email="pricehistory@test.com")
        db.session.add(company)
        db.session.commit()
        
        customer = Customer(name="Price History Customer", email="customer@pricehistory.com", company_id=company.id)
        db.session.add(customer)
        
        packaging = Packaging(packaging_type="Price History Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        item = Item(
            name="Price History Item", 
            code="PH001", 
            unit_of_weight=UnitOfWeight.POUND, 
            packaging_id=packaging.id, 
            company_id=company.id
        )
        db.session.add(item)
        db.session.commit()
        
        # Create price history entries
        price_history1 = PriceHistory(
            item_id=item.id,
            date=date(2023, 1, 1),
            company_id=company.id,
            customer_id=customer.id,
            price=10.50
        )
        
        price_history2 = PriceHistory(
            item_id=item.id,
            date=date(2023, 2, 1),
            company_id=company.id,
            customer_id=customer.id,
            price=11.25
        )
        
        db.session.add(price_history1)
        db.session.add(price_history2)
        db.session.commit()
        
        # Query the price history entries
        history_entries = PriceHistory.query.filter_by(item_id=item.id).order_by(PriceHistory.date).all()
        
        # Verify the price history entries
        assert len(history_entries) == 2
        assert history_entries[0].price == 10.50
        assert history_entries[1].price == 11.25
        assert history_entries[0].date == date(2023, 1, 1)
        assert history_entries[1].date == date(2023, 2, 1)

def test_labor_cost(app):
    """Test creating and retrieving labor cost."""
    with app.app_context():
        # Create company
        company = Company(name="Labor Cost Company", admin_email="labor@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create labor costs for different dates
        labor_cost1 = LaborCost(
            date=date(2023, 1, 1),
            labor_cost=25.50,
            company_id=company.id
        )
        
        labor_cost2 = LaborCost(
            date=date(2023, 2, 1),
            labor_cost=27.75,
            company_id=company.id
        )
        
        db.session.add(labor_cost1)
        db.session.add(labor_cost2)
        db.session.commit()
        
        # Query labor costs
        labor_costs = LaborCost.query.filter_by(company_id=company.id).order_by(LaborCost.date).all()
        
        # Verify labor costs
        assert len(labor_costs) == 2
        assert labor_costs[0].labor_cost == 25.50
        assert labor_costs[1].labor_cost == 27.75
        assert labor_costs[0].date == date(2023, 1, 1)
        assert labor_costs[1].date == date(2023, 2, 1)

def test_packaging_cost(app):
    """Test creating and retrieving packaging costs."""
    with app.app_context():
        # Create company and packaging
        company = Company(name="Packaging Cost Company", admin_email="packaging@test.com")
        db.session.add(company)
        db.session.commit()
        
        packaging = Packaging(packaging_type="Test Packaging", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create packaging cost
        packaging_cost = PackagingCost(
            box_cost=1.25,
            bag_cost=0.75,
            tray_andor_chemical_cost=0.50,
            label_andor_tape_cost=0.25,
            company_id=company.id,
            packaging_id=packaging.id,
            date=date.today()
        )
        db.session.add(packaging_cost)
        db.session.commit()
        
        # Query packaging cost
        queried_cost = PackagingCost.query.filter_by(packaging_id=packaging.id).first()
        
        # Verify packaging cost
        assert queried_cost is not None
        assert queried_cost.box_cost == 1.25
        assert queried_cost.bag_cost == 0.75
        assert queried_cost.tray_andor_chemical_cost == 0.50
        assert queried_cost.label_andor_tape_cost == 0.25
        assert queried_cost.company_id == company.id
        assert queried_cost.packaging_id == packaging.id

def test_item_info(app):
    """Test creating and retrieving item info."""
    with app.app_context():
        # Create company
        company = Company(name="Item Info Company", admin_email="iteminfo@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create packaging
        packaging = Packaging(packaging_type="Item Info Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create item
        item = Item(
            name="Item Info Test Item", 
            code="II001", 
            unit_of_weight=UnitOfWeight.POUND, 
            packaging_id=packaging.id, 
            company_id=company.id
        )
        db.session.add(item)
        db.session.commit()
        
        # Create item info
        item_info = ItemInfo(
            product_yield=0.85,
            item_id=item.id,
            labor_hours=2.5,
            date=date.today(),
            company_id=company.id
        )
        db.session.add(item_info)
        db.session.commit()
        
        # Query item info
        queried_info = ItemInfo.query.filter_by(item_id=item.id).first()
        
        # Verify item info
        assert queried_info is not None
        assert queried_info.product_yield == 0.85
        assert queried_info.labor_hours == 2.5
        assert queried_info.item_id == item.id
        assert queried_info.company_id == company.id

def test_cascade_delete_company(app):
    """Test that deleting a company cascades to its users and items."""
    with app.app_context():
        # Create company
        company = Company(name="Cascade Company", admin_email="cascade@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create users for the company
        user1 = User(
            first_name="Cascade", 
            last_name="User1", 
            email="cascade1@test.com",
            password="password1", 
            company_id=company.id
        )
        
        user2 = User(
            first_name="Cascade", 
            last_name="User2", 
            email="cascade2@test.com",
            password="password2", 
            company_id=company.id
        )
        
        db.session.add_all([user1, user2])
        db.session.commit()
        
        # Create items for the company
        packaging = Packaging(packaging_type="Cascade Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        item1 = Item(
            name="Cascade Item 1", 
            code="CAS001", 
            unit_of_weight=UnitOfWeight.POUND, 
            packaging_id=packaging.id, 
            company_id=company.id
        )
        
        item2 = Item(
            name="Cascade Item 2", 
            code="CAS002", 
            unit_of_weight=UnitOfWeight.POUND, 
            packaging_id=packaging.id, 
            company_id=company.id
        )
        
        db.session.add_all([item1, item2])
        db.session.commit()
        
        # Verify data was created
        assert User.query.filter_by(company_id=company.id).count() == 2
        assert Item.query.filter_by(company_id=company.id).count() == 2
        assert Packaging.query.filter_by(company_id=company.id).count() == 1
        
        # Delete the company
        db.session.delete(company)
        db.session.commit()
        
        # Verify cascaded deletion
        assert Company.query.filter_by(id=company.id).first() is None
        assert User.query.filter_by(company_id=company.id).count() == 0
        assert Item.query.filter_by(company_id=company.id).count() == 0
        assert Packaging.query.filter_by(company_id=company.id).count() == 0

def test_user_password_hashing(app, bcrypt):
    """Test that user passwords are properly hashed."""
    with app.app_context():
        # Create a company
        company = Company(name="Password Company", admin_email="password@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Plain password
        plain_password = "securepassword123"
        
        # Create a user with the hashed password
        user = User(
            first_name="Password",
            last_name="Test",
            email="password_test@example.com",
            password=bcrypt.generate_password_hash(plain_password).decode('utf-8'),
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()
        
        # Retrieve the user
        retrieved_user = User.query.filter_by(email="password_test@example.com").first()
        
        # Check that the password was properly hashed (not stored as plaintext)
        assert retrieved_user.password != plain_password
        
        # Check that the password hash can be verified
        assert bcrypt.check_password_hash(retrieved_user.password, plain_password) is True
        
        # Check that incorrect passwords fail verification
        assert bcrypt.check_password_hash(retrieved_user.password, "wrongpassword") is False

def test_raw_product_to_item_relationship(app):
    """Test the many-to-many relationship between items and raw products."""
    with app.app_context():
        # Create company
        company = Company(name="Relationship Company", admin_email="relation@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create packaging
        packaging = Packaging(packaging_type="Relationship Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create raw products
        raw_product1 = RawProduct(name="Apples", company_id=company.id)
        raw_product2 = RawProduct(name="Oranges", company_id=company.id)
        raw_product3 = RawProduct(name="Bananas", company_id=company.id)
        db.session.add_all([raw_product1, raw_product2, raw_product3])
        db.session.commit()
        
        # Create items with relationships to raw products
        item1 = Item(
            name="Fruit Mix A", 
            code="MIX001", 
            unit_of_weight=UnitOfWeight.POUND, 
            packaging_id=packaging.id, 
            company_id=company.id
        )
        item1.raw_products.extend([raw_product1, raw_product2])  # Apples and Oranges
        
        item2 = Item(
            name="Fruit Mix B", 
            code="MIX002", 
            unit_of_weight=UnitOfWeight.POUND, 
            packaging_id=packaging.id, 
            company_id=company.id
        )
        item2.raw_products.extend([raw_product2, raw_product3])  # Oranges and Bananas
        
        db.session.add_all([item1, item2])
        db.session.commit()
        
        # Query and verify relationships
        queried_item1 = Item.query.filter_by(code="MIX001").first()
        queried_item2 = Item.query.filter_by(code="MIX002").first()
        
        # Check raw products for each item
        assert len(queried_item1.raw_products) == 2
        assert len(queried_item2.raw_products) == 2
        
        # Check that the correct raw products are related to each item
        assert raw_product1 in queried_item1.raw_products
        assert raw_product2 in queried_item1.raw_products
        assert raw_product2 in queried_item2.raw_products
        assert raw_product3 in queried_item2.raw_products
        
        # Check that Apples is not in Fruit Mix B
        assert raw_product1 not in queried_item2.raw_products
        
        # Check items related to each raw product
        assert queried_item1 in raw_product2.items  # Oranges should be in both mixes
        assert len(raw_product2.items) == 2
        
        assert queried_item1 in raw_product1.items  # Apples should only be in Mix A
        assert len(raw_product1.items) == 1

def test_ranch_price_trends(app):
    """Test creating ranch prices over time and analyzing trends."""
    with app.app_context():
        # Create company
        company = Company(name="Ranch Price Company", admin_email="ranch@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create raw product
        raw_product = RawProduct(name="Premium Tomatoes", company_id=company.id)
        db.session.add(raw_product)
        db.session.commit()
        
        # Create ranch prices for the product over time (for the last 6 months)
        today = date.today()
        prices = []
        
        # Add prices with an increasing trend
        for i in range(6):
            month_date = today.replace(day=1) - timedelta(days=30 * i)
            price = 10.00 + (i * 0.50)  # Price increases by $0.50 each month back in time
            
            ranch_price = RanchPrice(
                price=price,
                date=month_date,
                raw_product_id=raw_product.id,
                company_id=company.id
            )
            prices.append(ranch_price)
        
        # Add prices in reverse order so oldest is added first
        db.session.add_all(reversed(prices))
        db.session.commit()
        
        # Query all prices for this raw product, ordered by date
        price_history = RanchPrice.query.filter_by(
            raw_product_id=raw_product.id
        ).order_by(RanchPrice.date).all()
        
        # Verify we have 6 price points
        assert len(price_history) == 6
        
        # Verify the price trend (prices should increase over time)
        for i in range(1, len(price_history)):
            assert price_history[i].price > price_history[i-1].price
            
        # Calculate average price
        total_price = sum(record.price for record in price_history)
        avg_price = total_price / len(price_history)
        
        # Verify the average is in the expected range
        assert 11.25 <= avg_price <= 12.75

def test_cost_history_calculation(app):
    """Test creating cost history and calculating profit margins."""
    with app.app_context():
        # Create company
        company = Company(name="Cost History Company", admin_email="costhistory@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create customer
        customer = Customer(name="Cost History Customer", email="customer@costhistory.com", company_id=company.id)
        db.session.add(customer)
        db.session.commit()
        
        # Create packaging
        packaging = Packaging(packaging_type="Cost History Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create item
        item = Item(
            name="Cost History Item", 
            code="COST001", 
            unit_of_weight=UnitOfWeight.POUND, 
            packaging_id=packaging.id, 
            company_id=company.id
        )
        db.session.add(item)
        db.session.commit()
        
        # Create cost history for the item
        test_date = date(2023, 6, 1)
        cost_history = CostHistory(
            item_id=item.id,
            date=test_date,
            raw_product_cost=5.00,
            packaging_cost=1.25,
            labor_cost=2.50,
            total_cost=8.75,  # Sum of above costs
            company_id=company.id
        )
        db.session.add(cost_history)
        
        # Create price history (selling price) for the same item and date
        price_history = PriceHistory(
            item_id=item.id,
            customer_id=customer.id,
            date=test_date,
            price=12.50,  # Selling price
            company_id=company.id
        )
        db.session.add(price_history)
        db.session.commit()
        
        # Query the data
        cost = CostHistory.query.filter_by(item_id=item.id, date=test_date).first()
        price = PriceHistory.query.filter_by(item_id=item.id, date=test_date).first()
        
        # Verify the data was saved correctly
        assert cost is not None
        assert price is not None
        assert cost.total_cost == 8.75
        assert price.price == 12.50
        
        # Calculate profit and margin
        profit = price.price - cost.total_cost
        margin_percentage = (profit / price.price) * 100
        
        # Verify calculations
        assert profit == 3.75
        assert round(margin_percentage, 2) == 30.00  # 30% profit margin

def test_item_with_multiple_prices_by_customer(app):
    """Test that an item can have different prices for different customers."""
    with app.app_context():
        # Create company
        company = Company(name="Multi-Price Company", admin_email="multiprice@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create customers
        customer1 = Customer(name="Premium Customer", email="premium@customer.com", company_id=company.id)
        customer2 = Customer(name="Standard Customer", email="standard@customer.com", company_id=company.id)
        customer3 = Customer(name="Budget Customer", email="budget@customer.com", company_id=company.id)
        db.session.add_all([customer1, customer2, customer3])
        db.session.commit()
        
        # Create packaging
        packaging = Packaging(packaging_type="Multi-Price Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create item
        item = Item(
            name="Premium Product", 
            code="PREM001", 
            unit_of_weight=UnitOfWeight.POUND, 
            packaging_id=packaging.id, 
            company_id=company.id
        )
        db.session.add(item)
        db.session.commit()
        
        # Set different prices for the same item for different customers
        price_date = date.today()
        
        price1 = PriceHistory(
            item_id=item.id,
            customer_id=customer1.id,
            date=price_date,
            price=15.99,  # Premium price
            company_id=company.id
        )
        
        price2 = PriceHistory(
            item_id=item.id,
            customer_id=customer2.id,
            date=price_date,
            price=12.50,  # Standard price
            company_id=company.id
        )
        
        price3 = PriceHistory(
            item_id=item.id,
            customer_id=customer3.id,
            date=price_date,
            price=9.99,  # Budget price
            company_id=company.id
        )
        
        db.session.add_all([price1, price2, price3])
        db.session.commit()
        
        # Query all prices for the item
        prices = PriceHistory.query.filter_by(
            item_id=item.id,
            date=price_date
        ).order_by(PriceHistory.price.desc()).all()
        
        # Verify that we have 3 different prices
        assert len(prices) == 3
        
        # Verify price order (highest to lowest)
        assert prices[0].price == 15.99
        assert prices[0].customer_id == customer1.id
        
        assert prices[1].price == 12.50
        assert prices[1].customer_id == customer2.id
        
        assert prices[2].price == 9.99
        assert prices[2].customer_id == customer3.id
        
        # Calculate price difference between premium and budget
        price_difference = prices[0].price - prices[2].price
        percentage_difference = (price_difference / prices[2].price) * 100
        
        # Premium is 60% more expensive than budget
        assert round(percentage_difference, 0) == 60