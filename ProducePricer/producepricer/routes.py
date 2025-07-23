import datetime
from io import BytesIO
from flask_mailman import EmailMessage
import json
import math
from fpdf import FPDF
import matplotlib
matplotlib.use('Agg')  # Use 'Agg' backend for rendering without a display
import matplotlib.pyplot as plt
from flask import redirect, render_template, render_template_string, request, url_for, flash, make_response, Blueprint
from itsdangerous import BadSignature, Serializer, SignatureExpired
from producepricer.models import (
    CostHistory, 
    Customer,
    DesignationCost, 
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
    UnitOfWeight, 
    User, 
    Company, 
    Packaging,
    PendingUser
)
from producepricer.forms import(
    AddCustomer,
    AddDesignationCost, 
    AddItem, 
    AddLaborCost, 
    AddPackagingCost, 
    AddRanchPrice, 
    AddRawProduct, 
    AddRawProductCost, 
    CreatePackage, 
    EditItem,
    PriceQuoterForm,
    PriceSheetForm, 
    ResetPasswordForm, 
    ResetPasswordRequestForm, 
    SignUp, 
    Login, 
    CreateCompany, 
    UpdateItemInfo, 
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



main = Blueprint('main', __name__)

# route for the root URL
@main.route('/')
@main.route('/home')
@login_required
def home():
    return render_template('home.html')

# about page
@main.route('/about')
def about():
    return render_template('about.html')

# signup page
@main.route('/signup', methods=['GET', 'POST'])
def signup():
    # if the user is already logged in, redirect to home
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    
    # signup form
    form = SignUp()
    # existing companies to select from
    form.company.choices = [(c.id, c.name) for c in Company.query.all()]

    if form.validate_on_submit():
        # see if the email is already registered
        existing_pending = PendingUser.query.filter_by(email=form.email.data).first()
        existing = User.query.filter_by(email=form.email.data).first()
        if existing or existing_pending:
            flash('Email already registered.', 'warning')
            return redirect(url_for('main.login'))

        # grab the company
        company = Company.query.get(form.company.data)

        # if they are the company owner, auto-approve
        if form.email.data == company.admin_email:
            user = User( first_name=form.first_name.data,
                        last_name=form.last_name.data,
                        email=form.email.data,
                        password=form.password.data,
                        company_id=company.id )
            # add to db
            db.session.add(user)
            db.session.commit()
            # log them in
            login_user(user)
            flash('Welcome, you’re now the admin!', 'success')
            return redirect(url_for('main.home'))

        # store pending user data
        pending = PendingUser(
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            email=form.email.data,
            password=form.password.data,  # you might want to hash this
            company_id=company.id
        )
        # add to db
        db.session.add(pending)
        db.session.commit()

        # token and serializer
        s = Serializer(app.config['SECRET_KEY'], salt='user-approval')  # 1 hour expiration
        token = s.dumps({'pending_user_id': pending.id})

        # send link to admin
        send_admin_approval_email(token, company.id)
        flash('Account request submitted. Admin will review and approve.', 'info')

        return redirect(url_for('main.login'))
    
    return render_template('signup.html', title='Sign Up', form=form)

def send_admin_approval_email(token, company_id):
    # lookup admin email
    company = Company.query.get(company_id)
    admin_email = company.admin_email
    link = url_for('main.approve_user', token=token, _external=True)

    msg = EmailMessage(
      subject='Approve new user request',
      from_email=app.config['MAIL_DEFAULT_SENDER'],
      to=[admin_email],
      body=f'Click to approve new user:\n\n{link}\n\n'
           'This link will expire in 1 hour.\n(If the link takes you to the login page, please log in and then click the link again.)'

    )
    msg.send()

# route to approve a user
@main.route('/approve_user/<token>')
@login_required
def approve_user(token):
    # only company-admin may approve
    company = Company.query.get(current_user.company_id)
    if not company or current_user.email != company.admin_email:
        flash('Not authorized.', 'danger')
        return redirect(url_for('main.home'))

    # deserialize the token
    s = Serializer(app.config['SECRET_KEY'], salt='user-approval')
    try:
        data = s.loads(token, max_age=3600)
    except (BadSignature, SignatureExpired):
        flash('Invalid or expired token.', 'danger')
        return redirect(url_for('main.home'))

    # get the pending user
    pending = PendingUser.query.get(data.get('pending_user_id'))
    if not pending:
        flash('No pending request found or already processed.', 'warning')
        return redirect(url_for('main.company'))

    # check duplicate
    if User.query.filter_by(email=pending.email).first():
        flash('User already exists.', 'warning')
        db.session.delete(pending)
        db.session.commit()
        return redirect(url_for('main.company'))

    # create real user
    user = User(
        first_name = pending.first_name,
        last_name  = pending.last_name,
        email      = pending.email,
        password   = pending.password,  # if hashed in PendingUser, okay
        company_id = pending.company_id
    )
    db.session.add(user)
    # remove pending row
    db.session.delete(pending)
    db.session.commit()

    flash(f'User {user.email} approved and created.', 'success')
    return redirect(url_for('main.company'))

# company page
@main.route('/company')
@login_required
def company():
    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('main.index'))
    
    # get all users in the company
    users = User.query.filter_by(company_id=current_user.company_id).all()

    # get pending users
    pending_users = PendingUser.query.filter_by(company_id=current_user.company_id).all()

    # get the owner's account
    admin_email = company.admin_email if company else None
    admin = User.query.filter_by(email=admin_email).first() if admin_email else None
    if not admin:
        flash('Admin user not found for this company.', 'danger')
        return redirect(url_for('main.index'))

    return render_template('company.html',
                           title='Company',
                           company=company,
                           users=users,
                           admin=admin,
                           pending_users=pending_users)


# approve a user from the company page
@main.route('/approve_pending/<int:pending_id>', methods=['POST'])
@login_required
def approve_pending(pending_id):
    company = Company.query.get(current_user.company_id)
    if not company or current_user.email != company.admin_email:
        flash('Not authorized.', 'danger')
        return redirect(url_for('main.company'))

    # get the pending user
    pending = PendingUser.query.get(pending_id)
    if not pending:
        flash('Pending user not found.', 'warning')
        return redirect(url_for('main.company'))

    # create real user
    user = User(
        first_name = pending.first_name,
        last_name  = pending.last_name,
        email      = pending.email,
        password   = pending.password,
        company_id = pending.company_id
    )
    # add to db and get rid of pending request
    db.session.add(user)
    db.session.delete(pending)
    db.session.commit()

    flash(f'User {user.email} approved and created.', 'success')
    return redirect(url_for('main.company'))

# deny a pending user from the company page
@main.route('/deny_pending/<int:pending_id>', methods=['POST'])
@login_required
def deny_pending(pending_id):
    # only company-admin may deny
    company = Company.query.get(current_user.company_id)
    if not company or current_user.email != company.admin_email:
        flash('Not authorized.', 'danger')
        return redirect(url_for('main.company'))

    # get the pending user
    pending = PendingUser.query.get(pending_id)
    if not pending:
        flash('Pending user not found.', 'warning')
    else:
        db.session.delete(pending)
        db.session.commit()
        flash(f'Request from {pending.email} denied.', 'info')

    return redirect(url_for('main.company'))

# login page
@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    
    form = Login()
    if form.validate_on_submit():
        # check if the user exists
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.password == form.password.data:
            # log the user in
            login_user(user, remember=form.remember.data)
            # flash a message to the user
            flash(f'Welcome back {user.first_name}!', 'success')
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
        # process the form data, then redirect to the home page
        return redirect(url_for('main.home'))
    return render_template('login.html', title='Login', form=form)

# logout page
@main.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out!', 'success')
    return redirect(url_for('main.home'))

# create company page
@main.route('/create_company', methods=['GET', 'POST'])
def create_company():
    form = CreateCompany()
    if form.validate_on_submit():
        # flash a message to the user
        flash(f'Company created for {form.name.data}!', 'success')
        # make a new company object for database
        company = Company(name=form.name.data,
                          admin_email=form.admin_email.data)
        db.session.add(company)
        db.session.commit()
        # redirect to the home page
        return redirect(url_for('main.home'))
    # if the form is not submitted or is invalid, render the create company page
    else:
        # print errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'Error in {field}: {error}', 'danger')
                
    return render_template('create_company.html', title='Create Company', form=form)

# packaging page
@main.route('/packaging')
@login_required
def packaging():
    # search feature
    q = request.args.get('q', '').strip()

    if q:
        # filter the packaging by the search query
        packaging = Packaging.query.filter(
            Packaging.packaging_type.ilike(f'%{q}%'),
            Packaging.company_id == current_user.company_id
        ).all()
    else:
        # get the current user's company
        company = Company.query.filter_by(id=current_user.company_id).first()
        # get the packaging for the current user's company
        packaging = company.packaging

    # get the most recent packaging cost for each packaging
    packaging_costs = {}
    for pack in packaging:
        # get the most recent packaging cost for this packaging
        most_recent_cost = PackagingCost.query.filter_by(packaging_id=pack.id).order_by(PackagingCost.date.desc()).order_by(PackagingCost.id.desc()).first()
        if most_recent_cost:
            packaging_costs[pack.id] = most_recent_cost

    # forms
    create_package_form = CreatePackage()
    upload_packaging_csv_form = UploadPackagingCSV()
    return render_template(
            'packaging.html',
            title='Packaging',
            packaging=packaging,
            create_package_form=create_package_form,
            upload_csv_form=upload_packaging_csv_form,
            packaging_costs=packaging_costs,
            q=q
        )

# view an individual package
@main.route('/packaging/<int:packaging_id>')
@login_required
def view_packaging(packaging_id):
    # find the packaging in the database
    packaging = Packaging.query.filter_by(id=packaging_id, company_id=current_user.company_id).first()
    if packaging is None:
        flash('Packaging not found.', 'danger')
        return redirect(url_for('main.packaging'))
    
    # get all the packaging costs for this packaging
    packaging_costs = PackagingCost.query.filter_by(packaging_id=packaging_id).order_by(PackagingCost.date.desc()).all()

    form = AddPackagingCost()

    return render_template('view_packaging.html', title='View Packaging', packaging=packaging, packaging_costs=packaging_costs, form=form)


