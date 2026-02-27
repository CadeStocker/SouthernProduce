from flask_mailman import EmailMessage
from producepricer.blueprints.items import update_item_total_cost
from producepricer.blueprints._blueprint import main

from flask import (
    redirect,
    render_template,
    request,
    url_for,
    flash,
    current_app
)
from itsdangerous import BadSignature, Serializer, SignatureExpired
from producepricer.models import (
    AIResponse,
    APIKey,
    BrandName,
    CostHistory, 
    Customer,
    CustomerEmail,
    DesignationCost,
    EmailTemplate,
    GrowerOrDistributor,
    Item,
    ItemDesignation, 
    ItemInfo, 
    ItemTotalCost, 
    LaborCost, 
    PackagingCost,
    PriceHistory,
    PriceSheet, 
    RanchPrice, 
    RawProduct,
    ReceivingImage,
    ReceivingLog,
    Seller,
    UnitOfWeight, 
    User, 
    Company, 
    PendingUser
)
from producepricer.forms import(
    AddBrandName,
    AddCustomer,
    AddCustomerEmail,
    AddDesignationCost,
    AddGrowerOrDistributor,
    AddItem, 
    AddLaborCost, 
    AddPackagingCost, 
    AddRanchPrice, 
    AddRawProduct, 
    AddRawProductCost,
    AddSeller,
    CreatePackage,
    DeleteForm, 
    EditItem,
    EditRawProduct,
    EmailTemplateForm,
    PriceQuoterForm,
    PriceSheetForm, 
    ResetPasswordForm, 
    ResetPasswordRequestForm, 
    SignUp, 
    Login, 
    CreateCompany, 
    UpdateItemInfo,
    UploadCSV, 
    UploadCustomerCSV, 
    UploadItemCSV, 
    UploadPackagingCSV, 
    UploadRawProductCSV
)
from flask_login import login_user, login_required, current_user, logout_user
from producepricer import db, bcrypt
import pandas as pd
import os
from werkzeug.utils import secure_filename
from flask_mailman import EmailMessage
from producepricer.utils.ai_utils import get_ai_response
from producepricer.utils.qr_utils import generate_api_key_qr_code, generate_qr_code_bytes
import pdfplumber
import tempfile
from sqlalchemy import func

# API Keys management page
@main.route('/api-keys')
@login_required
def api_keys():
    """Display all API keys for the current user's company."""
    # Get all API keys for the company
    api_keys = APIKey.query.filter_by(company_id=current_user.company_id).order_by(APIKey.created_at.desc()).all()
    
    return render_template('api_keys.html',
                           title='API Keys',
                           api_keys=api_keys)


# Create a new API key
@main.route('/api-keys/create', methods=['POST'])
@login_required
def create_api_key():
    """Create a new API key for a device."""
    device_name = request.form.get('device_name', '').strip()
    
    if not device_name:
        flash('Device name is required.', 'danger')
        return redirect(url_for('main.api_keys'))
    
    # Generate a new API key
    key = APIKey.generate_key()
    
    # Create the API key record
    api_key = APIKey(
        key=key,
        device_name=device_name,
        company_id=current_user.company_id,
        created_by_user_id=current_user.id
    )
    
    db.session.add(api_key)
    db.session.commit()
    
    # Generate QR code
    api_base_url = request.url_root.rstrip('/')
    qr_code_data = generate_api_key_qr_code(key, device_name, api_base_url)
    
    flash(f'API key created successfully for device: {device_name}', 'success')
    # Store the key and QR code in session to display them once (for security)
    from flask import session
    session['new_api_key'] = key
    session['new_api_key_device'] = device_name
    session['new_api_key_qr'] = qr_code_data
    session['new_api_key_id'] = api_key.id
    
    return redirect(url_for('main.api_keys'))


# Download QR code for an API key
@main.route('/api-keys/<int:key_id>/qr-code')
@login_required
def download_api_key_qr(key_id):
    """Generate and download a QR code for an existing API key."""
    api_key = APIKey.query.get_or_404(key_id)
    
    # Verify the key belongs to the user's company
    if api_key.company_id != current_user.company_id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('main.api_keys'))
    
    # Generate QR code with API configuration
    api_base_url = request.url_root.rstrip('/')
    import json
    config = {
        "type": "api_key",
        "key": api_key.key,
        "device_name": api_key.device_name,
        "api_url": api_base_url
    }
    qr_data = json.dumps(config)
    
    # Generate QR code bytes
    qr_bytes = generate_qr_code_bytes(qr_data)
    
    # Send as downloadable file
    from flask import send_file
    filename = f"api_key_{api_key.device_name.replace(' ', '_')}.png"
    return send_file(
        qr_bytes,
        mimetype='image/png',
        as_attachment=True,
        download_name=filename
    )


# Revoke an API key
@main.route('/api-keys/<int:key_id>/revoke', methods=['POST'])
@login_required
def revoke_api_key(key_id):
    """Revoke (deactivate) an API key."""
    api_key = APIKey.query.get_or_404(key_id)
    
    # Verify the key belongs to the user's company
    if api_key.company_id != current_user.company_id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('main.api_keys'))
    
    api_key.revoke()
    flash(f'API key for device "{api_key.device_name}" has been revoked.', 'success')
    
    return redirect(url_for('main.api_keys'))


# Activate an API key
@main.route('/api-keys/<int:key_id>/activate', methods=['POST'])
@login_required
def activate_api_key(key_id):
    """Reactivate a previously revoked API key."""
    api_key = APIKey.query.get_or_404(key_id)
    
    # Verify the key belongs to the user's company
    if api_key.company_id != current_user.company_id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('main.api_keys'))
    
    api_key.activate()
    flash(f'API key for device "{api_key.device_name}" has been reactivated.', 'success')
    
    return redirect(url_for('main.api_keys'))


# Delete an API key permanently
@main.route('/api-keys/<int:key_id>/delete', methods=['POST'])
@login_required
def delete_api_key(key_id):
    """Permanently delete an API key."""
    api_key = APIKey.query.get_or_404(key_id)
    
    # Verify the key belongs to the user's company
    if api_key.company_id != current_user.company_id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('main.api_keys'))
    
    device_name = api_key.device_name
    db.session.delete(api_key)
    db.session.commit()
    
    flash(f'API key for device "{device_name}" has been permanently deleted.', 'success')
    
    return redirect(url_for('main.api_keys'))