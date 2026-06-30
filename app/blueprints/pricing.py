# Copyright Cade Stocker 2026
import datetime
import math
from flask_mailman import EmailMessage
from fpdf import FPDF
from app.blueprints.items import update_item_total_cost
from app.blueprints._blueprint import main

from flask import (
    make_response,
    redirect,
    render_template,
    render_template_string,
    request,
    url_for,
    flash,
    current_app
)
from itsdangerous import BadSignature, Serializer, SignatureExpired
from app.models import (
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
    CurrentItemPrice,
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
from app.forms import(
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
from app import db, bcrypt
import pandas as pd
import os
from werkzeug.utils import secure_filename
from flask_mailman import EmailMessage
from app.utils.ai_utils import get_ai_response
from app.utils.qr_utils import generate_api_key_qr_code, generate_qr_code_bytes
import pdfplumber
import tempfile
from sqlalchemy import func

@main.route('/delete_price_history/<int:price_history_id>', methods=['POST'])
@login_required
def delete_price_history(price_history_id):

    """
    Delete a price history entry from the database after confirming it exists and belongs to the current user's company.
    """

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

# price page for showing cost of each item and different prices (along with associated profit and margins)
@main.route('/price')
@login_required
def price():

    """
    Display the price page with cost and pricing information for each item, including optional search and pagination.
    """

    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 15  # Items per page
    use_pagination = request.args.get('paginate', '0').lower() in ('1', 'true', 'yes')

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
    if use_pagination:
        pagination = query.order_by(Item.name).paginate(page=page, per_page=per_page, error_out=False)
        items = pagination.items
    else:
        items = query.order_by(Item.name).all()
        pagination = None

    # Process items for display
    item_data = []

    def round_up_to_nearest_quarter(value):
        return math.ceil(value * 4) / 4

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

        ranch_cost = 0
        if item.ranch:
            recent_ranch_cost = (RanchPrice.query
                          .order_by(RanchPrice.date.desc(), RanchPrice.id.desc())
                          .first()
            )

            if recent_ranch_cost:
                ranch_cost = recent_ranch_cost.cost

        designation_cost = 0
        if item.item_designation:
            recent_designation_cost = (DesignationCost.query
                                .filter_by(item_designation=item.item_designation)
                                .order_by(DesignationCost.date.desc(), DesignationCost.id.desc())
                                .first()
            )

            if recent_designation_cost:
                designation_cost = recent_designation_cost.cost

        # Skip items that still don't have a cost after trying to calculate it
        if not most_recent_cost:
            continue

        recent_item_info = (ItemInfo.query.
                            filter_by(item_id=item.id)
                            .order_by(ItemInfo.date.desc(), ItemInfo.id.desc())
                            .first())

        if not recent_item_info:
            product_yield = 0
        else:
            product_yield = recent_item_info.product_yield

        # Calculate additional values
        cost_per_lb = most_recent_cost.total_cost / item.case_weight if item.case_weight else 0.0
        cost_per_oz = cost_per_lb / 16  # 1 pound = 16 ounces
        labor_cost = most_recent_cost.labor_cost
        packaging_cost = most_recent_cost.packaging_cost
        unit_cost = most_recent_cost.total_cost

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
            'alternate_code': item.alternate_code or '',
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
                           q=q,
                           use_pagination=use_pagination)

@main.route('/current_prices')
@login_required
def current_prices():
    """
    Display a page showing the current master prices for each item.
    Uses CurrentItemPrice model as the source of truth.
    """

    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Items per page
    
    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('main.index'))

    # Get all items for this company
    items = Item.query.filter_by(company_id=current_user.company_id).order_by(Item.name).all()
    
    # Get current prices for each item
    price_data = []
    for item in items:
        current_price = CurrentItemPrice.query.filter_by(
            item_id=item.id, 
            company_id=current_user.company_id
        ).first()
        
        # Add the item info with its current price to the data array
        price_data.append({
            'item': item,
            'current_price': current_price.price if current_price else None,  # Can be None if no price set
            'effective_date': current_price.effective_date if current_price else None,
        })
    
    return render_template(
        'current_prices.html',
        title='Current Prices',
        price_data=price_data,
        company=company
    )