@main.route('/add_package', methods=['POST'])
@login_required
def add_package():
    form = CreatePackage()
    if form.validate_on_submit():
        # flash a message to the user
        flash(f'Package created for {form.name.data}!', 'success')
        # make a new package object for database
        package = Packaging(packaging_type=form.name.data,
                            company_id=current_user.company_id)
        db.session.add(package)
        db.session.commit()
        # redirect to the packaging page
        return redirect(url_for('main.packaging'))
    # if the form is not submitted or is invalid, render the packaging page
    flash('Invalid Information.', 'danger')
    return render_template('packaging.html', title='Packaging', form=form)

@main.route('/add_packaging_cost/<int:packaging_id>', methods=['GET', 'POST'])
@login_required
def add_packaging_cost(packaging_id):
    # form for the page
    form = AddPackagingCost()
    # find the packaging in the database
    packaging = Packaging.query.filter_by(id=packaging_id).first()
    if packaging is None:
        flash('Packaging not found.', 'danger')
        return redirect(url_for('main.packaging'))
    if form.validate_on_submit():
        # flash a message to the user
        flash(f'Packaging cost added for {packaging.packaging_type}!', 'success')
        # make a new packaging cost object for database
        packaging_cost = PackagingCost(date=form.date.data,
                                       box_cost=form.box_cost.data,
                                       bag_cost=form.bag_cost.data,
                                       tray_andor_chemical_cost=form.tray_andor_chemical_cost.data,
                                       label_andor_tape_cost=form.label_andor_tape_cost.data,
                                       packaging_id=packaging_id,
                                       company_id=current_user.company_id)
        db.session.add(packaging_cost)
        db.session.commit()

        # update TotalItemCost of any items using this packaging
        with db.session.no_autoflush:
            items_using_packaging = Item.query.filter_by(packaging_id=packaging_id, company_id=current_user.company_id).all()
            for item in items_using_packaging:
                # update the total cost for the item
                update_item_total_cost(item.id)

        # redirect to the packaging page
        return redirect(url_for('main.view_packaging', packaging_id=packaging_id))
    # if the form is not submitted or is invalid, render the add packaging cost page
    #flash('Invalid Information.', 'danger')
    else:
        # print errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'Error in {field}: {error}', 'danger')
    return render_template('add_packaging_cost.html', title='Add Packaging Cost', form=form, packaging=packaging)

# delete a package
@main.route('/delete_packaging/<int:packaging_id>', methods=['POST'])
@login_required
def delete_packaging(packaging_id):
    # Find the packaging in the database
    packaging = Packaging.query.filter_by(id=packaging_id, company_id=current_user.company_id).first()
    if not packaging:
        flash('Packaging not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.packaging'))

    # Delete all associated PackagingCost entries
    PackagingCost.query.filter_by(packaging_id=packaging_id).delete()

    # Delete the packaging itself
    db.session.delete(packaging)
    db.session.commit()

    flash(f'Packaging "{packaging.packaging_type}" and its associated costs have been deleted.', 'success')
    return redirect(url_for('main.packaging'))

@main.route('/delete_packaging_cost/<int:cost_id>', methods=['POST'])
@login_required
def delete_packaging_cost(cost_id):
    cost = PackagingCost.query.filter_by(id=cost_id, company_id=current_user.company_id).first()
    packaging = Packaging.query.filter_by(id=cost.packaging_id, company_id=current_user.company_id).first() if cost else None
    
    if not cost:
        flash('Packaging cost not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.packaging'))

    db.session.delete(cost)
    db.session.commit()

    flash('Packaging cost has been deleted.', 'success')
    return redirect(url_for('main.view_packaging', packaging_id=packaging.id))

@main.route('/upload_packaging_csv', methods=['GET', 'POST'])
@login_required
def upload_packaging_csv():
    form = UploadPackagingCSV()
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
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])

            # Save the file securely
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Read the CSV file into a pandas DataFrame
            try:
                df = pd.read_csv(filepath)
            except Exception as e:
                flash(f'Error reading CSV file: {e}', 'danger')
                return redirect(request.url)

            # Make sure the columns are all in the CSV
            required_columns = ['name', 'box_cost', 'bag_cost', 'tray_andor_chemical_cost', 'label_andor_tape_cost']
            if not all(column in df.columns for column in required_columns):
                flash('Invalid CSV format. Please ensure all required columns are present.', 'danger')
                return redirect(request.url)

            # Process the DataFrame and add packaging costs to the database
            for index, row in df.iterrows():
                # Clean and convert cost values
                box_cost = float(row['box_cost'].replace('$', '').strip())
                bag_cost = float(row['bag_cost'].replace('$', '').strip())
                tray_andor_chemical_cost = float(row['tray_andor_chemical_cost'].replace('$', '').strip())
                label_andor_tape_cost = float(row['label_andor_tape_cost'].replace('$', '').strip())

                # get the total cost of the packaging
                total_packaging_cost = box_cost + bag_cost + tray_andor_chemical_cost + label_andor_tape_cost

                # Check if the package already exists
                packaging = Packaging.query.filter_by(packaging_type=row['name'], company_id=current_user.company_id).first()
                if packaging is None:
                    packaging = Packaging(packaging_type=row['name'], company_id=current_user.company_id)
                    db.session.add(packaging)
                    db.session.commit()

                # Create a new packaging cost object
                packaging_cost = PackagingCost(
                    date=pd.Timestamp.now(),
                    box_cost=box_cost,
                    bag_cost=bag_cost,
                    tray_andor_chemical_cost=tray_andor_chemical_cost,
                    label_andor_tape_cost=label_andor_tape_cost,
                    packaging_id=packaging.id,
                    company_id=current_user.company_id
                )
                db.session.add(packaging_cost)
                db.session.commit()

                # update TotalItemCost of any items using this packaging
                items_using_packaging = Item.query.filter_by(packaging_id=packaging.id, company_id=current_user.company_id).all()
                for item in items_using_packaging:
                    # update the total cost for the item
                    update_item_total_cost(item.id)

            flash('Packaging costs added successfully!', 'success')
            return redirect(url_for('main.packaging'))
    return render_template('upload_packaging_csv.html', title='Upload Packaging CSV', form=form)

@main.route('/raw_product')
@login_required
def raw_product():
    # search feature
    q = request.args.get('q', '').strip()

    if q:
        # filter the raw products by the search query
        raw_products = RawProduct.query.filter(
            RawProduct.company_id == current_user.company_id,
            RawProduct.name.ilike(f'%{q}%')
        ).all()

    else:
        # Get the current user's company
        company = Company.query.filter_by(id=current_user.company_id).first()
        # Get the raw products for the current user's company
        raw_products = company.raw_products if company else []

    # Get the most recent cost for each raw product
    raw_product_costs = {}
    for raw_product in raw_products:
        most_recent_cost = (
            CostHistory.query
            .filter_by(raw_product_id=raw_product.id)
            .order_by(
                CostHistory.date.desc(),   # newest date first
                CostHistory.id.desc()
            )     # for ties, highest id (i.e. last inserted) first
            .first()
        )
        #most_recent_cost = CostHistory.query.filter_by(raw_product_id=raw_product.id).order_by(CostHistory.date.desc(), CostHistory.id.desc()).first()
        # most_recent_cost = CostHistory.query.filter_by(raw_product_id=raw_product.id).order_by(CostHistory.date.desc()),(CostHistory.id.desc()).first()
        if most_recent_cost:
            raw_product_costs[raw_product.id] = most_recent_cost

    # Forms
    form = AddRawProduct()
    cost_form = AddRawProductCost()
    upload_raw_product_csv_form = UploadRawProductCSV()

    return render_template(
        'raw_product.html',
        title='Raw Product',
        raw_products=raw_products,
        raw_product_costs=raw_product_costs,
        form=form,
        cost_form=cost_form,
        upload_csv_form=upload_raw_product_csv_form,
        q=q
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
    cost_history = CostHistory.query.filter_by(raw_product_id=raw_product_id).order_by(CostHistory.date.desc()).all()

    # find the items that use this raw product
    items_using_raw_product = Item.query.filter(Item.raw_products.any(id=raw_product_id)).all()

    cost_form = AddRawProductCost()

    return render_template('view_raw_product.html', items_using_raw_product=items_using_raw_product, title='View Raw Product', cost_form=cost_form, raw_product=raw_product, cost_history=cost_history)

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
    return redirect(url_for('main.view_raw_product', raw_product_id=raw_product_id))


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
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])

            # Save the file securely
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
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
                cost = float(row['cost'].replace('$', '').strip())

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
    return render_template('upload_raw_product_csv.html', title='Upload Raw Product CSV', form=form)

@main.route('/delete_raw_product/<int:raw_product_id>', methods=['POST'])
@login_required
def delete_raw_product(raw_product_id):
    # Find the raw product in the database
    raw_product = RawProduct.query.filter_by(id=raw_product_id, company_id=current_user.company_id).first()
    if not raw_product:
        flash('Raw product not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.raw_product'))

    # Delete all associated CostHistory entries
    CostHistory.query.filter_by(raw_product_id=raw_product_id).delete()

    # Delete the raw product itself
    db.session.delete(raw_product)
    db.session.commit()

    flash(f'Raw product "{raw_product.name}" and its associated costs have been deleted.', 'success')
    return redirect(url_for('main.raw_product'))

