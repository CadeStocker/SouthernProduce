import datetime
import math
from flask import redirect, render_template, render_template_string, request, url_for, flash
from producepricer.models import (
    CostHistory, 
    Customer, 
    Item, 
    ItemInfo, 
    ItemTotalCost, 
    LaborCost, 
    PackagingCost, 
    RanchPrice, 
    RawProduct, 
    User, 
    Company, 
    Packaging
)
from producepricer.forms import(
    AddCustomer, 
    AddItem, 
    AddLaborCost, 
    AddPackagingCost, 
    AddRanchPrice, 
    AddRawProduct, 
    AddRawProductCost, 
    CreatePackage, 
    EditItem, 
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
from producepricer import app, db, bcrypt
import pandas as pd
import os
from werkzeug.utils import secure_filename
from flask_mailman import EmailMessage

# route for the root URL
@login_required
@app.route('/')
@app.route('/home')
def home():
    return render_template('home.html')

# about page
@app.route('/about')
def about():
    return render_template('about.html')

# signup page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    form = SignUp()
    form.company.choices = [(company.id, company.name) for company in Company.query.all()]
    
    if form.validate_on_submit():
        # flash a message to the user
        flash(f'Account created for {form.first_name.data}!', 'success')
        # make a new user object for database
        user = User(first_name=form.first_name.data,
                    last_name=form.last_name.data,
                    email=form.email.data,
                    password=form.password.data,
                    company_id=form.company.data)
        db.session.add(user)
        db.session.commit()
        # log the user in
        login_user(user)
        # flash a message to the user
        flash(f'Welcome {form.first_name.data}!', 'success')
        # redirect to the home page
        return redirect(url_for('home'))
    # if the form is not submitted or is invalid, render the signup page
    flash('Invalid Information.', 'danger')
    return render_template('signup.html', title='Sign Up', form=form)

# login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
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
        return redirect(url_for('home'))
    return render_template('login.html', title='Login', form=form)

# logout page
@app.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out!', 'success')
    return redirect(url_for('home'))

# create company page
@app.route('/create_company', methods=['GET', 'POST'])
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
        return redirect(url_for('home'))
    # if the form is not submitted or is invalid, render the create company page
    flash('Invalid Information.', 'danger')
    return render_template('create_company.html', title='Create Company', form=form)

# packaging page
@app.route('/packaging')
@login_required
def packaging():
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
            packaging_costs=packaging_costs
        )

# view an individual package
@app.route('/packaging/<int:packaging_id>')
@login_required
def view_packaging(packaging_id):
    # find the packaging in the database
    packaging = Packaging.query.filter_by(id=packaging_id, company_id=current_user.company_id).first()
    if packaging is None:
        flash('Packaging not found.', 'danger')
        return redirect(url_for('packaging'))
    
    # get all the packaging costs for this packaging
    packaging_costs = PackagingCost.query.filter_by(packaging_id=packaging_id).order_by(PackagingCost.date.desc()).all()

    form = AddPackagingCost()

    return render_template('view_packaging.html', title='View Packaging', packaging=packaging, packaging_costs=packaging_costs, form=form)


@app.route('/add_package', methods=['POST'])
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
        return redirect(url_for('packaging'))
    # if the form is not submitted or is invalid, render the packaging page
    flash('Invalid Information.', 'danger')
    return render_template('packaging.html', title='Packaging', form=form)

@app.route('/add_packaging_cost/<int:packaging_id>', methods=['GET', 'POST'])
@login_required
def add_packaging_cost(packaging_id):
    # form for the page
    form = AddPackagingCost()
    # find the packaging in the database
    packaging = Packaging.query.filter_by(id=packaging_id).first()
    if packaging is None:
        flash('Packaging not found.', 'danger')
        return redirect(url_for('packaging'))
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
        return redirect(url_for('view_packaging', packaging_id=packaging_id))
    # if the form is not submitted or is invalid, render the add packaging cost page
    flash('Invalid Information.', 'danger')
    return render_template('add_packaging_cost.html', title='Add Packaging Cost', form=form, packaging=packaging)

