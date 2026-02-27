import datetime
from flask_mailman import EmailMessage
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

# customer page
@main.route('/customer')
@login_required
def customer():
    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('main.index'))

    # Get all customers for the current user's company
    customers = Customer.query.filter_by(company_id=current_user.company_id).all()

    form = AddCustomer()
    import_form = UploadCustomerCSV()

    return render_template('customer.html', form=form, import_form=import_form, title='Customer', customers=customers, company=company)

@main.route('/edit_customer/<int:customer_id>', methods=['POST'])
@login_required
def edit_customer(customer_id):
    # Find the customer in the database
    customer = Customer.query.filter_by(id=customer_id, company_id=current_user.company_id).first()
    if not customer:
        flash('Customer not found or you do not have permission to edit it.', 'danger')
        return make_response(redirect(url_for('main.customer')), 404)

    # Update the customer's basic info
    customer.name = request.form['name']
    customer.email = request.form['email']

    # handle master customer checkbox
    is_master = request.form.get('is_master') == 'on'

    # only can be one master customer
    if is_master:
        # unmark any other master
        existing_master = Customer.query.filter_by(
            company_id=current_user.company_id,
            is_master=True
        ).first()
        if existing_master and existing_master.id != customer.id:
            existing_master.is_master = False
            flash(
              f'Customer "{existing_master.name}" has been un-marked as master.', 
              'info'
            )
        customer.is_master = True
    else:
        customer.is_master = False

    db.session.commit()
    flash(f'Customer "{customer.name}" has been updated successfully!', 'success')
    return redirect(url_for('main.customer'))

@main.route('/view_price_sheet/<int:sheet_id>')
@login_required
def view_price_sheet(sheet_id):
    sheet = PriceSheet.query.filter_by(
        id=sheet_id,
        company_id=current_user.company_id
    ).first_or_404()

    # get the customer associated with this price sheet
    customer = Customer.query.filter_by(
        id=sheet.customer_id,
        company_id=current_user.company_id
    ).first_or_404()

    # for each item, pull the most recent PriceHistory for this sheet
    recent = {}

    # get the master customer
    master_customer = Customer.query.filter_by(
        company_id=current_user.company_id,
        is_master=True
    ).first()

    for item in sheet.items:
        q = PriceHistory.query.filter_by(
            company_id=current_user.company_id,
            item_id=item.id,
            customer_id=customer.id if customer else None,
        ).order_by(PriceHistory.date.desc(), PriceHistory.id.desc())
        ph = q.first()

        if ph:
            # find customer name from customer id
            customer = Customer.query.filter_by(
                id=ph.customer_id,
                company_id=current_user.company_id
            ).first()

            ph.formatted_date = ph.date.strftime('%Y-%m-%d')

            recent[item.id] = {
                'price': ph.price,
                'date': ph.formatted_date,
                'customer': customer.name if customer else 'Unknown'
            }

    return render_template(
        'view_price_sheet.html',
        sheet=sheet,
        recent_prices=recent,
        now=datetime.datetime.utcnow(),
        customer=customer,
        master_customer=master_customer,
        recent=recent
    )

# add new customer
@main.route('/add_customer', methods=['POST'])
@login_required
def add_customer():
    form = AddCustomer()
    if form.validate_on_submit():
        # Check if the customer already exists
        existing_customer = Customer.query.filter_by(
            name=form.name.data,
            email=form.email.data,
            company_id=current_user.company_id
        ).first()
        if existing_customer:
            flash(f'Customer "{form.name.data}" already exists.', 'warning')
            return redirect(url_for('main.customer'))
        
        # if email isn't unique, flash a warning
        if Customer.query.filter_by(email=form.email.data, company_id=current_user.company_id).first():
            flash('Email must be unique for each customer.', 'warning')
            return redirect(url_for('main.customer'))

        customer = Customer(
            name=form.name.data,
            email=form.email.data,
            company_id=current_user.company_id
        )
        db.session.add(customer)
        db.session.commit()
        flash('Customer added successfully!', 'success')
        return redirect(url_for('main.customer'))

    return render_template('add_customer.html', title='Add Customer', form=form)