@main.route('/items')
@login_required
def items():
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 15  # Items per page
    
    # Get search parameter
    q = request.args.get('q', '').strip()
    
    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    
    # Forms
    form = AddItem()
    update_item_form = UpdateItemInfo()
    form.packaging.choices = [(pack.id, pack.packaging_type) for pack in company.packaging] if company else []
    form.raw_products.choices = [(raw.id, raw.name) for raw in company.raw_products] if company else []
    upload_item_csv = UploadItemCSV()
    
    # Base query - filtered by company
    query = Item.query.filter_by(company_id=current_user.company_id)
    
    # Apply search filter if provided
    if q:
        query = query.filter(
            (Item.name.ilike(f'%{q}%')) | (Item.code.ilike(f'%{q}%'))
        )
    
    # Apply pagination
    pagination = query.order_by(Item.name).paginate(page=page, per_page=per_page, error_out=False)
    items = pagination.items
    
    # Get packaging lookup
    packaging_lookup = {
        p.id: p.packaging_type
        for p in Packaging.query.filter_by(company_id=current_user.company_id).all()
    }
    
    # Get raw product lookup
    raw_product_lookup = {
        rp.id: rp.name
        for rp in RawProduct.query.filter_by(company_id=current_user.company_id).all()
    }
    
    # Get item info lookup
    item_info_lookup = {}
    for item in items:
        most_recent_info = (
            ItemInfo.query
            .filter_by(item_id=item.id)
            .order_by(ItemInfo.date.desc(), ItemInfo.id.desc())
            .first()
        )
        if most_recent_info:
            item_info_lookup[item.id] = most_recent_info
    
    # Render the page
    return render_template(
        'items.html',
        title='Items',
        items=items,
        pagination=pagination,  # Pass pagination object to template
        packaging_lookup=packaging_lookup,
        raw_product_lookup=raw_product_lookup,
        form=form,
        update_item_info_form=update_item_form,
        item_info_lookup=item_info_lookup,
        upload_item_csv=upload_item_csv,
        q=q  # Pass search query for maintaining state
    )
    
@main.route('/add_item', methods=['POST'])
@login_required
def add_item():
    # make sure a labor cost exists for the current user
    most_recent_labor_cost = LaborCost.query.order_by(LaborCost.date.desc(), LaborCost.id.desc()).filter_by(company_id=current_user.company_id).first()
    if not most_recent_labor_cost:
        flash('Please add a labor cost before adding items.', 'warning')
        return redirect(url_for('main.items'))

    # add item form
    form = AddItem()
    # form to add yield and labor hours
    update_item_info_form = UpdateItemInfo()
    form.packaging.choices = [(pack.id, pack.packaging_type) for pack in Packaging.query.filter_by(company_id=current_user.company_id).all()]
    form.raw_products.choices = [(raw.id, raw.name) for raw in RawProduct.query.filter_by(company_id=current_user.company_id).all()]

    if form.validate_on_submit():

        # check if the item already exists
        existing_item = Item.query.filter_by(name=form.name.data, company_id=current_user.company_id).first()
        if existing_item:
            flash(f'Item "{form.name.data}" already exists.', 'warning')
            return redirect(url_for('main.items'))
        
        # create a new item object
        item = Item(
            name=form.name.data,
            code=form.item_code.data,
            unit_of_weight=form.unit_of_weight.data,
            #weight=form.weight.data,
            packaging_id=form.packaging.data,
            company_id=current_user.company_id,
            ranch=form.ranch.data,
            item_designation=form.item_designation.data,
            case_weight=form.case_weight.data if form.case_weight.data else 0.0
        )

        # add the selected raw products to the item (to the secondary table)
        for raw_product_id in form.raw_products.data:
            raw_product = RawProduct.query.get(raw_product_id)
            if raw_product:
                item.raw_products.append(raw_product)

        # add the item to the database
        db.session.add(item)
        db.session.commit()

        # add the item info
        item_info = ItemInfo(
            product_yield=update_item_info_form.product_yield.data,
            labor_hours=update_item_info_form.labor_hours.data,
            date=update_item_info_form.date.data,
            item_id=item.id,
            company_id=current_user.company_id
        )
        # add the item info to the database
        db.session.add(item_info)
        db.session.commit()

        # flash a message to the user
        flash(f'Item "{form.name.data}" has been added successfully!', 'success')
        # redirect to the items page
        return redirect(url_for('main.items'))
    # if the form is not submitted or is invalid, render the items page
    for field, errs in form.errors.items():
        for e in errs:
            flash(f"{getattr(form, field).label.text}: {e}", 'danger')
    flash('Invalid data submitted.', 'danger')
    return redirect(url_for('main.items'))

# delete an item
@main.route('/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    # find the item in the database
    item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first()
    if not item:
        flash('Item not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.items'))
    
    # delete all associated ItemInfo entries
    ItemInfo.query.filter_by(item_id=item_id).delete()
    # delete the item itself
    db.session.delete(item)
    db.session.commit()
    flash(f'Item "{item.name}" and its associated information have been deleted.', 'success')
    return redirect(url_for('main.items'))

@main.route('/delete_price_history/<int:price_history_id>', methods=['POST'])
@login_required
def delete_price_history(price_history_id):
    # Find the price history entry
    price_history = PriceHistory.query.filter_by(
        id=price_history_id, 
        company_id=current_user.company_id
    ).first()
    
    if not price_history:
        flash('Price history entry not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.items'))
    
    # Store the item_id before deleting the entry
    item_id = price_history.item_id
    
    # Delete the price history entry
    db.session.delete(price_history)
    db.session.commit()
    
    flash('Price history entry has been deleted successfully.', 'success')
    return redirect(url_for('main.view_item', item_id=item_id))

# update info for an item
@main.route('/update_item/<int:item_id>', methods=['GET', 'POST'])
@login_required
def update_item(item_id):
    # find the item in db
    item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first()
    if not item:
        flash('Item not found or you do not have permission to update it.', 'danger')
        return redirect(url_for('main.items'))
    
    # form for updating item info
    form = UpdateItemInfo()
    if form.validate_on_submit():
        # create a new ItemInfo object
        item_info = ItemInfo(
            product_yield=form.product_yield.data,
            labor_hours=form.labor_hours.data,
            date=form.date.data,
            item_id=item.id,
            company_id=current_user.company_id
        )
        # add the item info to the database
        db.session.add(item_info)
        db.session.commit()
        flash(f'Item info for "{item.name}" has been updated successfully!', 'success')
        return redirect(url_for('main.view_item', item_id=item.id))
    # if the form is not submitted or is invalid, render the update item page
    flash('Invalid data submitted.', 'danger')
    return render_template('update_item.html', title='Update Item', form=form, item=item)

# view an individual item
@main.route('/item/<int:item_id>')
@login_required
def view_item(item_id):
    # Get pagination parameters
    price_page = request.args.get('price_page', 1, type=int)
    cost_page = request.args.get('cost_page', 1, type=int)
    info_page = request.args.get('info_page', 1, type=int)
    per_page = 10  # Number of items per page
    
    # Find the item in the database
    item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first()
    if item is None:
        flash('Item not found.', 'danger')
        return redirect(url_for('main.items'))
    
    # Get packaging and raw products
    packaging = Packaging.query.filter_by(id=item.packaging_id, company_id=current_user.company_id).first()
    raw_products = [rp for rp in item.raw_products]
    
    # Most recent labor cost
    most_recent_labor_cost = LaborCost.query.order_by(LaborCost.date.desc(), LaborCost.id.desc()).filter_by(company_id=current_user.company_id).first()

    # PAGINATED TABLES:
    
    # 1. Price history with pagination (for table)
    price_pagination = (
        PriceHistory.query
        .filter_by(item_id=item_id, company_id=current_user.company_id)
        .order_by(PriceHistory.date.desc(), PriceHistory.id.desc())
        .paginate(page=price_page, per_page=per_page, error_out=False)
    )
    price_history = price_pagination.items
    
    # 2. Cost history with pagination (for table)
    cost_pagination = (
        ItemTotalCost.query
        .filter_by(item_id=item_id)
        .order_by(ItemTotalCost.date.desc())
        .paginate(page=cost_page, per_page=per_page, error_out=False)
    )
    item_costs = cost_pagination.items
    
    # 3. Item info history with pagination (for table)
    info_pagination = (
        ItemInfo.query
        .filter_by(item_id=item_id)
        .order_by(ItemInfo.date.desc())
        .paginate(page=info_page, per_page=per_page, error_out=False)
    )
    item_info = info_pagination.items
    
    # DATA FOR CHARTS (needs all records, not just current page)
    
    # Get ALL records for charts
    all_price_history = (
        PriceHistory.query
        .filter_by(item_id=item_id, company_id=current_user.company_id)
        .order_by(PriceHistory.date.asc())
        .all()
    )
    
    all_item_costs = (
        ItemTotalCost.query
        .filter_by(item_id=item_id)
        .order_by(ItemTotalCost.date.asc())
        .all()
    )
    
    all_item_info = (
        ItemInfo.query
        .filter_by(item_id=item_id)
        .order_by(ItemInfo.date.asc())
        .all()
    )
    
    # Map customer IDs to names
    customer_map = {customer.id: customer.name for customer in Customer.query.filter_by(company_id=current_user.company_id).all()}

    # Price chart data preparation (using ALL records)
    price_chart_data = {}
    for entry in all_price_history:
        customer_name = customer_map.get(entry.customer_id, "General Price")
        if customer_name not in price_chart_data:
            price_chart_data[customer_name] = []
        price_chart_data[customer_name].append({
            'x': entry.date.strftime('%Y-%m-%d'),
            'y': float(entry.price)
        })

    # if there's no item costs, calculate the current cost
    if not item_costs:
        update_item_total_cost(item_id)

    # get the most recent item cost
    item_costs = ItemTotalCost.query.filter_by(item_id=item_id).order_by(ItemTotalCost.date.desc()).all()
    current_cost = item_costs[0] if item_costs else None
    #print(current_cost.total_cost)

    raw_product_latest_costs = {}

    for rp in raw_products:
        # get the most recent cost for each raw product
        most_recent_cost = (
            CostHistory.query
            .filter_by(raw_product_id=rp.id)
            .order_by(CostHistory.date.desc(), CostHistory.id.desc())
            .first()
        )
        if most_recent_cost:
            raw_product_latest_costs[rp.id] = most_recent_cost.cost

    # form
    update_item_info_form = UpdateItemInfo()
    form = EditItem()

    form.packaging.choices = [(pack.id, pack.packaging_type) for pack in Packaging.query.filter_by(company_id=current_user.company_id).all()]
    form.raw_products.choices = [(raw.id, raw.name) for raw in RawProduct.query.filter_by(company_id=current_user.company_id).all()]
    # populate the form with the item's data
    #form.name.data = item.name
    #form.item_code.data = item.code
    form.unit_of_weight.data = item.unit_of_weight
    form.alternate_code.data = item.alternate_code if item.alternate_code else ''
    form.case_weight.data = item.case_weight if item.case_weight else 0.0
    form.ranch.data = item.ranch
    form.item_designation.data = item.item_designation
    form.packaging.data = item.packaging_id
    form.raw_products.data = [rp.id for rp in item.raw_products]

    return render_template('view_item.html', 
                          form=form,
                          current_cost=current_cost,
                          item_costs=item_costs,
                          most_recent_labor_cost=most_recent_labor_cost,
                          update_item_info_form=update_item_info_form,
                          title='View Item',
                          item=item,
                          item_info=item_info,
                          packaging=packaging,
                          raw_products=raw_products,
                          price_history=price_history,
                          customer_map=customer_map,
                          price_chart_data=price_chart_data,
                          raw_product_latest_costs=raw_product_latest_costs,
                          # Add pagination objects
                          price_pagination=price_pagination,
                          cost_pagination=cost_pagination,
                          info_pagination=info_pagination,
                          # For charts
                          all_item_costs=all_item_costs,
                          all_item_info=all_item_info)

