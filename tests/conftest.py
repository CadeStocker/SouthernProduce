# Copyright Cade Stocker 2026
import pytest
import os
import sys
import tempfile

# Add parent directory to path so we can import from the app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import directly from the app package
from app import create_app, db
from app.models import User, Company

@pytest.fixture
def app():
    app = create_app('sqlite:///:memory:')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
    app.config['SERVER_NAME'] = 'localhost.localdomain'  # Required for url_for with _external=True
    app.config['APPLICATION_ROOT'] = '/'
    app.config['PREFERRED_URL_SCHEME'] = 'http'
    app.config['SECRET_KEY'] = 'test-secret-key-for-sessions'  # Ensure sessions work
    
    # Create tables
    with app.app_context():
        db.create_all()
    
    yield app
    
    with app.app_context():
        db.drop_all()

@pytest.fixture
def client(app):
    """Create a test client for the app with request context.
    
    This pushes a request context which allows url_for() to work
    without explicit app.app_context() blocks in tests.
    """
    with app.test_request_context():
        yield app.test_client()

@pytest.fixture
def bcrypt():
    """Provide the bcrypt password hashing utility for tests."""
    from app import bcrypt
    return bcrypt

@pytest.fixture
def logged_in_user(client, app):
    """Create a user and log them in."""
    with app.app_context():
        company = Company(name="Test Company", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        user = User(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()
        
        # Store necessary attributes before leaving context
        user_data = {
            'id': user.id,
            'email': user.email,
            'company_id': user.company_id,
            'first_name': user.first_name,
            'last_name': user.last_name
        }
        
    client.post('/login', data={
        'email': 'test@example.com',
        'password': 'password'
    }, follow_redirects=True)
    
    # Return a helper object that allows accessing user data
    class LoggedInUserHelper:
        def __init__(self, user_data, app):
            self._data = user_data
            self._app = app
            # Add Flask-Login required attributes
            self.is_active = True
            self.is_authenticated = True
            self.is_anonymous = False
            
        def __getattr__(self, name):
            if name in self._data:
                return self._data[name]
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
        def get_id(self):
            """Flask-Login required method to get user ID as string."""
            return str(self._data['id'])
        
        def get_user(self):
            """Get the actual User object within an app context."""
            with self._app.app_context():
                return db.session.get(User, self._data['id'])
    
    return LoggedInUserHelper(user_data, app)

class AnalyticsEnv:
    """Minimal operational graph for analytics fact tests.

    Builds one company plus the reference data every fact source needs, and
    exposes a helper per operational table so tests can create source rows
    (already flushed, so they have primary keys) in one line.
    """

    def __init__(self, suffix=''):
        from datetime import date, datetime
        from app.models import (
            Company, Packaging, Item, RawProduct, BrandName, Seller,
            GrowerOrDistributor, Customer, DesignationCost, PayGroups,
            UnitOfWeight, ItemDesignation,
        )

        self.company = Company(name=f'Fact Co{suffix}', admin_email=f'facts{suffix}@example.com')
        db.session.add(self.company)
        db.session.flush()

        self.packaging = Packaging(packaging_type='Box', company_id=self.company.id)
        self.raw_product = RawProduct(name='Lettuce', company_id=self.company.id)
        self.brand = BrandName(name='Brand', company_id=self.company.id)
        self.seller = Seller(name='Seller', company_id=self.company.id)
        self.grower = GrowerOrDistributor(
            name='Grower', company_id=self.company.id, city='Salinas', state='CA'
        )
        self.customer = Customer(
            name='Customer', email=f'cust{suffix}@example.com', company_id=self.company.id
        )
        self.designation = DesignationCost(
            item_designation=ItemDesignation.FOODSERVICE,
            cost=1.0,
            date=date(2026, 8, 1),
            company_id=self.company.id,
        )
        self.pay_group = PayGroups(company_id=self.company.id, name='Packing')
        db.session.add_all([
            self.packaging, self.raw_product, self.brand, self.seller,
            self.grower, self.customer, self.designation, self.pay_group,
        ])
        db.session.flush()

        self.item = Item(
            name='Sliced Apples',
            code='APL001',
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=self.packaging.id,
            company_id=self.company.id,
            case_weight=25.0,
        )
        db.session.add(self.item)
        db.session.flush()

    def sale(self, quantity=10, unit_price=5.0, with_customer=True, sale_date=None):
        from datetime import datetime
        from app.models import SalesRecord
        record = SalesRecord(
            company_id=self.company.id,
            sale_date=sale_date or datetime(2026, 8, 27, 14, 30),
            item_designation_id=self.designation.id,
            quantity_sold=quantity,
            unit_price=unit_price,
            customer_id=self.customer.id if with_customer else None,
        )
        db.session.add(record)
        db.session.flush()
        return record

    def receiving(self, quantity=20, price_paid=2.5, received_at=None):
        from datetime import datetime
        from app.models import ReceivingLog
        log = ReceivingLog(
            raw_product_id=self.raw_product.id,
            pack_size_unit='lb',
            pack_size=10.0,
            brand_name_id=self.brand.id,
            quantity_received=quantity,
            seller_id=self.seller.id,
            temperature=35.0,
            hold_or_used='used',
            grower_or_distributor_id=self.grower.id,
            country_of_origin='USA',
            received_by='Tester',
            company_id=self.company.id,
            price_paid=price_paid,
            date_time=received_at or datetime(2026, 8, 26, 9, 0),
        )
        db.session.add(log)
        db.session.flush()
        return log

    def inventory_count(self, quantity=42, count_date=None):
        from datetime import datetime
        from app.models import ItemInventory
        count = ItemInventory(
            item_id=self.item.id,
            quantity=quantity,
            company_id=self.company.id,
            count_date=count_date or datetime(2026, 8, 25, 8, 0),
        )
        db.session.add(count)
        db.session.flush()
        return count

    def daily_log(self, log_date=None, sales=10000.0, payroll_cost=2500.0, labor_hours=180.0):
        from datetime import date
        from app.models import DailyLog
        log = DailyLog(
            company_id=self.company.id,
            date=log_date or date(2026, 8, 24),
            items=500,
            sales=sales,
            labor_hours=labor_hours,
            overtime_hours=12.0,
            payroll_cost=payroll_cost,
            number_of_employees=20,
            labor_ratio=0.25,
            sales_over_labor_cost=4.0,
            average_man_hour_cost=13.9,
            average_case_cost=5.0,
            average_hours_per_employee=9.0,
        )
        db.session.add(log)
        db.session.flush()
        return log

    def weekly_labor(self, week_start=None, regular_hours=400.0, overtime_hours=35.5, pay=9000.0):
        from datetime import date
        from app.models import WeeklyLaborEntry
        entry = WeeklyLaborEntry(
            company_id=self.company.id,
            week_start_date=week_start or date(2026, 8, 17),
            pay_group_id=self.pay_group.id,
            regular_hours=regular_hours,
            overtime_hours=overtime_hours,
            pay=pay,
            percent_of_sales=0.22,
            cost_per_hour=20.7,
            number_in_pay_group=15,
            number_with_overtime=4,
            average_hours_per_employee=29.0,
        )
        db.session.add(entry)
        db.session.flush()
        return entry

    def item_cost(self, cost_date=None, total_cost=12.75):
        from datetime import date
        from app.models import ItemTotalCost
        cost = ItemTotalCost(
            item_id=self.item.id,
            date=cost_date or date(2026, 8, 23),
            total_cost=total_cost,
            ranch_cost=0.5,
            packaging_cost=1.25,
            raw_product_cost=8.0,
            labor_cost=2.5,
            designation_cost=0.5,
            company_id=self.company.id,
        )
        db.session.add(cost)
        db.session.flush()
        return cost


@pytest.fixture
def analytics_env_factory(app):
    """Expose AnalyticsEnv inside an app context so tests can build several."""
    with app.app_context():
        yield AnalyticsEnv


@pytest.fixture
def analytics_env(analytics_env_factory):
    """A single operational graph for analytics fact tests."""
    return analytics_env_factory()
