import datetime
from flask_mailman import EmailMessage
from fpdf import FPDF
from producepricer.auth_utils import optional_api_key_or_login
from producepricer.blueprints.items import update_item_total_cost
from producepricer.blueprints._blueprint import main

from flask import (
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
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

# Debug route to check market price data
@main.route('/debug_receiving_log/<int:log_id>')
@login_required
def debug_receiving_log(log_id):
    """Debug route to check why market cost comparison isn't working."""
    from datetime import timedelta
    from sqlalchemy import and_
    
    log = ReceivingLog.query.filter_by(id=log_id, company_id=current_user.company_id).first_or_404()
    
    debug_info = {
        'log_id': log.id,
        'raw_product': log.raw_product.name if log.raw_product else None,
        'raw_product_id': log.raw_product_id,
        'price_paid': log.price_paid,
        'log_date': log.datetime.strftime('%Y-%m-%d') if log.datetime else None,
    }
    
    # Check for cost history
    if log.datetime:
        log_date = log.datetime.date()
        search_start = log_date - timedelta(days=30)
        
        debug_info['search_window_start'] = search_start.strftime('%Y-%m-%d')
        debug_info['search_window_end'] = log_date.strftime('%Y-%m-%d')
        
        # Get all cost history for this raw product
        all_costs = CostHistory.query.filter(
            and_(
                CostHistory.raw_product_id == log.raw_product_id,
                CostHistory.company_id == current_user.company_id
            )
        ).order_by(CostHistory.date.desc()).limit(10).all()
        
        debug_info['all_cost_history'] = [
            {
                'cost': float(ch.cost),
                'date': ch.date.strftime('%Y-%m-%d')
            }
            for ch in all_costs
        ]
        
        # Get cost history within the search window
        relevant_costs = CostHistory.query.filter(
            and_(
                CostHistory.raw_product_id == log.raw_product_id,
                CostHistory.company_id == current_user.company_id,
                CostHistory.date <= log_date,
                CostHistory.date >= search_start
            )
        ).order_by(CostHistory.date.desc()).all()
        
        debug_info['relevant_cost_history'] = [
            {
                'cost': float(ch.cost),
                'date': ch.date.strftime('%Y-%m-%d'),
                'days_before_log': (log_date - ch.date).days
            }
            for ch in relevant_costs
        ]
        
        # Get the actual market cost that would be used
        market_data = log.get_master_customer_price()
        if market_data:
            debug_info['market_cost_used'] = float(market_data[0])
            debug_info['market_cost_date'] = market_data[1].strftime('%Y-%m-%d')
        else:
            debug_info['market_cost_used'] = None
            debug_info['market_cost_date'] = None
        
        # Get the comparison
        comparison = log.get_price_comparison()
        debug_info['comparison'] = comparison if comparison else None
    
    return jsonify(debug_info)

# Receiving Logs - display all receiving log entries
@main.route('/receiving_logs')
@login_required
def receiving_logs():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 15  # Number of logs per page
    use_pagination = request.args.get('paginate', '0').lower() in ('1', 'true', 'yes')
    pagination = None

    base_query = ReceivingLog.query.filter_by(company_id=current_user.company_id)
    
    # Apply search filter if provided (search by raw product name, received_by, or country_of_origin)
    if q:
        base_query = base_query.join(RawProduct).filter(
            (RawProduct.name.ilike(f'%{q}%')) | 
            (ReceivingLog.received_by.ilike(f'%{q}%')) |
            (ReceivingLog.country_of_origin.ilike(f'%{q}%'))
        )
    
    if use_pagination:
        pagination = base_query.order_by(ReceivingLog.datetime.desc()).paginate(page=page, per_page=per_page, error_out=False)
        logs = pagination.items
    else:
        # return all results without pagination
        logs = base_query.order_by(ReceivingLog.datetime.desc()).all()

    return render_template(
        'receiving_logs.html',
        title='Receiving Logs',
        logs=logs,
        q=q,
        pagination=pagination,
        use_pagination=use_pagination
    )

# View individual receiving log
@main.route('/receiving_log/<int:log_id>')
@login_required
def view_receiving_log(log_id):
    log = ReceivingLog.query.filter_by(id=log_id, company_id=current_user.company_id).first_or_404()
    
    # Get master customer price even if no price_paid is set yet
    # This allows the modal to show market reference
    market_data = log.get_master_customer_price()
    master_price = market_data[0] if market_data else None
    master_price_date = market_data[1] if market_data else None
    
    return render_template(
        'view_receiving_log.html',
        title=f'Receiving Log - {log.raw_product.name if log.raw_product else "Log"}',
        log=log,
        master_price=master_price,
        master_price_date=master_price_date,
        now=datetime.datetime.utcnow()
    )

# Edit receiving log (for adding price paid by management)
@main.route('/edit_receiving_log/<int:log_id>', methods=['POST'])
@login_required
def edit_receiving_log(log_id):
    log = ReceivingLog.query.filter_by(id=log_id, company_id=current_user.company_id).first_or_404()
    
    # Get price_paid from form
    price_paid_str = request.form.get('price_paid', '').strip()
    
    # Validate and convert price_paid
    if price_paid_str:
        try:
            price_paid = float(price_paid_str)
            if price_paid < 0:
                flash('Price paid must be a positive number.', 'danger')
                return redirect(url_for('main.view_receiving_log', log_id=log_id))
            log.price_paid = price_paid
        except ValueError:
            flash('Invalid price format. Please enter a valid number.', 'danger')
            return redirect(url_for('main.view_receiving_log', log_id=log_id))
    else:
        # If empty, set to None to remove price
        log.price_paid = None
    
    db.session.commit()
    flash('Receiving log updated successfully!', 'success')
    return redirect(url_for('main.view_receiving_log', log_id=log_id))

# Email receiving log
@main.route('/email_receiving_log/<int:log_id>', methods=['POST'])
@login_required
def email_receiving_log(log_id):
    log = ReceivingLog.query.filter_by(id=log_id, company_id=current_user.company_id).first_or_404()
    
    recipient = request.form.get('recipient', '').strip()
    subject = request.form.get('subject', '').strip()
    additional_message = request.form.get('message', '').strip()
    
    if not recipient:
        flash('Recipient email address is required.', 'danger')
        return redirect(url_for('main.view_receiving_log', log_id=log_id))
    
    # Set default subject if not provided
    if not subject:
        product_name = log.raw_product.name if log.raw_product else 'Product'
        date_str = log.datetime.strftime('%Y-%m-%d') if log.datetime else ''
        subject = f'Receiving Log - {product_name} - {date_str}'
    
    # Build email body
    body_parts = []
    
    if additional_message:
        body_parts.append(additional_message)
        body_parts.append('<br><br><hr><br>')
    
    # Add log details
    body_parts.append(f'<h2>Receiving Log Details</h2>')
    body_parts.append(f'<p><strong>Log ID:</strong> #{log.id}</p>')
    body_parts.append(f'<p><strong>Date & Time:</strong> {log.datetime.strftime("%Y-%m-%d %H:%M") if log.datetime else "N/A"}</p>')
    body_parts.append('<br>')
    
    body_parts.append('<h3>Product Information</h3>')
    body_parts.append(f'<p><strong>Raw Product:</strong> {log.raw_product.name if log.raw_product else "N/A"}</p>')
    body_parts.append(f'<p><strong>Brand Name:</strong> {log.brand_name.name if log.brand_name else "N/A"}</p>')
    body_parts.append(f'<p><strong>Pack Size:</strong> {log.pack_size} {log.pack_size_unit}</p>')
    body_parts.append(f'<p><strong>Quantity Received:</strong> {log.quantity_received} units</p>')
    body_parts.append(f'<p><strong>Total:</strong> {log.quantity_received * log.pack_size:.2f} {log.pack_size_unit}</p>')
    
    # Add price information if available
    if log.price_paid:
        body_parts.append(f'<p><strong>Price Paid:</strong> ${log.price_paid:.2f} per {log.pack_size_unit}</p>')
    
    body_parts.append('<br>')
    
    body_parts.append('<h3>Quality & Status</h3>')
    body_parts.append(f'<p><strong>Temperature:</strong> {log.temperature:.1f}°F</p>')
    body_parts.append(f'<p><strong>Status:</strong> {log.hold_or_used.upper()}</p>')
    body_parts.append(f'<p><strong>Country of Origin:</strong> {log.country_of_origin}</p>')
    if log.returned:
        body_parts.append(f'<p><strong>Returned By:</strong> {log.returned}</p>')
    body_parts.append('<br>')
    
    body_parts.append('<h3>Source Information</h3>')
    body_parts.append(f'<p><strong>Seller:</strong> {log.seller.name if log.seller else "N/A"}</p>')
    body_parts.append(f'<p><strong>Grower/Distributor:</strong> {log.grower_or_distributor.name if log.grower_or_distributor else "N/A"}</p>')
    if log.grower_or_distributor and (log.grower_or_distributor.city or log.grower_or_distributor.state):
        location_parts = []
        if log.grower_or_distributor.city:
            location_parts.append(log.grower_or_distributor.city)
        if log.grower_or_distributor.state:
            location_parts.append(log.grower_or_distributor.state)
        body_parts.append(f'<p><strong>Location:</strong> {", ".join(location_parts)}</p>')
    body_parts.append('<br>')
    
    body_parts.append('<h3>Receiving Details</h3>')
    body_parts.append(f'<p><strong>Received By:</strong> {log.received_by}</p>')
    
    if log.images:
        body_parts.append('<br>')
        body_parts.append(f'<p><em>Note: This log includes {len(log.images)} image(s). Please view the log online to see the images.</em></p>')
        body_parts.append(f'<p><a href="{url_for("main.view_receiving_log", log_id=log.id, _external=True)}">View Full Log with Images</a></p>')
    
    body = ''.join(body_parts)
    
    # Send email
    sender = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('EMAIL_USER')
    
    msg = EmailMessage(
        subject=subject,
        body=body,
        to=[recipient],
        from_email=sender
    )
    msg.content_subtype = 'html'
    
    try:
        msg.send()
        flash(f'Receiving log emailed to {recipient}.', 'success')
    except Exception as e:
        flash(f'Failed to send email: {str(e)}', 'danger')
    
    return redirect(url_for('main.view_receiving_log', log_id=log_id))

# Generate and download receiving log as PDF
@main.route('/receiving_log/<int:log_id>/pdf')
@login_required
def download_receiving_log_pdf(log_id):
    log = ReceivingLog.query.filter_by(id=log_id, company_id=current_user.company_id).first_or_404()
    
    # Generate PDF
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    
    # Company header
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Southern Produce Processors Inc.", ln=1, align="C")
    
    # Title
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Receiving Log", ln=1, align="C")
    
    # Date generated
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 8, f"Generated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}", ln=1, align="C")
    pdf.ln(5)
    
    # Log header info
    pdf.set_font("Arial", "B", 12)
    product_name = log.raw_product.name if log.raw_product else 'N/A'
    pdf.cell(0, 8, product_name, ln=1)
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 6, f"Received: {log.datetime.strftime('%B %d, %Y at %I:%M %p') if log.datetime else 'N/A'}", ln=1)
    pdf.cell(0, 6, f"Log ID: #{log.id}", ln=1)
    pdf.ln(5)
    
    # Column widths for the table
    col1_width = 70  # Label column
    col2_width = 110  # Value column
    table_width = col1_width + col2_width  # Total table width: 180mm
    row_height = 8
    
    # Helper function to add a table row
    def add_table_row(label, value, border=1):
        pdf.set_font("Arial", "B", 10)
        pdf.cell(col1_width, row_height, label, border=border, align="L")
        pdf.set_font("Arial", "", 10)
        pdf.cell(col2_width, row_height, value, border=border, align="L", ln=1)
    
    # Product Information Section
    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(200, 220, 255)  # Light blue background
    pdf.cell(table_width, row_height, "Product Information", border=1, ln=1, align="L", fill=True)
    
    add_table_row("Raw Product", product_name)
    add_table_row("Brand Name", log.brand_name.name if log.brand_name else 'N/A')
    add_table_row("Pack Size", f"{log.pack_size} {log.pack_size_unit}")
    add_table_row("Quantity Received", f"{log.quantity_received} units")
    add_table_row("Total Weight/Count", f"{log.quantity_received * log.pack_size:.2f} {log.pack_size_unit}")
    
    # Add price information if available
    if log.price_paid:
        add_table_row("Price Paid", f"${log.price_paid:.2f} per {log.pack_size_unit}")
    
    pdf.ln(3)
    
    # Quality & Status Section
    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(table_width, row_height, "Quality & Status", border=1, ln=1, align="L", fill=True)
    
    add_table_row("Temperature", f"{log.temperature:.1f} degrees F")
    add_table_row("Status", log.hold_or_used.upper())
    add_table_row("Country of Origin", log.country_of_origin)
    if log.returned:
        add_table_row("Returned By", log.returned)
    
    pdf.ln(3)
    
    # Source Information Section
    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(table_width, row_height, "Source Information", border=1, ln=1, align="L", fill=True)
    
    add_table_row("Seller", log.seller.name if log.seller else 'N/A')
    
    grower_name = log.grower_or_distributor.name if log.grower_or_distributor else 'N/A'
    add_table_row("Grower/Distributor", grower_name)
    
    if log.grower_or_distributor and (log.grower_or_distributor.city or log.grower_or_distributor.state):
        location_parts = []
        if log.grower_or_distributor.city:
            location_parts.append(log.grower_or_distributor.city)
        if log.grower_or_distributor.state:
            location_parts.append(log.grower_or_distributor.state)
        add_table_row("Location", ", ".join(location_parts))
    
    pdf.ln(3)
    
    # Receiving Details Section
    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(table_width, row_height, "Receiving Details", border=1, ln=1, align="L", fill=True)
    
    add_table_row("Received By", log.received_by)
    add_table_row("Date & Time", log.datetime.strftime('%Y-%m-%d %H:%M') if log.datetime else 'N/A')
    
    pdf.ln(5)
    
    # Images note
    if log.images:
        pdf.set_font("Arial", "I", 9)
        pdf.multi_cell(0, 5, f"Note: This log includes {len(log.images)} image(s). Images are not included in this PDF. Please view the log online to see the images.")
    
    # Generate PDF bytes
    pdf_bytes = bytes(pdf.output(dest='S'))
    
    # Create response
    resp = make_response(pdf_bytes)
    resp.headers['Content-Type'] = 'application/pdf'
    
    # Generate filename
    product_name_safe = ''.join(c for c in product_name if c.isalnum() or c in (' ', '-', '_')).strip()
    date_str = log.datetime.strftime('%Y%m%d') if log.datetime else 'unknown'
    filename = f"receiving_log_{product_name_safe}_{date_str}.pdf"
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return resp