# delete a package
@app.route('/delete_packaging/<int:packaging_id>', methods=['POST'])
@login_required
def delete_packaging(packaging_id):
    # Find the packaging in the database
    packaging = Packaging.query.filter_by(id=packaging_id, company_id=current_user.company_id).first()
    if not packaging:
        flash('Packaging not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('packaging'))

    # Delete all associated PackagingCost entries
    PackagingCost.query.filter_by(packaging_id=packaging_id).delete()

    # Delete the packaging itself
    db.session.delete(packaging)
    db.session.commit()

    flash(f'Packaging "{packaging.packaging_type}" and its associated costs have been deleted.', 'success')
    return redirect(url_for('packaging'))

@app.route('/delete_packaging_cost/<int:cost_id>', methods=['POST'])
@login_required
def delete_packaging_cost(cost_id):
    cost = PackagingCost.query.filter_by(id=cost_id, company_id=current_user.company_id).first()
    packaging = Packaging.query.filter_by(id=cost.packaging_id, company_id=current_user.company_id).first() if cost else None
    
    if not cost:
        flash('Packaging cost not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('packaging'))

    db.session.delete(cost)
    db.session.commit()

    flash('Packaging cost has been deleted.', 'success')
    return redirect(url_for('view_packaging', packaging_id=packaging.id))

@app.route('/upload_packaging_csv', methods=['GET', 'POST'])
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
                    total_cost = calculate_item_cost(item.id)
                    item_cost = ItemTotalCost(
                        item_id=item.id,
                        total_cost=total_cost,
                        date=pd.Timestamp.now().date(),
                        company_id=current_user.company_id
                    )
                    db.session.add(item_cost)
                db.session.commit()

            flash('Packaging costs added successfully!', 'success')
            return redirect(url_for('packaging'))
    return render_template('upload_packaging_csv.html', title='Upload Packaging CSV', form=form)

@app.route('/raw_product')
@login_required
def raw_product():
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
        upload_csv_form=upload_raw_product_csv_form
    )

# view an individual raw product
@app.route('/raw_product/<int:raw_product_id>')
@login_required
def view_raw_product(raw_product_id):
    # Find the raw product in the database
    raw_product = RawProduct.query.filter_by(id=raw_product_id, company_id=current_user.company_id).first()
    if raw_product is None:
        flash('Raw product not found.', 'danger')
        return redirect(url_for('raw_product'))
    
    # Get all the cost history for this raw product
    cost_history = CostHistory.query.filter_by(raw_product_id=raw_product_id).order_by(CostHistory.date.desc()).all()

    # find the items that use this raw product
    items_using_raw_product = Item.query.filter(Item.raw_products.any(id=raw_product_id)).all()

    cost_form = AddRawProductCost()

    return render_template('view_raw_product.html', items_using_raw_product=items_using_raw_product, title='View Raw Product', cost_form=cost_form, raw_product=raw_product, cost_history=cost_history)

# delete a raw product cost
@app.route('/delete_raw_product_cost/<int:cost_id>', methods=['POST'])
@login_required
def delete_raw_product_cost(cost_id):
    # Find the cost in the database
    cost = CostHistory.query.filter_by(id=cost_id, company_id=current_user.company_id).first()
    if not cost:
        flash('Cost not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('raw_product'))

    # Delete the cost
    db.session.delete(cost)
    db.session.commit()

    # Update the total cost for any items using this raw product
    items_using_raw_product = Item.query.filter(Item.raw_products.any(id=cost.raw_product_id)).all()
    
    for item in items_using_raw_product:
        update_item_total_cost(item.id)

    flash('Raw product cost has been deleted successfully.', 'success')
    return redirect(url_for('view_raw_product', raw_product_id=cost.raw_product_id))

# Add a new raw product
@app.route('/add_raw_product', methods=['POST'])
@login_required
def add_raw_product():
    form = AddRawProduct()
    if form.validate_on_submit():

        # Check if the raw product already exists
        existing_raw_product = RawProduct.query.filter_by(name=form.name.data, company_id=current_user.company_id).first()
        if existing_raw_product:
            flash(f'Raw product "{form.name.data}" already exists.', 'warning')
            return redirect(url_for('raw_product'))
        
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
        return redirect(url_for('raw_product'))
    flash('Invalid data submitted.', 'danger')
    return redirect(url_for('raw_product'))

# Add a new raw product cost
@app.route('/add_raw_product_cost/<int:raw_product_id>', methods=['POST'])
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
    return redirect(url_for('raw_product'))


# raw product import
@app.route('/upload_raw_product_csv', methods=['GET', 'POST'])
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
            return redirect(url_for('raw_product'))
    return render_template('upload_raw_product_csv.html', title='Upload Raw Product CSV', form=form)

@app.route('/delete_raw_product/<int:raw_product_id>', methods=['POST'])
@login_required
def delete_raw_product(raw_product_id):
    # Find the raw product in the database
    raw_product = RawProduct.query.filter_by(id=raw_product_id, company_id=current_user.company_id).first()
    if not raw_product:
        flash('Raw product not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('raw_product'))

    # Delete all associated CostHistory entries
    CostHistory.query.filter_by(raw_product_id=raw_product_id).delete()

    # Delete the raw product itself
    db.session.delete(raw_product)
    db.session.commit()

    flash(f'Raw product "{raw_product.name}" and its associated costs have been deleted.', 'success')
    return redirect(url_for('raw_product'))

# route for items page
@app.route('/items')
@login_required
def items():
    company = Company.query.filter_by(id=current_user.company_id).first()
    form = AddItem()
    update_item_form = UpdateItemInfo()
    form.packaging.choices = [(pack.id, pack.packaging_type) for pack in company.packaging] if company else []
    form.raw_products.choices = [(raw.id, raw.name) for raw in company.raw_products] if company else []
    upload_item_csv = UploadItemCSV()
    # get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    # get the items from the current user's company
    items = company.items if company else []
    #packaging = Packaging.query.filter_by(company_id=current_user.company_id).all()
    
    packaging_lookup = {
        p.id: p.packaging_type
        for p in Packaging.query.filter_by(company_id=current_user.company_id).all()
    }

    raw_product_lookup = {
        rp.id: rp.name
        for rp in RawProduct.query.filter_by(company_id=current_user.company_id).all()
    }

    # get the most recent item info for each item
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


    
    # render the page
    return render_template(
        'items.html',
        title='Items',
        items=items,
        packaging_lookup=packaging_lookup,
        raw_product_lookup=raw_product_lookup,
        #packaging=packaging,
        #item_costs=item_costs,
        form=form,
        update_item_info_form=update_item_form,
        item_info_lookup=item_info_lookup,
        upload_item_csv=upload_item_csv
    )
    
@app.route('/add_item', methods=['POST'])
@login_required
def add_item():
    # make sure a labor cost exists for the current user
    most_recent_labor_cost = LaborCost.query.order_by(LaborCost.date.desc(), LaborCost.id.desc()).filter_by(company_id=current_user.company_id).first()
    if not most_recent_labor_cost:
        flash('Please add a labor cost before adding items.', 'warning')
        return redirect(url_for('items'))

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
            return redirect(url_for('items'))
        
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
        return redirect(url_for('items'))
    # if the form is not submitted or is invalid, render the items page
    for field, errs in form.errors.items():
        for e in errs:
            flash(f"{getattr(form, field).label.text}: {e}", 'danger')
    flash('Invalid data submitted.', 'danger')
    return redirect(url_for('items'))

# delete an item
@app.route('/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    # find the item in the database
    item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first()
    if not item:
        flash('Item not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('items'))
    
    # delete all associated ItemInfo entries
    ItemInfo.query.filter_by(item_id=item_id).delete()
    # delete the item itself
    db.session.delete(item)
    db.session.commit()
    flash(f'Item "{item.name}" and its associated information have been deleted.', 'success')
    return redirect(url_for('items'))

# update info for an item
@app.route('/update_item/<int:item_id>', methods=['GET', 'POST'])
@login_required
def update_item(item_id):
    # find the item in db
    item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first()
    if not item:
        flash('Item not found or you do not have permission to update it.', 'danger')
        return redirect(url_for('items'))
    
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
        return redirect(url_for('items'))
    # if the form is not submitted or is invalid, render the update item page
    flash('Invalid data submitted.', 'danger')
    return render_template('update_item.html', title='Update Item', form=form, item=item)

# view an individual item
@app.route('/item/<int:item_id>')
@login_required
def view_item(item_id):
    # find the item in the database
    item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first()
    if item is None:
        flash('Item not found.', 'danger')
        return redirect(url_for('items'))
    
    # get all the item info for this item
    item_info = ItemInfo.query.filter_by(item_id=item_id).order_by(ItemInfo.date.desc()).all()
    packaging = Packaging.query.filter_by(id=item.packaging_id, company_id=current_user.company_id).first()
    raw_products = [rp for rp in item.raw_products]

    # most recent labor cost
    most_recent_labor_cost = LaborCost.query.order_by(LaborCost.date.desc(), LaborCost.id.desc()).filter_by(company_id=current_user.company_id).first()

    # history of total costs for this item
    item_costs = ItemTotalCost.query.filter_by(item_id=item_id).order_by(ItemTotalCost.date.desc()).all()
    
    # if there's no item costs, calculate the current cost
    if not item_costs:
        update_item_total_cost(item_id)

    # get the most recent item cost
    item_costs = ItemTotalCost.query.filter_by(item_id=item_id).order_by(ItemTotalCost.date.desc()).all()
    current_cost = item_costs[0] if item_costs else None
    #print(current_cost.total_cost)

    # form
    update_item_info_form = UpdateItemInfo()
    form = EditItem()

    form.packaging.choices = [(pack.id, pack.packaging_type) for pack in Packaging.query.filter_by(company_id=current_user.company_id).all()]
    form.raw_products.choices = [(raw.id, raw.name) for raw in RawProduct.query.filter_by(company_id=current_user.company_id).all()]
    # populate the form with the item's data
    #form.name.data = item.name
    #form.item_code.data = item.code
    form.unit_of_weight.data = item.unit_of_weight
    form.case_weight.data = item.case_weight if item.case_weight else 0.0
    form.ranch.data = item.ranch
    form.item_designation.data = item.item_designation
    form.packaging.data = item.packaging_id
    form.raw_products.data = [rp.id for rp in item.raw_products]

    return render_template('view_item.html', form=form, current_cost=current_cost, item_costs=item_costs, most_recent_labor_cost=most_recent_labor_cost, update_item_info_form=update_item_info_form, title='View Item', item=item, item_info=item_info, packaging=packaging, raw_products=raw_products)

@app.route('/delete_item_info/<int:item_info_id>', methods=['POST'])
@login_required
def delete_item_info(item_info_id):
    item_info = ItemInfo.query.filter_by(id=item_info_id, company_id=current_user.company_id).first()
    if not item_info:
        flash('Item info not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('items'))
    
    item_id = item_info.item_id
    db.session.delete(item_info)
    db.session.commit()
    flash('Item info deleted successfully!', 'success')
    return redirect(url_for('view_item', item_id=item_id))

# item import
@app.route('/upload_item_csv', methods=['GET', 'POST'])
@login_required
def upload_item_csv():
    # make sure a labor cost exists for the current user
    most_recent_labor_cost = LaborCost.query.order_by(LaborCost.date.desc(), LaborCost.id.desc()).filter_by(company_id=current_user.company_id).first()
    if not most_recent_labor_cost:
        flash('Please add a labor cost before uploading items.', 'warning')
        return redirect(url_for('items'))

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
            required_columns = ['name', 'item_code', 'raw_product', 'ranch', 'item_designation', 'packaging_type', 'yield', 'case_weight', 'labor']
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
                name = row['name'].strip()
                item_code = row['item_code'].strip()
                raw_product = row['raw_product'].strip()
                ranch = row['ranch'].strip().lower() == 'true'
                item_designation = row['item_designation'].strip()
                packaging_type = row['packaging_type'].strip()
                case_weight = row.get('case_weight', 0.0)  # Default to 0.0 if not provided
                #labor = row.get('labor', 0.0)  # Default to 0.0 if not provided

                try:
                    labor = float(row['labor'])
                except (ValueError, TypeError) as e:
                    flash(f'Invalid labor value "{row["labor"]}" for item "{name}". Defaulting to 0.0.', 'warning')
                    labor = 0.0

                #yield_value = float(row['yield'].replace('%', '').strip())
                raw_yield = row['yield']
                yield_str = str(raw_yield).strip()
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
                    db.session.add(new_info)
                    db.session.commit()
                    flash(f'Item "{name}" already exists. Skipping item.', 'warning')
                    continue

                # Check if the packaging exists
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
                    case_weight=row.get('case_weight', 0.0),  # Default to 0.0 if not provided
                    packaging_id=packaging.id,
                    company_id=current_user.company_id,
                    ranch=ranch,
                    item_designation=item_designation
                )

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
    return redirect(url_for('items'))

# view an individual item cost
@app.route('/item_cost/<int:item_cost_id>')
@login_required
def view_item_cost(item_cost_id):
    # Find the item cost in the database
    item_cost = ItemTotalCost.query.filter_by(id=item_cost_id, company_id=current_user.company_id).first()
    if not item_cost:
        flash('Item cost not found or you do not have permission to view it.', 'danger')
        return redirect(url_for('items'))

    # Get the item associated with this cost
    item = Item.query.filter_by(id=item_cost.item_id, company_id=current_user.company_id).first()
    if not item:
        flash('Item not found or you do not have permission to view it.', 'danger')
        return redirect(url_for('items'))

    # Get the most recent item info for this item
    most_recent_info = (
        ItemInfo.query
        .filter_by(item_id=item.id)
        .order_by(ItemInfo.date.desc(), ItemInfo.id.desc())
        .first()
    )

    return render_template('view_item_cost.html', title='View Item Cost', item_cost=item_cost, item=item, most_recent_info=most_recent_info)

# delete an item cost
@app.route('/delete_item_cost/<int:item_cost_id>', methods=['GET','POST'])
@login_required
def delete_item_cost(item_cost_id):
    # find the item in the database
    item = Item.query.filter_by(id=item_cost_id, company_id=current_user.company_id).first()
    # Find the item cost in the database
    item_cost = ItemTotalCost.query.filter_by(id=item_cost_id, company_id=current_user.company_id).first()
    if not item_cost:
        flash('Item cost not found or you do not have permission to delete it.', 'danger')
        if item:
            return redirect(url_for('view_item', item_id=item.id))
        return redirect(url_for('items'))

    # Delete the item cost
    db.session.delete(item_cost)
    db.session.commit()

    flash('Item cost has been deleted successfully.', 'success')
    return redirect(url_for('items'))

@app.route('/edit_item/<int:item_id>', methods=['POST'])
@login_required
def edit_item(item_id):
    # Find the item in the database
    item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first()
    if not item:
        flash('Item not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('items'))

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
        return redirect(url_for('view_item', item_id=item.id))

    flash('Invalid data submitted.', 'danger')
    # print the form errors
    for field, errs in form.errors.items():
        for e in errs:
            flash(f"{getattr(form, field).label.text}: {e}", 'danger')

    return redirect(url_for('view_item', item_id=item.id))

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
    flash(f'Total cost for item: {item_id} has been updated to ${cost:.2f}.', 'success')

# price page for showing cost of each item and different prices (along with associated profit and margins)
@app.route('/price')
@login_required
def price():
    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('index'))

    # Get all items for the current user's company
    items = Item.query.filter_by(company_id=current_user.company_id).all()

    # Get the most recent total cost for each item
    item_costs = {}
    for item in items:
        most_recent_cost = (
            ItemTotalCost.query
            .filter_by(item_id=item.id)
            .order_by(ItemTotalCost.date.desc(), ItemTotalCost.id.desc())
            .first()
        )
        if most_recent_cost:
            item_costs[item.id] = most_recent_cost
        else:
            # if no cost found, attempt to calculate it
            update_item_total_cost(item.id)

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

    return render_template('price.html', title='Price', items=item_data, item_costs=item_costs, item_data=item_data, company=company)

# page to add labor cost
@app.route('/add_labor_cost', methods=['GET', 'POST'])
@login_required
def add_labor_cost():
    form = AddLaborCost()

    if form.validate_on_submit():
        # Create a new labor cost entry
        labor_cost = LaborCost(
            labor_cost=form.cost.data,
            date=form.date.data,
            company_id=current_user.company_id
        )
        db.session.add(labor_cost)
        db.session.commit()
        update_item_costs_on_labor_change()
        flash('Labor cost added successfully!', 'success')

        # get past labor costs for the current user
        past_labor_costs = LaborCost.query.filter_by(company_id=current_user.company_id).order_by(LaborCost.date.desc()).all()

    else:
        flash('Invalid data submitted.', 'danger')

        # get past labor costs for the current user
        past_labor_costs = LaborCost.query.filter_by(company_id=current_user.company_id).order_by(LaborCost.date.desc()).all()

    return render_template('add_labor_cost.html', title='Add Labor Cost', form=form, past_labor_costs=past_labor_costs)

# delete a labor cost
@app.route('/delete_labor_cost/<int:cost_id>', methods=['POST'])
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
            return redirect(url_for('add_labor_cost'))

        # Delete the labor cost
        db.session.delete(labor_cost)
        db.session.commit()

        update_item_costs_on_labor_change()

    else:
        # Find the labor cost in the database
        labor_cost = LaborCost.query.filter_by(id=cost_id, company_id=current_user.company_id).first()
        if not labor_cost:
            flash('Labor cost not found or you do not have permission to delete it.', 'danger')
            return redirect(url_for('add_labor_cost'))

        # Delete the labor cost
        db.session.delete(labor_cost)
        db.session.commit()

    flash('Labor cost has been deleted successfully.', 'success')
    return redirect(url_for('add_labor_cost'))

# update all item costs when a labor cost is added or deleted
def update_item_costs_on_labor_change():
    # Get all items for the current user's company
    items = Item.query.filter_by(company_id=current_user.company_id).all()

    # Update the total cost for each item
    for item in items:
        update_item_total_cost(item.id)

    flash('All item costs have been updated based on the latest labor costs.', 'success')

# company page
@app.route('/company')
@login_required
def company():
    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('index'))
    
    # get all users in the company
    users = User.query.filter_by(company_id=current_user.company_id).all()

    # get the owner's account
    admin_email = company.admin_email if company else None
    admin = User.query.filter_by(email=admin_email).first() if admin_email else None
    if not admin:
        flash('Admin user not found for this company.', 'danger')
        return redirect(url_for('index'))

    return render_template('company.html', title='Company', company=company, users=users, admin=admin)

# ability for business owner to delete users
@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    # Check if the current user is the admin of the company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company or current_user.email != company.admin_email:
        flash('You do not have permission to delete users.', 'danger')
        return redirect(url_for('company'))

    # Find the user in the database
    user = User.query.filter_by(id=user_id, company_id=current_user.company_id).first()
    if not user:
        flash('User not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('company'))

    # Delete the user
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{user.email}" has been deleted successfully.', 'success')
    return redirect(url_for('company'))

# customer page
@app.route('/customer')
@login_required
def customer():
    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('index'))

    # Get all customers for the current user's company
    customers = Customer.query.filter_by(company_id=current_user.company_id).all()

    form = AddCustomer()
    import_form = UploadCustomerCSV()

    return render_template('customer.html', form=form, import_form=import_form, title='Customer', customers=customers, company=company)

@app.route('/edit_customer/<int:customer_id>', methods=['POST'])
@login_required
def edit_customer(customer_id):
    # Find the customer in the database
    customer = Customer.query.filter_by(id=customer_id, company_id=current_user.company_id).first()
    if not customer:
        flash('Customer not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('customer'))

    # Update the customer's details
    customer.name = request.form['name']
    customer.email = request.form['email']
    db.session.commit()

    flash(f'Customer "{customer.name}" has been updated successfully!', 'success')
    return redirect(url_for('customer'))

# add new customer
@app.route('/add_customer', methods=['POST'])
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
        return redirect(url_for('customer'))

    return render_template('add_customer.html', title='Add Customer', form=form)

# delete a customer
@app.route('/delete_customer/<int:customer_id>', methods=['POST'])
@login_required
def delete_customer(customer_id):
    # Find the customer in the database
    customer = Customer.query.filter_by(id=customer_id, company_id=current_user.company_id).first()
    if not customer:
        flash('Customer not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('customer'))

    # Delete the customer
    db.session.delete(customer)
    db.session.commit()
    flash(f'Customer "{customer.name}" has been deleted successfully.', 'success')
    return redirect(url_for('customer'))

# upload customer CSV
@app.route('/upload_customer_csv', methods=['GET', 'POST'])
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
    return redirect(url_for('customer'))

@app.route('/ranch', methods=['GET', 'POST'])
@login_required
def ranch():
    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('index'))

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
        return redirect(url_for('ranch'))

    return render_template('ranch.html', title='Ranch', ranch_prices=ranch_prices, form=form)

@app.route("/reset/_password", methods=["GET", "POST"])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_reset_password_email(user)
            flash('An email has been sent with instructions to reset your password.', 'info')
        else:
            flash('No account found with that email address.', 'danger')
        return redirect(url_for('login'))
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

@app.route('/reset_password/<token>/<int:user_id>', methods=['GET', 'POST'])
def reset_password(token, user_id):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    user = User.query.get(user_id)
    if not user or not user.verify_reset_password_token(token, user_id):
        flash('Invalid or expired token.', 'danger')
        return redirect(url_for('reset_password_request'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset successfully!', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', title='Reset Password', form=form, user=user)

# only true if this file is run directly
if __name__ == '__main__':
    app.run(debug=True)