@main.route('/current_prices/export-pdf')
@login_required
def export_current_prices_pdf():
    """
    Export the current prices as a PDF
    """

    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('main.index'))

    # Get all items for this company
    items = Item.query.filter_by(company_id=current_user.company_id).order_by(Item.name).all()

    # Get current prices for each item
    price_data = []
    for item in items:
        current_price = CurrentItemPrice.query.filter_by(
            item_id=item.id,
            company_id=current_user.company_id
        ).first()

        # Add the item info with its current price to the data array
        price_data.append({
            'item': item,
            'current_price': current_price.price if current_price else None,  # Can be None if no price set
            'effective_date': current_price.effective_date if current_price else None,
        })

    # Create PDF - using similar formatting to existing export templates
    pdf = FPDF(orientation="L", unit="mm", format="A4")  # Landscape A4
    pdf.set_auto_page_break(auto=True, margin=15)

    # Set font and colors
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"{company.name} - Current Prices", 0, 1, 'C')
    pdf.ln(5)  # Add space after header

    # Add date
    from datetime import datetime
    current_date = datetime.now().strftime('%Y-%m-%d')
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 8, f"Generated on: {current_date}", 0, 1, 'C')
    pdf.ln(5)

    # Table setup with columns for better formatting
    if price_data:
        col_widths = [70, 25, 25, 30]  # Name, Code, Price, Date
        headers = ['Item Name', 'Code', 'Current Price', 'Effective Date']
        
        # Header row with styling
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(52, 73, 94)  # Dark blue-gray
        pdf.set_text_color(255, 255, 255)  # White text

        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 8, header, 1, 0, 'C', 1)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)  # Reset to black
        
        # Table data
        pdf.set_font("Arial", "", 9)
        
        for idx, item_data in enumerate(price_data):
            # Alternate row colors
            if idx % 2 == 0:
                pdf.set_fill_color(245, 245, 245)  # Light gray background for even rows
                fill = 1
            else:
                pdf.set_fill_color(255, 255, 255)  # White background for odd rows
                fill = 0

            # Add cell with item data 
            pdf.cell(col_widths[0], 6, item_data['item'].name[:35] + '...' if len(item_data['item'].name) > 35 else item_data['item'].name, 1, 0, 'L', fill)
            pdf.cell(col_widths[1], 6, str(item_data['item'].code), 1, 0, 'C', fill)
            
            # Format price
            price_cell = f"${item_data['current_price']:.2f}" if item_data['current_price'] else "Not Set"
            pdf.cell(col_widths[2], 6, price_cell, 1, 0, 'R', fill)
            
            # Format date
            date_cell = item_data['effective_date'].strftime('%Y-%m-%d') if item_data['effective_date'] else "Never"
            pdf.cell(col_widths[3], 6, date_cell, 1, 0, 'C', fill)
            pdf.ln()

        # Add footer note
        pdf.ln(5)
        pdf.set_font("Arial", "I", 8)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 5, f'Total Items: {len(price_data)}', 0, 1, 'R')
    else:
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, "No items found.", 0, 1)

    # Generate PDF output
    pdf_output = bytes(pdf.output(dest='S'))

    # Create response
    response = make_response(pdf_output)
    response.headers['Content-Type'] = 'application/pdf'
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'current_prices_{timestamp}.pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response

