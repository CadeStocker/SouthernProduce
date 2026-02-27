import datetime
from flask_mailman import EmailMessage
from fpdf import FPDF
from producepricer.blueprints.items import update_item_total_cost
from producepricer.blueprints._blueprint import main

from flask import (
    make_response,
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

# raw price sheet
@main.route('/raw_price_sheet')
@login_required
def raw_price_sheet():
    """
    Show a price sheet with the latest cost for every raw product for the current company.
    """
    # load all raw products for the company
    raw_products = RawProduct.query.filter_by(company_id=current_user.company_id).order_by(RawProduct.name).all()
    
    # load all customers for the email modal
    customers = Customer.query.filter_by(company_id=current_user.company_id).order_by(Customer.name).all()

    # build a mapping of latest cost + date for each raw product
    # need to show 1st and 2nd most recent costs
    # also make a mapping of average costs
    recent   = {}
    previous = {}
    average  = {}

    for rp in raw_products:
        ch = (CostHistory.query
              .filter_by(raw_product_id=rp.id, company_id=current_user.company_id)
              .order_by(CostHistory.date.desc(), CostHistory.id.desc())
              .first())
        recent[rp.id] = {
            'name': rp.name,
            'price': f"{ch.cost:.2f}" if ch and ch.cost is not None else None,
            'date': ch.date.strftime('%Y-%m-%d') if ch and ch.date else None
        }

        # Get the second-most-recent CostHistory entry by offsetting the ordered query.
        ch_prev = (CostHistory.query
              .filter_by(raw_product_id=rp.id, company_id=current_user.company_id)
              .order_by(CostHistory.date.desc(), CostHistory.id.desc())
              .offset(1)
              .first())  # second most recent
        previous[rp.id] = {
            'name': rp.name,
            'price': f"{ch_prev.cost:.2f}" if ch_prev and ch_prev.cost is not None else None,
            'date': ch_prev.date.strftime('%Y-%m-%d') if ch_prev and ch_prev.date else None
        }

        average[rp.id] = db.session.query(func.avg(CostHistory.cost)).filter(
            CostHistory.raw_product_id == rp.id,
            CostHistory.company_id == current_user.company_id
        ).scalar()

    return render_template('raw_price_sheet.html', title='Raw Product Price Sheet', raw_products=raw_products, recent=recent, previous=previous, customers=customers, average=average)

def _generate_raw_price_sheet_pdf_bytes(raw_products, recent_map, previous_map=None, hide_previous=False, sheet_name="Raw Product Price Sheet"):
    """
    Simple PDF generator that lists raw products and their most recent prices.
    Returns bytes.
    """
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    # Add company name as a prominent title
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Southern Produce Processors Inc.", ln=1, align="C")
    # Add the sheet name as a subtitle
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, sheet_name, ln=1, align="C")
    pdf.set_font("Arial", "", 12)
    pdf.ln(2)

    # table header
    pdf.set_font("Arial", "B", 11)
    
    if hide_previous:
        # 3 columns
        col_widths = [100, 40, 40]
        headers = ["Raw Product", "Latest Cost", "Date"]
    else:
        # 5 columns - need to adjust widths to fit A4 (approx 190mm usable width)
        # 190 total. 
        col_widths = [70, 30, 30, 30, 30]
        headers = ["Raw Product", "Latest Cost", "Date", "Prev Cost", "Prev Date"]

    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, border=1, align="C")
    pdf.ln()

    pdf.set_font("Arial", "", 10)
    for rp in raw_products:
        info = recent_map.get(rp.id, {})
        price = f"${info['price']}" if info.get('price') else "-"
        date = info.get('date') or "-"
        
        # Truncate name if needed
        name = rp.name[:40] if not hide_previous else rp.name[:60]

        pdf.cell(col_widths[0], 8, name, border=1)
        pdf.cell(col_widths[1], 8, price, border=1, align="C")
        pdf.cell(col_widths[2], 8, date, border=1, align="C")
        
        if not hide_previous:
            prev_info = previous_map.get(rp.id, {}) if previous_map else {}
            prev_price = f"${prev_info['price']}" if prev_info.get('price') else "-"
            prev_date = prev_info.get('date') or "-"
            
            pdf.cell(col_widths[3], 8, prev_price, border=1, align="C")
            pdf.cell(col_widths[4], 8, prev_date, border=1, align="C")
            
        pdf.ln()

    return bytes(pdf.output(dest='S'))


