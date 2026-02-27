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

# page to add labor cost
@main.route('/add_labor_cost', methods=['GET', 'POST'])
@login_required
def add_labor_cost():
    form = AddLaborCost()

    page = request.args.get('page', 1, type=int)
    per_page = 15  # amount per page
    labor_pagination = LaborCost.query.filter_by(company_id=current_user.company_id).order_by(LaborCost.date.asc()).paginate(page=page, per_page=per_page, error_out=False)
    past_labor_costs = labor_pagination.items

    # get past labor costs for the current user
    #past_labor_costs = LaborCost.query.filter_by(company_id=current_user.company_id).order_by(LaborCost.date.asc()).all()

    chart_labels = [lc.date.strftime('%Y-%m-%d') for lc in past_labor_costs]
    chart_data = [lc.labor_cost for lc in past_labor_costs]

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
            return redirect(url_for('main.add_labor_cost'))

        else:
            flash('Invalid data submitted.', 'danger')
            return redirect(url_for('main.add_labor_cost'))

    return render_template(
        'add_labor_cost.html',
        title='Add Labor Cost',
        form=form,
        past_labor_costs=past_labor_costs,
        chart_labels=chart_labels,
        chart_data=chart_data,
        labor_pagination=labor_pagination  # Pass pagination object to template
    )

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

@main.route('/ranch', methods=['GET', 'POST'])
@login_required
def ranch():
    page = request.args.get('page', 1, type=int)
    per_page = 15  # Items per page
    ranch_pagination = RanchPrice.query.filter_by(company_id=current_user.company_id).order_by(RanchPrice.date.asc()).paginate(page=page, per_page=per_page, error_out=False)

    delete_form = DeleteForm()

    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('main.index'))

    # Get all previous ranch prices and costs for the current user's company
    ranch_prices = ranch_pagination.items

    # Initialize the form
    form = AddRanchPrice()

    chart_labels = [rp.date.strftime('%Y-%m-%d') for rp in ranch_prices]
    chart_data = [rp.price for rp in ranch_prices]

    if form.validate_on_submit():
        # Create a new ranch price entry
        ranch_price = RanchPrice(
            price=form.price.data,
            cost=form.cost.data,
            date=form.date.data,
            company_id=current_user.company_id,
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

    return render_template('ranch.html',
        title='Ranch',
        ranch_prices=ranch_prices,
        form=form,
        chart_data=chart_data,
        chart_labels=chart_labels,
        pagination=ranch_pagination,
        delete_form=delete_form,
        )

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

@main.route('/delete_ranch_price/<int:ranch_price_id>', methods=['POST'])
@login_required
def delete_ranch_price(ranch_price_id):
    ranch_price = RanchPrice.query.filter_by(id=ranch_price_id, company_id=current_user.company_id).first()
    if not ranch_price:
        flash('Ranch price not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.ranch'))
    db.session.delete(ranch_price)
    db.session.commit()
    flash('Ranch price/cost deleted successfully.', 'success')
    return redirect(url_for('main.ranch'))

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
        flash('Admin user')
        return redirect(url_for('main.index'))

    return render_template('company.html',
                           title='Company',
                           company=company,
                           users=users,
                           admin=admin,
                           pending_users=pending_users)