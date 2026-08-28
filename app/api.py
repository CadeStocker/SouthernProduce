# Copyright Cade Stocker 2026
from flask import Blueprint, jsonify, request, current_app, url_for, g
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from pydantic import ValidationError
import os
from app.models import (
    ReceivingLog,
    ReceivingImage,
    RawProduct,
    BrandName,
    Seller,
    GrowerOrDistributor,
    Item,
    ItemInventory,
    InventorySession,
    Supply,
    SupplyInventory,
    DailyLog,
    PayGroups,
    WeeklyLaborEntry,
    SalesByDesignation,
    FilmUsage,
    db
)
from app.models.core import ItemDesignation, LABOR_APP_ITEM_DESIGNATIONS
from app.models.customers import Customer
from app.models.labor import SalesRecord
from app.schemas import (
    ReceivingLogCreateSchema,
    ItemInventoryCreateSchema,
    SalesRecordCreateSchema,
    SupplyCreateSchema,
    SupplyInventoryCreateSchema,
    InventorySessionCreateSchema,
    DailyLogCreateSchema,
    PayGroupCreateSchema,
    WeeklyLaborEntryCreateSchema,
    SalesByItemTypeCreateSchema,
    FilmUsageCreateSchema,
    validate_foreign_key_exists,
)
from app.auth_utils import (
    require_api_key,
    optional_api_key_or_login,
    get_api_key_from_request,
    authenticate_api_key_request,
)
from datetime import datetime, date as date_type
from app.services.analytics_facts import (
    record_item_sale,
    record_customer_order,
    record_receiving,
    record_inventory_snapshot,
    record_labor_summary,
    record_weekly_labor_summary,
)
from app.utils.notification_utils import (
    create_receiving_log_notification,
    maybe_create_receiving_log_outlier_notification
)

"""
Date: July 28 2026

reorganizing the url structures to be grouped in a more reasonable / organized way

breaking them into:
api/receiving  : receiving log stuff
api/sales      : anything with sales records, sales by item type, etc
api/inventory  : anything with inventory counts, supply inventory counts, etc
api/labor      : anything with labor, pay groups, weekly labor entries, etc
api/           : base stuff like raw products, brand names, sellers, growers/distributors, items, supplies, etc

"""

"""
This file contains the API endpoints for the Southern Produce applications.
It includes routes for managing receiving logs, raw products, brand names, sellers, growers/distributors, items, inventory counts, supplies, and supply inventory counts.
"""

api = Blueprint('api', __name__)

# Helper function to get the company_id from the request context
def get_request_company_id():
    return g.company_id if hasattr(g, 'company_id') else current_user.company_id

# Helper function to parse date values from request data
def parse_date_value(raw_value, field_name):
    try:
        return date_type.fromisoformat(raw_value)
    except ValueError as exc:
        try:
            return datetime.fromisoformat(raw_value.replace('Z', '+00:00')).date()
        except ValueError as inner_exc:
            raise ValueError(f'Invalid {field_name} format. Use YYYY-MM-DD or ISO datetime') from inner_exc

"""
FUNCTIONS FOR PRODUCERECEIVER
"""

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

    # Check for API key in request
    api_key_string = get_api_key_from_request()
    if api_key_string:
        api_key, error_response = authenticate_api_key_request(api_key_string=api_key_string, require_key=False)
        if api_key:
            # Set global context variables
            api_key.update_last_used()
            g.company_id = api_key.company_id
            g.api_key = api_key
            g.device_name = api_key.device_name
            g.auth_method = 'api_key'
            return None
        if error_response:
            return error_response

    # If the request provided an API key header, let the route-level
    # decorators handle invalid/expired keys (they will return the
    # appropriate 401/429 responses and perform rate-limiting). Only
    # return a generic 401 here when there is no API key and the user
    # is not authenticated via session.
    if not current_user.is_authenticated and not api_key_string:
        return jsonify({'error': 'Unauthorized'}), 401

# RECEIVING ENDPOINTS

@api.route('/api/receiving/receiving_logs', methods=['GET'])
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


@api.route('/api/receiving/receiving_logs', methods=['POST'])
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
        raw_data = request.get_json(silent=True)
        if not raw_data:
            # If the client submitted form-encoded data (e.g. a browser form),
            # try to accept that as a fallback by converting `request.form`
            # into a dict. Otherwise log the raw body for debugging and
            # return a helpful 400 response.
            if request.form:
                raw_data = request.form.to_dict(flat=True)
                current_app.logger.info('Fallback: received form-encoded data for /api/labor/daily_logs')
            else:
                content_type = request.content_type
                body = request.get_data(as_text=True)
                current_app.logger.warning(
                    f"No JSON received for daily_logs POST. Content-Type: {content_type}; Body: {body!r}"
                )
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
            date_time=validated_data.datetime,
            price_paid=validated_data.price_paid
        )
        
        db.session.add(new_log)
        db.session.flush()
        record_receiving(new_log)
        db.session.commit()

        try:
            create_receiving_log_notification(new_log, commit=True)
            maybe_create_receiving_log_outlier_notification(new_log, commit=True)
        except Exception:
            current_app.logger.exception('Failed to create receiving log notifications')
        
        return jsonify({'message': 'Receiving log created successfully', 'id': new_log.id}), 201
        
    except Exception as e:
        db.session.rollback()
        # Don't expose internal error details to users
        current_app.logger.error(f"Error creating receiving log: {str(e)}")
        return jsonify({'error': 'An error occurred while creating the receiving log'}), 500