@main.route('/delete_item_info/<int:item_info_id>', methods=['POST'])
@login_required
def delete_item_info(item_info_id):
    item_info = ItemInfo.query.filter_by(id=item_info_id, company_id=current_user.company_id).first()
    if not item_info:
        flash('Item info not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.items'))
    
    item_id = item_info.item_id
    db.session.delete(item_info)
    db.session.commit()
    flash('Item info deleted successfully!', 'success')
    return redirect(url_for('main.view_item', item_id=item_id))

# item import
@main.route('/upload_item_csv', methods=['GET', 'POST'])
@login_required
def upload_item_csv():
    # make sure a labor cost exists for the current user
    most_recent_labor_cost = LaborCost.query.order_by(LaborCost.date.desc(), LaborCost.id.desc()).filter_by(company_id=current_user.company_id).first()
    if not most_recent_labor_cost:
        flash('Please add a labor cost before uploading items.', 'warning')
        return redirect(url_for('main.items'))

    form = UploadItemCSV()
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
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])

            # Save the file securely
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Read the CSV file into a pandas DataFrame
            try:
                df = pd.read_csv(filepath)
            except Exception as e:
                flash(f'Error reading CSV file: {e}', 'danger')
                return redirect(request.url)

            # Make sure the columns are all in the CSV
            required_columns = ['name', 'item_code', 'alternate_code', 'raw_product', 'ranch', 'item_designation', 'packaging_type', 'yield', 'case_weight', 'labor']
            missing_columns = [column for column in required_columns if column not in df.columns]

            if missing_columns:
                flash(f'Invalid CSV format. Missing columns: {", ".join(missing_columns)}', 'danger')
                return redirect(request.url)
            
            # if not all(column in df.columns for column in required_columns):
            #     flash('Invalid CSV format. Please ensure all required columns are present.', 'danger')
            #     return redirect(request.url)

            # Process the DataFrame and add items to the database
            for index, row in df.iterrows():
                # Clean and convert values
                name = safe_strip(row['name'])
                item_code = safe_strip(row['item_code'])
                alternate_code = safe_strip(row['alternate_code'])
                raw_product = safe_strip(row['raw_product'])
                ranch = safe_strip(row['ranch'])  # Expecting 'yes' or 'no'
                item_designation = safe_strip(row['item_designation'])
                packaging_type = safe_strip(row['packaging_type'])
                case_weight = row.get('case_weight', 0.0)  # Default to 0.0 if not provided
                #labor = row.get('labor', 0.0)  # Default to 0.0 if not provided

                try:
                    labor = float(row['labor'])
                except (ValueError, TypeError) as e:
                    flash(f'Invalid labor value "{row["labor"]}" for item "{name}". Defaulting to 0.0.', 'warning')
                    labor = 0.0

                #yield_value = float(row['yield'].replace('%', '').strip())
                raw_yield = row['yield']
                yield_str = safe_strip(str(raw_yield))
                try:
                    yield_value = float(yield_str)
                except ValueError:
                    flash(f'Invalid yield value "{yield_str}" for item "{name}". Skipping item.', 'warning')
                    continue

                # Check if the item already exists
                existing_item = Item.query.filter_by(name=name, code=item_code, company_id=current_user.company_id).first()
                if existing_item:
                    # update yield and labor hours if the item already exists
                    yield_val = row.get('yield', 0.0)
                    new_info = ItemInfo(
                        product_yield=yield_value,
                        item_id=existing_item.id,
                        # change this if we add labor hours to the CSV
                        labor_hours=labor,
                        date=pd.Timestamp.now().date(),
                        company_id=current_user.company_id
                    )
                    # if there's an alternate code, update it
                    if alternate_code:
                        existing_item.alternate_code = safe_strip(alternate_code)
                    db.session.commit()  # Save the updated alternate_code to the item
                    db.session.add(new_info)

                    db.session.commit()
                    flash(f'Item "{name}" already exists. Skipping item.', 'warning')
                    continue

                # Check if the packaging exists (fix issue of capitalization)
                packaging_type = packaging_type.strip().upper()
                packaging = Packaging.query.filter_by(packaging_type=packaging_type, company_id=current_user.company_id).first()
                if not packaging:
                    # If packaging does not exist, create it
                    packaging = Packaging(packaging_type=packaging_type, company_id=current_user.company_id)
                    db.session.add(packaging)
                    db.session.commit()
                    #flash(f'Packaging ID {packaging_type} does not exist. Skipping item "{name}".', 'warning')
                    #continue

                # Check if the item designation is valid
                item_designation = item_designation.strip().upper()
                if item_designation not in ['SNAKPAK', 'RETAIL', 'FOODSERVICE']:
                    flash(f'Invalid item designation "{item_designation}" for item "{name}". Skipping item.', 'warning')
                    continue
                # If the item designation is not provided, default to 'FOODSERVICE'
                item_designation = item_designation if item_designation else 'FOODSERVICE'

                # check if ranch is true or false (is yes or no in csv)
                if (ranch == 'yes' or ranch == 'Yes'):
                    ranch = True
                else:
                    ranch = False

                # Create a new item object
                item = Item(
                    name=name,
                    code=item_code,
                    unit_of_weight=row.get('unit_of_weight', 'POUND'),  # Default to 'kg' if not provided
                    #weight=row.get('weight', 1.0),  # Default to 1.0 if not provided
                    # weight and case weight are the same, but only using case weight for now
                    #case_weight=row.get('case_weight', 0.0),  # Default to 0.0 if not provided
                    case_weight=case_weight if case_weight else 0.0,
                    packaging_id=packaging.id,
                    company_id=current_user.company_id,
                    ranch=ranch,
                    item_designation=item_designation
                )
                # If an alternate code is provided, set it
                if alternate_code:
                    item.alternate_code = safe_strip(alternate_code)
                    
                # Add the raw product to the item if it exists
                raw_product_obj = RawProduct.query.filter_by(name=raw_product, company_id=current_user.company_id).first()
                if raw_product_obj:
                    item.raw_products.append(raw_product_obj)
                else:
                    # make the raw product if it does not exist
                    raw_product_obj = RawProduct(name=raw_product, company_id=current_user.company_id)
                    db.session.add(raw_product_obj)
                    db.session.commit()
                    item.raw_products.append(raw_product_obj)
                    #flash(f'Raw product "{raw_product}" does not exist. Skipping item "{name}".', 'warning')
                    #continue

                # add the item to the database so that it gets assigned an ID
                db.session.add(item)
                db.session.flush()  # Flush to get the item ID before creating ItemInfo

                item_info = ItemInfo(
                    product_yield=yield_value,
                    item_id=item.id,
                    labor_hours=labor,  # Assuming a default labor hours
                    date=pd.Timestamp.now().date(),
                    company_id=current_user.company_id
                )

                # Add the item info to the database
                db.session.add(item_info)
                db.session.commit()

                # find the total cost of the item
                update_item_total_cost(item.id)
                
                #flash(f'Item "{name}" has been added successfully!', 'success')
            flash('Items imported successfully!', 'success')
    return redirect(url_for('main.items'))

def safe_strip(x):
    if x is None: return ''
    try:
        if math.isnan(x): return ''
    except Exception:
        pass
    return str(x).strip()

# view an individual item cost
@main.route('/item_cost/<int:item_cost_id>')
@login_required
def view_item_cost(item_cost_id):
    # Find the item cost in the database
    item_cost = ItemTotalCost.query.filter_by(id=item_cost_id, company_id=current_user.company_id).first()
    if not item_cost:
        flash('Item cost not found or you do not have permission to view it.', 'danger')
        return redirect(url_for('main.items'))

    # Get the item associated with this cost
    item = Item.query.filter_by(id=item_cost.item_id, company_id=current_user.company_id).first()
    if not item:
        flash('Item not found or you do not have permission to view it.', 'danger')
        return redirect(url_for('main.items'))

    # Get the most recent item info for this item
    most_recent_info = (
        ItemInfo.query
        .filter_by(item_id=item.id)
        .order_by(ItemInfo.date.desc(), ItemInfo.id.desc())
        .first()
    )

    return render_template('view_item_cost.html', title='View Item Cost', item_cost=item_cost, item=item, most_recent_info=most_recent_info)

# delete an item cost
@main.route('/delete_item_cost/<int:item_cost_id>', methods=['GET','POST'])
@login_required
def delete_item_cost(item_cost_id):
    # find the item in the database
    item = Item.query.filter_by(id=item_cost_id, company_id=current_user.company_id).first()
    # Find the item cost in the database
    item_cost = ItemTotalCost.query.filter_by(id=item_cost_id, company_id=current_user.company_id).first()
    if not item_cost:
        flash('Item cost not found or you do not have permission to delete it.', 'danger')
        if item:
            return redirect(url_for('main.view_item', item_id=item.id))
        return redirect(url_for('main.items'))

    # Delete the item cost
    db.session.delete(item_cost)
    db.session.commit()

    flash('Item cost has been deleted successfully.', 'success')
    return redirect(url_for('main.items'))