@main.route('/raw_price_sheet/export_pdf')
@login_required
def export_raw_price_sheet_pdf():
    # reuse same data gathering as the html view
    raw_products = RawProduct.query.filter_by(company_id=current_user.company_id).order_by(RawProduct.name).all()
    recent = {}
    previous = {}
    
    for rp in raw_products:
        ch = (CostHistory.query
              .filter_by(raw_product_id=rp.id, company_id=current_user.company_id)
              .order_by(CostHistory.date.desc(), CostHistory.id.desc())
              .first())
        recent[rp.id] = {
            'name': rp.name,
            'price': f"{ch.cost:.2f}" if ch and ch.cost is not None else None,
            'date': ch.date.strftime('%Y-%m-%d') if ch and ch.date else None
        }
        
        ch_prev = (CostHistory.query
              .filter_by(raw_product_id=rp.id, company_id=current_user.company_id)
              .order_by(CostHistory.date.desc(), CostHistory.id.desc())
              .offset(1)
              .first())
        previous[rp.id] = {
            'name': rp.name,
            'price': f"{ch_prev.cost:.2f}" if ch_prev and ch_prev.cost is not None else None,
            'date': ch_prev.date.strftime('%Y-%m-%d') if ch_prev and ch_prev.date else None
        }

    pdf_bytes = _generate_raw_price_sheet_pdf_bytes(raw_products, recent, previous_map=previous, hide_previous=False)

    resp = make_response(pdf_bytes)
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = 'attachment; filename=raw_price_sheet.pdf'
    return resp

@main.route('/raw_price_sheet/email', methods=['POST'])
@login_required
def email_raw_price_sheet():
    # Get recipients
    recipients = request.form.getlist('recipients')
    single_recipient = request.form.get('recipient')
    if single_recipient and single_recipient not in recipients:
        recipients.append(single_recipient)
    
    # Filter out empty strings
    recipients = [r.strip() for r in recipients if r and r.strip()]
    
    if not recipients:
        flash('At least one recipient email is required.', 'danger')
        return redirect(url_for('main.raw_price_sheet'))
        
    # Check if we should hide previous costs
    hide_previous = request.form.get('hide_previous') == 'on'
    
    # Generate PDF
    raw_products = RawProduct.query.filter_by(company_id=current_user.company_id).order_by(RawProduct.name).all()
    recent = {}
    previous = {}
    
    for rp in raw_products:
        ch = (CostHistory.query
              .filter_by(raw_product_id=rp.id, company_id=current_user.company_id)
              .order_by(CostHistory.date.desc(), CostHistory.id.desc())
              .first())
        recent[rp.id] = {
            'name': rp.name,
            'price': f"{ch.cost:.2f}" if ch and ch.cost is not None else None,
            'date': ch.date.strftime('%Y-%m-%d') if ch and ch.date else None
        }
        
        ch_prev = (CostHistory.query
              .filter_by(raw_product_id=rp.id, company_id=current_user.company_id)
              .order_by(CostHistory.date.desc(), CostHistory.id.desc())
              .offset(1)
              .first())
        previous[rp.id] = {
            'name': rp.name,
            'price': f"{ch_prev.cost:.2f}" if ch_prev and ch_prev.cost is not None else None,
            'date': ch_prev.date.strftime('%Y-%m-%d') if ch_prev and ch_prev.date else None
        }

    pdf_bytes = _generate_raw_price_sheet_pdf_bytes(raw_products, recent, previous_map=previous, hide_previous=hide_previous)
    
    # Send email
    sender = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('EMAIL_USER')
    subject = "Raw Product Price Sheet"
    body = "Attached is the current Raw Product Price Sheet."
    
    msg = EmailMessage(
        subject=subject,
        body=body,
        to=recipients,
        from_email=sender
    )
    msg.content_subtype = 'html'
    msg.attach('raw_price_sheet.pdf', pdf_bytes, 'application/pdf')
    
    try:
        msg.send()
        flash(f'Raw Price Sheet emailed to {", ".join(recipients)}.', 'success')
    except Exception as e:
        flash(f'Failed to send email: {e}', 'danger')
        
    return redirect(url_for('main.raw_price_sheet'))

@main.route('/raw_product')
@login_required
def raw_product():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 15  # Number of raw products per page
    use_pagination = request.args.get('paginate', '0').lower() in ('1', 'true', 'yes')

    base_query = RawProduct.query.filter_by(company_id=current_user.company_id)
    if q:
        base_query = RawProduct.query.filter(RawProduct.name.ilike(f'%{q}%'))
    
    if use_pagination:
        pagination = base_query.order_by(RawProduct.name.asc()).paginate(page=page, per_page=per_page, error_out=False)
        raw_products = pagination.items
    else:
        # return all result without pagination
        raw_products = base_query.order_by(RawProduct.name.asc()).all()
        pagination = None

    # Get the most recent cost for each raw product
    raw_product_costs = {}
    for raw_product in raw_products:
        most_recent_cost = (
            CostHistory.query
            .filter_by(raw_product_id=raw_product.id)
            .order_by(CostHistory.date.desc(), CostHistory.id.desc())
            .first()
        )
        if most_recent_cost:
            raw_product_costs[raw_product.id] = most_recent_cost

    # Forms
    form = AddRawProduct()
    cost_form = AddRawProductCost()
    upload_raw_product_csv_form = UploadRawProductCSV()
    csv_form = UploadCSV()
    delete_form = DeleteForm()

    return render_template(
        'raw_product.html',
        title='Raw Product',
        raw_products=raw_products,
        raw_product_costs=raw_product_costs,
        form=form,
        cost_form=cost_form,
        upload_csv_form=upload_raw_product_csv_form,
        q=q,
        delete_form=delete_form,
        csv_form=csv_form,
        pagination=pagination,  # Pass pagination object to template
        use_pagination=use_pagination
    )

