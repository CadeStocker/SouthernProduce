import pytest
import os
import sys
import tempfile

# Add parent directory to path so we can import from the app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import directly from the app package
from producepricer import create_app, db

@pytest.fixture
def app():
    app = create_app('sqlite:///:memory:')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
    app.config['SERVER_NAME'] = 'localhost'  # For url_for outside request
    
    # Create tables but don't leave context open
    with app.app_context():
        db.create_all()
    
    # Yield the app without an active context
    yield app
    
    # Clean up after test
    with app.app_context():
        db.drop_all()

@pytest.fixture
def client(app):
    """Create a test client for the app."""
    with app.test_client() as client:
        # Add a more robust method to get CSRF tokens
        def get_csrf_token():
            with app.app_context():
                response = client.get('/signup')
                html = response.data.decode('utf-8')
                
                # Look for the CSRF token in different possible formats
                # First try the standard Flask-WTF format
                import re
                csrf_token_match = re.search(r'name="csrf_token" value="([^"]+)"', html)
                if csrf_token_match:
                    return csrf_token_match.group(1)
                    
                # Try alternative format (hidden input)
                csrf_token_match = re.search(r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"', html)
                if csrf_token_match:
                    return csrf_token_match.group(1)
                    
                # If we still can't find it, check the response for debugging
                print("CSRF token not found in HTML:")
                print(f"Response status: {response.status_code}")
                print(f"Response length: {len(html)}")
                print(f"First 200 chars: {html[:200]}")
                
                # Return a placeholder if WTF_CSRF_ENABLED is False in testing
                if not app.config.get('WTF_CSRF_ENABLED', True):
                    return "testing-csrf-token"
                    
                raise ValueError("Could not find CSRF token in the response HTML")
                
        client.get_csrf_token = get_csrf_token
        yield client

@pytest.fixture
def bcrypt():
    """Provide the bcrypt password hashing utility for tests."""
    from producepricer import bcrypt
    return bcrypt