@main.route('/edit_item/<int:item_id>', methods=['POST'])
@login_required
def edit_item(item_id):
    # Find the item in the database
    item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first()
    if not item:
        flash('Item not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('main.items'))

    # Initialize the form
    form = EditItem()
    form.packaging.choices = [(pack.id, pack.packaging_type) for pack in Packaging.query.filter_by(company_id=current_user.company_id).all()]
    form.raw_products.choices = [(raw.id, raw.name) for raw in RawProduct.query.filter_by(company_id=current_user.company_id).all()]

    if form.validate_on_submit():
        # Update the item's attributes
        item.case_weight = form.case_weight.data
        item.item_designation = form.item_designation.data
        item.ranch = form.ranch.data
        item.packaging_id = form.packaging.data
        item.unit_of_weight = form.unit_of_weight.data
        item.alternate_code = form.alternate_code.data if form.alternate_code.data else None

        # Update the raw products
        item.raw_products = []
        for raw_product_id in form.raw_products.data:
            raw_product = RawProduct.query.get(raw_product_id)
            if raw_product:
                item.raw_products.append(raw_product)

        # Commit the changes to the database
        db.session.commit()
        # Update the total cost for the item
        update_item_total_cost(item.id)
        # Flash a success message
        flash(f'Item "{item.name}" has been updated successfully!', 'success')
        return redirect(url_for('main.view_item', item_id=item.id))

    flash('Invalid data submitted.', 'danger')
    # print the form errors
    for field, errs in form.errors.items():
        for e in errs:
            flash(f"{getattr(form, field).label.text}: {e}", 'danger')

    return redirect(url_for('main.view_item', item_id=item.id))

def calculate_item_cost(item_id):
    # Get the item from the database
    item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first()
    itemInfo = ItemInfo.query.filter_by(item_id=item_id).order_by(ItemInfo.date.desc(), ItemInfo.id.desc()).first()
    
    if not item:
        flash('Item not found or you do not have permission to calculate cost.', 'danger')
        print(f'Item with ID {item_id} not found for company {current_user.company_id}.')
        return 0.0, 0.0, 0.0, 0.0, 0.0
    
    if not itemInfo:
        flash(f'No item info found for item "{item.name}".', 'warning')
        print(f'No item info found for item with ID {item_id} for company {current_user.company_id}.')
        return 0.0, 0.0, 0.0, 0.0, 0.0

    # Calculate the total cost of the item based on its raw products and packaging costs
    total_cost = 0.0

    raw_product_cost = 0.0

    ranch_cost = 0.0

    # if ranch is true, add most recent ranch cost
    if item.ranch:
        most_recent_ranch_cost = RanchPrice.query.order_by(RanchPrice.date.desc(), RanchPrice.id.desc()).filter_by(company_id=current_user.company_id).first()
        if most_recent_ranch_cost:
            ranch_cost = most_recent_ranch_cost.cost
            total_cost += ranch_cost
        else:
            flash(f'No ranch cost found for item "{item.name}".', 'warning')

    # get the (raw price/yield) for each raw product
    for raw_product in item.raw_products:
        most_recent_cost = (
            CostHistory.query
            .filter_by(raw_product_id=raw_product.id)
            .order_by(CostHistory.date.desc(), CostHistory.id.desc())
            .first()
        )
        if most_recent_cost:
            # calculate the cost per unit of yield
            cost_per_unit_yield = most_recent_cost.cost / (itemInfo.product_yield or 1)  # Avoid division by zero
            total_cost += (cost_per_unit_yield * item.case_weight)
            raw_product_cost += (cost_per_unit_yield * item.case_weight)

    # get the packaging cost for the item
    packaging_costs = PackagingCost.query.filter_by(packaging_id=item.packaging_id).order_by(PackagingCost.date.desc()).all()
    total_packaging_cost = 0.0

    if packaging_costs:
        # Use the most recent packaging cost
        most_recent_packaging_cost = packaging_costs[0]
        total_cost += (
            most_recent_packaging_cost.box_cost +
            most_recent_packaging_cost.bag_cost +
            most_recent_packaging_cost.tray_andor_chemical_cost +
            most_recent_packaging_cost.label_andor_tape_cost
        )
        # update total_packaging_cost
        total_packaging_cost = (
            most_recent_packaging_cost.box_cost +
            most_recent_packaging_cost.bag_cost +
            most_recent_packaging_cost.tray_andor_chemical_cost +
            most_recent_packaging_cost.label_andor_tape_cost
        )
    else:
        flash(f'No packaging costs found for item "{item.name}".', 'warning')

    labor_cost = 0.0

    # Calculate the total cost based on labor hours and other factors
    if itemInfo and itemInfo.labor_hours:
        # Assuming a fixed labor cost per hour, e.g., $15/hour
        labor_cost_per_hour = LaborCost.query.filter_by(company_id=current_user.company_id).first()
        if labor_cost_per_hour:
            labor_cost_per_hour = labor_cost_per_hour.labor_cost
        else:
            flash('Labor cost not found. Assuming $0 per hour.', 'warning')
            labor_cost_per_hour = 0

        total_cost += itemInfo.labor_hours * labor_cost_per_hour
        labor_cost = itemInfo.labor_hours * labor_cost_per_hour

    designation_cost = 0.0

    # add 2.25 if snakpak, add 1 otherwise
    if item.item_designation == 'SNAKPAK':
        total_cost += 2.25
        designation_cost = 2.25
    else:
        total_cost += 1.00
        designation_cost = 1.00

    # return the different costs and the total
    return total_cost, labor_cost, designation_cost, total_packaging_cost, raw_product_cost, ranch_cost

# overriden version of calculate_item_cost that takes item info as args, rather than
# just the item id
def calculate_item_cost_with_info(packaging_id, product_yield, labor_hours, case_weight, ranch, item_designation, raw_products):
    # Calculate the total cost of the item based on its raw products and packaging costs
    total_cost = 0.0

    raw_product_cost = 0.0

    ranch_cost = 0.0

    # if ranch is true, add most recent ranch cost
    if ranch:
        most_recent_ranch_cost = RanchPrice.query.order_by(RanchPrice.date.desc(), RanchPrice.id.desc()).filter_by(company_id=current_user.company_id).first()
        if most_recent_ranch_cost:
            ranch_cost = most_recent_ranch_cost.cost
            total_cost += ranch_cost
        else:
            flash('No ranch cost found.', 'warning')

    # get the (raw price/yield) for each raw product
    for raw_product in raw_products:
        most_recent_cost = (
            CostHistory.query
            .filter_by(raw_product_id=raw_product.id)
            .order_by(CostHistory.date.desc(), CostHistory.id.desc())
            .first()
        )
        if most_recent_cost:
            # calculate the cost per unit of yield
            cost_per_unit_yield = most_recent_cost.cost / (product_yield or 1)  # Avoid division by zero
            total_cost += (cost_per_unit_yield * case_weight)
            raw_product_cost += (cost_per_unit_yield * case_weight)

    # get the packaging cost for the item
    packaging_costs = PackagingCost.query.filter_by(packaging_id=packaging_id).order_by(PackagingCost.date.desc()).all()
    total_packaging_cost = 0.0

    if packaging_costs:
        # Use the most recent packaging cost
        most_recent_packaging_cost = packaging_costs[0]
        total_cost += (
            most_recent_packaging_cost.box_cost +
            most_recent_packaging_cost.bag_cost +
            most_recent_packaging_cost.tray_andor_chemical_cost +
            most_recent_packaging_cost.label_andor_tape_cost
        )
        # update total_packaging_cost
        total_packaging_cost = (
            most_recent_packaging_cost.box_cost +
            most_recent_packaging_cost.bag_cost +
            most_recent_packaging_cost.tray_andor_chemical_cost +
            most_recent_packaging_cost.label_andor_tape_cost
        )
    else:
        flash('No packaging costs found.', 'warning')

    labor_cost = 0.0

    # Calculate the total cost based on labor hours and other factors
    if labor_hours:
        # Assuming a fixed labor cost per hour, e.g., $15/hour
        labor_cost_per_hour = LaborCost.query.filter_by(company_id=current_user.company_id).first()
        if labor_cost_per_hour:
            labor_cost_per_hour = labor_cost_per_hour.labor_cost
        else:
            flash('Labor cost not found. Assuming $0 per hour.', 'warning')
            labor_cost_per_hour = 0

        total_cost += labor_hours * labor_cost_per_hour
        labor_cost = labor_hours * labor_cost_per_hour

    designation_cost = 0.0

    # Calculate designation cost
    designation_cost += find_designation_cost(item_designation)

    # return the different costs and the total
    return total_cost, labor_cost, designation_cost, total_packaging_cost, raw_product_cost, ranch_cost

# overriden version of calculate_item_cost that takes item info as args, rather than
# just the item id
def calculate_item_cost_with_info(packaging_id, product_yield, labor_hours, case_weight, ranch, item_designation, raw_products):
    # Calculate the total cost of the item based on its raw products and packaging costs
    total_cost = 0.0

    raw_product_cost = 0.0

    ranch_cost = 0.0

    # if ranch is true, add most recent ranch cost
    if ranch:
        most_recent_ranch_cost = RanchPrice.query.order_by(RanchPrice.date.desc(), RanchPrice.id.desc()).filter_by(company_id=current_user.company_id).first()
        if most_recent_ranch_cost:
            ranch_cost = most_recent_ranch_cost.cost
            total_cost += ranch_cost
        else:
            flash('No ranch cost found.', 'warning')

    # get the (raw price/yield) for each raw product
    raw_costs = []
    for raw_product in raw_products:
        most_recent_cost = (
            CostHistory.query
            .filter_by(raw_product_id=raw_product.id)
            .order_by(CostHistory.date.desc(), CostHistory.id.desc())
            .first()
        )
        if most_recent_cost:
            # calculate the cost per unit of yield
            cost_per_unit_yield = most_recent_cost.cost / (product_yield or 1)  # Avoid division by zero
            cost = cost_per_unit_yield * case_weight
            total_cost += cost
            raw_costs.append(cost)
    # If there are raw costs, average them for raw_product_cost
    raw_product_cost = sum(raw_costs) / len(raw_costs) if raw_costs else 0.0



    # get the packaging cost for the item
    packaging_costs = PackagingCost.query.filter_by(packaging_id=packaging_id).order_by(PackagingCost.date.desc()).all()
    total_packaging_cost = 0.0

    if packaging_costs:
        # Use the most recent packaging cost
        most_recent_packaging_cost = packaging_costs[0]
        total_cost += (
            most_recent_packaging_cost.box_cost +
            most_recent_packaging_cost.bag_cost +
            most_recent_packaging_cost.tray_andor_chemical_cost +
            most_recent_packaging_cost.label_andor_tape_cost
        )
        # update total_packaging_cost
        total_packaging_cost = (
            most_recent_packaging_cost.box_cost +
            most_recent_packaging_cost.bag_cost +
            most_recent_packaging_cost.tray_andor_chemical_cost +
            most_recent_packaging_cost.label_andor_tape_cost
        )
    else:
        flash('No packaging costs found.', 'warning')

    labor_cost = 0.0
    # Calculate the total cost based on labor hours and other factors
    if labor_hours:
        # Assuming a fixed labor cost per hour, e.g., $15/hour
        labor_cost_per_hour = LaborCost.query.filter_by(company_id=current_user.company_id).first()
        if labor_cost_per_hour:
            labor_cost_per_hour = labor_cost_per_hour.labor_cost
        else:
            flash('Labor cost not found. Assuming $0 per hour.', 'warning')
            labor_cost_per_hour = 0

        total_cost += labor_hours * labor_cost_per_hour
        labor_cost = labor_hours * labor_cost_per_hour

    # Calculate designation cost
    designation_cost = 0.0
    designation_cost += find_designation_cost(item_designation)

    # add designation cost to the total
    total_cost += designation_cost

# automatically update total cost for an item
def update_item_total_cost(item_id):
    #cost = calculate_item_cost(item_id)
    cost, labor_cost, designation_cost, packaging_cost, raw_product_cost, ranch_cost = calculate_item_cost(item_id)

    # checks
    if cost is None:
        flash(f'Could not calculate cost for item with ID {item_id}.', 'danger')
        return
    if cost <= 0:
        flash(f'Calculated cost for item with ID {item_id} is not positive: ${cost:.2f}.', 'warning')
        return
    
    # Check if the item exists
    item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first()
    if not item:
        flash(f'Item with ID {item_id} not found for company {current_user.company_id}.', 'danger')
        return

    total_cost = ItemTotalCost(
        item_id=item_id,
        date=datetime.datetime.utcnow().date(),
        total_cost=cost,
        company_id=current_user.company_id,
        labor_cost=labor_cost,
        designation_cost=designation_cost,
        packaging_cost=packaging_cost,
        ranch_cost=ranch_cost,
        raw_product_cost=raw_product_cost
    )
    db.session.add(total_cost)
    db.session.commit()
    #flash(f'Total cost for item: {item_id} has been updated to ${cost:.2f}.', 'success')

# price page for showing cost of each item and different prices (along with associated profit and margins)
@main.route('/price')
@login_required
def price():
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 15  # Items per page
    
    # Get search parameter
    q = request.args.get('q', '').strip()
    
    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('main.index'))
    
    # Base query - filtered by company
    query = Item.query.filter_by(company_id=current_user.company_id)
    
    # Apply search filter if provided
    if q:
        query = query.filter(
            (Item.name.ilike(f'%{q}%')) | (Item.code.ilike(f'%{q}%'))
        )
    
    # Apply pagination
    pagination = query.order_by(Item.name).paginate(page=page, per_page=per_page, error_out=False)
    items = pagination.items
    
    # Process items for display
    item_data = []
    for item in items:
        # Get the most recent total cost for the item
        most_recent_cost = (
            ItemTotalCost.query
            .filter_by(item_id=item.id)
            .order_by(ItemTotalCost.date.desc(), ItemTotalCost.id.desc())
            .first()
        )
        if not most_recent_cost:
            # If no cost is found, calculate it
            update_item_total_cost(item.id)
            most_recent_cost = (
                ItemTotalCost.query
                .filter_by(item_id=item.id)
                .order_by(ItemTotalCost.date.desc(), ItemTotalCost.id.desc())
                .first()
            )

        # Calculate additional values
        cost_per_lb = most_recent_cost.total_cost / item.case_weight if item.case_weight else 0.0
        cost_per_oz = cost_per_lb / 16  # 1 pound = 16 ounces
        labor_cost = most_recent_cost.labor_cost
        packaging_cost = most_recent_cost.packaging_cost
        unit_cost = most_recent_cost.total_cost
        
        # Rounded costs (rounded up to the nearest .25)
        def round_up_to_nearest_quarter(value):
            return math.ceil(value * 4) / 4

        # Calculate rounded prices
        rounded_25 = round_up_to_nearest_quarter(unit_cost * 1.25)
        rounded_30 = round_up_to_nearest_quarter(unit_cost * 1.30)
        rounded_35 = round_up_to_nearest_quarter(unit_cost * 1.35)
        rounded_40 = round_up_to_nearest_quarter(unit_cost * 1.40)
        rounded_45 = round_up_to_nearest_quarter(unit_cost * 1.45)

        # Append data for this item
        item_data.append({
            'id': item.id,
            'name': item.name,
            'code': item.code,
            'case_weight': item.case_weight,
            'total_cost': f"{most_recent_cost.total_cost:.2f}",
            'ranch_cost': f"{most_recent_cost.ranch_cost:.2f}",
            'cost_per_lb': f"{cost_per_lb:.2f}",
            'cost_per_oz': f"{cost_per_oz:.2f}",
            'labor_cost': f"{labor_cost:.2f}",
            'packaging_cost': f"{packaging_cost:.2f}",
            'unit_cost': f"{unit_cost:.2f}",
            'rounded_25': f"{rounded_25:.2f}",
            'rounded_30': f"{rounded_30:.2f}",
            'rounded_35': f"{rounded_35:.2f}",
            'rounded_40': f"{rounded_40:.2f}",
            'rounded_45': f"{rounded_45:.2f}",
        })

    # render the price page with the item data
    return render_template('price.html',
                           title='Price',
                           items=items,
                           pagination=pagination,  # Pass pagination object to template 
                           item_data=item_data,
                           company=company,
                           q=q)

