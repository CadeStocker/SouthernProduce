# Copyright Cade Stocker 2026
"""Authentication utilities for API key validation."""
from collections import deque
from functools import wraps
from time import time

from flask import current_app, request, jsonify, g
from app.models import APIKey
from app import db


def _get_rate_limit_store():
    return current_app.extensions.setdefault('bad_api_key_attempts', {})


def _get_rate_limit_settings():
    return {
        'max_attempts': current_app.config.get('BAD_API_KEY_RATE_LIMIT_ATTEMPTS', 10),
        'window_seconds': current_app.config.get('BAD_API_KEY_RATE_LIMIT_WINDOW_SECONDS', 300),
    }


def _get_client_identifier():
    # Prefer X-Forwarded-For when behind a proxy, but fall back to the
    # REMOTE_ADDR provided by the WSGI environment which is stable for
    # the Flask test client (avoids returning different values across
    # successive test-client requests).
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()

    # REMOTE_ADDR is set by Werkzeug for the test client and by most WSGI
    # servers; prefer it over request.remote_addr which can be None in tests.
    remote_addr = request.environ.get('REMOTE_ADDR') or request.remote_addr
    return remote_addr or 'unknown'


def _prune_attempts(attempts, now, window_seconds):
    while attempts and now - attempts[0] > window_seconds:
        attempts.popleft()


def record_bad_api_key_attempt():
    client_id = _get_client_identifier()
    settings = _get_rate_limit_settings()
    now = time()
    attempts = _get_rate_limit_store().setdefault(client_id, deque())
    _prune_attempts(attempts, now, settings['window_seconds'])
    attempts.append(now)
    # Debugging: log attempt counts to help diagnose test failures
    try:
        current_app.logger.debug(f"Bad API key attempt: client_id={client_id} attempts={list(attempts)} max={settings['max_attempts']}")
    except Exception:
        pass
    return len(attempts) >= settings['max_attempts']


def clear_bad_api_key_attempts():
    _get_rate_limit_store().pop(_get_client_identifier(), None)


def bad_api_key_response():
    rate_limited = record_bad_api_key_attempt()
    if rate_limited:
        return jsonify({
            'error': 'Too many invalid API key attempts',
            'message': 'Try again later'
        }), 429

    return jsonify({
        'error': 'Invalid or inactive API key',
        'message': 'The provided API key is invalid or has been revoked'
    }), 401


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
        clear_bad_api_key_attempts()
        return api_key
    
    return None


def authenticate_api_key_request(api_key_string=None, require_key=True):
    api_key_string = api_key_string if api_key_string is not None else get_api_key_from_request()

    if not api_key_string:
        if require_key:
            return None, (jsonify({
                'error': 'API key required',
                'message': 'Please provide an API key in the X-API-Key header'
            }), 401)
        return None, None

    api_key = validate_api_key(api_key_string)
    if not api_key:
        # If the caller requested a required key, surface the bad-key
        # response (which records the failed attempt). If this check is
        # happening as a lightweight pre-flight (e.g. app.before_request
        # to mark CSRF-valid requests), don't record or return an error
        # here so the actual route decorator can handle rate-limiting.
        if require_key:
            return None, bad_api_key_response()
        return None, None

    return api_key, None


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
        api_key, error_response = authenticate_api_key_request(require_key=True)
        if error_response:
            return error_response
        
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
        if not get_api_key_from_request():
            return jsonify({
                'error': 'Authentication required',
                'message': 'Please log in or provide an API key'
            }), 401

        api_key, error_response = authenticate_api_key_request(require_key=True)
        if error_response:
            return error_response
        
        # Update last used timestamp
        api_key.update_last_used()
        
        # Set company context
        g.company_id = api_key.company_id
        g.api_key = api_key
        g.device_name = api_key.device_name
        g.auth_method = 'api_key'
        
        return f(*args, **kwargs)
    
    return decorated_function
