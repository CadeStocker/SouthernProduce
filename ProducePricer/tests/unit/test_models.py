import re
import pytest
from datetime import date, timedelta
from producepricer import db  # Add this import
from producepricer.models import (
    Company,
    CostHistory,
    ItemTotalCost,
    RanchPrice, 
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

# def test_cascade_delete_company(app):
#     """Test that deleting a company cascades to its users and items."""
#     with app.app_context():
#         # Create company
#         company = Company(name="Cascade Company", admin_email="cascade@test.com")
#         db.session.add(company)
#         db.session.commit()
        
#         # Create users for the company
#         user1 = User(
#             first_name="Cascade", 
#             last_name="User1", 
#             email="cascade1@test.com",
#             password="password1", 
#             company_id=company.id
#         )
        
#         user2 = User(
#             first_name="Cascade", 
#             last_name="User2", 
#             email="cascade2@test.com",
#             password="password2", 
#             company_id=company.id
#         )
        
#         db.session.add_all([user1, user2])
#         db.session.commit()
        
#         # Create items for the company
#         packaging = Packaging(packaging_type="Cascade Box", company_id=company.id)
#         db.session.add(packaging)
#         db.session.commit()
        
#         item1 = Item(
#             name="Cascade Item 1", 
#             code="CAS001", 
#             unit_of_weight=UnitOfWeight.POUND, 
#             packaging_id=packaging.id, 
#             company_id=company.id
#         )
        
#         item2 = Item(
#             name="Cascade Item 2", 
#             code="CAS002", 
#             unit_of_weight=UnitOfWeight.POUND, 
#             packaging_id=packaging.id, 
#             company_id=company.id
#         )
        
#         db.session.add_all([item1, item2])
#         db.session.commit()
        
#         # Verify data was created
#         assert User.query.filter_by(company_id=company.id).count() == 2
#         assert Item.query.filter_by(company_id=company.id).count() == 2
#         assert Packaging.query.filter_by(company_id=company.id).count() == 1
        
#         # Delete the company
#         db.session.delete(company)
#         db.session.commit()
        
#         # Verify cascaded deletion
#         assert Company.query.filter_by(id=company.id).first() is None
#         assert User.query.filter_by(company_id=company.id).count() == 0
#         assert Item.query.filter_by(company_id=company.id).count() == 0
#         assert Packaging.query.filter_by(company_id=company.id).count() == 0

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
        item1.raw_products.append(raw_product1)  # Apples
        item1.raw_products.append(raw_product2)  # Oranges
        db.session.add(item1)
        db.session.commit()


        item2 = Item(
            name="Fruit Mix B",
            code="MIX002",
            unit_of_weight=UnitOfWeight.POUND, 
            packaging_id=packaging.id, 
            company_id=company.id
        )
        item2.raw_products.append(raw_product2)  # Oranges
        item2.raw_products.append(raw_product3)  # Bananas
        db.session.add(item2)
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
        assert raw_product2.items.count() == 2

        assert queried_item1 in raw_product1.items  # Apples should only be in Mix A
        assert raw_product1.items.count() == 1

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
            price = 10.00 + (i * 0.5)  # Price increases by $0.75 each month back in time

            ranch_price = RanchPrice(
                price=price,
                date=month_date,
                cost=8.00 + (i * 0.25),  # Cost increases by $0.25 each month back in time
                #raw_product_id=raw_product.id,
                company_id=company.id
            )
            prices.append(ranch_price)
        
        db.session.add_all(prices)
        db.session.commit()

        # Query ranch prices
        ranch_prices = RanchPrice.query.filter_by(company_id=company.id).order_by(RanchPrice.date.desc()).all()

        # Verify ranch prices
        assert len(ranch_prices) == 6
        for i, ranch_price in enumerate(ranch_prices):
            expected_price = 10.00 + (i * 0.5)
            expected_cost = 8.00 + (i * 0.25)
            assert ranch_price.price == expected_price
            assert ranch_price.cost == expected_cost
            assert ranch_price.date == (today.replace(day=1) - timedelta(days=30 * i))

            # Verify the company association
            assert ranch_price.company_id == company.id

        

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

        # Create raw product
        raw_product = RawProduct(name="Cost History Product", company_id=company.id)
        db.session.add(raw_product)
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
            raw_product_id=raw_product.id,
            cost=8.75,  # Cost per unit
            date=test_date,
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
        cost = CostHistory.query.filter_by().first()
        price = PriceHistory.query.filter_by(item_id=item.id, date=test_date).first()
        
        # Verify cost and price
        assert cost is not None
        assert cost.cost == 8.75
        assert cost.date == test_date

        assert price is not None
        assert price.price == 12.50

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

def test_user_model_fields():
    """Test that the User model has the expected fields."""
    # Create a user instance
    user = User(
        first_name="John",
        last_name="Doe",
        email="john.doe@example.com",
        password="hashed_password",
        company_id=1
    )
    
    # Check field values
    assert user.first_name == "John"
    assert user.last_name == "Doe"
    assert user.email == "john.doe@example.com"
    assert user.password == "hashed_password"
    assert user.company_id == 1
    
    # Check that the id field is not set yet (as the user hasn't been saved)
    assert user.id is None

def test_user_email_validation(app):
    """Test email validation for User model."""
    with app.app_context():
        # Create a company for foreign key constraint
        company = Company(name="Email Test Company", admin_email="admin@emailtest.com")
        db.session.add(company)
        db.session.commit()
        
        # Valid email formats
        valid_emails = [
            "user@example.com",
            "user.name@example.com",
            "user+tag@example.com",
            "user-name@example-site.com",
            "user_name@example.co.uk"
        ]
        
        for email in valid_emails:
            user = User(
                first_name="Test", 
                last_name="User", 
                email=email,
                password="password",
                company_id=company.id
            )
            db.session.add(user)
            db.session.commit()
            
            # Check the user was created with the email
            retrieved_user = User.query.filter_by(email=email).first()
            assert retrieved_user is not None
            assert retrieved_user.email == email
            
            # Clean up
            db.session.delete(user)
            db.session.commit()
        
        # Test email uniqueness constraint
        user1 = User(
            first_name="First", 
            last_name="User", 
            email="duplicate@example.com",
            password="password1",
            company_id=company.id
        )
        db.session.add(user1)
        db.session.commit()
        
        # Try to create another user with the same email
        user2 = User(
            first_name="Second", 
            last_name="User", 
            email="duplicate@example.com",
            password="password2",
            company_id=company.id
        )
        db.session.add(user2)
        
        # This should fail due to unique constraint
        with pytest.raises(Exception) as excinfo:
            db.session.commit()
        
        # Check if the error is related to uniqueness constraint
        assert "UNIQUE constraint failed" in str(excinfo.value) or "unique constraint" in str(excinfo.value).lower()
        
        # Clean up
        db.session.rollback()
        db.session.delete(user1)
        db.session.commit()

def test_user_password_hashing_verification(app, bcrypt):
    """Test password hashing and verification for User model."""
    with app.app_context():
        # Create a company
        company = Company(name="Password Test Company", admin_email="admin@passwordtest.com")
        db.session.add(company)
        db.session.commit()
        
        # Plain password
        plain_password = "SecurePassword123!"
        
        # Hash the password
        hashed_password = bcrypt.generate_password_hash(plain_password).decode('utf-8')
        
        # Create a user with the hashed password
        user = User(
            first_name="Password",
            last_name="Tester",
            email="password.test@example.com",
            password=hashed_password,
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()
        
        # Retrieve the user
        retrieved_user = User.query.filter_by(email="password.test@example.com").first()
        
        # Verify password is stored as hash (not plaintext)
        assert retrieved_user.password != plain_password
        
        # Check that the hash appears to be bcrypt format (starts with $2b$)
        assert re.match(r'^\$2[abxy]\$', retrieved_user.password) is not None
        
        # Verify the correct password passes verification
        assert bcrypt.check_password_hash(retrieved_user.password, plain_password) is True
        
        # Verify incorrect passwords fail verification
        assert bcrypt.check_password_hash(retrieved_user.password, "WrongPassword") is False
        assert bcrypt.check_password_hash(retrieved_user.password, "securepassword123!") is False
        assert bcrypt.check_password_hash(retrieved_user.password, "SecurePassword123") is False

def test_user_deletion_cascade(app):
    """Test that deleting a user doesn't cascade delete company."""
    with app.app_context():
        # Create a company
        company = Company(name="Cascade Test Company", admin_email="cascade@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create multiple users in the company
        user1 = User(
            first_name="User",
            last_name="One",
            email="user.one@example.com",
            password="password1",
            company_id=company.id
        )
        
        user2 = User(
            first_name="User",
            last_name="Two",
            email="user.two@example.com",
            password="password2",
            company_id=company.id
        )
        
        db.session.add_all([user1, user2])
        db.session.commit()
        
        # Verify users were created
        assert User.query.filter_by(company_id=company.id).count() == 2
        
        # Delete the first user
        db.session.delete(user1)
        db.session.commit()
        
        # Verify user1 is deleted
        assert User.query.filter_by(email="user.one@example.com").first() is None
        
        # Verify user2 still exists
        assert User.query.filter_by(email="user.two@example.com").first() is not None
        
        # Most importantly, verify company still exists
        assert Company.query.filter_by(id=company.id).first() is not None

def test_user_company_relationship(app):
    """Test the relationship between User and Company models."""
    with app.app_context():
        # Create multiple companies
        company1 = Company(name="Company One", admin_email="admin@company1.com")
        company2 = Company(name="Company Two", admin_email="admin@company2.com")
        db.session.add_all([company1, company2])
        db.session.commit()
        
        # Create users in different companies
        user1 = User(
            first_name="Company1",
            last_name="User",
            email="user@company1.com",
            password="password1",
            company_id=company1.id
        )
        
        user2 = User(
            first_name="Company2",
            last_name="User",
            email="user@company2.com",
            password="password2",
            company_id=company2.id
        )
        
        db.session.add_all([user1, user2])
        db.session.commit()
        
        # Query users by company
        company1_users = User.query.filter_by(company_id=company1.id).all()
        company2_users = User.query.filter_by(company_id=company2.id).all()
        
        # Verify correct assignment
        assert len(company1_users) == 1
        assert len(company2_users) == 1
        assert company1_users[0].email == "user@company1.com"
        assert company2_users[0].email == "user@company2.com"
        
        # If relationship is set up correctly, check backref
        if hasattr(company1, 'users'):
            assert user1 in company1.users
            assert user1 not in company2.users
            assert user2 in company2.users
            assert user2 not in company1.users

def test_item_total_cost_creation():
    """Test creating an ItemTotalCost instance."""
    item_cost = ItemTotalCost(
        item_id=1,
        date=date.today(),
        ranch_cost=5.75,
        total_cost=15.50,
        packaging_cost=2.25,
        raw_product_cost=5.75,
        labor_cost=4.50,
        designation_cost=3.00,
        company_id=1
    )
    
    # Verify field values
    assert item_cost.item_id == 1
    assert item_cost.date == date.today()
    assert item_cost.ranch_cost == 5.75
    assert item_cost.total_cost == 15.50
    assert item_cost.packaging_cost == 2.25
    assert item_cost.raw_product_cost == 5.75
    assert item_cost.labor_cost == 4.50
    assert item_cost.designation_cost == 3.00
    assert item_cost.company_id == 1
    
    # ID should not be set yet as it's auto-incremented
    assert item_cost.id is None

def test_item_total_cost_db_operations(app):
    """Test ItemTotalCost database operations."""
    with app.app_context():
        # Create company and item first
        company = Company(name="Cost Testing Company", admin_email="cost@test.com")
        db.session.add(company)
        db.session.commit()
        
        packaging = Packaging(packaging_type="Cost Test Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        item = Item(
            name="Cost Test Item",
            code="COST123",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id,
            company_id=company.id
        )
        db.session.add(item)
        db.session.commit()
        
        # Create an ItemTotalCost entry
        test_date = date.today()
        item_cost = ItemTotalCost(
            item_id=item.id,
            date=test_date,
            ranch_cost=5.75,
            total_cost=15.50,
            packaging_cost=2.25,
            raw_product_cost=5.75,
            labor_cost=4.50,
            designation_cost=3.00,
            company_id=company.id
        )
        db.session.add(item_cost)
        db.session.commit()
        
        # Retrieve and verify
        retrieved_cost = ItemTotalCost.query.filter_by(item_id=item.id, date=test_date).first()
        
        assert retrieved_cost is not None
        assert retrieved_cost.id is not None
        assert retrieved_cost.ranch_cost == 5.75
        assert retrieved_cost.total_cost == 15.50
        assert retrieved_cost.packaging_cost == 2.25
        assert retrieved_cost.raw_product_cost == 5.75
        assert retrieved_cost.labor_cost == 4.50
        assert retrieved_cost.designation_cost == 3.00
        
        # Update the entry
        retrieved_cost.total_cost = 16.25
        retrieved_cost.labor_cost = 5.25
        db.session.commit()
        
        # Verify update
        updated_cost = db.session.get(ItemTotalCost, retrieved_cost.id)
        assert updated_cost.total_cost == 16.25
        assert updated_cost.labor_cost == 5.25
        
        # Delete the entry
        db.session.delete(updated_cost)
        db.session.commit()
        
        # Verify deletion
        assert db.session.get(ItemTotalCost, updated_cost.id) is None

def test_item_total_cost_calculation_accuracy(app):
    """Test that ItemTotalCost calculations are accurate."""
    with app.app_context():
        # Create company and item
        company = Company(name="Calculation Company", admin_email="calc@test.com")
        db.session.add(company)
        db.session.commit()
        
        packaging = Packaging(packaging_type="Calc Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        item = Item(
            name="Calculation Item",
            code="CALC123",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id,
            company_id=company.id
        )
        db.session.add(item)
        db.session.commit()
        
        # Set up costs
        ranch_cost = 6.50
        packaging_cost = 2.75
        raw_product_cost = 6.50
        labor_cost = 5.25
        designation_cost = 2.50
        
        # Calculate expected total
        expected_total = ranch_cost + packaging_cost + raw_product_cost + labor_cost + designation_cost
        
        # Create ItemTotalCost entry
        test_date = date.today()
        item_cost = ItemTotalCost(
            item_id=item.id,
            date=test_date,
            ranch_cost=ranch_cost,
            packaging_cost=packaging_cost,
            raw_product_cost=raw_product_cost,
            labor_cost=labor_cost,
            designation_cost=designation_cost,
            total_cost=expected_total,  # Using our calculated total
            company_id=company.id
        )
        db.session.add(item_cost)
        db.session.commit()
        
        # Retrieve and verify calculation
        retrieved_cost = ItemTotalCost.query.filter_by(item_id=item.id, date=test_date).first()
        
        calculated_total = (
            retrieved_cost.ranch_cost + 
            retrieved_cost.packaging_cost + 
            retrieved_cost.raw_product_cost + 
            retrieved_cost.labor_cost + 
            retrieved_cost.designation_cost
        )
        
        # Assert that our calculated total matches the stored total cost
        assert round(calculated_total, 2) == round(retrieved_cost.total_cost, 2)
        assert round(calculated_total, 2) == round(expected_total, 2)

def test_item_total_cost_historical_tracking(app):
    """Test tracking ItemTotalCost over time."""
    with app.app_context():
        # Create company and item
        company = Company(name="History Company", admin_email="history@test.com")
        db.session.add(company)
        db.session.commit()
        
        packaging = Packaging(packaging_type="History Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        item = Item(
            name="History Item",
            code="HIST123",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id,
            company_id=company.id
        )
        db.session.add(item)
        db.session.commit()
        
        # Create cost records for different dates with increasing costs
        base_date = date.today()
        costs = []
        
        for i in range(5):
            record_date = base_date - timedelta(days=i*30)  # Every 30 days back in time
            
            # Increase costs as we go back in time (simulating inflation)
            cost = ItemTotalCost(
                item_id=item.id,
                date=record_date,
                ranch_cost=5.00 + (i * 0.25),
                packaging_cost=2.00 + (i * 0.15),
                raw_product_cost=5.00 + (i * 0.25),
                labor_cost=4.00 + (i * 0.20),
                designation_cost=2.50 + (i * 0.10),
                total_cost=18.50 + (i * 0.95),  # Sum of individual costs
                company_id=company.id
            )
            costs.append(cost)
        
        db.session.add_all(costs)
        db.session.commit()
        
        # Retrieve costs in date order (newest first)
        history = ItemTotalCost.query.filter_by(item_id=item.id).order_by(ItemTotalCost.date.desc()).all()
        
        # Verify we have 5 records
        assert len(history) == 5
        
        # Verify dates are in correct order
        for i in range(4):
            assert history[i].date > history[i+1].date
        
        # Verify costs are lower for newer entries (since we added higher costs to older dates)
        assert history[0].total_cost < history[4].total_cost
        
        # Calculate average cost
        avg_total = sum(h.total_cost for h in history) / len(history)
        
        # Calculate cost increase percentage from newest to oldest
        cost_increase = ((history[4].total_cost - history[0].total_cost) / history[0].total_cost) * 100
        
        # Verify the cost increase is approximately what we expect (4 increases of ~5% each)
        # This will depend on your test data, adjust as needed
        assert 15 < cost_increase < 25  # Roughly 20% increase

def test_item_total_cost_relationships(app):
    """Test relationships between ItemTotalCost and related models."""
    with app.app_context():
        # Create company
        company = Company(name="Relationship Company", admin_email="rel@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create item prerequisites
        packaging = Packaging(packaging_type="Rel Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create two items
        item1 = Item(
            name="Relationship Item 1",
            code="REL001",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id,
            company_id=company.id
        )
        
        item2 = Item(
            name="Relationship Item 2",
            code="REL002",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id,
            company_id=company.id
        )
        
        db.session.add_all([item1, item2])
        db.session.commit()
        
        # Create ItemTotalCost entries for both items
        test_date = date.today()
        
        item1_cost = ItemTotalCost(
            item_id=item1.id,
            date=test_date,
            ranch_cost=5.25,
            packaging_cost=2.00,
            raw_product_cost=5.25,
            labor_cost=4.25,
            designation_cost=2.50,
            total_cost=19.25,
            company_id=company.id
        )
        
        item2_cost = ItemTotalCost(
            item_id=item2.id,
            date=test_date,
            ranch_cost=6.75,
            packaging_cost=2.25,
            raw_product_cost=6.75,
            labor_cost=4.50,
            designation_cost=3.00,
            total_cost=23.25,
            company_id=company.id
        )
        
        db.session.add_all([item1_cost, item2_cost])
        db.session.commit()
        
        # Query by company
        company_costs = ItemTotalCost.query.filter_by(company_id=company.id).all()
        assert len(company_costs) == 2
        
        # Query by item
        item1_costs = ItemTotalCost.query.filter_by(item_id=item1.id).all()
        item2_costs = ItemTotalCost.query.filter_by(item_id=item2.id).all()
        
        assert len(item1_costs) == 1
        assert len(item2_costs) == 1
        
        # Verify costs are associated with correct items
        assert item1_costs[0].total_cost == 19.25
        assert item2_costs[0].total_cost == 23.25
        
        # If you have relationships defined in your models, test those too
        # For example, if Item has a relationship to ItemTotalCost:
        if hasattr(item1, 'total_costs'):
            assert len(item1.total_costs) == 1
            assert item1.total_costs[0].total_cost == 19.25

def test_item_total_cost_filtering(app):
    """Test filtering ItemTotalCost by date ranges."""
    with app.app_context():
        # Create company and item
        company = Company(name="Filter Company", admin_email="filter@test.com")
        db.session.add(company)
        db.session.commit()
        
        packaging = Packaging(packaging_type="Filter Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        item = Item(
            name="Filter Item",
            code="FILT123",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id,
            company_id=company.id
        )
        db.session.add(item)
        db.session.commit()
        
        # Create cost entries for different dates
        today = date.today()
        dates = [
            today,
            today - timedelta(days=30),
            today - timedelta(days=60),
            today - timedelta(days=90),
            today - timedelta(days=120)
        ]
        
        # Create costs for each date
        for i, record_date in enumerate(dates):
            cost = ItemTotalCost(
                item_id=item.id,
                date=record_date,
                ranch_cost=5.00,
                packaging_cost=2.00,
                raw_product_cost=5.00,
                labor_cost=4.00,
                designation_cost=2.50,
                total_cost=18.50,
                company_id=company.id
            )
            db.session.add(cost)
        db.session.commit()
        
        # Test filtering by exact date
        exact_date_results = ItemTotalCost.query.filter_by(
            item_id=item.id,
            date=today
        ).all()
        assert len(exact_date_results) == 1
        
        # Test filtering by date range (last 60 days)
        sixty_days_ago = today - timedelta(days=60)
        date_range_results = ItemTotalCost.query.filter(
            ItemTotalCost.item_id == item.id,
            ItemTotalCost.date >= sixty_days_ago
        ).all()
        assert len(date_range_results) == 3  # Today, 30 days ago, 60 days ago
        
        # Test filtering by date range with multiple conditions
        ninety_days_ago = today - timedelta(days=90)
        thirty_days_ago = today - timedelta(days=30)
        
        middle_range_results = ItemTotalCost.query.filter(
            ItemTotalCost.item_id == item.id,
            ItemTotalCost.date >= ninety_days_ago,
            ItemTotalCost.date <= thirty_days_ago
        ).all()
        assert len(middle_range_results) == 3  # 30, 60, and 90 days ago

def test_item_creation():
    """Test creating an Item instance with all fields."""
    item = Item(
        name="Premium Tomatoes",
        code="TOM001",
        alternate_code="ALT-TOM-001",
        unit_of_weight=UnitOfWeight.POUND,
        ranch=True,
        case_weight=25.5,
        packaging_id=1,
        item_designation=ItemDesignation.RETAIL,
        company_id=1
    )
    
    # Verify all fields
    assert item.name == "Premium Tomatoes"
    assert item.code == "TOM001"
    assert item.alternate_code == "ALT-TOM-001"
    assert item.unit_of_weight == UnitOfWeight.POUND
    assert item.ranch is True
    assert item.case_weight == 25.5
    assert item.packaging_id == 1
    assert item.item_designation == ItemDesignation.RETAIL
    assert item.company_id == 1
    
    # ID should not be set (as it's auto-incremented)
    assert item.id is None

def test_item_defaults():
    """Test default values for Item fields."""
    item = Item(
        name="Basic Item",
        code="BASIC001",
        unit_of_weight=UnitOfWeight.POUND,
        packaging_id=1,
        company_id=1
    )
    
    # Check default values
    assert item.ranch is False
    assert item.case_weight == 0.0
    assert item.item_designation == ItemDesignation.FOODSERVICE
    # Alternate code should be None by default
    assert item.alternate_code is None

def test_item_db_operations(app):
    """Test database operations with Item model."""
    with app.app_context():
        # Create prerequisites
        company = Company(name="Item Test Company", admin_email="item@test.com")
        db.session.add(company)
        db.session.commit()
        
        packaging = Packaging(packaging_type="Item Test Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create an item
        item = Item(
            name="Database Test Item",
            code="DB001",
            alternate_code="ALT-DB-001",
            unit_of_weight=UnitOfWeight.POUND,
            ranch=True,
            case_weight=30.0,
            packaging_id=packaging.id,
            item_designation=ItemDesignation.FOODSERVICE,
            company_id=company.id
        )
        db.session.add(item)
        db.session.commit()
        
        # Retrieve the item
        retrieved_item = Item.query.filter_by(code="DB001").first()
        
        # Verify all fields were saved correctly
        assert retrieved_item is not None
        assert retrieved_item.id is not None
        assert retrieved_item.name == "Database Test Item"
        assert retrieved_item.code == "DB001"
        assert retrieved_item.alternate_code == "ALT-DB-001"
        assert retrieved_item.unit_of_weight == UnitOfWeight.POUND
        assert retrieved_item.ranch is True
        assert retrieved_item.case_weight == 30.0
        assert retrieved_item.packaging_id == packaging.id
        assert retrieved_item.item_designation == ItemDesignation.FOODSERVICE
        assert retrieved_item.company_id == company.id
        
        # Update the item
        retrieved_item.name = "Updated Item Name"
        retrieved_item.case_weight = 32.5
        db.session.commit()
        
        # Verify updates
        updated_item = db.session.get(Item, retrieved_item.id)
        assert updated_item.name == "Updated Item Name"
        assert updated_item.case_weight == 32.5
        
        # Delete the item
        db.session.delete(updated_item)
        db.session.commit()
        
        # Verify deletion
        assert db.session.get(Item, updated_item.id) is None

def test_item_enum_fields(app):
    """Test enum fields in Item model."""
    with app.app_context():
        # Create company and packaging
        company = Company(name="Enum Test Company", admin_email="enum@test.com")
        db.session.add(company)
        db.session.commit()
        
        packaging = Packaging(packaging_type="Enum Test Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create items with different enum values
        retail_item = Item(
            name="Retail Item",
            code="RETAIL001",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id,
            item_designation=ItemDesignation.RETAIL,
            company_id=company.id
        )
        
        foodservice_item = Item(
            name="Foodservice Item",
            code="FOOD001",
            unit_of_weight=UnitOfWeight.KILOGRAM,
            packaging_id=packaging.id,
            item_designation=ItemDesignation.FOODSERVICE,
            company_id=company.id
        )
        
        processing_item = Item(
            name="Processing Item",
            code="PROC001",
            unit_of_weight=UnitOfWeight.OUNCE,
            packaging_id=packaging.id,
            item_designation=ItemDesignation.SNAKPAK,
            company_id=company.id
        )
        
        db.session.add_all([retail_item, foodservice_item, processing_item])
        db.session.commit()
        
        # Verify enum values were saved correctly
        assert Item.query.filter_by(code="RETAIL001").first().item_designation == ItemDesignation.RETAIL
        assert Item.query.filter_by(code="FOOD001").first().item_designation == ItemDesignation.FOODSERVICE
        assert Item.query.filter_by(code="PROC001").first().item_designation == ItemDesignation.SNAKPAK
        
        assert Item.query.filter_by(code="RETAIL001").first().unit_of_weight == UnitOfWeight.POUND
        assert Item.query.filter_by(code="FOOD001").first().unit_of_weight == UnitOfWeight.KILOGRAM
        assert Item.query.filter_by(code="PROC001").first().unit_of_weight == UnitOfWeight.OUNCE
        
        # Test filtering by enum values
        retail_items = Item.query.filter_by(item_designation=ItemDesignation.RETAIL).all()
        assert len(retail_items) == 1
        assert retail_items[0].code == "RETAIL001"
        
        pound_items = Item.query.filter_by(unit_of_weight=UnitOfWeight.POUND).all()
        assert len(pound_items) == 1
        assert pound_items[0].code == "RETAIL001"

def test_item_raw_product_relationship(app):
    """Test many-to-many relationship between Item and RawProduct."""
    with app.app_context():
        # Create prerequisites
        company = Company(name="Relationship Test Company", admin_email="relation@test.com")
        db.session.add(company)
        db.session.commit()
        
        packaging = Packaging(packaging_type="Relationship Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create raw products
        raw_product1 = RawProduct(name="Raw Material 1", company_id=company.id)
        raw_product2 = RawProduct(name="Raw Material 2", company_id=company.id)
        raw_product3 = RawProduct(name="Raw Material 3", company_id=company.id)
        db.session.add_all([raw_product1, raw_product2, raw_product3])
        db.session.commit()
        
        # Create items with raw product relationships
        item1 = Item(
            name="Compound Item 1",
            code="COMP001",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id,
            company_id=company.id
        )
        item1.raw_products.append(raw_product1)
        item1.raw_products.append(raw_product2)
        
        item2 = Item(
            name="Compound Item 2",
            code="COMP002",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id,
            company_id=company.id
        )
        item2.raw_products.append(raw_product2)
        item2.raw_products.append(raw_product3)
        
        db.session.add_all([item1, item2])
        db.session.commit()
        
        # Verify relationships
        retrieved_item1 = Item.query.filter_by(code="COMP001").first()
        retrieved_item2 = Item.query.filter_by(code="COMP002").first()
        
        # Check raw products for each item
        assert len(retrieved_item1.raw_products) == 2
        assert len(retrieved_item2.raw_products) == 2
        
        # Check specific raw products are in the correct items
        assert raw_product1 in retrieved_item1.raw_products
        assert raw_product2 in retrieved_item1.raw_products
        assert raw_product2 in retrieved_item2.raw_products
        assert raw_product3 in retrieved_item2.raw_products
        
        # Check raw_product1 is only in item1
        assert raw_product1 not in retrieved_item2.raw_products
        
        # Check raw_product3 is only in item2
        assert raw_product3 not in retrieved_item1.raw_products
        
        # Check items from raw products' perspective
        assert retrieved_item1 in raw_product1.items.all()
        assert retrieved_item2 not in raw_product1.items.all()
        
        # Raw product 2 should be in both items
        assert retrieved_item1 in raw_product2.items.all()
        assert retrieved_item2 in raw_product2.items.all()
        assert raw_product2.items.count() == 2
        
        # Modify relationships
        retrieved_item1.raw_products.remove(raw_product1)
        db.session.commit()
        
        # Check the modification worked
        updated_item1 = Item.query.filter_by(code="COMP001").first()
        assert len(updated_item1.raw_products) == 1
        assert raw_product1 not in updated_item1.raw_products
        assert raw_product2 in updated_item1.raw_products

def test_item_filtering_by_attributes(app):
    """Test filtering Items by various attributes."""
    with app.app_context():
        # Create prerequisites
        company = Company(name="Filter Test Company", admin_email="filter@test.com")
        db.session.add(company)
        db.session.commit()
        
        packaging = Packaging(packaging_type="Filter Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create items with different attributes
        items = [
            Item(
                name="Ranch Item 1",
                code="RANCH001",
                unit_of_weight=UnitOfWeight.POUND,
                ranch=True,
                case_weight=25.0,
                packaging_id=packaging.id,
                item_designation=ItemDesignation.RETAIL,
                company_id=company.id
            ),
            Item(
                name="Ranch Item 2",
                code="RANCH002",
                unit_of_weight=UnitOfWeight.POUND,
                ranch=True,
                case_weight=30.0,
                packaging_id=packaging.id,
                item_designation=ItemDesignation.FOODSERVICE,
                company_id=company.id
            ),
            Item(
                name="Non-Ranch Item 1",
                code="NONR001",
                unit_of_weight=UnitOfWeight.KILOGRAM,
                ranch=False,
                case_weight=15.0,
                packaging_id=packaging.id,
                item_designation=ItemDesignation.RETAIL,
                company_id=company.id
            ),
            Item(
                name="Non-Ranch Item 2",
                code="NONR002",
                alternate_code="SPECIAL-001",
                unit_of_weight=UnitOfWeight.OUNCE,
                ranch=False,
                case_weight=10.0,
                packaging_id=packaging.id,
                item_designation=ItemDesignation.SNAKPAK,
                company_id=company.id
            )
        ]
        db.session.add_all(items)
        db.session.commit()
        
        # Filter by ranch attribute
        ranch_items = Item.query.filter_by(ranch=True).all()
        assert len(ranch_items) == 2
        assert all(item.ranch for item in ranch_items)
        
        # Filter by item designation
        retail_items = Item.query.filter_by(item_designation=ItemDesignation.RETAIL).all()
        assert len(retail_items) == 2
        assert all(item.item_designation == ItemDesignation.RETAIL for item in retail_items)
        
        # Filter by unit of weight
        pound_items = Item.query.filter_by(unit_of_weight=UnitOfWeight.POUND).all()
        assert len(pound_items) == 2
        
        # Filter by case weight range
        heavy_items = Item.query.filter(Item.case_weight > 20.0).all()
        assert len(heavy_items) == 2
        assert all(item.case_weight > 20.0 for item in heavy_items)
        
        # Filter by alternate code
        special_items = Item.query.filter_by(alternate_code="SPECIAL-001").all()
        assert len(special_items) == 1
        assert special_items[0].code == "NONR002"
        
        # Combine filters
        retail_ranch_items = Item.query.filter_by(
            ranch=True,
            item_designation=ItemDesignation.RETAIL
        ).all()
        assert len(retail_ranch_items) == 1
        assert retail_ranch_items[0].code == "RANCH001"

def test_item_code_not_unique(app):
    """Test that item codes don't have to be unique."""
    with app.app_context():
        # Create prerequisites
        company1 = Company(name="Company One", admin_email="one@test.com")
        company2 = Company(name="Company Two", admin_email="two@test.com")
        db.session.add_all([company1, company2])
        db.session.commit()
        
        packaging1 = Packaging(packaging_type="Box One", company_id=company1.id)
        packaging2 = Packaging(packaging_type="Box Two", company_id=company2.id)
        db.session.add_all([packaging1, packaging2])
        db.session.commit()
        
        # Create items with same code in different companies
        item1 = Item(
            name="Item Company 1",
            code="SAME001",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging1.id,
            company_id=company1.id
        )
        
        item2 = Item(
            name="Item Company 2",
            code="SAME001",  # Same code
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging2.id,
            company_id=company2.id
        )
        
        db.session.add_all([item1, item2])
        
        # This should succeed since code isn't unique
        db.session.commit()
        
        # Verify both items exist
        company1_item = Item.query.filter_by(code="SAME001", company_id=company1.id).first()
        company2_item = Item.query.filter_by(code="SAME001", company_id=company2.id).first()
        
        assert company1_item is not None
        assert company2_item is not None
        assert company1_item.id != company2_item.id
        
        # Create another item with the same code in the same company
        item3 = Item(
            name="Another Item Company 1",
            code="SAME001",  # Same code in same company
            unit_of_weight=UnitOfWeight.OUNCE,
            packaging_id=packaging1.id,
            company_id=company1.id
        )
        
        db.session.add(item3)
        db.session.commit()
        
        # Verify all three items exist
        same_code_items = Item.query.filter_by(code="SAME001").all()
        assert len(same_code_items) == 3

def test_item_packaging_relationship(app):
    """Test the relationship between Item and Packaging."""
    with app.app_context():
        # Create company
        company = Company(name="Packaging Relationship Company", admin_email="pkg_rel@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create packaging types
        packaging1 = Packaging(packaging_type="Standard Box", company_id=company.id)
        packaging2 = Packaging(packaging_type="Premium Box", company_id=company.id)
        db.session.add_all([packaging1, packaging2])
        db.session.commit()
        
        # Create items with different packaging
        standard_item = Item(
            name="Standard Item",
            code="STD001",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging1.id,
            company_id=company.id
        )
        
        premium_item = Item(
            name="Premium Item",
            code="PREM001",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging2.id,
            company_id=company.id
        )
        
        db.session.add_all([standard_item, premium_item])
        db.session.commit()
        
        # Verify the relationships
        retrieved_standard = Item.query.filter_by(code="STD001").first()
        retrieved_premium = Item.query.filter_by(code="PREM001").first()
        
        # Check packaging IDs
        assert retrieved_standard.packaging_id == packaging1.id
        assert retrieved_premium.packaging_id == packaging2.id
        
        # If you have a relationship/backref set up, you could also check that
        # For example, if Packaging has a relationship to its items:
        if hasattr(packaging1, 'items'):
            assert retrieved_standard in packaging1.items
            assert retrieved_premium not in packaging1.items
            assert retrieved_premium in packaging2.items