# delete a customer
@main.route('/delete_customer/<int:customer_id>', methods=['POST'])
@login_required
def delete_customer(customer_id):
    # Find the customer in the database
    customer = Customer.query.filter_by(id=customer_id, company_id=current_user.company_id).first()
    if not customer:
        flash('Customer not found or you do not have permission to delete it.', 'danger')
        return make_response(redirect(url_for('main.customer')), 404)

    # Delete the customer
    db.session.delete(customer)
    db.session.commit()
    flash(f'Customer "{customer.name}" has been deleted successfully.', 'success')
    return redirect(url_for('main.customer'))

# manage customer emails page
@main.route('/customer/<int:customer_id>/emails')
@login_required
def manage_customer_emails(customer_id):
    customer = Customer.query.filter_by(id=customer_id, company_id=current_user.company_id).first_or_404()
    form = AddCustomerEmail()
    return render_template('customer_emails.html', customer=customer, form=form, title=f'Manage Emails - {customer.name}')

# add email to customer
@main.route('/customer/<int:customer_id>/emails/add', methods=['POST'])
@login_required
def add_customer_email(customer_id):
    customer = Customer.query.filter_by(id=customer_id, company_id=current_user.company_id).first_or_404()
    form = AddCustomerEmail()
    if form.validate_on_submit():
        # Check if email already exists for this customer
        existing = CustomerEmail.query.filter_by(customer_id=customer_id, email=form.email.data).first()
        if existing:
            flash('This email is already added to this customer.', 'warning')
            return redirect(url_for('main.manage_customer_emails', customer_id=customer_id))
        
        # Also check against primary email
        if customer.email and customer.email.lower() == form.email.data.lower():
            flash('This email is already the primary email for this customer.', 'warning')
            return redirect(url_for('main.manage_customer_emails', customer_id=customer_id))
        
        new_email = CustomerEmail(
            email=form.email.data,
            customer_id=customer_id,
            label=form.label.data if form.label.data else None
        )
        db.session.add(new_email)
        db.session.commit()
        flash(f'Email "{form.email.data}" added successfully!', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
    return redirect(url_for('main.manage_customer_emails', customer_id=customer_id))

# delete email from customer
@main.route('/customer/<int:customer_id>/emails/<int:email_id>/delete', methods=['POST'])
@login_required
def delete_customer_email(customer_id, email_id):
    customer = Customer.query.filter_by(id=customer_id, company_id=current_user.company_id).first_or_404()
    email_entry = CustomerEmail.query.filter_by(id=email_id, customer_id=customer_id).first_or_404()
    
    email_address = email_entry.email
    db.session.delete(email_entry)
    db.session.commit()
    flash(f'Email "{email_address}" removed successfully.', 'success')
    return redirect(url_for('main.manage_customer_emails', customer_id=customer_id))

# update customer email label
@main.route('/customer/<int:customer_id>/emails/<int:email_id>/update', methods=['POST'])
@login_required
def update_customer_email(customer_id, email_id):
    customer = Customer.query.filter_by(id=customer_id, company_id=current_user.company_id).first_or_404()
    email_entry = CustomerEmail.query.filter_by(id=email_id, customer_id=customer_id).first_or_404()
    
    new_label = request.form.get('label', '').strip()
    email_entry.label = new_label if new_label else None
    db.session.commit()
    flash(f'Email label updated successfully.', 'success')
    return redirect(url_for('main.manage_customer_emails', customer_id=customer_id))

# upload customer CSV
@main.route('/upload_customer_csv', methods=['GET', 'POST'])
@login_required
def upload_customer_csv():
    form = UploadCustomerCSV()
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
            required_columns = ['name', 'email']
            missing_columns = [column for column in required_columns if column not in df.columns]

            if missing_columns:
                flash(f'Invalid CSV format. Missing columns: {", ".join(missing_columns)}', 'danger')
                return redirect(request.url)

            # Process the DataFrame and add customers to the database
            for index, row in df.iterrows():
                name = row['name'].strip()
                email = row['email'].strip()

                # Check if the customer already exists
                existing_customer = Customer.query.filter_by(name=name, company_id=current_user.company_id).first()
                if existing_customer:
                    flash(f'Customer "{name}" already exists. Skipping.', 'warning')
                    continue

                # Create a new customer object
                customer = Customer(
                    name=name,
                    email=email,
                    company_id=current_user.company_id
                )

                # Add the customer to the database
                db.session.add(customer)
                db.session.commit()

            flash('Customers imported successfully!', 'success')
    else:
        if request.method == 'POST':
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{field}: {error}', 'danger')

    return redirect(url_for('main.customer'))