# view an individual raw product
@main.route('/raw_product/<int:raw_product_id>')
@login_required
def view_raw_product(raw_product_id):
    # Find the raw product in the database
    raw_product = RawProduct.query.filter_by(id=raw_product_id, company_id=current_user.company_id).first()
    if raw_product is None:
        flash('Raw product not found.', 'danger')
        return redirect(url_for('main.raw_product'))
    
    # Get all the cost history for this raw product
    cost_history = CostHistory.query.filter_by(raw_product_id=raw_product_id).order_by(CostHistory.date.asc()).all()

    # find the items that use this raw product
    items_using_raw_product = Item.query.filter(Item.raw_products.any(id=raw_product_id)).all()

    # Get all receiving logs for this raw product
    receiving_logs = ReceivingLog.query.filter_by(
        raw_product_id=raw_product_id,
        company_id=current_user.company_id
    ).order_by(ReceivingLog.datetime.desc()).all()

    cost_form = AddRawProductCost()
    edit_form = EditRawProduct()
    edit_form.name.data = raw_product.name  # Pre-populate with current name

    return render_template(
        'view_raw_product.html',
        items_using_raw_product=items_using_raw_product,
        title='View Raw Product',
        cost_form=cost_form,
        edit_form=edit_form,
        raw_product=raw_product,
        cost_history=cost_history,
        receiving_logs=receiving_logs
    )

# delete a raw product cost
@main.route('/delete_raw_product_cost/<int:cost_id>', methods=['POST'])
@login_required
def delete_raw_product_cost(cost_id):
    # Find the cost in the database
    cost = CostHistory.query.filter_by(id=cost_id, company_id=current_user.company_id).first()
    if not cost:
        flash('Cost not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.raw_product'))

    # Delete the cost
    db.session.delete(cost)
    db.session.commit()

    # Update the total cost for any items using this raw product
    items_using_raw_product = Item.query.filter(Item.raw_products.any(id=cost.raw_product_id)).all()
    
    for item in items_using_raw_product:
        update_item_total_cost(item.id)

    flash('Raw product cost has been deleted successfully.', 'success')
    return redirect(url_for('main.view_raw_product', raw_product_id=cost.raw_product_id))

# Add a new raw product
@main.route('/add_raw_product', methods=['POST'])
@login_required
def add_raw_product():
    form = AddRawProduct()
    if form.validate_on_submit():

        # Check if the raw product already exists
        existing_raw_product = RawProduct.query.filter_by(name=form.name.data, company_id=current_user.company_id).first()
        if existing_raw_product:
            flash(f'Raw product "{form.name.data}" already exists.', 'warning')
            return redirect(url_for('main.raw_product'))
        
        # Create a new raw product object
        raw_product = RawProduct(
            name=form.name.data,
            company_id=current_user.company_id
        )

        # Add the raw product to the database
        db.session.add(raw_product)
        db.session.commit()

        # tell the user the raw product was added
        flash(f'Raw product "{form.name.data}" has been added successfully!', 'success')
        return redirect(url_for('main.raw_product'))
    flash('Invalid data submitted.', 'danger')
    return redirect(url_for('main.raw_product'))

# Add a new raw product cost
@main.route('/add_raw_product_cost/<int:raw_product_id>', methods=['POST'])
@login_required
def add_raw_product_cost(raw_product_id):
    form = AddRawProductCost()
    if form.validate_on_submit():
        # Create a new cost history entry
        cost_history = CostHistory(
            raw_product_id=raw_product_id,
            cost=form.cost.data,
            date=form.date.data,
            company_id=current_user.company_id
        )
        db.session.add(cost_history)
        db.session.commit()

        # Update the total cost for any items using this raw product
        items_using_raw_product = Item.query.filter(Item.raw_products.any(id=raw_product_id)).all()
    
        for item in items_using_raw_product:
            update_item_total_cost(item.id)

        flash(f'Cost added for raw product!', 'success')
    else:
        flash('Invalid data submitted.', 'danger')
    return redirect(url_for('main.raw_product', raw_product_id=raw_product_id))