# page to add labor cost
@main.route('/add_labor_cost', methods=['GET', 'POST'])
@login_required
def add_labor_cost():
    form = AddLaborCost()

    # get past labor costs for the current user
    past_labor_costs = LaborCost.query.filter_by(company_id=current_user.company_id).order_by(LaborCost.date.desc()).all()

    # if a new labor cost is being added
    if request.method == 'POST':
        if form.validate_on_submit():
            # Create a new labor cost entry
            labor_cost = LaborCost(
                labor_cost=form.cost.data,
                date=form.date.data,
                company_id=current_user.company_id
            )

            # add to db
            db.session.add(labor_cost)
            db.session.commit()

            # update all item costs based on the new labor cost
            update_item_costs_on_labor_change()

            flash('Labor cost added successfully!', 'success')

            # get past labor costs for the current user
            past_labor_costs = LaborCost.query.filter_by(company_id=current_user.company_id).order_by(LaborCost.date.desc()).all()

        else:
            flash('Invalid data submitted.', 'danger')

    return render_template('add_labor_cost.html', title='Add Labor Cost', form=form, past_labor_costs=past_labor_costs)

# delete a labor cost
@main.route('/delete_labor_cost/<int:cost_id>', methods=['POST'])
@login_required
def delete_labor_cost(cost_id):
    # see if you're deleting the most recent labor cost
    # if so, allow deletion but then update all item costs
    most_recent_labor_cost = LaborCost.query.order_by(LaborCost.date.desc(), LaborCost.id.desc()).filter_by(company_id=current_user.company_id).first()
    if most_recent_labor_cost and most_recent_labor_cost.id == cost_id:
        # Find the labor cost in the database
        labor_cost = LaborCost.query.filter_by(id=cost_id, company_id=current_user.company_id).first()
        if not labor_cost:
            flash('Labor cost not found or you do not have permission to delete it.', 'danger')
            return redirect(url_for('main.add_labor_cost'))

        # Delete the labor cost
        db.session.delete(labor_cost)
        db.session.commit()

        update_item_costs_on_labor_change()

    else:
        # Find the labor cost in the database
        labor_cost = LaborCost.query.filter_by(id=cost_id, company_id=current_user.company_id).first()
        if not labor_cost:
            flash('Labor cost not found or you do not have permission to delete it.', 'danger')
            return redirect(url_for('main.add_labor_cost'))

        # Delete the labor cost
        db.session.delete(labor_cost)
        db.session.commit()

    flash('Labor cost has been deleted successfully.', 'success')
    return redirect(url_for('main.add_labor_cost'))

# update all item costs when a labor cost is added or deleted
def update_item_costs_on_labor_change():
    # Get all items for the current user's company
    items = Item.query.filter_by(company_id=current_user.company_id).all()

    # Update the total cost for each item
    for item in items:
        update_item_total_cost(item.id)

    flash('All item costs have been updated based on the latest labor costs.', 'success')

# ability for business owner to delete users
@main.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    # Check if the current user is the admin of the company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company or current_user.email != company.admin_email:
        flash('You do not have permission to delete users.', 'danger')
        return redirect(url_for('main.company'))

    # Find the user in the database
    user = User.query.filter_by(id=user_id, company_id=current_user.company_id).first()
    if not user:
        flash('User not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.company'))

    # Delete the user
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{user.email}" has been deleted successfully.', 'success')
    return redirect(url_for('main.company'))

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
        return redirect(url_for('main.customer'))

    # Update the customer's basic info
    customer.name = request.form['name']
    customer.email = request.form['email']

    # handle master customer checkbox
    is_master = request.form.get('is_master') == 'on'

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

