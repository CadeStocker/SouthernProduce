from flask import redirect, render_template, request, url_for, flash
from producepricer.models import User, Company, Packaging
from producepricer.forms import CreatePackage, SignUp, Login, CreateCompany
from flask_login import login_user, login_required, current_user, logout_user
from producepricer import app, db, bcrypt

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
    # form
    form = CreatePackage()
    return render_template('packaging.html', title='Packaging', packaging=packaging, form=form)

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

# only true if this file is run directly
if __name__ == '__main__':
    app.run(debug=True)