# Brand Names - display and manage brand names
@main.route('/brand_names')
@login_required
def brand_names():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 15
    use_pagination = request.args.get('paginate', '0').lower() in ('1', 'true', 'yes')

    base_query = BrandName.query.filter_by(company_id=current_user.company_id)
    
    if q:
        base_query = base_query.filter(BrandName.name.ilike(f'%{q}%'))
    
    if use_pagination:
        pagination = base_query.order_by(BrandName.name.asc()).paginate(page=page, per_page=per_page, error_out=False)
        brands = pagination.items
    else:
        brands = base_query.order_by(BrandName.name.asc()).all()
        pagination = None

    form = AddBrandName()
    delete_form = DeleteForm()

    return render_template(
        'brand_names.html',
        title='Brand Names',
        brands=brands,
        form=form,
        delete_form=delete_form,
        q=q,
        pagination=pagination,
        use_pagination=use_pagination
    )

@main.route('/add_brand_name', methods=['POST'])
@login_required
def add_brand_name():
    form = AddBrandName()
    if form.validate_on_submit():
        brand = BrandName(name=form.name.data, company_id=current_user.company_id)
        db.session.add(brand)
        db.session.commit()
        flash(f'Brand name "{form.name.data}" has been added successfully!', 'success')
    else:
        flash('Invalid data submitted.', 'danger')
    return redirect(url_for('main.brand_names'))

