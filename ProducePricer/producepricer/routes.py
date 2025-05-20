from flask import redirect, render_template, request, url_for, flash
from producepricer.models import CostHistory, PackagingCost, User, Company, Packaging
from producepricer.forms import AddPackagingCost, CreatePackage, SignUp, Login, CreateCompany, UploadPackagingCSV
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
        most_recent_cost = PackagingCost.query.filter_by(packaging_id=pack.id).order_by(PackagingCost.date.desc()).first()
        if most_recent_cost:
            packaging_costs[pack.id] = most_recent_cost

    # form
    form = CreatePackage()
    return render_template('packaging.html', title='Packaging', packaging=packaging, form=form, packaging_costs=packaging_costs)

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
    form = AddPackagingCost()
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

@app.route('/upload_packaging_csv', methods=['GET', 'POST'])
@login_required
def upload_packaging_csv():
    form = UploadPackagingCSV()
    if form.validate_on_submit():
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        # if user does not select file, browser also submit an empty part without filename
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            # read the csv file into a pandas dataframe
            df = pd.read_csv(filepath)
            # process the dataframe and add packaging costs to the database
            for index, row in df.iterrows():
                packaging_cost = PackagingCost(date=row['date'],
                                               box_cost=row['box_cost'],
                                               bag_cost=row['bag_cost'],
                                               tray_andor_chemical_cost=row['tray_andor_chemical_cost'],
                                               label_andor_tape_cost=row['label_andor_tape_cost'],
                                               packaging_id=row['packaging_id'],
                                               company_id=current_user.company_id)
                db.session.add(packaging_cost)
            db.session.commit()
            flash('Packaging costs added successfully!', 'success')
            return redirect(url_for('packaging'))
    return render_template('upload_packaging_csv.html', title='Upload Packaging CSV', form=form)

@app.route('/raw_product')
@login_required
def raw_product():
    # get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    # get the raw products for the current user's company
    raw_products = company.raw_products
    # get the most recent cost for each raw product
    raw_product_costs = {}
    for raw_product in raw_products:
        # get the most recent cost for this raw product
        most_recent_cost = CostHistory.query.filter_by(raw_product_id=raw_product.id).order_by(CostHistory.date.desc()).first()
        if most_recent_cost:
            raw_product_costs[raw_product.id] = most_recent_cost

    return render_template('raw_product.html', title='Raw Product', raw_products=raw_products, raw_product_costs=raw_product_costs)

# only true if this file is run directly
if __name__ == '__main__':
    app.run(debug=True)