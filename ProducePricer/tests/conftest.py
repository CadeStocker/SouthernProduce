import pytest
import os
import sys
import tempfile

# Add parent directory to path so we can import from the app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import directly from the app package
from producepricer import create_app, db

@pytest.fixture()
def app():
    """Create and configure a Flask app for testing."""
    # Create a temporary file for the database
    db_fd, db_path = tempfile.mkstemp()
    
    app = create_app(f"sqlite:///{db_path}")
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    with app.app_context():
        db.create_all()
        
    yield app
    
    # Teardown - close and remove the temporary database
    os.close(db_fd)
    os.unlink(db_path)