@main.route('/delete_brand_name/<int:brand_id>', methods=['POST'])
@login_required
def delete_brand_name(brand_id):
    brand = BrandName.query.filter_by(id=brand_id, company_id=current_user.company_id).first()
    if not brand:
        flash('Brand name not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.brand_names'))
    
    db.session.delete(brand)
    db.session.commit()
    flash(f'Brand name "{brand.name}" has been deleted.', 'success')
    return redirect(url_for('main.brand_names'))

# Sellers - display and manage sellers
@main.route('/sellers')
@login_required
def sellers():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 15
    use_pagination = request.args.get('paginate', '0').lower() in ('1', 'true', 'yes')

    base_query = Seller.query.filter_by(company_id=current_user.company_id)
    
    if q:
        base_query = base_query.filter(Seller.name.ilike(f'%{q}%'))
    
    if use_pagination:
        pagination = base_query.order_by(Seller.name.asc()).paginate(page=page, per_page=per_page, error_out=False)
        sellers_list = pagination.items
    else:
        sellers_list = base_query.order_by(Seller.name.asc()).all()
        pagination = None

    form = AddSeller()
    delete_form = DeleteForm()

    return render_template(
        'sellers.html',
        title='Sellers',
        sellers=sellers_list,
        form=form,
        delete_form=delete_form,
        q=q,
        pagination=pagination,
        use_pagination=use_pagination
    )