@api.route('/api/receiving/growers_distributors', methods=['GET'])
@optional_api_key_or_login
def get_growers_distributors():
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
    growers = GrowerOrDistributor.query.filter_by(company_id=company_id).all()
    return jsonify([{'id': g.id, 'name': g.name, 'city': g.city, 'state': g.state} for g in growers])


@api.route('/api/receiving/growers_distributors', methods=['POST'])
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


@api.route('/api/receiving/receiving_logs/<int:log_id>/images', methods=['POST'])
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

# BASE ENDPOINTS FOR RAW PRODUCTS, BRAND NAMES, SELLERS, GROWERS/DISTRIBUTORS, CUSTOMERS

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
        
        # Handle JSON parsing errors
        try:
            data = request.get_json()
        except Exception as json_err:
            return jsonify({'error': f'Invalid JSON: {str(json_err)}'}), 400
            
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


@api.route('/api/customers', methods=['GET'])
@optional_api_key_or_login
def get_customers():
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
    customers = Customer.query.filter_by(company_id=company_id).all()
    return jsonify([{'id': c.id, 'name': c.name} for c in customers])


@api.route('/api/customers', methods=['POST'])
@optional_api_key_or_login
def create_customer():
    """Create a new customer."""

    try:
        company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id

        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Customer name is required'}), 400

        name = data['name'].strip()
        if not name:
            return jsonify({'error': 'Customer name cannot be empty'}), 400

        # Check if customer already exists for this company
        existing = Customer.query.filter_by(company_id=company_id, name=name).first()
        if existing:
            return jsonify({'error': 'A customer with this name already exists', 'id': existing.id}), 409

        new_customer = Customer(
            name=name,
            email=data.get('email'),
            company_id=company_id
        )

        db.session.add(new_customer)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Customer created successfully',
            'customer': {
                'id': new_customer.id,
                'name': new_customer.name
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating customer: {str(e)}")
        return jsonify({'error': 'An error occurred while creating the customer'}), 500


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


@api.route('/api/items', methods=['GET'])
@optional_api_key_or_login
def get_items():
    """Get all items for inventory taking.
    
    Returns a list of all items in the company for the iPad app to display
    for inventory counting. Includes item details like name, code, and current
    inventory if available.
    
    Returns:
        JSON array of items with id, name, code, alternate_code, case_weight, etc.
    """
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
    
    items = Item.query.filter_by(company_id=company_id).order_by(Item.name).all()
    
    items_data = []
    for item in items:
        # Get the most recent inventory count if available
        latest_count = ItemInventory.query.filter_by(
            item_id=item.id,
            company_id=company_id
        ).order_by(ItemInventory.count_date.desc()).first()
        
        items_data.append({
            'id': item.id,
            'name': item.name,
            'code': item.code,
            'alternate_code': item.alternate_code,
            'case_weight': item.case_weight,
            'unit_of_weight': item.unit_of_weight.value if item.unit_of_weight else None,
            'item_designation': item.item_designation.value if item.item_designation else None,
            'last_count': {
                'quantity': latest_count.quantity,
                'date': latest_count.count_date.isoformat(),
                'counted_by': latest_count.counted_by
            } if latest_count else None
        })
    
    return jsonify(items_data), 200


@api.route('/api/item_designations', methods=['GET'])
@optional_api_key_or_login
def get_item_designations():
    """Get all item designations with id, name, and unit for the iOS app."""

    designations = [dict(d) for d in LABOR_APP_ITEM_DESIGNATIONS]

    return jsonify(designations), 200


@api.route('/api/item_designations', methods=['POST'])
@optional_api_key_or_login
def create_item_designation():
    """Create a new item designation (type)."""
    try:
        company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id

        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Item type name is required'}), 400

        name = data['name'].strip()
        unit = data.get('unit', 'units').strip()

        if not name:
            return jsonify({'error': 'Item type name cannot be empty'}), 400

        # For now, return the created item type with a generated ID
        # In a full implementation, you might store these in a database table
        next_id = 6  # Start after the hardcoded ones
        return jsonify({
            'success': True,
            'message': 'Item type created successfully',
            'item_type': {
                'id': next_id,
                'name': name,
                'unit': unit
            }
        }), 201

    except Exception as e:
        current_app.logger.error(f"Error creating item designation: {str(e)}")
        return jsonify({'error': 'An error occurred while creating the item type'}), 500

# INVENTORY ENDPOINTS

@api.route('/api/inventory/inventory_counts', methods=['POST'])
@optional_api_key_or_login
def create_inventory_count():
    """Submit an inventory count from the iPad app.
    
    Creates a new inventory count record for an item. This is used when
    staff take physical inventory and want to record the counts.
    
    Request JSON:
        {
            "item_id": 123,
            "quantity": 45,
            "counted_by": "John Doe",  # optional
            "notes": "Found extra in back cooler",  # optional
            "count_date": "2026-01-09T14:30:00"  # optional, defaults to now
        }
    
    Returns:
        JSON with success message and created inventory count details
    """

    try:
        company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
        
        # Handle JSON parsing errors
        try:
            data = request.get_json()
        except Exception as json_err:
            return jsonify({'error': f'Invalid JSON: {str(json_err)}'}), 400
        
        # Validate required fields
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        if 'item_id' not in data:
            return jsonify({'error': 'item_id is required'}), 400
        
        if 'quantity' not in data:
            return jsonify({'error': 'quantity is required'}), 400
        
        item_id = data['item_id']
        quantity = data['quantity']
        
        # Validate item exists and belongs to company
        item = Item.query.filter_by(id=item_id, company_id=company_id).first()
        if not item:
            return jsonify({'error': f'Item with id {item_id} not found or does not belong to your company'}), 404
        
        # Validate quantity is a non-negative integer
        try:
            quantity = int(quantity)
            if quantity < 0:
                return jsonify({'error': 'quantity must be non-negative'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'quantity must be a valid integer'}), 400
        
        # Parse optional count_date
        count_date = None
        if 'count_date' in data and data['count_date']:
            try:
                count_date = datetime.fromisoformat(data['count_date'].replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                return jsonify({'error': f'Invalid count_date format. Use ISO format: {str(e)}'}), 400
        
        # Create inventory count
        inventory_count = ItemInventory(
            item_id=item_id,
            quantity=quantity,
            company_id=company_id,
            counted_by=data.get('counted_by'),
            notes=data.get('notes'),
            count_date=count_date
        )
        
        db.session.add(inventory_count)
        db.session.flush()
        record_inventory_snapshot(inventory_count)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Inventory count recorded successfully',
            'inventory_count': {
                'id': inventory_count.id,
                'item_id': inventory_count.item_id,
                'item_name': item.name,
                'quantity': inventory_count.quantity,
                'count_date': inventory_count.count_date.isoformat(),
                'counted_by': inventory_count.counted_by,
                'notes': inventory_count.notes
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating inventory count: {str(e)}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500


@api.route('/api/inventory/inventory_counts', methods=['GET'])
@optional_api_key_or_login
def get_inventory_counts():
    """Get inventory count history.
    
    Returns all inventory counts for the company, with optional filtering.
    
    Query parameters:
        item_id: Filter by item ID
        start_date: Filter counts after this date (ISO format)
        end_date: Filter counts before this date (ISO format)
        limit: Maximum number of results (default 100)
    
    Returns:
        JSON array of inventory counts with item details
    """

    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
    
    # Build query
    query = ItemInventory.query.filter_by(company_id=company_id)
    
    # Apply filters
    item_id = request.args.get('item_id', type=int)
    if item_id:
        query = query.filter_by(item_id=item_id)
    
    start_date = request.args.get('start_date')
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            query = query.filter(ItemInventory.count_date >= start_dt)
        except ValueError:
            return jsonify({'error': 'Invalid start_date format'}), 400
    
    end_date = request.args.get('end_date')
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query = query.filter(ItemInventory.count_date <= end_dt)
        except ValueError:
            return jsonify({'error': 'Invalid end_date format'}), 400
    
    # Apply limit
    limit = request.args.get('limit', default=100, type=int)
    if limit > 1000:
        limit = 1000  # Cap at 1000 for performance
    
    # Execute query with order
    counts = query.order_by(ItemInventory.count_date.desc()).limit(limit).all()
    
    counts_data = []
    for count in counts:
        counts_data.append({
            'id': count.id,
            'item_id': count.item_id,
            'item_name': count.item.name if count.item else None,
            'item_code': count.item.code if count.item else None,
            'quantity': count.quantity,
            'count_date': count.count_date.isoformat(),
            'counted_by': count.counted_by,
            'notes': count.notes
        })
    
    return jsonify(counts_data), 200


@api.route('/api/inventory/supplies', methods=['GET'])
@optional_api_key_or_login
def get_supplies():
    """Get all supplies in the company's catalog.

    Query parameters:
        category: filter by category string (case-insensitive)
        active_only: if 'true' (default), only return active supplies
    """
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id

    query = Supply.query.filter_by(company_id=company_id)

    active_only = request.args.get('active_only', 'true').lower()
    if active_only != 'false':
        query = query.filter_by(is_active=True)

    category = request.args.get('category')
    if category:
        query = query.filter(Supply.category.ilike(f'%{category}%'))

    supplies = query.order_by(Supply.category, Supply.name).all()

    return jsonify([
        {
            'id': s.id,
            'name': s.name,
            'unit': s.unit,
            'category': s.category,
            'notes': s.notes,
            'is_active': s.is_active,
        }
        for s in supplies
    ]), 200


@api.route('/api/inventory/supplies', methods=['POST'])
@optional_api_key_or_login
def create_supply():
    """Create a new supply in the catalog.

    Request JSON:
        {
            "name": "Latex Gloves",
            "unit": "box",
            "category": "Safety",   // optional
            "notes": "100 count",   // optional
            "is_active": true       // optional, defaults to true
        }
    """
    try:
        company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id

        raw_data = request.get_json()
        if not raw_data:
            return jsonify({'error': 'No data provided'}), 400

        try:
            data = SupplyCreateSchema(**raw_data)
        except ValidationError as e:
            errors = {'.'.join(str(l) for l in err['loc']): err['msg'] for err in e.errors()}
            return jsonify({'error': 'Invalid input', 'details': errors}), 400

        # Prevent duplicates within the same company
        existing = Supply.query.filter_by(
            company_id=company_id, name=data.name
        ).first()
        if existing:
            return jsonify({'error': 'A supply with this name already exists', 'id': existing.id}), 409

        supply = Supply(
            name=data.name,
            unit=data.unit,
            company_id=company_id,
            category=data.category,
            notes=data.notes,
            is_active=data.is_active,
        )
        db.session.add(supply)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Supply created successfully',
            'supply': {
                'id': supply.id,
                'name': supply.name,
                'unit': supply.unit,
                'category': supply.category,
                'notes': supply.notes,
                'is_active': supply.is_active,
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating supply: {e}")
        return jsonify({'error': 'An error occurred while creating the supply'}), 500


@api.route('/api/inventory/supply_inventory_counts', methods=['POST'])
@optional_api_key_or_login
def create_supply_inventory_count():
    """Submit a supply inventory count from the iPad.

    Request JSON:
        {
            "supply_id": 7,
            "quantity": 3.5,
            "counted_by": "Jane",       // optional
            "notes": "Half roll left",  // optional
            "count_date": "2026-03-06T09:00:00"  // optional, defaults to now
        }
    """
    try:
        company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id

        if hasattr(g, 'device_name'):
            default_counted_by = g.device_name
        else:
            default_counted_by = f"{current_user.first_name} {current_user.last_name}"

        raw_data = request.get_json()
        if not raw_data:
            return jsonify({'error': 'No data provided'}), 400

        try:
            data = SupplyInventoryCreateSchema(**raw_data)
        except ValidationError as e:
            errors = {'.'.join(str(l) for l in err['loc']): err['msg'] for err in e.errors()}
            return jsonify({'error': 'Invalid input', 'details': errors}), 400

        # Verify the supply belongs to this company
        supply = Supply.query.filter_by(id=data.supply_id, company_id=company_id).first()
        if not supply:
            return jsonify({'error': f'Supply with id {data.supply_id} not found'}), 404

        count = SupplyInventory(
            supply_id=data.supply_id,
            quantity=data.quantity,
            company_id=company_id,
            count_date=data.count_date,
            counted_by=data.counted_by or default_counted_by,
            notes=data.notes,
        )
        db.session.add(count)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Supply inventory count recorded successfully',
            'supply_inventory_count': {
                'id': count.id,
                'supply_id': count.supply_id,
                'supply_name': supply.name,
                'supply_unit': supply.unit,
                'quantity': count.quantity,
                'count_date': count.count_date.isoformat(),
                'counted_by': count.counted_by,
                'notes': count.notes,
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating supply inventory count: {e}")
        return jsonify({'error': 'An error occurred while recording the count'}), 500


@api.route('/api/inventory/supply_inventory_counts', methods=['GET'])
@optional_api_key_or_login
def get_supply_inventory_counts():
    """Get supply inventory count history.

    Query parameters:
        supply_id:   filter by supply ID
        start_date:  ISO datetime, inclusive lower bound
        end_date:    ISO datetime, inclusive upper bound
        limit:       max results (default 100, max 1000)
    """
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id

    query = SupplyInventory.query.filter_by(company_id=company_id)

    supply_id = request.args.get('supply_id', type=int)
    if supply_id:
        query = query.filter_by(supply_id=supply_id)

    start_date = request.args.get('start_date')
    if start_date:
        try:
            query = query.filter(
                SupplyInventory.count_date >= datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            )
        except ValueError:
            return jsonify({'error': 'Invalid start_date format'}), 400

    end_date = request.args.get('end_date')
    if end_date:
        try:
            query = query.filter(
                SupplyInventory.count_date <= datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            )
        except ValueError:
            return jsonify({'error': 'Invalid end_date format'}), 400

    limit = min(request.args.get('limit', default=100, type=int), 1000)

    counts = query.order_by(SupplyInventory.count_date.desc()).limit(limit).all()

    return jsonify([
        {
            'id': c.id,
            'supply_id': c.supply_id,
            'supply_name': c.supply.name if c.supply else None,
            'supply_unit': c.supply.unit if c.supply else None,
            'category': c.supply.category if c.supply else None,
            'quantity': c.quantity,
            'count_date': c.count_date.isoformat(),
            'counted_by': c.counted_by,
            'notes': c.notes,
        }
        for c in counts
    ]), 200


@api.route('/api/inventory/inventory_sessions', methods=['POST'])
@optional_api_key_or_login
def create_inventory_session():
    """Submit a complete inventory session (items + supplies) in one request.

    The iPad sends a single JSON object that contains both item counts and
    supply counts. One ``InventorySession`` parent row is created, and every
    line is stored as a child ``ItemInventory`` or ``SupplyInventory`` row.

    Request JSON::

        {
            "label": "Morning count",          // optional
            "counted_by": "John",              // optional (falls back to device name)
            "notes": "Cooler #2 was locked",   // optional
            "submitted_at": "2026-03-06T08:00:00",  // optional, defaults to now
            "item_counts": [
                {"item_id": 1, "quantity": 40},
                {"item_id": 3, "quantity": 12, "notes": "One damaged box"}
            ],
            "supply_counts": [
                {"supply_id": 2, "quantity": 5},
                {"supply_id": 4, "quantity": 0.5, "notes": "Half roll left"}
            ]
        }
    """

    try:
        company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id
        default_counted_by = (
            g.device_name if hasattr(g, 'device_name')
            else f"{current_user.first_name} {current_user.last_name}"
        )

        raw_data = request.get_json()
        if not raw_data:
            return jsonify({'error': 'No data provided'}), 400

        try:
            data = InventorySessionCreateSchema(**raw_data)
        except ValidationError as e:
            errors = {'.'.join(str(l) for l in err['loc']): err['msg'] for err in e.errors()}
            return jsonify({'error': 'Invalid input', 'details': errors}), 400

        # Validate all item IDs belong to this company before writing anything
        item_ids = {line.item_id for line in data.item_counts}
        if item_ids:
            found_items = {
                i.id: i for i in
                Item.query.filter(
                    Item.id.in_(item_ids),
                    Item.company_id == company_id
                ).all()
            }
            missing = item_ids - found_items.keys()
            if missing:
                return jsonify({'error': f'Item IDs not found: {sorted(missing)}'}), 404

        # Validate all supply IDs belong to this company before writing anything
        supply_ids = {line.supply_id for line in data.supply_counts}
        if supply_ids:
            found_supplies = {
                s.id: s for s in
                Supply.query.filter(
                    Supply.id.in_(supply_ids),
                    Supply.company_id == company_id
                ).all()
            }
            missing = supply_ids - found_supplies.keys()
            if missing:
                return jsonify({'error': f'Supply IDs not found: {sorted(missing)}'}), 404

        counted_by = data.counted_by or default_counted_by

        # Create the parent session
        session = InventorySession(
            company_id=company_id,
            counted_by=counted_by,
            label=data.label,
            notes=data.notes,
            submitted_at=data.submitted_at,
        )
        db.session.add(session)
        db.session.flush()  # get session.id before adding children

        # Create item count rows
        item_rows = []
        for line in data.item_counts:
            row = ItemInventory(
                item_id=line.item_id,
                quantity=line.quantity,
                company_id=company_id,
                session_id=session.id,
                counted_by=counted_by,
                notes=line.notes,
                count_date=data.submitted_at,
            )
            db.session.add(row)
            item_rows.append(row)

        # Create supply count rows
        supply_rows = []
        for line in data.supply_counts:
            row = SupplyInventory(
                supply_id=line.supply_id,
                quantity=line.quantity,
                company_id=company_id,
                session_id=session.id,
                counted_by=counted_by,
                notes=line.notes,
                count_date=data.submitted_at,
            )
            db.session.add(row)
            supply_rows.append(row)

        db.session.flush()  # get item row ids before recording facts
        for row in item_rows:
            record_inventory_snapshot(row)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Inventory session recorded successfully',
            'session': {
                'id': session.id,
                'label': session.label,
                'counted_by': session.counted_by,
                'notes': session.notes,
                'submitted_at': session.submitted_at.isoformat(),
                'item_count': len(item_rows),
                'supply_count': len(supply_rows),
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating inventory session: {e}")
        return jsonify({'error': 'An error occurred while recording the inventory session'}), 500


@api.route('/api/inventory/inventory_sessions', methods=['GET'])
@optional_api_key_or_login
def get_inventory_sessions():
    """List inventory sessions for this company.

    Query parameters:
        start_date:  ISO datetime, inclusive lower bound on ``submitted_at``
        end_date:    ISO datetime, inclusive upper bound on ``submitted_at``
        limit:       max results (default 50, max 500)
    """
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id

    query = InventorySession.query.filter_by(company_id=company_id)

    start_date = request.args.get('start_date')
    if start_date:
        try:
            query = query.filter(
                InventorySession.submitted_at >= datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            )
        except ValueError:
            return jsonify({'error': 'Invalid start_date format'}), 400

    end_date = request.args.get('end_date')
    if end_date:
        try:
            query = query.filter(
                InventorySession.submitted_at <= datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            )
        except ValueError:
            return jsonify({'error': 'Invalid end_date format'}), 400

    limit = min(request.args.get('limit', default=50, type=int), 500)
    sessions = query.order_by(InventorySession.submitted_at.desc()).limit(limit).all()

    return jsonify([
        {
            'id': s.id,
            'label': s.label,
            'counted_by': s.counted_by,
            'notes': s.notes,
            'submitted_at': s.submitted_at.isoformat(),
            'item_count': len(s.item_counts),
            'supply_count': len(s.supply_counts),
        }
        for s in sessions
    ]), 200


@api.route('/api/inventory/inventory_sessions/<int:session_id>', methods=['GET'])
@optional_api_key_or_login
def get_inventory_session(session_id):
    """Return full detail of one inventory session including all line items."""
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id

    session = InventorySession.query.filter_by(
        id=session_id, company_id=company_id
    ).first_or_404()

    return jsonify({
        'id': session.id,
        'label': session.label,
        'counted_by': session.counted_by,
        'notes': session.notes,
        'submitted_at': session.submitted_at.isoformat(),
        'item_counts': [
            {
                'id': r.id,
                'item_id': r.item_id,
                'item_name': r.item.name if r.item else None,
                'quantity': r.quantity,
                'notes': r.notes,
            }
            for r in session.item_counts
        ],
        'supply_counts': [
            {
                'id': r.id,
                'supply_id': r.supply_id,
                'supply_name': r.supply.name if r.supply else None,
                'supply_unit': r.supply.unit if r.supply else None,
                'quantity': r.quantity,
                'notes': r.notes,
            }
            for r in session.supply_counts
        ],
    }), 200


@api.route('/api/inventory/inventory_sessions/<int:session_id>', methods=['DELETE'])
@optional_api_key_or_login
def delete_inventory_session(session_id):
    """Delete an inventory session and all its line items."""
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id

    session = InventorySession.query.filter_by(
        id=session_id, company_id=company_id
    ).first_or_404()

    db.session.delete(session)
    db.session.commit()

    return jsonify({'success': True, 'message': f'Inventory session {session_id} deleted'}), 200


# SALES ENDPOINTS

@api.route('/api/sales/records', methods=['GET'])
@optional_api_key_or_login
def get_sales_records():
    company_id = get_request_company_id()
    query = SalesRecord.query.filter_by(company_id=company_id)

    return jsonify([
        {
            'id': record.id,
            'sale_date': record.sale_date.isoformat(),
            'company_id': record.company_id,
            'item_designation_id': record.item_designation_id,
            'quantity_sold': record.quantity_sold,
            'unit_price': record.unit_price,
            'total_price': record.total_price,
            'customer_id': record.customer_id,
        }
        for record in query.order_by(SalesRecord.sale_date.desc(), SalesRecord.id.desc()).all()
    ]), 200


@api.route('/api/sales/records', methods=['POST'])
@optional_api_key_or_login
def create_sales_record():
    """Create a new sales record."""
    try:
        company_id = get_request_company_id()
        raw_data = request.get_json()
        if not raw_data:
            return jsonify({'error': 'No data provided'}), 400

        try:
            data = SalesRecordCreateSchema(**raw_data)
        except ValidationError as e:
            errors = {'.'.join(str(l) for l in err['loc']): err['msg'] for err in e.errors()}
            return jsonify({'error': 'Invalid input', 'details': errors}), 400

        # Verify customer exists if provided
        if data.customer_id and data.customer_id > 0:
            customer = Customer.query.filter_by(id=data.customer_id, company_id=company_id).first()
            if not customer:
                return jsonify({'error': f'Customer with id {data.customer_id} not found'}), 404

        sale = SalesRecord(
            company_id=company_id,
            sale_date=data.sale_date or datetime.utcnow(),
            item_designation_id=data.item_designation_id,
            quantity_sold=data.quantity_sold,
            unit_price=data.unit_price,
            customer_id=data.customer_id if data.customer_id and data.customer_id > 0 else None,
        )
        db.session.add(sale)
        db.session.flush()
        record_item_sale(sale)
        record_customer_order(sale)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Sale record created successfully',
            'sale_record': {
                'id': sale.id,
                'sale_date': sale.sale_date.isoformat(),
                'item_designation_id': sale.item_designation_id,
                'quantity_sold': sale.quantity_sold,
                'unit_price': sale.unit_price,
                'total_price': sale.total_price,
                'customer_id': sale.customer_id,
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating sales record: {e}")
        return jsonify({'error': 'An error occurred while creating the sales record'}), 500


@api.route('/api/sales/records/<int:record_id>', methods=['DELETE'])
@optional_api_key_or_login
def delete_sales_record(record_id):
    """Delete a sales record."""
    try:
        company_id = get_request_company_id()
        sale = SalesRecord.query.filter_by(id=record_id, company_id=company_id).first()

        if not sale:
            return jsonify({'error': 'Sales record not found'}), 404

        db.session.delete(sale)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Sales record {record_id} deleted successfully'
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting sales record: {e}")
        return jsonify({'error': 'An error occurred while deleting the sales record'}), 500

# LABOR ENDPOINTS

@api.route('/api/labor/weekly_labor_entries', methods=['POST'])
@optional_api_key_or_login
def create_weekly_labor_entry():
    try:
        company_id = get_request_company_id()
        raw_data = request.get_json()
        if not raw_data:
            return jsonify({'error': 'No data provided'}), 400

        try:
            data = WeeklyLaborEntryCreateSchema(**raw_data)
        except ValidationError as e:
            errors = {'.'.join(str(l) for l in err['loc']): err['msg'] for err in e.errors()}
            return jsonify({'error': 'Invalid input', 'details': errors}), 400

        pay_group = PayGroups.query.filter_by(id=data.pay_group_id, company_id=company_id).first()
        if not pay_group:
            return jsonify({'error': f'Pay group with id {data.pay_group_id} not found'}), 404

        entry = WeeklyLaborEntry(
            company_id=company_id,
            week_start_date=data.week_start_date,
            pay_group_id=data.pay_group_id,
            regular_hours=data.regular_hours,
            overtime_hours=data.overtime_hours,
            pay=data.pay,
            percent_of_sales=data.percent_of_sales,
            cost_per_hour=data.cost_per_hour,
            number_in_pay_group=data.number_in_pay_group,
            number_with_overtime=data.number_with_overtime,
            average_hours_per_employee=data.average_hours_per_employee,
        )
        db.session.add(entry)
        db.session.flush()
        record_weekly_labor_summary(entry)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Weekly labor entry created successfully',
            'weekly_labor_entry': {
                'id': entry.id,
                'week_start_date': entry.week_start_date.isoformat(),
                'pay_group_id': entry.pay_group_id,
                'regular_hours': entry.regular_hours,
                'overtime_hours': entry.overtime_hours,
                'pay': entry.pay,
                'percent_of_sales': entry.percent_of_sales,
                'cost_per_hour': entry.cost_per_hour,
                'number_in_pay_group': entry.number_in_pay_group,
                'number_with_overtime': entry.number_with_overtime,
                'average_hours_per_employee': entry.average_hours_per_employee,
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating weekly labor entry: {e}")
        return jsonify({'error': 'An error occurred while creating the weekly labor entry'}), 500


@api.route('/api/labor/sales_by_item_designation', methods=['GET'])
@optional_api_key_or_login
def get_sales_by_item_designation():
    company_id = get_request_company_id()

    query = SalesByDesignation.query.filter_by(company_id=company_id)

    item_type_id = request.args.get('item_type_id', type=int)
    if item_type_id:
        query = query.filter_by(item_type_id=item_type_id)

    start_date = request.args.get('start_date')
    if start_date:
        try:
            query = query.filter(SalesByDesignation.date >= parse_date_value(start_date, 'start_date'))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    end_date = request.args.get('end_date')
    if end_date:
        try:
            query = query.filter(SalesByDesignation.date <= parse_date_value(end_date, 'end_date'))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    limit = min(request.args.get('limit', default=100, type=int), 1000)
    rows = query.order_by(SalesByDesignation.date.desc(), SalesByDesignation.id.desc()).limit(limit).all()

    return jsonify([
        {
            'id': row.id,
            'date': row.date.isoformat(),
            'item_type_id': row.item_type_id,
            'number_of_items': row.number_of_items,
            'sales': row.sales,
            'average_price_per_item': row.average_price_per_item,
            'percent_of_total_sales': row.percent_of_total_sales,
            'percent_of_total_boxes': row.percent_of_total_boxes,
        }
        for row in rows
    ]), 200


@api.route('/api/labor/sales_by_item_designation', methods=['POST'])
@optional_api_key_or_login
def create_sales_by_item_designation():
    try:
        company_id = get_request_company_id()
        raw_data = request.get_json()
        if not raw_data:
            return jsonify({'error': 'No data provided'}), 400

        try:
            data = SalesRecordCreateSchema(**raw_data)
        except ValidationError as e:
            errors = {'.'.join(str(l) for l in err['loc']): err['msg'] for err in e.errors()}
            return jsonify({'error': 'Invalid input', 'details': errors}), 400

        row = SalesByDesignation(
            company_id=company_id,
            date=data.date,
            item_type_id=data.item_type_id,
            number_of_items=data.number_of_items,
            sales=data.sales,
            average_price_per_item=data.average_price_per_item,
            percent_of_total_sales=data.percent_of_total_sales,
            percent_of_total_boxes=data.percent_of_total_boxes,
        )
        db.session.add(row)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Sales by item designation created successfully',
            'sales_by_item_designation': {
                'id': row.id,
                'date': row.date.isoformat(),
                'item_type_id': row.item_type_id,
                'number_of_items': row.number_of_items,
                'sales': row.sales,
                'average_price_per_item': row.average_price_per_item,
                'percent_of_total_sales': row.percent_of_total_sales,
                'percent_of_total_boxes': row.percent_of_total_boxes,
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating sales by item designation: {e}")
        return jsonify({'error': 'An error occurred while creating the sales by item designation record'}), 500


@api.route('/api/labor/film_usage', methods=['GET'])
@optional_api_key_or_login
def get_film_usage():
    company_id = get_request_company_id()
    query = FilmUsage.query.filter_by(company_id=company_id)

    month = request.args.get('month', type=int)
    if month:
        query = query.filter_by(month=month)

    year = request.args.get('year', type=int)
    if year:
        query = query.filter_by(year=year)

    limit = min(request.args.get('limit', default=100, type=int), 1000)
    usage_rows = query.order_by(FilmUsage.year.desc(), FilmUsage.month.desc(), FilmUsage.id.desc()).limit(limit).all()

    return jsonify([
        {
            'id': row.id,
            'month': row.month,
            'year': row.year,
            'number_of_cases': row.number_of_cases,
            'number_of_rolls': row.number_of_rolls,
        }
        for row in usage_rows
    ]), 200


@api.route('/api/labor/film_usage', methods=['POST'])
@optional_api_key_or_login
def create_film_usage():
    try:
        company_id = get_request_company_id()
        raw_data = request.get_json()
        if not raw_data:
            return jsonify({'error': 'No data provided'}), 400

        try:
            data = FilmUsageCreateSchema(**raw_data)
        except ValidationError as e:
            errors = {'.'.join(str(l) for l in err['loc']): err['msg'] for err in e.errors()}
            return jsonify({'error': 'Invalid input', 'details': errors}), 400

        existing = FilmUsage.query.filter_by(company_id=company_id, month=data.month, year=data.year).first()
        if existing:
            return jsonify({'error': 'Film usage already exists for this month and year', 'id': existing.id}), 409

        row = FilmUsage(
            company_id=company_id,
            month=data.month,
            year=data.year,
            number_of_cases=data.number_of_cases,
            number_of_rolls=data.number_of_rolls,
        )
        db.session.add(row)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Film usage created successfully',
            'film_usage': {
                'id': row.id,
                'month': row.month,
                'year': row.year,
                'number_of_cases': row.number_of_cases,
                'number_of_rolls': row.number_of_rolls,
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating film usage: {e}")
        return jsonify({'error': 'An error occurred while creating the film usage record'}), 500


@api.route('/api/labor/daily_logs', methods=['GET'])
@optional_api_key_or_login
def get_daily_logs():
    """
    Endpoint for viewing daily labor logs
    Keeps track of labor ratio, etc.
    """

    company_id = get_request_company_id()

    query = DailyLog.query.filter_by(company_id=company_id)

    start_date = request.args.get('start_date')
    if start_date:
        try:
            query = query.filter(DailyLog.date >= parse_date_value(start_date, 'start_date'))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    end_date = request.args.get('end_date')
    if end_date:
        try:
            query = query.filter(DailyLog.date <= parse_date_value(end_date, 'end_date'))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    limit = min(request.args.get('limit', default=100, type=int), 1000)
    logs = query.order_by(DailyLog.date.desc(), DailyLog.id.desc()).limit(limit).all()

    return jsonify([
        {
            'id': log.id,
            'date': log.date.isoformat(),
            'items': log.items,
            'sales': log.sales,
            'labor_hours': log.labor_hours,
            'overtime_hours': log.overtime_hours,
            'payroll_cost': log.payroll_cost,
            'number_of_employees': log.number_of_employees,
            'labor_ratio': log.labor_ratio,
            'sales_over_labor_cost': log.sales_over_labor_cost,
            'average_man_hour_cost': log.average_man_hour_cost,
            'average_case_cost': log.average_case_cost,
            'average_hours_per_employee': log.average_hours_per_employee,
        }
        for log in logs
    ]), 200


@api.route('/api/labor/daily_logs', methods=['POST'])
@optional_api_key_or_login
def create_daily_log():
    try:
        company_id = get_request_company_id()
        raw_data = request.get_json()
        if not raw_data:
            return jsonify({'error': 'No data provided'}), 400

        try:
            data = DailyLogCreateSchema(**raw_data)
        except ValidationError as e:
            errors = {'.'.join(str(l) for l in err['loc']): err['msg'] for err in e.errors()}
            return jsonify({'error': 'Invalid input', 'details': errors}), 400

        raw_date = raw_data.get('date')
        if raw_date is None:
            log_date = datetime.utcnow().date()
        elif isinstance(raw_date, str):
            try:
                log_date = parse_date_value(raw_date, 'date')
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
        else:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD or ISO datetime'}), 400

        log = DailyLog(
            company_id=company_id,
            date=log_date,
            items=data.items,
            sales=data.sales,
            labor_hours=data.labor_hours,
            overtime_hours=data.overtime_hours,
            payroll_cost=data.payroll_cost,
            number_of_employees=data.number_of_employees,
            labor_ratio=data.labor_ratio,
            sales_over_labor_cost=data.sales_over_labor_cost,
            average_man_hour_cost=data.average_man_hour_cost,
            average_case_cost=data.average_case_cost,
            average_hours_per_employee=data.average_hours_per_employee,
        )

        db.session.add(log)
        db.session.flush()
        record_labor_summary(log)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Daily log created successfully',
            'daily_log': {
                'id': log.id,
                'date': log.date.isoformat(),
                'items': log.items,
                'sales': log.sales,
                'labor_hours': log.labor_hours,
                'overtime_hours': log.overtime_hours,
                'payroll_cost': log.payroll_cost,
                'number_of_employees': log.number_of_employees,
                'labor_ratio': log.labor_ratio,
                'sales_over_labor_cost': log.sales_over_labor_cost,
                'average_man_hour_cost': log.average_man_hour_cost,
                'average_case_cost': log.average_case_cost,
                'average_hours_per_employee': log.average_hours_per_employee,
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating daily log: {e}")
        return jsonify({'error': 'An error occurred while creating the daily log'}), 500


@api.route('/api/labor/daily_logs/<int:log_id>', methods=['DELETE'])
@optional_api_key_or_login
def delete_daily_log(log_id):
    try:
        company_id = get_request_company_id()
        log = DailyLog.query.filter_by(company_id=company_id, id=log_id).first()
        if not log:
            return jsonify({'error': 'Daily log not found'}), 404

        db.session.delete(log)
        db.session.commit()

        return jsonify({'success': True, 'message': f'Daily log {log_id} deleted successfully'}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting daily log: {e}")
        return jsonify({'error': 'An error occurred while deleting the daily log'}), 500


@api.route('/api/labor/pay_groups', methods=['GET'])
@optional_api_key_or_login
def get_pay_groups():
    company_id = get_request_company_id()
    pay_groups = PayGroups.query.filter_by(company_id=company_id).order_by(PayGroups.name).all()

    return jsonify([
        {
            'id': pay_group.id,
            'name': pay_group.name,
            'description': pay_group.description,
        }
        for pay_group in pay_groups
    ]), 200


@api.route('/api/labor/pay_groups', methods=['POST'])
@optional_api_key_or_login
def create_pay_group():
    try:
        company_id = get_request_company_id()
        raw_data = request.get_json()
        if not raw_data:
            return jsonify({'error': 'No data provided'}), 400

        try:
            data = PayGroupCreateSchema(**raw_data)
        except ValidationError as e:
            errors = {'.'.join(str(l) for l in err['loc']): err['msg'] for err in e.errors()}
            return jsonify({'error': 'Invalid input', 'details': errors}), 400

        existing = PayGroups.query.filter_by(company_id=company_id, name=data.name).first()
        if existing:
            return jsonify({'error': 'A pay group with this name already exists', 'id': existing.id}), 409

        pay_group = PayGroups(
            company_id=company_id,
            name=data.name,
            description=data.description,
        )
        db.session.add(pay_group)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Pay group created successfully',
            'pay_group': {
                'id': pay_group.id,
                'name': pay_group.name,
                'description': pay_group.description,
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating pay group: {e}")
        return jsonify({'error': 'An error occurred while creating the pay group'}), 500


@api.route('/api/labor/weekly_labor_entries', methods=['GET'])
@optional_api_key_or_login
def get_weekly_labor_entries():
    company_id = get_request_company_id()

    query = WeeklyLaborEntry.query.filter_by(company_id=company_id)

    pay_group_id = request.args.get('pay_group_id', type=int)
    if pay_group_id:
        query = query.filter_by(pay_group_id=pay_group_id)

    start_date = request.args.get('start_date')
    if start_date:
        try:
            query = query.filter(WeeklyLaborEntry.week_start_date >= parse_date_value(start_date, 'start_date'))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    end_date = request.args.get('end_date')
    if end_date:
        try:
            query = query.filter(WeeklyLaborEntry.week_start_date <= parse_date_value(end_date, 'end_date'))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    limit = min(request.args.get('limit', default=100, type=int), 1000)
    entries = query.order_by(WeeklyLaborEntry.week_start_date.desc(), WeeklyLaborEntry.id.desc()).limit(limit).all()

    return jsonify([
        {
            'id': entry.id,
            'week_start_date': entry.week_start_date.isoformat(),
            'pay_group_id': entry.pay_group_id,
            'regular_hours': entry.regular_hours,
            'overtime_hours': entry.overtime_hours,
            'pay': entry.pay,
            'percent_of_sales': entry.percent_of_sales,
            'cost_per_hour': entry.cost_per_hour,
            'number_in_pay_group': entry.number_in_pay_group,
            'number_with_overtime': entry.number_with_overtime,
            'average_hours_per_employee': entry.average_hours_per_employee,
        }
        for entry in entries
    ]), 200
