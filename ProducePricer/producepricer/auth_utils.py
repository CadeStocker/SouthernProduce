"""Authentication utilities for API key validation."""
from functools import wraps
from flask import request, jsonify, g
from producepricer.models import APIKey
from producepricer import db


def get_api_key_from_request():
    """Extract API key from request headers.
    
    Checks multiple common header formats:
    - X-API-Key: <key>
    - Authorization: Bearer <key>
    """
    # Check X-API-Key header (most common)
    api_key = request.headers.get('X-API-Key') or request.headers.get('X-Api-Key')
    
    if api_key:
        return api_key
    
    # Check Authorization header with Bearer token
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header[7:]  # Remove 'Bearer ' prefix
    
    return None


def validate_api_key(api_key_string):
    """Validate an API key and return the associated APIKey object.
    
    Args:
        api_key_string: The API key string to validate
        
    Returns:
        APIKey object if valid and active, None otherwise
    """
    if not api_key_string:
        return None
    
    # Query the database for the API key
    api_key = APIKey.query.filter_by(key=api_key_string).first()
    
    # Check if key exists and is active
    if api_key and api_key.is_active:
        return api_key
    
    return None


def require_api_key(f):
    """Decorator to require a valid API key for route access.
    
    This decorator validates the API key from the request header,
    updates the last_used_at timestamp, and sets the company context
    in Flask's g object for use in the route.
    
    Usage:
        @app.route('/api/some-endpoint')
        @require_api_key
        def some_endpoint():
            company_id = g.company_id
            # ... rest of your code
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Extract API key from request
        api_key_string = get_api_key_from_request()
        
        if not api_key_string:
            return jsonify({
                'error': 'API key required',
                'message': 'Please provide an API key in the X-API-Key header'
            }), 401
        
        # Validate the API key
        api_key = validate_api_key(api_key_string)
        
        if not api_key:
            return jsonify({
                'error': 'Invalid or inactive API key',
                'message': 'The provided API key is invalid or has been revoked'
            }), 401
        
        # Update last used timestamp
        api_key.update_last_used()
        
        # Set company context in Flask's g object
        g.company_id = api_key.company_id
        g.api_key = api_key
        g.device_name = api_key.device_name
        
        # Call the actual route function
        return f(*args, **kwargs)
    
    return decorated_function


def optional_api_key_or_login(f):
    """Decorator that accepts either API key OR user login.
    
    This decorator allows routes to be accessed either by:
    1. Logged-in users (via session)
    2. Devices with valid API keys
    
    Sets g.company_id in either case.
    
    Usage:
        @app.route('/api/some-endpoint')
        @optional_api_key_or_login
        def some_endpoint():
            company_id = g.company_id
            # ... rest of your code
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask_login import current_user
        
        # First, check if user is logged in via session
        if current_user.is_authenticated:
            g.company_id = current_user.company_id
            g.user_id = current_user.id
            g.auth_method = 'session'
            return f(*args, **kwargs)
        
        # If not logged in, try API key authentication
        api_key_string = get_api_key_from_request()
        
        if not api_key_string:
            return jsonify({
                'error': 'Authentication required',
                'message': 'Please log in or provide an API key'
            }), 401
        
        # Validate the API key
        api_key = validate_api_key(api_key_string)
        
        if not api_key:
            return jsonify({
                'error': 'Invalid or inactive API key',
                'message': 'The provided API key is invalid or has been revoked'
            }), 401
        
        # Update last used timestamp
        api_key.update_last_used()
        
        # Set company context
        g.company_id = api_key.company_id
        g.api_key = api_key
        g.device_name = api_key.device_name
        g.auth_method = 'api_key'
        
        return f(*args, **kwargs)
    
    return decorated_function