def _generate_price_sheet_pdf_bytes(sheet):
    """Helper function to generate the price sheet PDF bytes."""
    # Build recent dict for each item
    recent = {}
    master = Customer.query.filter_by(
        company_id=current_user.company_id,
        is_master=True
    ).first()
    for item in sheet.items:
        # Try to get price for master customer first
        ph = None
        if master:
            ph = PriceHistory.query.filter_by(
                company_id=current_user.company_id,
                item_id=item.id,
                customer_id=master.id
            ).order_by(PriceHistory.date.desc(), PriceHistory.id.desc()).first()
        # Fallback: any customer
        if not ph:
            ph = PriceHistory.query.filter_by(
                company_id=current_user.company_id,
                item_id=item.id
            ).order_by(PriceHistory.date.desc(), PriceHistory.id.desc()).first()
        
        recent[item.id] = {
            'price': float(ph.price) if ph and ph.price is not None else None,
            'date': ph.date if ph and ph.date else None,
        }

    # Create PDF
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Price Sheet: {sheet.name}", ln=1)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Date: {sheet.date.strftime('%Y-%m-%d')}", ln=1)
    pdf.ln(4)

    # Table header
    pdf.set_font("Arial", "B", 11)
    col_widths = [120, 35, 35]
    headers = ["Product", "Price", "Changed"]
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, border=1, align="C")
    pdf.ln()

    # Table rows
    pdf.set_font("Arial", "", 10)
    seven_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)

    for item in sheet.items:
        info = recent.get(item.id, {})
        price = f"${info.get('price'):.2f}" if info.get('price') is not None else "—"
        
        changed_char = ""
        item_date = info.get('date')
        if item_date and item_date >= seven_days_ago.date():
            changed_char = "*"

        pdf.cell(col_widths[0], 8, item.name, border=1)
        pdf.cell(col_widths[1], 8, price, border=1, align="C")
        pdf.cell(col_widths[2], 8, changed_char, border=1, align="C")
        pdf.ln()

    return bytes(pdf.output(dest='S'))

# add new customer
@main.route('/add_customer', methods=['POST'])
@login_required
def add_customer():
    form = AddCustomer()
    if form.validate_on_submit():
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
        return redirect(url_for('main.customer'))

    # Delete the customer
    db.session.delete(customer)
    db.session.commit()
    flash(f'Customer "{customer.name}" has been deleted successfully.', 'success')
    return redirect(url_for('main.customer'))

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
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])

            # Save the file securely
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
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
    return redirect(url_for('main.customer'))

@main.route('/ranch', methods=['GET', 'POST'])
@login_required
def ranch():
    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('main.index'))

    # Get all previous ranch prices and costs for the current user's company
    ranch_prices = RanchPrice.query.filter_by(company_id=current_user.company_id).order_by(RanchPrice.date.desc()).all()

    # Initialize the form
    form = AddRanchPrice()

    if form.validate_on_submit():
        # Create a new ranch price entry
        ranch_price = RanchPrice(
            price=form.price.data,
            cost=form.cost.data,
            date=form.date.data,
            company_id=current_user.company_id
        )
        db.session.add(ranch_price)
        db.session.commit()

        # Update all item costs that use ranch prices
        items = Item.query.filter_by(company_id=current_user.company_id, ranch=True).all()
        for item in items:
            update_item_total_cost(item.id)

        # Flash a success message
        flash('Ranch price and cost updated successfully!', 'success')
        return redirect(url_for('main.ranch'))

    return render_template('ranch.html', title='Ranch', ranch_prices=ranch_prices, form=form)

@main.route("/reset/_password", methods=["GET", "POST"])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_reset_password_email(user)
            flash('An email has been sent with instructions to reset your password.', 'info')
        else:
            flash('No account found with that email address.', 'danger')
        return redirect(url_for('main.login'))
    return render_template('reset_password_request.html', title='Reset Password', form=form)

# get content for the actual email body
from producepricer.templates.reset_password_email_content import (
    reset_password_email_html_content
)

def send_reset_password_email(user):
    reset_password_url = url_for(
        'reset_password',
        token=user.generate_reset_password_token(),
        user_id=user.id,
        _external=True
    )

    email_body = render_template_string(
        reset_password_email_html_content,
        reset_password_url=reset_password_url
    )

    message = EmailMessage(
        subject='Reset Your Password',
        to=[user.email],
        body=email_body
    )

    message.content_subtype = 'html'  # Set the content type to HTML

    try:
        message.send()
        flash('An email has been sent with instructions to reset your password.', 'info')
    except Exception as e:
        flash(f'An error occurred while sending the email: {e}', 'danger')

