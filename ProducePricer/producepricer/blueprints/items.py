import datetime
from io import BytesIO
from sqlite3 import IntegrityError
from flask_mailman import EmailMessage
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


def safe_strip(x):
    """Strip whitespace from a value, returning empty string for NaN/None."""
    if pd.isna(x):
        return ''
    return str(x).strip()


def find_designation_cost(item_designation):
    """Return the most recent designation cost for the given item designation."""
    from producepricer.models import DesignationCost
    from flask_login import current_user
    designation_cost = DesignationCost.query.filter_by(
        item_designation=item_designation,
        company_id=current_user.company_id
    ).order_by(DesignationCost.date.desc()).first()
    if designation_cost:
        return designation_cost.cost
    else:
        flash(f'No designation cost found for {item_designation}. Using default cost of $1.00.', 'warning')
        return 1.00


@main.route('/items')
@login_required
def items():
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 15  # Items per page
    use_pagination = request.args.get('paginate') == 'true'
    
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
    
    # Apply pagination or get all
    if use_pagination:
        pagination = query.order_by(Item.name).paginate(page=page, per_page=per_page, error_out=False)
        items = pagination.items
    else:
        items = query.order_by(Item.name).all()
        pagination = None
    
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
    # Clear price sheet backup association rows directly so SQLAlchemy
    # doesn't need to query the price_sheet_backup table during flush.
    try:
        from producepricer.models import price_sheet_backup_items
        db.session.execute(
            price_sheet_backup_items.delete().where(
                price_sheet_backup_items.c.item_id == item_id
            )
        )
    except Exception:
        pass
    # delete the item itself
    db.session.delete(item)
    db.session.commit()
    flash(f'Item "{item.name}" and its associated information have been deleted.', 'success')
    return redirect(url_for('main.items'))

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
        .order_by(PriceHistory.date.asc(), PriceHistory.id.asc())
        .paginate(page=price_page, per_page=per_page, error_out=False)
    )
    price_history = price_pagination.items
    
    # 2. Cost history with pagination (for table)
    cost_pagination = (
        ItemTotalCost.query
        .filter_by(item_id=item_id)
        .order_by(ItemTotalCost.date.asc())
        .paginate(page=cost_page, per_page=per_page, error_out=False)
    )
    item_costs = cost_pagination.items
    
    # 3. Item info history with pagination (for table)
    info_pagination = (
        ItemInfo.query
        .filter_by(item_id=item_id)
        .order_by(ItemInfo.date.asc())
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

                # Check if the item already exists
                existing_item = Item.query.filter_by(name=name, code=item_code, company_id=current_user.company_id, packaging_id=packaging.id).first()
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

                # test for git

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
                    # continue

                # add the item to the database so that it gets assigned an ID
                db.session.add(item)
                db.session.flush()  # Flush to get the item ID before creating ItemInfo

                item_info = ItemInfo(
                    product_yield=yield_value,
                    item_id=item.id,
                    labor_hours=labor,
                    date=pd.Timestamp.now().date(),
                    company_id=current_user.company_id
                )

                # Add the item info to the database
                db.session.add(item_info)

                try:
                    db.session.commit()

                    # find the total cost of the item
                    update_item_total_cost(item.id)
                except IntegrityError:
                    db.session.rollback()
                    flash(f'Skipped item {name}')
                    continue
                
                #flash(f'Item "{name}" has been added successfully!', 'success')
            flash('Items imported successfully!', 'success')
    return redirect(url_for('main.items'))

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

        # comment to test git

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
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    
    if not itemInfo:
        flash(f'No item info found for item "{item.name}".', 'warning')
        print(f'No item info found for item with ID {item_id} for company {current_user.company_id}.')
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

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
    raw_products_with_cost_count = 0
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
            #total_cost += (cost_per_unit_yield * item.case_weight)
            raw_product_cost += (cost_per_unit_yield * item.case_weight)
            raw_products_with_cost_count += 1
        else:
            print(f"Skipping raw product {raw_product.name} (id {raw_product.id}) - no cost found")

    # If it is a combo, average the raw product cost
    if item.item_designation == ItemDesignation.COMBO:
        if raw_products_with_cost_count > 0:
            raw_product_cost = raw_product_cost / raw_products_with_cost_count
        else:
            raw_product_cost = 0.0
            
    total_cost += raw_product_cost

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
        labor_cost_per_hour = LaborCost.query.filter_by(company_id=current_user.company_id).order_by(LaborCost.date.desc(), LaborCost.id.desc()).first()
        if labor_cost_per_hour:
            labor_cost_per_hour = labor_cost_per_hour.labor_cost
        else:
            flash('Labor cost not found. Assuming $0 per hour.', 'warning')
            labor_cost_per_hour = 0

        total_cost += itemInfo.labor_hours * labor_cost_per_hour
        labor_cost = itemInfo.labor_hours * labor_cost_per_hour

    designation_cost = 0.0

    # Calculate designation cost
    if not find_designation_cost(item.item_designation):
        flash('No designation cost found. Please assign values to each designation cost.')
    
    designation_cost += find_designation_cost(item.item_designation)
    total_cost += designation_cost

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
    raw_products_with_cost_count = 0
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
            #total_cost += (cost_per_unit_yield * case_weight)
            raw_product_cost += (cost_per_unit_yield * case_weight)
            raw_products_with_cost_count += 1

    # If it is a combo, average the raw product cost
    if item_designation == ItemDesignation.COMBO or item_designation == 'combo':
        if raw_products_with_cost_count > 0:
            raw_product_cost = raw_product_cost / raw_products_with_cost_count
        else:
            raw_product_cost = 0.0

    total_cost += raw_product_cost

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
    total_cost += designation_cost

    # return the different costs and the total
    return total_cost, labor_cost, designation_cost, total_packaging_cost, raw_product_cost, ranch_cost