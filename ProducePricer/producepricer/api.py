from flask import Blueprint, jsonify, request, current_app, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
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
from datetime import datetime

api = Blueprint('api', __name__)

@api.before_request
def require_login():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Unauthorized'}), 401

@api.route('/api/receiving_logs', methods=['GET'])
@login_required
def get_receiving_logs():
    logs = ReceivingLog.query.filter_by(company_id=current_user.company_id).order_by(ReceivingLog.datetime.desc()).all()
    
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
            'images': [url_for('static', filename=f'receiving_images/{img.filename}', _external=True) for img in log.images]
        })
    
    return jsonify(logs_data)

@api.route('/api/receiving_logs', methods=['POST'])
@login_required
def create_receiving_log():
    data = request.get_json()
    
    try:
        new_log = ReceivingLog(
            raw_product_id=data['raw_product_id'],
            pack_size_unit=data['pack_size_unit'],
            pack_size=data['pack_size'],
            brand_name_id=data['brand_name_id'],
            quantity_received=data['quantity_received'],
            seller_id=data['seller_id'],
            temperature=data['temperature'],
            hold_or_used=data['hold_or_used'],
            grower_or_distributor_id=data['grower_or_distributor_id'],
            country_of_origin=data['country_of_origin'],
            received_by=data.get('received_by', f"{current_user.first_name} {current_user.last_name}"),
            company_id=current_user.company_id,
            returned=data.get('returned'),
            date_time=datetime.fromisoformat(data['datetime']) if 'datetime' in data else None
        )
        
        db.session.add(new_log)
        db.session.commit()
        
        return jsonify({'message': 'Receiving log created successfully', 'id': new_log.id}), 201
        
    except KeyError as e:
        return jsonify({'error': f'Missing required field: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api.route('/api/raw_products', methods=['GET'])
@login_required
def get_raw_products():
    products = RawProduct.query.filter_by(company_id=current_user.company_id).all()
    return jsonify([{'id': p.id, 'name': p.name} for p in products])

@api.route('/api/brand_names', methods=['GET'])
@login_required
def get_brand_names():
    brands = BrandName.query.filter_by(company_id=current_user.company_id).all()
    return jsonify([{'id': b.id, 'name': b.name} for b in brands])

@api.route('/api/sellers', methods=['GET'])
@login_required
def get_sellers():
    sellers = Seller.query.filter_by(company_id=current_user.company_id).all()
    return jsonify([{'id': s.id, 'name': s.name} for s in sellers])

@api.route('/api/growers_distributors', methods=['GET'])
@login_required
def get_growers_distributors():
    growers = GrowerOrDistributor.query.filter_by(company_id=current_user.company_id).all()
    return jsonify([{'id': g.id, 'name': g.name, 'city': g.city, 'state': g.state} for g in growers])

@api.route('/api/receiving_logs/<int:log_id>/images', methods=['POST'])
@login_required
def upload_receiving_images(log_id):
    log = ReceivingLog.query.get_or_404(log_id)
    
    if log.company_id != current_user.company_id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    if 'images' not in request.files:
        return jsonify({'error': 'No images provided'}), 400
        
    files = request.files.getlist('images')
    uploaded_images = []
    
    # Ensure directory exists
    upload_dir = os.path.join(current_app.root_path, 'static', 'receiving_images')
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
                company_id=current_user.company_id
            )
            db.session.add(new_image)
            uploaded_images.append(filename)
            
    db.session.commit()
    
    return jsonify({
        'message': f'{len(uploaded_images)} images uploaded successfully',
        'images': [url_for('static', filename=f'receiving_images/{img}', _external=True) for img in uploaded_images]
    }), 201