@main.route('/add_seller', methods=['POST'])
@login_required
def add_seller():
    form = AddSeller()
    if form.validate_on_submit():
        seller = Seller(name=form.name.data, company_id=current_user.company_id)
        db.session.add(seller)
        db.session.commit()
        flash(f'Seller "{form.name.data}" has been added successfully!', 'success')
    else:
        flash('Invalid data submitted.', 'danger')
    return redirect(url_for('main.sellers'))

@main.route('/delete_seller/<int:seller_id>', methods=['POST'])
@login_required
def delete_seller(seller_id):
    seller = Seller.query.filter_by(id=seller_id, company_id=current_user.company_id).first()
    if not seller:
        flash('Seller not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.sellers'))
    
    db.session.delete(seller)
    db.session.commit()
    flash(f'Seller "{seller.name}" has been deleted.', 'success')
    return redirect(url_for('main.sellers'))

# Growers/Distributors - display and manage growers/distributors
@main.route('/growers_distributors')
@login_required
def growers_distributors():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 15
    use_pagination = request.args.get('paginate', '0').lower() in ('1', 'true', 'yes')

    base_query = GrowerOrDistributor.query.filter_by(company_id=current_user.company_id)
    
    if q:
        base_query = base_query.filter(
            (GrowerOrDistributor.name.ilike(f'%{q}%')) |
            (GrowerOrDistributor.city.ilike(f'%{q}%')) |
            (GrowerOrDistributor.state.ilike(f'%{q}%'))
        )
    
    if use_pagination:
        pagination = base_query.order_by(GrowerOrDistributor.name.asc()).paginate(page=page, per_page=per_page, error_out=False)
        growers = pagination.items
    else:
        growers = base_query.order_by(GrowerOrDistributor.name.asc()).all()
        pagination = None

    form = AddGrowerOrDistributor()
    delete_form = DeleteForm()

    return render_template(
        'growers_distributors.html',
        title='Growers/Distributors',
        growers=growers,
        form=form,
        delete_form=delete_form,
        q=q,
        pagination=pagination,
        use_pagination=use_pagination
    )

