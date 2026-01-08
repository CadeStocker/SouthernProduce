from flask import Blueprint, jsonify, request, current_app, url_for, g
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from pydantic import ValidationError
import os
from producepricer.models import (
    ReceivingLog,
    ReceivingImage,
    RawProduct,
    BrandName,
    Seller,
    GrowerOrDistributor,
    db
)
from producepricer.schemas import ReceivingLogCreateSchema, validate_foreign_key_exists
from producepricer.auth_utils import require_api_key, optional_api_key_or_login, get_api_key_from_request, validate_api_key
from datetime import datetime

api = Blueprint('api', __name__)

# Test endpoint for API key authentication
@api.route('/api/test', methods=['GET'])
@require_api_key
def test_api_key():
    """Simple endpoint to test if your API key is working.
    
    This endpoint requires a valid API key and returns information
    about the authenticated device and company.
    """
    return jsonify({
        'success': True,
        'message': 'API key is valid and working!',
        'device_name': g.device_name,
        'company_id': g.company_id,
        'authenticated': True,
        'timestamp': datetime.utcnow().isoformat()
    }), 200


@api.before_request
def require_login():
    # Skip authentication for the test endpoint (it has its own decorator)
    if request.endpoint == 'api.test_api_key':
        return None
    
    # Skip if API key authentication is already set up by decorator
    if hasattr(g, 'company_id'):
        return None
        
    # Check for API key in request
    api_key_string = get_api_key_from_request()
    if api_key_string:
        api_key = validate_api_key(api_key_string)
        if api_key:
            # Set global context variables
            api_key.update_last_used()
            g.company_id = api_key.company_id
            g.api_key = api_key
            g.device_name = api_key.device_name
            g.auth_method = 'api_key'
            return None
    
    if not current_user.is_authenticated:
        return jsonify({'error': 'Unauthorized'}), 401

@api.route('/api/receiving_logs', methods=['GET'])
@optional_api_key_or_login
def get_receiving_logs():
    # Get company_id from either API key (g.company_id) or logged-in user
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
    
    logs = ReceivingLog.query.filter_by(company_id=company_id).order_by(ReceivingLog.datetime.desc()).all()
    
    logs_data = []
    for log in logs:
        logs_data.append({
            'id': log.id,
            'raw_product_name': log.raw_product.name if log.raw_product else None,
            'pack_size_unit': log.pack_size_unit,
            'pack_size': log.pack_size,
            'brand_name': log.brand_name.name if log.brand_name else None,
            'quantity_received': log.quantity_received,
            'seller_name': log.seller.name if log.seller else None,
            'temperature': log.temperature,
            'hold_or_used': log.hold_or_used,
            'datetime': log.datetime.isoformat(),
            'grower_or_distributor_name': log.grower_or_distributor.name if log.grower_or_distributor else None,
            'country_of_origin': log.country_of_origin,
            'received_by': log.received_by,
            'returned': log.returned,
            'images': [url_for('main.get_receiving_image', filename=img.filename, _external=True) for img in log.images]
        })
    
    return jsonify(logs_data)