@main.route('/price/export-pdf')
@login_required
def export_price_pdf():

    """
    Export the price table as a PDF
    """

    # Get search parameter
    q = request.args.get('q', '').strip()
    
    # Get the current user's company
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('main.index'))
    
    # Base query - filtered by company (no pagination for export)
    query = Item.query.filter_by(company_id=current_user.company_id)
    
    # Apply search filter if provided
    if q:
        query = query.filter(
            (Item.name.ilike(f'%{q}%')) | (Item.code.ilike(f'%{q}%'))
        )
    
    items = query.order_by(Item.name).all()
    
    # Process items for display
    item_data = []

    def round_up_to_nearest_quarter(value):
        return math.ceil(value * 4) / 4

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
        
        # Skip items that still don't have a cost after trying to calculate it
        if not most_recent_cost:
            continue

        # Calculate additional values
        cost_per_lb = most_recent_cost.total_cost / item.case_weight if item.case_weight else 0.0
        cost_per_oz = cost_per_lb / 16
        labor_cost = most_recent_cost.labor_cost
        packaging_cost = most_recent_cost.packaging_cost
        unit_cost = most_recent_cost.total_cost

        # Calculate rounded prices
        rounded_25 = round_up_to_nearest_quarter(unit_cost * 1.25)
        rounded_30 = round_up_to_nearest_quarter(unit_cost * 1.30)
        rounded_35 = round_up_to_nearest_quarter(unit_cost * 1.35)
        rounded_40 = round_up_to_nearest_quarter(unit_cost * 1.40)
        rounded_45 = round_up_to_nearest_quarter(unit_cost * 1.45)

        # Append data for this item
        item_data.append({
            'name': item.name,
            'alternate_code': item.alternate_code,
            'case_weight': item.case_weight,
            'total_cost': most_recent_cost.total_cost,
            'ranch_cost': most_recent_cost.ranch_cost,
            'cost_per_lb': cost_per_lb,
            'cost_per_oz': cost_per_oz,
            'labor_cost': labor_cost,
            'packaging_cost': packaging_cost,
            'unit_cost': unit_cost,
            'rounded_25': rounded_25,
            'rounded_30': rounded_30,
            'rounded_35': rounded_35,
            'rounded_40': rounded_40,
            'rounded_45': rounded_45,
        })

    # Create PDF
    pdf = FPDF(orientation='L', unit='mm', format='A4')  # Landscape orientation
    pdf.add_page()
    pdf.set_font('Arial', 'B', 14)
    
    # Title without background box
    pdf.set_text_color(0, 0, 0)  # Black text
    pdf.cell(0, 10, f'Item Pricing Report - {company.name}', 0, 1, 'C')
    
    if q:
        pdf.set_font('Arial', 'I', 9)
        pdf.set_text_color(100, 100, 100)  # Gray text
        pdf.cell(0, 5, f'Filtered by: "{q}"', 0, 1, 'C')
        pdf.set_text_color(0, 0, 0)  # Reset to black
    
    # Add date
    pdf.set_font('Arial', '', 8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, f'Generated: {datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")}', 0, 1, 'C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)
    
    # Table headers with background
    pdf.set_font('Arial', 'B', 7)
    pdf.set_fill_color(52, 73, 94)  # Dark blue-gray
    pdf.set_text_color(255, 255, 255)  # White text
    
    # Adjusted column widths - made item name much wider (80mm)
    col_widths = [80, 18, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11]
    headers = ['Item Name', 'Alternate Code', 'Weight', 'Total', 'Cost/LB', 'Cost/Oz', 'Labor', 
               'Pkg', 'Ranch', 'Unit', '25%', '30%', '35%', '40%', '45%']
    
    # Calculate table width and center it
    table_width = sum(col_widths)
    page_width = 297  # A4 landscape width in mm
    left_margin = (page_width - table_width) / 2
    pdf.set_left_margin(left_margin)
    pdf.set_x(left_margin)
    
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 7, header, 1, 0, 'C', 1)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)  # Reset to black
    
    # Table data with alternating row colors
    pdf.set_font('Arial', '', 7)
    for idx, item in enumerate(item_data):
        # Set X position to center the table
        pdf.set_x(left_margin)
        
        # Alternate row colors
        if idx % 2 == 0:
            pdf.set_fill_color(245, 245, 245)  # Light gray
            fill = 1
        else:
            fill = 0
        
        # Truncate item name if too long (now fits more characters with wider column)
        item_name = item['name'][:95] + '...' if len(item['name']) > 95 else item['name']
        
        pdf.cell(col_widths[0], 6, item_name, 1, 0, 'L', fill)
        pdf.cell(col_widths[1], 6, str(item['alternate_code']), 1, 0, 'C', fill)
        pdf.cell(col_widths[2], 6, f"{item['case_weight']:.1f}", 1, 0, 'C', fill)
        pdf.cell(col_widths[3], 6, f"${item['total_cost']:.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[4], 6, f"${item['cost_per_lb']:.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[5], 6, f"${item['cost_per_oz']:.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[6], 6, f"${item['labor_cost']:.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[7], 6, f"${item['packaging_cost']:.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[8], 6, f"${item['ranch_cost']:.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[9], 6, f"${item['unit_cost']:.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[10], 6, f"${item['rounded_25']:.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[11], 6, f"${item['rounded_30']:.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[12], 6, f"${item['rounded_35']:.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[13], 6, f"${item['rounded_40']:.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[14], 6, f"${item['rounded_45']:.2f}", 1, 0, 'R', fill)
        pdf.ln()
    
    # Footer with item count
    pdf.ln(2)
    pdf.set_font('Arial', 'I', 8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, f'Total Items: {len(item_data)}', 0, 1, 'R')
    
    # Generate PDF output
    pdf_output = bytes(pdf.output(dest='S'))
    
    # Create response
    response = make_response(pdf_output)
    response.headers['Content-Type'] = 'application/pdf'
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'item_pricing_{timestamp}.pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


@main.route('/pricing_workflow', methods=['GET', 'POST'])
@login_required
def pricing_workflow():

    """
    Guided pricing workflow: update master customer prices from current unit costs
    with a target dollar margin (for example, +$10.00).
    """

    master_customer = Customer.query.filter_by(
        company_id=current_user.company_id,
        is_master=True
    ).first()

    if not master_customer:
        flash('Set a Master Customer first to use Pricing Workflow.', 'warning')
        return redirect(url_for('main.customer'))

    target_margin = request.values.get('target_margin', default=10.0, type=float)
    if target_margin is None:
        target_margin = 10.0

    items = Item.query.filter_by(company_id=current_user.company_id).order_by(Item.name.asc()).all()

    if request.method == 'POST':
        saved_count = 0
        skipped_count = 0
        today = datetime.datetime.utcnow().date()

        for item in items:
            raw_price = (request.form.get(f'price_input_{item.id}') or '').strip()
            if not raw_price:
                skipped_count += 1
                continue

            try:
                price = float(raw_price)
            except ValueError:
                skipped_count += 1
                continue

            if price < 0:
                skipped_count += 1
                continue

            current_price = CurrentItemPrice.query.filter_by(
                item_id=item.id,
                company_id=current_user.company_id
            ).first()

            if current_price:
                current_price.price = price
                current_price.effective_date = today
            else:
                db.session.add(
                    CurrentItemPrice(
                        item_id=item.id,
                        company_id=current_user.company_id,
                        price=price,
                        effective_date=today
                    )
                )
            saved_count += 1

        db.session.commit()

        if saved_count:
            flash(
                f'Saved {saved_count} master price(s). Other customers will use these prices unless overridden.',
                'success'
            )
        else:
            flash('No valid prices were submitted.', 'warning')

        if skipped_count and saved_count:
            flash(f'Skipped {skipped_count} item(s) with blank/invalid prices.', 'info')

        return redirect(url_for('main.pricing_workflow', target_margin=target_margin))

    def round_up_to_nearest_quarter(value):
        return math.ceil(value * 4) / 4

    rows = []
    for item in items:
        recent_cost = (
            ItemTotalCost.query
            .filter_by(item_id=item.id, company_id=current_user.company_id)
            .order_by(ItemTotalCost.date.desc(), ItemTotalCost.id.desc())
            .first()
        )

        if not recent_cost:
            update_item_total_cost(item.id)
            recent_cost = (
                ItemTotalCost.query
                .filter_by(item_id=item.id, company_id=current_user.company_id)
                .order_by(ItemTotalCost.date.desc(), ItemTotalCost.id.desc())
                .first()
            )

        unit_cost = float(recent_cost.total_cost) if recent_cost and recent_cost.total_cost is not None else 0.0

        current_price_row = CurrentItemPrice.query.filter_by(
            item_id=item.id,
            company_id=current_user.company_id
        ).first()

        if current_price_row and current_price_row.price is not None:
            current_price = float(current_price_row.price)
        else:
            fallback_ph = (
                PriceHistory.query
                .filter_by(item_id=item.id, company_id=current_user.company_id)
                .order_by(PriceHistory.date.desc(), PriceHistory.id.desc())
                .first()
            )
            current_price = float(fallback_ph.price) if fallback_ph and fallback_ph.price is not None else None

        margin = (current_price - unit_cost) if current_price is not None else None
        suggested_price = round_up_to_nearest_quarter(unit_cost + target_margin)

        rows.append({
            'item': item,
            'unit_cost': unit_cost,
            'current_price': current_price,
            'margin': margin,
            'suggested_price': suggested_price
        })

    rows.sort(key=lambda r: (r['item'].name or '').lower())

    return render_template(
        'pricing_workflow.html',
        title='Pricing Workflow',
        rows=rows,
        target_margin=target_margin,
        master_customer=master_customer
    )

def _generate_price_sheet_pdf_bytes(sheet):
    
    """
    Helper function to generate the price sheet PDF bytes.
    """

    # Helper to sanitize text for FPDF by replacing non-standard characters
    def sanitize_text(text):
        if text is None:
            return ""
        return text.encode('latin-1', 'replace').decode('latin-1')

    # Build recent dict for each item
    recent = {}
    
    seven_days_ago_date = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).date()

    for item in sheet.items:
        sheet_price = PriceHistory.query.filter_by(
            company_id=current_user.company_id,
            customer_id=sheet.customer_id,
            price_sheet_id=sheet.id,
            item_id=item.id
        ).order_by(PriceHistory.date.desc(), PriceHistory.id.desc()).first()

        customer_latest = None
        if not sheet_price:
            customer_latest = (
                PriceHistory.query
                .filter_by(
                    company_id=current_user.company_id,
                    customer_id=sheet.customer_id,
                    item_id=item.id
                )
                .order_by(PriceHistory.date.desc(), PriceHistory.id.desc())
                .first()
            )

        cp = None
        if not sheet_price and not customer_latest:
            cp = CurrentItemPrice.query.filter_by(
                company_id=current_user.company_id,
                item_id=item.id
            ).first()

        ph_old = PriceHistory.query.filter_by(
            company_id=current_user.company_id,
            customer_id=sheet.customer_id,
            item_id=item.id
        ).filter(PriceHistory.date <= seven_days_ago_date).order_by(PriceHistory.date.desc(), PriceHistory.id.desc()).first()

        selected = sheet_price or customer_latest
        
        recent[item.id] = {
            'price': float(selected.price) if selected and selected.price is not None else (float(cp.price) if cp and cp.price is not None else None),
            'date': selected.date if selected and selected.date else (cp.effective_date if cp and cp.effective_date else None),
            'old_price': float(ph_old.price) if ph_old and ph_old.price is not None else None
        }

    # Create PDF
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Center on page
    col_widths = [90, 25, 20, 25]
    total_width = sum(col_widths)
    left_margin = (210 - total_width) / 2
    pdf.set_left_margin(left_margin)
    pdf.set_right_margin(left_margin)

    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    
    # Sanitize the sheet name before rendering
    sanitized_sheet_name = sanitize_text(sheet.name)
    pdf.cell(0, 8, f"Price Sheet: {sanitized_sheet_name}", ln=1, align='C')
    
    pdf.set_font("Arial", "", 10)
    
    v_start = sheet.valid_from.strftime('%Y-%m-%d') if sheet.valid_from else '?'
    v_end   = sheet.valid_to.strftime('%Y-%m-%d')   if sheet.valid_to   else '?'
    pdf.cell(0, 6, f"Valid: {v_start} to {v_end}", ln=1, align='C')
    pdf.ln(4)

    # Table header
    pdf.set_font("Arial", "B", 9)
    # col_widths defined above
    headers = ["Product", "Price", "Changed", "Alt Code"]
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 6, header, border=1, align="C")
    pdf.ln()

    # Table rows
    pdf.set_font("Arial", "", 8)

    # Sort items alphabetically by name
    sorted_items = sorted(sheet.items, key=lambda x: x.name.lower() if x.name else '')
    
    for item in sorted_items:
        info = recent.get(item.id, {})
        current_price = info.get('price')
        old_price = info.get('old_price')
        
        price_str = f"${current_price:.2f}" if current_price is not None else "-"
        
        changed_char = ""
        
        if current_price is not None:
            if old_price is not None:
                if abs(current_price - old_price) > 0.001:
                    changed_char = "*"
            else:
                # No price history older than 7 days, so this is a new price
                changed_char = "*"

        # Sanitize the item name before rendering
        sanitized_item_name = sanitize_text(item.name)
        sanitized_alternate_code = sanitize_text(item.alternate_code or "-")

        pdf.cell(col_widths[0], 6, sanitized_item_name, border=1)
        pdf.cell(col_widths[1], 6, price_str, border=1, align="C")
        pdf.cell(col_widths[2], 6, changed_char, border=1, align="C")
        pdf.cell(col_widths[3], 6, sanitized_alternate_code, border=1, align="C")
        pdf.ln()

    return bytes(pdf.output(dest='S'))

@main.route('/price_quoter', methods=['GET','POST'])
@login_required
def price_quoter():
    
    """
    Display the price quoter form and handle price calculations based on user input.
    """

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

    # Keep a lookup of the most recent cost for each raw product so the UI can auto-fill
    raw_cost_lookup = {}
    for raw in raws:
        latest_cost = (CostHistory.query
                       .filter_by(raw_product_id=raw.id, company_id=current_user.company_id)
                       .order_by(CostHistory.date.desc(), CostHistory.id.desc())
                       .first())
        raw_cost_lookup[str(raw.id)] = float(latest_cost.cost) if latest_cost and latest_cost.cost is not None else 0.0

    # Initialize the result variable
    result = None

    # Pre‐fill the form if an item has been selected via query param
    item_id = request.args.get('item_id', type=int)
    if item_id and not form.is_submitted():
        item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first()
        if item:
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
            raw_cost_values = []
            for raw_product in item.raw_products:
                raw_cost_entry = (CostHistory.query
                                  .filter_by(raw_product_id=raw_product.id, company_id=current_user.company_id)
                                  .order_by(CostHistory.date.desc(), CostHistory.id.desc())
                                  .first())
                if raw_cost_entry and raw_cost_entry.cost is not None:
                    raw_cost_values.append(float(raw_cost_entry.cost))
            if raw_cost_values:
                form.raw_product_cost.data = sum(raw_cost_values) / len(raw_cost_values)

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

        # The form field holds the total raw cost (sum of selected raw products).
        # If the user provided a value, use it directly. Otherwise sum from DB.
        if form.raw_product_cost.data is not None and len(selected_raws) > 0:
            total_raw = form.raw_product_cost.data
        else:
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
        if item_designation:
            dc = DesignationCost.query.filter_by(item_designation=item_designation, company_id=current_user.company_id).first()
            if dc:
                designation_cost += dc.cost

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
        raw_cost_lookup=raw_cost_lookup
    )

@main.route('/price_sheet', methods=['GET', 'POST'])
@login_required
def price_sheet():

    """
    Display the price sheet management page, allowing users to create new price sheets and view existing ones.
    """

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
    # Sort items alphabetically by name
    all_items.sort(key=lambda x: x.name.lower() if x.name else '')
    form.items.choices = [(i.id, i.name) for i in all_items]

    # get all the customer names for the existing sheets
    customer_names = {c.id: c.name for c in customers}

    # Group price sheets by customer for display purposes
    from collections import defaultdict
    grouped_sheets = defaultdict(list)
    for sheet in price_sheets:
        grouped_sheets[sheet.customer_id].append(sheet)

    if form.validate_on_submit():
        # create new sheet
        sheet = PriceSheet(
            name        = form.name.data,
            date        = form.valid_from.data,  # Use valid_from as the date
            valid_from  = form.valid_from.data,
            valid_to    = form.valid_to.data,
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
      customer_names = customer_names,
      grouped_sheets = grouped_sheets  # For grouping in template
    )

@main.route('/edit_price_sheet/<int:sheet_id>', methods=['GET', 'POST'])
@login_required
def edit_price_sheet(sheet_id):

    """
    Display the price sheet editing page, allowing users to update prices and sheet details.
    """

    sheet = PriceSheet.query.filter_by(
        id=sheet_id,
        company_id=current_user.company_id
    ).first_or_404()

    # find all items that aren't already in the sheet
    all_items = Item.query.filter_by(company_id=current_user.company_id).all()
    existing_item_ids = {item.id for item in sheet.items}
    available_items = [item for item in all_items if item.id not in existing_item_ids]
    # Sort available items alphabetically by name
    available_items.sort(key=lambda x: x.name.lower() if x.name else '')

    # on save…
    if request.method=='POST':
        # Check if this is a date update
        if 'update_dates' in request.form:
            valid_from_str = request.form.get('valid_from')
            valid_to_str = request.form.get('valid_to')

            try:
                # Convert strings to date objects
                v_from = datetime.datetime.strptime(valid_from_str, '%Y-%m-%d').date()
                if valid_to_str:
                    v_to = datetime.datetime.strptime(valid_to_str, '%Y-%m-%d').date()
                else:
                    v_to = None
                
                # Check 1: validate valid_to >= valid_from
                if v_to and v_to < v_from:
                    flash('Error: Valid To date cannot be before Valid From date.', 'danger')
                    return redirect(url_for('main.edit_price_sheet', sheet_id=sheet.id))

                # Update the sheet
                sheet.valid_from = v_from
                sheet.valid_to = v_to
                # Also sync sheet.date to valid_from if useful, or keep separate
                sheet.date = v_from 

                db.session.commit()
                flash('Price Sheet dates updated successfully!', 'success')
            except ValueError:
                flash('Invalid date format provided.', 'danger')
            
            return redirect(url_for('main.edit_price_sheet', sheet_id=sheet.id))

        # Otherwise, saving prices
        for item in sheet.items:
            cp_sel = request.form.get(f'current_price_{item.id}')
            sel = request.form.get(f'price_select_{item.id}')
            inp = request.form.get(f'price_input_{item.id}')
            
            # Respect explicit user selection order:
            # 1) Current Price (QuickBooks), 2) markup select, 3) custom input.
            price = None
            
            if cp_sel and cp_sel != '':
                try:
                    price = float(cp_sel)
                except ValueError:
                    continue
            elif sel and sel != '':
                try:
                    price = float(sel)
                except ValueError:
                    continue
            elif inp and inp != '':
                try:
                    price = float(inp)
                except ValueError:
                    continue
            
            # If neither field has a valid value, skip this item
            if price is None:
                continue

            # Keep one row per sheet+item so edits on another sheet don't rewrite history.
            ph = PriceHistory.query.filter_by(
                company_id=current_user.company_id,
                customer_id=sheet.customer_id,
                price_sheet_id=sheet.id,
                item_id=item.id
            ).first()

            if ph:
                ph.price = price
                ph.date = datetime.datetime.utcnow().date()
            else:
                db.session.add(
                    PriceHistory(
                        date=datetime.datetime.utcnow().date(),
                        company_id=current_user.company_id,
                        customer_id=sheet.customer_id,
                        price_sheet_id=sheet.id,
                        item_id=item.id,
                        price=price
                    )
                )
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

    # get all current prices for items in this company (to populate the dropdown)
    current_prices = {}
    
    # get the unit cost for each item in the sheet
    unit_costs = {}

    # For each item, get current price from CurrentItemPrice and build markup options
    for item in sheet.items:
        # Get price history for the specific sheet/customer (this is what the frontend uses for display)
        current_price = PriceHistory.query.filter_by(
            item_id=item.id,
            customer_id=sheet.customer_id,
            company_id=current_user.company_id,
            price_sheet_id=sheet.id
        ).order_by(PriceHistory.date.desc(), PriceHistory.id.desc()).first()

        if current_price:
            recent_prices[item.id] = current_price.price
        else:
            # Fallback to latest known customer price, then master company price.
            customer_latest = PriceHistory.query.filter_by(
                item_id=item.id,
                customer_id=sheet.customer_id,
                company_id=current_user.company_id
            ).order_by(PriceHistory.date.desc(), PriceHistory.id.desc()).first()

            if customer_latest:
                recent_prices[item.id] = customer_latest.price
            else:
                last_cp = CurrentItemPrice.query.filter_by(
                    item_id=item.id,
                    company_id=current_user.company_id
                ).first()
                recent_prices[item.id] = last_cp.price if last_cp else None

        # Get all prices that were used in the system for this item that could have been selected as current prices
        # This is what we'll use to populate the dropdown in the template
        item_current_prices = CurrentItemPrice.query.filter_by(
            item_id=item.id,
            company_id=current_user.company_id
        ).order_by(CurrentItemPrice.effective_date.desc()).all()
        
        # Store a list of available prices for this item so the frontend can show them as options
        current_prices[item.id] = [cp.price for cp in item_current_prices]

        # most recent cost
        itc = ItemTotalCost.query.filter_by(
            item_id=item.id, company_id=current_user.company_id
        ).order_by(ItemTotalCost.date.desc(), ItemTotalCost.id.desc()).first()
        base = itc.total_cost if itc else 0

        # store the unit cost
        unit_costs[item.id] = base

        opts = []
        for pct in percents:
            raw = base * (1 + pct/100)
            price = math.ceil(raw * 4) / 4  # round up to nearest quarter
            opts.append((pct, price))
        markup_opts[item.id] = opts

    # Sort items alphabetically by name for display
    sorted_items = sorted(sheet.items, key=lambda x: x.name.lower() if x.name else '')

    return render_template(
      'edit_price_sheet.html',
      sheet=sheet,
      sorted_items=sorted_items,
      history_opts=history_opts,
      markup_opts=markup_opts,
      recent_prices=recent_prices,
      current_prices=current_prices,
      unit_costs=unit_costs,
      available_items=available_items
    )

@main.route('/view_price_sheet/<int:sheet_id>/export_pdf')
@login_required
def export_price_sheet_pdf(sheet_id):

    """
    Generate and return a PDF version of the price sheet for download.
    """

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

    """
    Add selected items to the price sheet.
    """

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

# remove an item from the price sheet
@main.route('/edit_price_sheet/<int:sheet_id>/remove_item/<int:item_id>', methods=['POST'])
@login_required
def remove_item_from_sheet(sheet_id, item_id):

    """
    Remove an item from the price sheet.
    """

    sheet = PriceSheet.query.filter_by(
        id=sheet_id, company_id=current_user.company_id
    ).first_or_404()
    item = Item.query.filter_by(
        id=item_id, company_id=current_user.company_id
    ).first_or_404()
    if item in sheet.items:
        sheet.items.remove(item)
        db.session.commit()
        flash(f'"{item.name}" removed from sheet.', 'success')
    else:
        flash(f'"{item.name}" was not on this sheet.', 'warning')
    return redirect(url_for('main.edit_price_sheet', sheet_id=sheet.id))

# delete a price sheet
@main.route('/delete_price_sheet/<int:sheet_id>', methods=['POST'])
@login_required
def delete_price_sheet(sheet_id):

    """
    Delete the price sheet and all associated price history entries.
    """

    sheet = PriceSheet.query.filter_by(
        id=sheet_id,
        company_id=current_user.company_id
    ).first_or_404()

    PriceHistory.query.filter_by(
        company_id=current_user.company_id,
        price_sheet_id=sheet.id
    ).delete()

    db.session.delete(sheet)
    db.session.commit()

    flash(f'Price Sheet "{sheet.name}" deleted!', 'success')
    return redirect(url_for('main.price_sheet'))

@main.route('/duplicate_price_sheet', methods=['POST'])
@login_required
def duplicate_price_sheet():
    """
    Duplicate an existing price sheet with the same items for a new date range.
    """

    # Get form data
    source_sheet_id = request.form.get('source_sheet_id')
    name = request.form.get('name', '').strip()
    
    if not source_sheet_id:
        flash('No source sheet specified.', 'danger')
        return redirect(url_for('main.price_sheet'))
    
    # Find the source sheet
    source_sheet = PriceSheet.query.filter_by(
        id=source_sheet_id,
        company_id=current_user.company_id
    ).first_or_404()
    
    # Validate name
    if not name:
        flash('Name is required.', 'danger')
        return redirect(url_for('main.price_sheet'))
    
    # Get dates from form or use current date
    valid_from_str = request.form.get('valid_from', '').strip()
    valid_to_str = request.form.get('valid_to', '').strip()
    
    try:
        if valid_from_str:
            valid_from = datetime.datetime.strptime(valid_from_str, '%Y-%m-%d').date()
        else:
            valid_from = source_sheet.valid_from or datetime.datetime.utcnow().date()
            
        if valid_to_str:
            valid_to = datetime.datetime.strptime(valid_to_str, '%Y-%m-%d').date()
        else:
            valid_to = source_sheet.valid_to
    except ValueError:
        flash('Invalid date format provided.', 'danger')
        return redirect(url_for('main.price_sheet'))
    
    # Create duplicate
    new_sheet = PriceSheet(
        name=name,
        date=datetime.datetime.utcnow().date(),
        company_id=current_user.company_id,
        customer_id=source_sheet.customer_id,
        valid_from=valid_from,
        valid_to=valid_to
    )
    
    # Copy items from source sheet
    new_sheet.items = source_sheet.items
    
    db.session.add(new_sheet)

    source_prices = PriceHistory.query.filter_by(
        company_id=current_user.company_id,
        customer_id=source_sheet.customer_id,
        price_sheet_id=source_sheet.id
    ).all()

    db.session.flush()

    for src in source_prices:
        db.session.add(
            PriceHistory(
                item_id=src.item_id,
                date=datetime.datetime.utcnow().date(),
                company_id=current_user.company_id,
                customer_id=source_sheet.customer_id,
                price_sheet_id=new_sheet.id,
                price=src.price
            )
        )

    db.session.commit()
    
    flash(f'Price Sheet "{new_sheet.name}" duplicated successfully!', 'success')
    return redirect(url_for('main.edit_price_sheet', sheet_id=new_sheet.id))

# Update email_price_sheet route to use template
@main.route('/email_price_sheet/<int:sheet_id>', methods=['POST'])
@login_required
def email_price_sheet(sheet_id):

    """
    Generate a PDF of the price sheet and email it to the specified recipients using the selected email template.
    """

    sheet = PriceSheet.query.filter_by(id=sheet_id, company_id=current_user.company_id).first_or_404()

    # Choose template_id from form or fallback to company default
    template_id = request.form.get('template_id', type=int)
    tpl = None
    if template_id:
        tpl = EmailTemplate.query.filter_by(id=template_id, company_id=current_user.company_id).first()
    if tpl is None:
        tpl = EmailTemplate.query.filter_by(company_id=current_user.company_id, is_default=True).first()

    # Support multiple recipients - can be from form or getlist for multiple selection
    recipients = request.form.getlist('recipients')
    # Also support single recipient field for backwards compatibility
    single_recipient = request.form.get('recipient')
    if single_recipient and single_recipient not in recipients:
        recipients.append(single_recipient)
    
    # Filter out empty strings
    recipients = [r.strip() for r in recipients if r and r.strip()]
    
    if not recipients:
        flash('At least one recipient email is required.', 'danger')
        return redirect(url_for('main.view_price_sheet', sheet_id=sheet.id))

    # Build context for template rendering
    context = {
        'sheet': sheet,
        'company': Company.query.get(current_user.company_id),
        'recipient': ', '.join(recipients),  # For template compatibility
        'recipients': recipients,
        'sheet_url': url_for('main.view_price_sheet', sheet_id=sheet.id, _external=True),
        'now': datetime.datetime.utcnow()
    }

    # Render subject/body from template or use defaults
    subject = f'Price Sheet: {sheet.name}'
    body = 'Attached is your requested price sheet PDF.'

    if tpl:
        try:
            subject = render_template_string(tpl.subject, **context)
            # Apply nl2br filter to convert newlines to <br> tags
            body_text = render_template_string(tpl.body, **context)
            # Convert newlines to <br> tags for HTML email
            body = body_text.replace('\r\n', '<br>').replace('\r', '<br>').replace('\n', '<br>')
        except Exception as e:
            # if template rendering fails, fallback and notify
            print(f"Template render error: {e}")
            flash('Error rendering selected email template - using defaults.', 'warning')
            subject = f'Price Sheet: {sheet.name}'
            body = 'Attached is your requested price sheet PDF.'

    # Generate PDF bytes
    pdf_bytes = _generate_price_sheet_pdf_bytes(sheet)

    sender = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('EMAIL_USER')

    # send email to all recipients
    msg = EmailMessage(
        subject=subject,
        body=body,
        to=recipients,
        from_email=sender
    )
    msg.content_subtype = 'html'  # Set content type to HTML
    msg.attach(f'price_sheet_{sheet.name}.pdf', pdf_bytes, 'application/pdf')
    try:
        msg.send()
        recipient_list = ', '.join(recipients)
        flash(f'Price sheet emailed to {recipient_list}.', 'success')
    except Exception as e:
        flash(f'Failed to send email: {e}', 'danger')

    return redirect(url_for('main.view_price_sheet', sheet_id=sheet.id))
