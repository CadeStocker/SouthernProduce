import os
import sys
import tempfile
import pytest
from datetime import date, datetime

# Add the parent directory to Python's path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the app instance instead of create_app
from producepricer import app, db
from producepricer.models import User, Company, Item, Packaging, UnitOfWeight, ItemDesignation, RawProduct

@pytest.fixture(scope='function')
def app_fixture():
    """Configure the Flask app for testing."""
    # Save original config
    original_config = app.config.copy()
    
    # Create a temporary file to isolate the database for each test
    db_fd, db_path = tempfile.mkstemp()
    
    # Update app configuration for testing
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'WTF_CSRF_ENABLED': False,
        'SERVER_NAME': 'localhost',
        'SECRET_KEY': 'test-key',
        'RESET_PASS_TOKEN_MAX_AGE': 3600
    })

    # Create the database and the database tables
    with app.app_context():
        db.create_all()
        yield app

    # Close and remove the temporary database
    os.close(db_fd)
    os.unlink(db_path)
    
    # Restore original configuration
    app.config = original_config

@pytest.fixture(scope='function')
def client(app_fixture):
    """A test client for the app."""
    return app_fixture.test_client()

@pytest.fixture(scope='function')
def runner(app_fixture):
    """A test CLI runner for the app."""
    return app_fixture.test_cli_runner()

@pytest.fixture(scope='function')
def _db(app_fixture):
    """Create and return the database."""
    with app_fixture.app_context():
        db.create_all()
        yield db
        db.session.remove()
        db.drop_all()

@pytest.fixture(scope='function')
def test_company(_db):
    """Create a test company."""
    company = Company(
        name="Test Company", 
        admin_email="admin@testcompany.com"
    )
    _db.session.add(company)
    _db.session.commit()
    return company

@pytest.fixture(scope='function')
def test_user(test_company, _db):
    """Create a test user."""
    user = User(
        first_name="Test",
        last_name="User",
        email="test@example.com",
        password="password",  # In a real app, you'd hash this
        company_id=test_company.id
    )
    user.set_password("password")  # This should hash the password
    _db.session.add(user)
    _db.session.commit()
    return user

@pytest.fixture(scope='function')
def test_packaging(test_company, _db):
    """Create test packaging."""
    packaging = Packaging(
        packaging_type="Test Box",
        company_id=test_company.id
    )
    _db.session.add(packaging)
    _db.session.commit()
    return packaging

@pytest.fixture(scope='function')
def test_raw_product(test_company, _db):
    """Create a test raw product."""
    raw_product = RawProduct(
        name="Test Raw Product",
        company_id=test_company.id
    )
    _db.session.add(raw_product)
    _db.session.commit()
    return raw_product

@pytest.fixture(scope='function')
def test_item(test_company, test_packaging, test_raw_product, _db):
    """Create a test item."""
    item = Item(
        name="Test Item",
        code="TI-001",
        unit_of_weight=UnitOfWeight.POUND,
        packaging_id=test_packaging.id,
        company_id=test_company.id,
        case_weight=20.0,
        ranch=False,
        item_designation=ItemDesignation.FOODSERVICE
    )
    _db.session.add(item)
    
    # Add relationship to raw product
    item.raw_products.append(test_raw_product)
    
    _db.session.commit()
    return item

@pytest.fixture(scope='function')
def auth_client(client, test_user):
    """Authenticate the test client."""
    client.post('/login', data={
        'email': 'test@example.com',
        'password': 'password'
    }, follow_redirects=True)
    return client

@pytest.fixture(scope='function')
def current_user(auth_client):
    """Get the current_user from an authenticated session."""
    with auth_client.application.app_context():
        from flask_login import current_user
        yield current_user