@api.route('/api/receiving_logs', methods=['POST'])
@optional_api_key_or_login
def create_receiving_log():
    """Create a new receiving log with input validation."""
    try:
        # Get company_id from either API key or logged-in user
        company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
        
        # Get received_by from device_name (API key) or user name
        if hasattr(g, 'device_name'):
            received_by_default = g.device_name
        else:
            received_by_default = f"{current_user.first_name} {current_user.last_name}"
        
        # Get and validate input data using Pydantic schema
        raw_data = request.get_json()
        if not raw_data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate input schema and types
        try:
            validated_data = ReceivingLogCreateSchema(**raw_data)
        except ValidationError as e:
            # Return validation errors in a user-friendly format
            print(f"DEBUG: Validation Error: {e}")
            errors = {}
            for error in e.errors():
                field = '.'.join(str(loc) for loc in error['loc'])
                errors[field] = error['msg']
            return jsonify({'error': 'Invalid input', 'details': errors}), 400
        
        # Validate foreign keys exist and belong to user's company
        try:
            validate_foreign_key_exists(
                RawProduct, 
                validated_data.raw_product_id, 
                company_id,
                'raw_product_id'
            )
            validate_foreign_key_exists(
                BrandName, 
                validated_data.brand_name_id, 
                company_id,
                'brand_name_id'
            )
            validate_foreign_key_exists(
                Seller, 
                validated_data.seller_id, 
                company_id,
                'seller_id'
            )
            validate_foreign_key_exists(
                GrowerOrDistributor, 
                validated_data.grower_or_distributor_id, 
                company_id,
                'grower_or_distributor_id'
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        # Create the receiving log with validated data
        new_log = ReceivingLog(
            raw_product_id=validated_data.raw_product_id,
            pack_size_unit=validated_data.pack_size_unit,
            pack_size=validated_data.pack_size,
            brand_name_id=validated_data.brand_name_id,
            quantity_received=validated_data.quantity_received,
            seller_id=validated_data.seller_id,
            temperature=validated_data.temperature,
            hold_or_used=validated_data.hold_or_used,
            grower_or_distributor_id=validated_data.grower_or_distributor_id,
            country_of_origin=validated_data.country_of_origin,
            received_by=validated_data.received_by or received_by_default,
            company_id=company_id,
            returned=validated_data.returned,
            date_time=validated_data.datetime
        )
        
        db.session.add(new_log)
        db.session.commit()
        
        return jsonify({'message': 'Receiving log created successfully', 'id': new_log.id}), 201
        
    except Exception as e:
        db.session.rollback()
        # Don't expose internal error details to users
        current_app.logger.error(f"Error creating receiving log: {str(e)}")
        return jsonify({'error': 'An error occurred while creating the receiving log'}), 500

@api.route('/api/raw_products', methods=['GET'])
@optional_api_key_or_login
def get_raw_products():
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
    products = RawProduct.query.filter_by(company_id=company_id).all()
    return jsonify([{'id': p.id, 'name': p.name} for p in products])

@api.route('/api/raw_products', methods=['POST'])
@optional_api_key_or_login
def create_raw_product():
    """Create a new raw product."""
    try:
        company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
        
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Product name is required'}), 400
        
        name = data['name'].strip()
        if not name:
            return jsonify({'error': 'Product name cannot be empty'}), 400
        
        # Check if product already exists for this company
        existing = RawProduct.query.filter_by(company_id=company_id, name=name).first()
        if existing:
            return jsonify({'error': 'A product with this name already exists', 'id': existing.id}), 409
        
        # Create new product
        new_product = RawProduct(
            name=name,
            company_id=company_id
        )
        
        db.session.add(new_product)
        db.session.commit()
        
        return jsonify({
            'message': 'Raw product created successfully',
            'id': new_product.id,
            'name': new_product.name
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating raw product: {str(e)}")
        return jsonify({'error': 'An error occurred while creating the product'}), 500

@api.route('/api/brand_names', methods=['GET'])
@optional_api_key_or_login
def get_brand_names():
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
    brands = BrandName.query.filter_by(company_id=company_id).all()
    return jsonify([{'id': b.id, 'name': b.name} for b in brands])

@api.route('/api/brand_names', methods=['POST'])
@optional_api_key_or_login
def create_brand_name():
    """Create a new brand name."""
    try:
        company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
        
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Brand name is required'}), 400
        
        name = data['name'].strip()
        if not name:
            return jsonify({'error': 'Brand name cannot be empty'}), 400
        
        # Check if brand already exists for this company
        existing = BrandName.query.filter_by(company_id=company_id, name=name).first()
        if existing:
            return jsonify({'error': 'A brand with this name already exists', 'id': existing.id}), 409
        
        # Create new brand
        new_brand = BrandName(
            name=name,
            company_id=company_id
        )
        
        db.session.add(new_brand)
        db.session.commit()
        
        return jsonify({
            'message': 'Brand name created successfully',
            'id': new_brand.id,
            'name': new_brand.name
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating brand name: {str(e)}")
        return jsonify({'error': 'An error occurred while creating the brand'}), 500

@api.route('/api/sellers', methods=['GET'])
@optional_api_key_or_login
def get_sellers():
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
    sellers = Seller.query.filter_by(company_id=company_id).all()
    return jsonify([{'id': s.id, 'name': s.name} for s in sellers])

@api.route('/api/sellers', methods=['POST'])
@optional_api_key_or_login
def create_seller():
    """Create a new seller."""
    try:
        company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
        
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Seller name is required'}), 400
        
        name = data['name'].strip()
        if not name:
            return jsonify({'error': 'Seller name cannot be empty'}), 400
        
        # Check if seller already exists for this company
        existing = Seller.query.filter_by(company_id=company_id, name=name).first()
        if existing:
            return jsonify({'error': 'A seller with this name already exists', 'id': existing.id}), 409
        
        # Create new seller
        new_seller = Seller(
            name=name,
            company_id=company_id
        )
        
        db.session.add(new_seller)
        db.session.commit()
        
        return jsonify({
            'message': 'Seller created successfully',
            'id': new_seller.id,
            'name': new_seller.name
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating seller: {str(e)}")
        return jsonify({'error': 'An error occurred while creating the seller'}), 500

@api.route('/api/growers_distributors', methods=['GET'])
@optional_api_key_or_login
def get_growers_distributors():
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
    growers = GrowerOrDistributor.query.filter_by(company_id=company_id).all()
    return jsonify([{'id': g.id, 'name': g.name, 'city': g.city, 'state': g.state} for g in growers])

@api.route('/api/growers_distributors', methods=['POST'])
@optional_api_key_or_login
def create_grower_distributor():
    """Create a new grower or distributor."""
    try:
        company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        # Validate required fields
        name = data.get('name', '').strip()
        city = data.get('city', '').strip()
        state = data.get('state', '').strip()
        
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        if not city:
            return jsonify({'error': 'City is required'}), 400
        if not state:
            return jsonify({'error': 'State is required'}), 400
        
        # Check if grower/distributor already exists for this company
        existing = GrowerOrDistributor.query.filter_by(
            company_id=company_id,
            name=name,
            city=city,
            state=state
        ).first()
        if existing:
            return jsonify({
                'error': 'A grower/distributor with this name, city, and state already exists',
                'id': existing.id
            }), 409
        
        # Create new grower/distributor
        new_grower = GrowerOrDistributor(
            name=name,
            city=city,
            state=state,
            company_id=company_id
        )
        
        db.session.add(new_grower)
        db.session.commit()
        
        return jsonify({
            'message': 'Grower/distributor created successfully',
            'id': new_grower.id,
            'name': new_grower.name,
            'city': new_grower.city,
            'state': new_grower.state
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating grower/distributor: {str(e)}")
        return jsonify({'error': 'An error occurred while creating the grower/distributor'}), 500

@api.route('/api/receiving_logs/<int:log_id>/images', methods=['POST'])
@optional_api_key_or_login
def upload_receiving_images(log_id):
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
    
    log = ReceivingLog.query.get_or_404(log_id)
    
    if log.company_id != company_id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    if 'images' not in request.files:
        return jsonify({'error': 'No images provided'}), 400
        
    files = request.files.getlist('images')
    uploaded_images = []
    
    # Ensure directory exists
    upload_dir = current_app.config['RECEIVING_IMAGES_DIR']
    os.makedirs(upload_dir, exist_ok=True)
    
    for file in files:
        if file.filename == '':
            continue
            
        if file:
            filename = secure_filename(f"{log_id}_{int(datetime.utcnow().timestamp())}_{file.filename}")
            file.save(os.path.join(upload_dir, filename))
            
            new_image = ReceivingImage(
                filename=filename,
                receiving_log_id=log.id,
                company_id=company_id
            )
            db.session.add(new_image)
            uploaded_images.append(filename)
            
    db.session.commit()
    
    return jsonify({
        'message': f'{len(uploaded_images)} images uploaded successfully',
        'images': [url_for('main.get_receiving_image', filename=img, _external=True) for img in uploaded_images]
    }), 201