@main.route('/add_grower_distributor', methods=['POST'])
@login_required
def add_grower_distributor():
    form = AddGrowerOrDistributor()
    if form.validate_on_submit():
        grower = GrowerOrDistributor(
            name=form.name.data,
            city=form.city.data,
            state=form.state.data,
            company_id=current_user.company_id
        )
        db.session.add(grower)
        db.session.commit()
        flash(f'Grower/Distributor "{form.name.data}" has been added successfully!', 'success')
    else:
        flash('Invalid data submitted.', 'danger')
    return redirect(url_for('main.growers_distributors'))

@main.route('/delete_grower_distributor/<int:grower_id>', methods=['POST'])
@login_required
def delete_grower_distributor(grower_id):
    grower = GrowerOrDistributor.query.filter_by(id=grower_id, company_id=current_user.company_id).first()
    if not grower:
        flash('Grower/Distributor not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.growers_distributors'))
    
    db.session.delete(grower)
    db.session.commit()
    flash(f'Grower/Distributor "{grower.name}" has been deleted.', 'success')
    return redirect(url_for('main.growers_distributors'))

@main.route('/receiving_images/<path:filename>')
@optional_api_key_or_login
def get_receiving_image(filename):
    return send_from_directory(current_app.config['RECEIVING_IMAGES_DIR'], filename)