@main.route('/reset_password/<token>/<int:user_id>', methods=['GET', 'POST'])
def reset_password(token, user_id):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    user = User.query.get(user_id)
    if not user or not user.verify_reset_password_token(token, user_id):
        flash('Invalid or expired token.', 'danger')
        return redirect(url_for('main.reset_password_request'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset successfully!', 'success')
        return redirect(url_for('main.login'))

    return render_template('reset_password.html', title='Reset Password', form=form, user=user)

@main.route('/price_quoter', methods=['GET','POST'])
@login_required
def price_quoter():
    form = PriceQuoterForm()

    # Populate the dropdowns
    items = Item.query.filter_by(company_id=current_user.company_id).all()
    #form.item.choices = [(i.id, i.name) for i in items]

    # Populate the packaging and raw products dropdowns
    packs = Packaging.query.filter_by(company_id=current_user.company_id).all()
    form.packaging.choices = [(p.id, p.packaging_type) for p in packs]

    # Populate the raw products dropdown
    raws = RawProduct.query.filter_by(company_id=current_user.company_id).all()
    form.raw_products.choices = [(r.id, r.name) for r in raws]

    # Initialize the result variable
    result = None

    # Pre‐fill the form if an item has been selected via query param
    item_id = request.args.get('item_id', type=int)
    if item_id and not form.is_submitted():
        item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first()
        if item:
            form.item.data = item.id
            form.packaging.data = item.packaging_id
            form.raw_products.data = [r.id for r in item.raw_products]

            # Load most recent ItemInfo for yield & labor_hours
            info = (ItemInfo.query
                        .filter_by(item_id=item.id)
                        .order_by(ItemInfo.date.desc(), ItemInfo.id.desc())
                        .first())
            if info:
                form.product_yield.data = info.product_yield
                form.labor_hours.data   = info.labor_hours

    # When the user submits the variables, do the calculation
    if form.validate_on_submit():
        # user can either create the item or just calculate the price
        action = request.form.get('action', 'create')

        # look up your selections
        pack = Packaging.query.get(form.packaging.data)
        selected_raws = RawProduct.query.filter(
            RawProduct.id.in_(form.raw_products.data)
        ).all()

        # get latest costs for the packaging
        pc = (PackagingCost.query
                .filter_by(packaging_id=pack.id)
                .order_by(PackagingCost.date.desc(), PackagingCost.id.desc())
                .first())
        pack_cost = sum([
            pc.box_cost, pc.bag_cost,
            pc.tray_andor_chemical_cost, pc.label_andor_tape_cost
        ]) if pc else 0

        # get the total cost of the selected raw products
        total_raw = 0
        for r in selected_raws:
            rh = (CostHistory.query
                     .filter_by(raw_product_id=r.id)
                     .order_by(CostHistory.date.desc(), CostHistory.id.desc())
                     .first())
            if rh:
                total_raw += rh.cost

        # ranch cost
        ranch_cost = 0
        if form.ranch.data:
            # get the most recent ranch cost
            rc = (RanchPrice.query
                    .filter_by(company_id=current_user.company_id)
                    .order_by(RanchPrice.date.desc(), RanchPrice.id.desc())
                    .first())
            ranch_cost = rc.cost if rc else 0

        # designation cost
        designation_cost = 0
        item_designation = form.item_designation.data
        designation_cost += DesignationCost.query.filter_by(item_designation=item_designation, company_id=current_user.company_id).first().cost if item_designation else 0

        # get the most recent labor cost
        lc = (LaborCost.query
                .filter_by(company_id=current_user.company_id)
                .order_by(LaborCost.date.desc(), LaborCost.id.desc())
                .first())
        labor_cost = (lc.labor_cost * form.labor_hours.data) if lc else 0

        # sum of all costs to find total cost
        total      = pack_cost + total_raw + labor_cost + ranch_cost + designation_cost
        cpl        = total / form.product_yield.data if form.product_yield.data else 0
        cpo        = cpl / 16

        # compute the rounded values
        r25 = total * 1.25
        r30 = total * 1.30
        r35 = total * 1.35
        r40 = total * 1.40
        r45 = total * 1.45

        # results to be displayed
        result = {
            #'item':         dict(form.item.choices).get(form.item.data),
            'name':         form.name.data,  # Use the item name directly,
            'raw_cost':     total_raw,
            'ranch_cost':  ranch_cost,
            'designation_cost': designation_cost,
            'item_designation': form.item_designation.data,
            'case_weight':  form.case_weight.data,
            'packaging':    dict(form.packaging.choices)[form.packaging.data],
            'packaging_cost': pack_cost,
            'raws':         [r.name for r in selected_raws],
            'product_yield':form.product_yield.data,
            'labor_hours':  form.labor_hours.data,
            'labor_cost':  labor_cost,
            'total_cost':   total,
            'cost_per_lb':  cpl,
            'cost_per_oz':  cpo,
            'rounded_25':   r25,
            'rounded_30':   r30,
            'rounded_35':   r35,
            'rounded_40':   r40,
            'rounded_45':   r45,
        }

        if action == 'create':
            # Create a new item with the calculated values
            item = Item(
                name=form.name.data,
                code=form.code.data,
                case_weight=form.case_weight.data,
                ranch=form.ranch.data,
                packaging_id=form.packaging.data,
                unit_of_weight=UnitOfWeight.POUND,
                company_id=current_user.company_id
            )
            # Add the raw products to the item
            for raw_product_id in form.raw_products.data:
                raw_product = RawProduct.query.get(raw_product_id)
                if raw_product:
                    item.raw_products.append(raw_product)

            db.session.add(item)
            db.session.flush()

            info = ItemInfo(
                item_id=item.id,
                product_yield=form.product_yield.data,
                labor_hours=form.labor_hours.data,
                date=pd.Timestamp.now().date(),
                company_id=current_user.company_id
            )
            db.session.add(info)
            db.session.commit()

            # flash that the item has been created
            flash(f'Item "{form.name.data}" has been created successfully!', 'success')
            # update the total cost for the item
            update_item_total_cost(item.id)

            return redirect(url_for('main.items'))
        
    # print the errors in the form if there are any
    if form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'Error in {field}: {error}', 'danger')

    return render_template(
        'price_quoter.html',
        title='Price Quoter',
        form=form,
        result=result,
        #selected_item_id=item_id
    )

# get the most recently dated cost for the given item designation
def find_designation_cost(item_designation):
    designation_cost = DesignationCost.query.filter_by(
        item_designation=item_designation,
        company_id=current_user.company_id
    ).order_by(DesignationCost.date.desc()).first()
    if designation_cost:
        return designation_cost.cost
    else:
        flash(f'No designation cost found for {item_designation}. Using default cost of $1.00.', 'warning')
        return 1.00  # Default cost if not found

# page to add designation costs
@main.route('/designation_costs', methods=['GET','POST'])
@login_required
def designation_costs():
    form = AddDesignationCost()
    # load all past entries
    all_entries = DesignationCost.query.filter_by(
        company_id=current_user.company_id
    ).all()

    # build lookup of most‐recent cost for each designation
    current_costs = {}
    for entry in all_entries:
        latest = (DesignationCost.query
                  .filter_by(item_designation=entry.item_designation,
                             company_id=current_user.company_id)
                  .order_by(DesignationCost.date.desc(), DesignationCost.id.desc())
                  .first())
        current_costs[entry.item_designation] = latest.cost if latest else 0.0

    if form.validate_on_submit():
        new_cost = DesignationCost(
            item_designation=form.item_designation.data,
            cost=form.cost.data,
            company_id=current_user.company_id,
            date=form.date.data
        )
        db.session.add(new_cost)
        db.session.commit()
        flash('Designation cost added successfully!', 'success')
        # redirect to avoid double‐POST

        # update prices of all items with this designation
        items = Item.query.filter_by(
            company_id=current_user.company_id,
            item_designation=form.item_designation.data
        ).all()
        for item in items:
            update_item_total_cost(item.id)
            
        return redirect(url_for('main.designation_costs'))

    # Print or flash errors after form is submitted and validation fails
    if form.is_submitted() and not form.validate():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {getattr(form, field).label.text}: {error}", 'danger')
                print(f"Error in {getattr(form, field).label.text}: {error}")

    # always render the page on GET or invalid POST
    return render_template(
        'designation_costs.html',
        title='Designation Costs',
        form=form,
        current_costs=current_costs
    )

@main.route('/price_sheet', methods=['GET', 'POST'])
@login_required
def price_sheet():
    form = PriceSheetForm()

    # 1) load existing sheets
    price_sheets = (
      PriceSheet.query
         .filter_by(company_id=current_user.company_id)
         .order_by(PriceSheet.date.desc())
         .all()
    )

    # populate dropdowns
    customers = Customer.query.filter_by(company_id=current_user.company_id).all()
    form.customer.choices = [(c.id, c.name) for c in customers]

    all_items = Item.query.filter_by(company_id=current_user.company_id).all()
    form.items.choices = [(i.id, i.name) for i in all_items]

    # get all the customer names for the existing sheets
    customer_names = {c.id: c.name for c in customers}

    if form.validate_on_submit():
        # create new sheet
        sheet = PriceSheet(
            name        = form.name.data,
            date        = form.date.data,
            company_id  = current_user.company_id,
            customer_id = form.customer.data
        )

        # link the selected items
        selected = Item.query.filter(
            Item.id.in_(form.items.data),
            Item.company_id==current_user.company_id
        ).all()
        sheet.items = selected

        db.session.add(sheet)
        db.session.commit()

        flash(f'Price Sheet "{sheet.name}" created!', 'success')
        # 2) redirect so the modal closes and the list refreshes
        return redirect(url_for('main.price_sheet'))

    # on GET or invalid POST, re-render the page
    return render_template(
      'price_sheet.html',
      title        = 'Price Sheets',
      form         = form,
      price_sheets = price_sheets,
      customer_names = customer_names
    )

@main.route('/edit_price_sheet/<int:sheet_id>', methods=['GET', 'POST'])
@login_required
def edit_price_sheet(sheet_id):
    sheet = PriceSheet.query.filter_by(
        id=sheet_id,
        company_id=current_user.company_id
    ).first_or_404()

    # find all items that aren't already in the sheet
    all_items = Item.query.filter_by(company_id=current_user.company_id).all()
    existing_item_ids = {item.id for item in sheet.items}
    available_items = [item for item in all_items if item.id not in existing_item_ids]

    # on save…
    if request.method=='POST':
        for item in sheet.items:
            sel = request.form.get(f'price_select_{item.id}')
            inp = request.form.get(f'price_input_{item.id}')
            raw = (inp or sel or '').strip()
            try:
                price = float(raw)
            except ValueError:
                continue
            ph = PriceHistory(
                date=datetime.datetime.utcnow().date(),
                company_id=current_user.company_id,
                customer_id=sheet.customer_id,
                item_id=item.id,
                price=price
            )
            db.session.add(ph)
        db.session.commit()
        flash('Prices saved!', 'success')
        return redirect(url_for('main.edit_price_sheet', sheet_id=sheet.id))

    # build “recent cost” choices (last 5) for each item
    history_opts = {}
    for item in sheet.items:
        history_opts[item.id] = (
          ItemTotalCost.query
            .filter_by(item_id=item.id, company_id=current_user.company_id)
            .order_by(ItemTotalCost.date.desc(), ItemTotalCost.id.desc())
            .limit(5)
            .all()
        )

        # if no history, calculate the cost
        if not history_opts[item.id]:
            update_item_total_cost(item.id)
            history_opts[item.id] = (
              ItemTotalCost.query
                .filter_by(item_id=item.id, company_id=current_user.company_id)
                .order_by(ItemTotalCost.date.desc(), ItemTotalCost.id.desc())
                .limit(5)
                .all()
            )

    # build markup options at 25%,30%,35%,40%,45% 
    percents = [25, 30, 35, 40, 45]
    markup_opts = {}

    # get the most recent price for each item in the sheet
    recent_prices = {}

    for item in sheet.items:
        # find master customer for the current company
        master_customer = Customer.query.filter_by(company_id=current_user.company_id, is_master=True).first()

        # latest PriceHistory entry for this sheet-item
        if master_customer:
            last_ph = PriceHistory.query \
                .filter_by(item_id=item.id, company_id=current_user.company_id, customer_id=master_customer.id) \
                .order_by(PriceHistory.date.desc(), PriceHistory.id.desc()) \
                .first()
            recent_prices[item.id] = last_ph.price if last_ph else None

            # if there is a master customer, but they don't have a price for this item,
            # just use the latest price for the item
            if not last_ph:
                last_ph = PriceHistory.query \
                    .filter_by(item_id=item.id, company_id=current_user.company_id) \
                    .order_by(PriceHistory.date.desc(), PriceHistory.id.desc()) \
                    .first()
                recent_prices[item.id] = last_ph.price if last_ph else None

        else:
            # if no master customer, just use the latest price for the item
            last_ph = PriceHistory.query \
                .filter_by(item_id=item.id, company_id=current_user.company_id) \
                .order_by(PriceHistory.date.desc(), PriceHistory.id.desc()) \
                .first()
            recent_prices[item.id] = last_ph.price if last_ph else None

        # most recent cost
        itc = ItemTotalCost.query.filter_by(
            item_id=item.id, company_id=current_user.company_id
        ).order_by(ItemTotalCost.date.desc(), ItemTotalCost.id.desc()).first()
        base = itc.total_cost if itc else 0
        opts = []
        for pct in percents:
            raw = base * (1 + pct/100)
            price = math.ceil(raw * 4) / 4  # round up to nearest quarter
            opts.append((pct, price))
        markup_opts[item.id] = opts

    return render_template(
      'edit_price_sheet.html',
      sheet=sheet,
      history_opts=history_opts,
      markup_opts=markup_opts,
      recent_prices=recent_prices,
      available_items=available_items
    )

@main.route('/email_price_sheet/<int:sheet_id>', methods=['POST'])
@login_required
def email_price_sheet(sheet_id):
    sheet = PriceSheet.query.filter_by(
        id=sheet_id,
        company_id=current_user.company_id
    ).first_or_404()

    # Generate PDF bytes using the helper function
    pdf_bytes = _generate_price_sheet_pdf_bytes(sheet)

    # Get recipient email from form
    recipient = request.form.get('recipient')
    if not recipient:
        flash('Recipient email required.', 'danger')
        return redirect(url_for('main.view_price_sheet', sheet_id=sheet.id))

    # Send email
    msg = EmailMessage(
        subject=f'Price Sheet: {sheet.name}',
        body='Attached is your requested price sheet PDF.',
        to=[recipient]
    )
    msg.attach(f'price_sheet_{sheet.name}.pdf', pdf_bytes, 'application/pdf')
    msg.send()

    flash(f'Price sheet emailed to {recipient}.', 'success')
    return redirect(url_for('main.view_price_sheet', sheet_id=sheet.id))

@main.route('/view_price_sheet/<int:sheet_id>/export_pdf')
@login_required
def export_price_sheet_pdf(sheet_id):
    sheet = PriceSheet.query.filter_by(
        id=sheet_id,
        company_id=current_user.company_id
    ).first_or_404()

    pdf_bytes = _generate_price_sheet_pdf_bytes(sheet)

    resp = make_response(pdf_bytes)
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=price_sheet_{sheet.name}.pdf'
    return resp

@main.route('/edit_price_sheet/<int:sheet_id>/add_items', methods=['POST'])
@login_required
def add_items_to_sheet(sheet_id):
    sheet = PriceSheet.query.filter_by(
        id=sheet_id, company_id=current_user.company_id
    ).first_or_404()
    ids = request.form.getlist('new_items')
    new_items = Item.query.filter(
        Item.id.in_(ids),
        Item.company_id==current_user.company_id
    ).all()
    for itm in new_items:
        if itm not in sheet.items:
            sheet.items.append(itm)
    db.session.commit()
    flash(f'Added {len(new_items)} item(s) to sheet.', 'success')
    return redirect(url_for('main.edit_price_sheet', sheet_id=sheet.id))

# delete a price sheet
@main.route('/delete_price_sheet/<int:sheet_id>', methods=['POST'])
@login_required
def delete_price_sheet(sheet_id):
    sheet = PriceSheet.query.filter_by(
        id=sheet_id,
        company_id=current_user.company_id
    ).first_or_404()

    db.session.delete(sheet)
    db.session.commit()

    flash(f'Price Sheet "{sheet.name}" deleted!', 'success')
    return redirect(url_for('main.price_sheet'))

# only true if this file is run directly
if __name__ == '__main__':
    app.run(debug=True)