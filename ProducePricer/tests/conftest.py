import pytest
import os
import sys
import tempfile

# Add parent directory to path so we can import from the app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import directly from the app package
from producepricer import create_app, db
from producepricer.models import User, Company

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
    from producepricer import bcrypt
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