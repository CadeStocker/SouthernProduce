from flask_mailman import EmailMessage
from producepricer.blueprints._blueprint import main

from flask import (
    redirect,
    render_template,
    render_template_string,
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
            user = User(
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                email=form.email.data,
                password=bcrypt.generate_password_hash(form.password.data).decode('utf-8'),
                company_id=company.id
            )
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
            password=bcrypt.generate_password_hash(form.password.data).decode('utf-8'),
            company_id=company.id
        )
        # add to db
        db.session.add(pending)
        db.session.commit()

        # token and serializer
        s = Serializer(current_app.config['SECRET_KEY'], salt='user-approval')  # 1 hour expiration
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
      from_email=current_app.config['MAIL_DEFAULT_SENDER'],
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
    s = Serializer(current_app.config['SECRET_KEY'], salt='user-approval')
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
        if user and user.check_password(form.password.data):
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

        # see if admin email is already registered
        existing_user = User.query.filter_by(email=form.admin_email.data).first()
        if existing_user:
            flash('Admin email already registered. Please use a different email.', 'warning')
            return redirect(url_for('main.create_company'))
        
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

@main.route("/reset_password", methods=["GET", "POST"])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
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
        return redirect(url_for('main.home'))
    
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