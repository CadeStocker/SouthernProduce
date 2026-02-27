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
    Packaging, 
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

# packaging page
@main.route('/packaging')
@login_required
def packaging():
    # search feature
    q = request.args.get('q', '').strip()

    if q:
        # filter the packaging by the search query
        pagination = Packaging.query.filter(
            Packaging.packaging_type.ilike(f'%{q}%'),
            Packaging.company_id == current_user.company_id
        ).order_by(Packaging.packaging_type.asc()).paginate(
            page=request.args.get('page', 1, type=int),
            per_page=15,
            error_out=False
        )
    else:
        # get the current user's company
        company = Company.query.filter_by(id=current_user.company_id).first()
        # get the packaging for the current user's company
        pagination = Packaging.query.filter_by(company_id=current_user.company_id).order_by(Packaging.packaging_type.asc()).paginate(
            page=request.args.get('page', 1, type=int),
            per_page=15,
            error_out=False
        )

    page = request.args.get('page', 1, type=int)
    per_page = 15  # amount per page
    packaging = pagination.items

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
            q=q,
            pagination=pagination
        )

# view an individual package
@main.route('/packaging/<int:packaging_id>')
@login_required
def view_packaging(packaging_id):
    packaging_costs = {}
    packaging_items = {}

    # find the packaging in the database
    packaging = Packaging.query.filter_by(id=packaging_id, company_id=current_user.company_id).first()
    if packaging is None:
        flash('Packaging not found.', 'danger')
        return redirect(url_for('main.packaging'))
    
    # get all the packaging costs for this packaging
    packaging_costs = PackagingCost.query.filter_by(packaging_id=packaging_id).order_by(PackagingCost.date.asc()).all()

    form = AddPackagingCost()

    # items using this packaging
    packaging_items = Item.query.filter_by(
        company_id=current_user.company_id,
        packaging_id=packaging_id
    ).all()

    return render_template('view_packaging.html',
        title='View Packaging',
        packaging=packaging,
        packaging_costs=packaging_costs,
        form=form,
        items_using=packaging_items,
        packaging_id=packaging_id
    )


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