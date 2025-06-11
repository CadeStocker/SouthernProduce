import datetime
from flask import redirect, render_template, request, url_for, flash
from producepricer.models import CostHistory, Item, ItemInfo, PackagingCost, RawProduct, User, Company, Packaging
from producepricer.forms import AddItem, AddPackagingCost, AddRawProduct, AddRawProductCost, CreatePackage, SignUp, Login, CreateCompany, UpdateItemInfo, UploadItemCSV, UploadPackagingCSV, UploadRawProductCSV
from flask_login import login_user, login_required, current_user, logout_user
from producepricer import app, db, bcrypt
import pandas as pd
import os
from werkzeug.utils import secure_filename

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

    return render_template('view_packaging.html', title='View Packaging', packaging=packaging, packaging_costs=packaging_costs)


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
        # redirect to the packaging page
        return redirect(url_for('packaging'))
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
    # add item form
    form = AddItem()
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
    update_item_info_form = UpdateItemInfo()

    return render_template('view_item.html', update_item_info_form=update_item_info_form, title='View Item', item=item, item_info=item_info, packaging=packaging, raw_products=raw_products)

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
            required_columns = ['name', 'item_code', 'raw_product', 'ranch', 'item_designation', 'packaging_type', 'yield']
            if not all(column in df.columns for column in required_columns):
                flash('Invalid CSV format. Please ensure all required columns are present.', 'danger')
                return redirect(request.url)

            # Process the DataFrame and add items to the database
            for index, row in df.iterrows():
                # Clean and convert values
                name = row['name'].strip()
                item_code = row['item_code'].strip()
                raw_product = row['raw_product'].strip()
                ranch = row['ranch'].strip().lower() == 'true'
                item_designation = row['item_designation'].strip()
                packaging_type = row['packaging_type'].strip()
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
                        labor_hours=0.0,  # Assuming a default labor hours
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
                    labor_hours=0.0,  # Assuming a default labor hours
                    date=pd.Timestamp.now().date(),
                    company_id=current_user.company_id
                )

                # Add the item info to the database
                db.session.add(item_info)
                db.session.commit()
                #flash(f'Item "{name}" has been added successfully!', 'success')
            flash('Items imported successfully!', 'success')
    return redirect(url_for('items'))

# only true if this file is run directly
if __name__ == '__main__':
    app.run(debug=True)