# raw product import
@main.route('/upload_raw_product_csv', methods=['GET', 'POST'])
@login_required
def upload_raw_product_csv():
    form = UploadRawProductCSV()
    if form.validate_on_submit():
        # Check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        # If user does not select a file, browser also submits an empty part without filename
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file:
            # Ensure the upload folder exists
            if not os.path.exists(current_app.config['UPLOAD_FOLDER']):
                os.makedirs(current_app.config['UPLOAD_FOLDER'])

            # Save the file securely
            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Read the CSV file into a pandas DataFrame
            try:
                df = pd.read_csv(filepath)
            except Exception as e:
                flash(f'Error reading CSV file: {e}', 'danger')
                return redirect(request.url)

            # Make sure the columns are all in the CSV
            required_columns = ['name', 'cost']
            if not all(column in df.columns for column in required_columns):
                flash('Invalid CSV format. Please ensure all required columns are present.', 'danger')
                return redirect(request.url)

            # Process the DataFrame and add raw products to the database
            for index, row in df.iterrows():
                # Clean and convert cost values
                name = row['name'].strip()
                
                try:
                    cost_value = row['cost']
                    # Check if the value is NaN
                    if pd.isna(cost_value):
                        flash(f'Invalid cost for raw product "{name}". Skipping.', 'warning')
                        continue
                    # Convert to float and strip dollar signs
                    cost = float(str(cost_value).replace('$', '').strip())
                except (ValueError, TypeError):
                    flash(f'Invalid cost format for raw product "{name}". Skipping.', 'warning')
                    continue

                if cost < 0:
                    flash(f'Cost for raw product "{name}" cannot be negative. Skipping.', 'warning')
                    continue

                # Check if the raw product already exists
                raw_product = RawProduct.query.filter_by(name=name, company_id=current_user.company_id).first()
                if raw_product is None:
                    raw_product = RawProduct(name=name, company_id=current_user.company_id)
                    db.session.add(raw_product)
                    db.session.commit()

                # Add a cost history entry for the raw product
                cost_history = CostHistory(
                    raw_product_id=raw_product.id,
                    cost=cost,
                    date=datetime.datetime.utcnow(),
                    company_id=current_user.company_id
                )

                db.session.add(cost_history)
                db.session.commit()

            flash('Raw products imported successfully!', 'success')
            return redirect(url_for('main.raw_product'))
    flash('Invalid data submitted.', 'danger')
    return render_template('raw_product.html', title='Raw Product', form=form)

@main.route('/delete_raw_product/<int:raw_product_id>', methods=['POST'])
@login_required
def delete_raw_product(raw_product_id):
    # Find the raw product in the database
    raw_product = RawProduct.query.filter_by(id=raw_product_id, company_id=current_user.company_id).first()
    if not raw_product:
        flash('Raw product not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.raw_product'))

    # Remove all associations from item_raw table (unlink from items)
    # This must be done before deleting the raw product to avoid foreign key issues
    for item in raw_product.items:
        item.raw_products.remove(raw_product)
    
    # Delete all associated CostHistory entries
    CostHistory.query.filter_by(raw_product_id=raw_product_id).delete()

    # Delete the raw product itself
    db.session.delete(raw_product)
    db.session.commit()

    flash(f'Raw product "{raw_product.name}" and its associated costs have been deleted.', 'success')
    return redirect(url_for('main.raw_product'))

@main.route('/edit_raw_product/<int:raw_product_id>', methods=['POST'])
@login_required
def edit_raw_product(raw_product_id):
    # Find the raw product in the database
    raw_product = RawProduct.query.filter_by(id=raw_product_id, company_id=current_user.company_id).first()
    if not raw_product:
        flash('Raw product not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('main.raw_product'))

    form = EditRawProduct()
    if form.validate_on_submit():
        new_name = form.name.data.strip()
        
        # Check if another raw product already has this name (excluding the current one)
        existing = RawProduct.query.filter(
            RawProduct.name == new_name,
            RawProduct.company_id == current_user.company_id,
            RawProduct.id != raw_product_id
        ).first()
        
        if existing:
            flash(f'A raw product with the name "{new_name}" already exists.', 'warning')
            return redirect(url_for('main.view_raw_product', raw_product_id=raw_product_id))
        
        old_name = raw_product.name
        raw_product.name = new_name
        db.session.commit()
        
        flash(f'Raw product renamed from "{old_name}" to "{new_name}" successfully!', 'success')
        return redirect(url_for('main.view_raw_product', raw_product_id=raw_product_id))
    
    flash('Invalid data submitted.', 'danger')
    return redirect(url_for('main.view_raw_product', raw_product_id=raw_product_id))