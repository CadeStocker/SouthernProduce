# Copyright Cade Stocker 2026
import datetime
import calendar
from flask_mailman import EmailMessage
from fpdf import FPDF
from app.auth_utils import optional_api_key_or_login
from app.blueprints.items import update_item_total_cost
from app.blueprints._blueprint import main

from flask import (
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
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
from app.utils.notification_utils import maybe_create_receiving_log_outlier_notification
import pdfplumber
import tempfile
import csv
import io
from sqlalchemy import func
from app.utils.notification_utils import _get_outlier_threshold

# Debug route to check market price data
@main.route('/debug_receiving_log/<int:log_id>')
@login_required
def debug_receiving_log(log_id):

    """
    Debug route to check why market cost comparison isn't working.
    """

    from datetime import timedelta
    from sqlalchemy import and_
    
    log = ReceivingLog.query.filter_by(id=log_id, company_id=current_user.company_id).first_or_404()
    
    debug_info = {
        'log_id': log.id,
        'raw_product': log.raw_product.name if log.raw_product else None,
        'raw_product_id': log.raw_product_id,
        'price_paid': log.price_paid,
        'log_date': log.datetime.strftime('%Y-%m-%d') if log.datetime else None,
    }
    
    # Check for cost history
    if log.datetime:
        log_date = log.datetime.date()
        search_start = log_date - timedelta(days=30)
        
        debug_info['search_window_start'] = search_start.strftime('%Y-%m-%d')
        debug_info['search_window_end'] = log_date.strftime('%Y-%m-%d')
        
        # Get all cost history for this raw product
        all_costs = CostHistory.query.filter(
            and_(
                CostHistory.raw_product_id == log.raw_product_id,
                CostHistory.company_id == current_user.company_id
            )
        ).order_by(CostHistory.date.desc()).limit(10).all()
        
        debug_info['all_cost_history'] = [
            {
                'cost': float(ch.cost),
                'date': ch.date.strftime('%Y-%m-%d')
            }
            for ch in all_costs
        ]
        
        # Get cost history within the search window
        relevant_costs = CostHistory.query.filter(
            and_(
                CostHistory.raw_product_id == log.raw_product_id,
                CostHistory.company_id == current_user.company_id,
                CostHistory.date <= log_date,
                CostHistory.date >= search_start
            )
        ).order_by(CostHistory.date.desc()).all()
        
        debug_info['relevant_cost_history'] = [
            {
                'cost': float(ch.cost),
                'date': ch.date.strftime('%Y-%m-%d'),
                'days_before_log': (log_date - ch.date).days
            }
            for ch in relevant_costs
        ]
        
        # Get the actual market cost that would be used
        market_data = log.get_master_customer_price()
        if market_data:
            debug_info['market_cost_used'] = float(market_data[0])
            debug_info['market_cost_date'] = market_data[1].strftime('%Y-%m-%d')
        else:
            debug_info['market_cost_used'] = None
            debug_info['market_cost_date'] = None
        
        # Get the comparison
        comparison = log.get_price_comparison()
        debug_info['comparison'] = comparison if comparison else None
    
    return jsonify(debug_info)

# Receiving Logs - display all receiving log entries
@main.route('/receiving_logs')
@login_required
def receiving_logs():

    """
    Display all receiving logs with search, filters, a KPI summary, trend data,
    outlier highlighting, and CSV export.
    """

    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 15  # Number of logs per page
    use_pagination = request.args.get('paginate', '0').lower() in ('1', 'true', 'yes')
    export = request.args.get('export', '').strip().lower()
    pagination = None

    # Filter params
    start_str = request.args.get('start_date', '').strip()
    end_str = request.args.get('end_date', '').strip()
    raw_product_id = request.args.get('raw_product_id', type=int)
    grower_id = request.args.get('grower_id', type=int)
    seller_id = request.args.get('seller_id', type=int)
    status = request.args.get('status', '').strip().lower()
    outliers_only = request.args.get('outliers_only', '0').lower() in ('1', 'true', 'yes')

    start_date = None
    end_date = None
    if start_str:
        try:
            start_date = datetime.datetime.strptime(start_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid start date. Please use YYYY-MM-DD format.', 'danger')
    if end_str:
        try:
            end_date = datetime.datetime.strptime(end_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid end date. Please use YYYY-MM-DD format.', 'danger')

    # The summary/dashboard is only useful when scoped to recent activity, so the
    # view defaults to a rolling 30-day window. An explicit date range overrides
    # it, and `all=1` opts into the full history.
    all_time = request.args.get('all', '0').strip().lower() in ('1', 'true', 'yes')
    default_window = False
    if not start_date and not end_date and not all_time:
        start_date = datetime.date.today() - datetime.timedelta(days=30)
        start_str = start_date.strftime('%Y-%m-%d')
        default_window = True

    if all_time:
        window_label = 'All time'
    elif default_window:
        window_label = 'Last 30 days'
    else:
        window_label = f"{start_str or '…'} → {end_str or 'today'}"

    base_query = ReceivingLog.query.filter_by(company_id=current_user.company_id)

    # Apply search filter if provided (search by raw product name, received_by, or country_of_origin)
    if q:
        base_query = base_query.join(RawProduct).filter(
            (RawProduct.name.ilike(f'%{q}%')) |
            (ReceivingLog.received_by.ilike(f'%{q}%')) |
            (ReceivingLog.country_of_origin.ilike(f'%{q}%'))
        )
    if start_date:
        base_query = base_query.filter(
            ReceivingLog.datetime >= datetime.datetime.combine(start_date, datetime.time.min)
        )
    if end_date:
        base_query = base_query.filter(
            ReceivingLog.datetime <= datetime.datetime.combine(end_date, datetime.time.max)
        )
    if raw_product_id:
        base_query = base_query.filter(ReceivingLog.raw_product_id == raw_product_id)
    if grower_id:
        base_query = base_query.filter(ReceivingLog.grower_or_distributor_id == grower_id)
    if seller_id:
        base_query = base_query.filter(ReceivingLog.seller_id == seller_id)
    if status in ('hold', 'used'):
        base_query = base_query.filter(ReceivingLog.hold_or_used == status)

    # Full filtered set (newest first) drives the KPIs, trend chart, outlier
    # detection, and CSV export. Price comparison is computed once per log here
    # and reused by the template to avoid duplicate lookups.
    all_filtered = base_query.order_by(ReceivingLog.datetime.desc()).all()
    threshold = _get_outlier_threshold()

    comparisons = {}
    outlier_ids = set()
    held = used = priced = above_market = below_market = at_market = 0
    est_spend = 0.0
    over_market_amount = 0.0
    daily = {}  # 'YYYY-MM-DD' -> {'loads': int, 'spend': float}

    for log in all_filtered:
        if log.hold_or_used == 'hold':
            held += 1
        elif log.hold_or_used == 'used':
            used += 1

        if log.datetime:
            day_key = log.datetime.strftime('%Y-%m-%d')
            bucket = daily.setdefault(day_key, {'loads': 0, 'spend': 0.0})
            bucket['loads'] += 1
        else:
            bucket = None

        comp = log.get_price_comparison()
        comparisons[log.id] = comp
        if log.price_paid is not None:
            priced += 1
            line_total = log.price_paid * (log.quantity_received or 0)
            est_spend += line_total
            if bucket is not None:
                bucket['spend'] += line_total
            if comp and comp.get('master_price') is not None:
                pct = comp.get('percentage') or 0.0
                if comp['status'] == 'above_market':
                    above_market += 1
                    if comp.get('difference') is not None:
                        over_market_amount += comp['difference'] * (log.quantity_received or 0)
                    if abs(pct) >= threshold:
                        outlier_ids.add(log.id)
                elif comp['status'] == 'below_market':
                    below_market += 1
                    if abs(pct) >= threshold:
                        outlier_ids.add(log.id)
                elif comp['status'] == 'at_market':
                    at_market += 1

    kpis = {
        'total_loads': len(all_filtered),
        'held': held,
        'used': used,
        'priced': priced,
        'unpriced': len(all_filtered) - priced,
        'above_market': above_market,
        'below_market': below_market,
        'at_market': at_market,
        'outliers': len(outlier_ids),
        'est_spend': est_spend,
        'over_market_amount': over_market_amount,
        'threshold': threshold,
    }

    trend = sorted(
        (
            {'date': d, 'loads': v['loads'], 'spend': round(v['spend'], 2)}
            for d, v in daily.items()
        ),
        key=lambda x: x['date']
    )

    # CSV export of the full filtered set (ignores pagination/outlier toggle)
    if export == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Date', 'Raw Product', 'Brand', 'Quantity', 'Pack Size', 'Unit',
            'Price Paid', 'Market Cost', 'Variance %', 'Seller', 'Temperature (F)',
            'Hold/Used', 'Grower/Distributor', 'Country', 'Received By', 'Returned'
        ])
        for log in all_filtered:
            comp = comparisons.get(log.id)
            market = comp.get('master_price') if comp else None
            variance = comp.get('percentage') if comp else None
            writer.writerow([
                log.datetime.strftime('%Y-%m-%d %H:%M') if log.datetime else '',
                log.raw_product.name if log.raw_product else '',
                log.brand_name.name if log.brand_name else '',
                log.quantity_received,
                log.pack_size,
                log.pack_size_unit,
                f"{log.price_paid:.2f}" if log.price_paid is not None else '',
                f"{market:.2f}" if market is not None else '',
                f"{variance:.1f}" if variance is not None else '',
                log.seller.name if log.seller else '',
                log.temperature,
                log.hold_or_used,
                log.grower_or_distributor.name if log.grower_or_distributor else '',
                log.country_of_origin,
                log.received_by,
                log.returned or ''
            ])
        response = make_response(output.getvalue())
        filename = f"receiving_logs_{datetime.date.today().strftime('%Y%m%d')}.csv"
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response

    # Restrict the displayed list to outliers if requested (KPIs/trend stay full).
    if outliers_only:
        # When no outliers exist, force an empty result set (id is never -1).
        base_query = base_query.filter(ReceivingLog.id.in_(outlier_ids or [-1]))

    if use_pagination:
        pagination = base_query.order_by(ReceivingLog.datetime.desc()).paginate(page=page, per_page=per_page, error_out=False)
        logs = pagination.items
    else:
        # return all results without pagination
        logs = base_query.order_by(ReceivingLog.datetime.desc()).all()

    # Filter dropdown options (company-scoped, alphabetical)
    products = RawProduct.query.filter_by(company_id=current_user.company_id).order_by(RawProduct.name).all()
    growers = GrowerOrDistributor.query.filter_by(company_id=current_user.company_id).order_by(GrowerOrDistributor.name).all()
    sellers = Seller.query.filter_by(company_id=current_user.company_id).order_by(Seller.name).all()

    # Non-date filters, reused when switching the quick-range window.
    nondate_args = {
        'q': q,
        'raw_product_id': raw_product_id or '',
        'grower_id': grower_id or '',
        'seller_id': seller_id or '',
        'status': status,
        'outliers_only': 1 if outliers_only else '',
    }

    # Preserve active filters (including the window) when building links.
    filter_args = dict(nondate_args)
    filter_args['start_date'] = start_str
    filter_args['end_date'] = end_str
    if all_time:
        filter_args['all'] = 1

    today = datetime.date.today()
    quick_ranges = [
        {'label': 'Last 7 days', 'start': (today - datetime.timedelta(days=7)).strftime('%Y-%m-%d')},
        {'label': 'Last 30 days', 'start': (today - datetime.timedelta(days=30)).strftime('%Y-%m-%d')},
        {'label': 'Last 90 days', 'start': (today - datetime.timedelta(days=90)).strftime('%Y-%m-%d')},
        {'label': 'All time', 'all': True},
    ]

    return render_template(
        'receiving_logs.html',
        title='Receiving Logs',
        logs=logs,
        comparisons=comparisons,
        outlier_ids=outlier_ids,
        kpis=kpis,
        trend=trend,
        q=q,
        pagination=pagination,
        use_pagination=use_pagination,
        today=today,
        window_label=window_label,
        all_time=all_time,
        quick_ranges=quick_ranges,
        nondate_args=nondate_args,
        products=products,
        growers=growers,
        sellers=sellers,
        filters={
            'start_date': start_str,
            'end_date': end_str,
            'raw_product_id': raw_product_id,
            'grower_id': grower_id,
            'seller_id': seller_id,
            'status': status,
            'outliers_only': outliers_only,
        },
        filter_args=filter_args
    )


@main.route('/receiving_logs/print')
@login_required
def receiving_logs_print():

    """
    Display receiving logs in a print-friendly format, with optional date filtering.
    """

    date_str = request.args.get('date', '').strip()
    month_str = request.args.get('month', '').strip()
    if date_str:
        try:
            selected_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date. Please use YYYY-MM-DD format.', 'danger')
            return redirect(url_for('main.receiving_logs'))
    else:
        selected_date = datetime.date.today()

    if month_str:
        try:
            month_parts = month_str.split('-')
            if len(month_parts) != 2:
                raise ValueError
            calendar_year = int(month_parts[0])
            calendar_month = int(month_parts[1])
            calendar_date = datetime.date(calendar_year, calendar_month, 1)
        except ValueError:
            flash('Invalid month. Please use YYYY-MM format.', 'danger')
            return redirect(url_for('main.receiving_logs_print', date=selected_date.strftime('%Y-%m-%d')))
    else:
        calendar_date = selected_date.replace(day=1)

    start_dt = datetime.datetime.combine(selected_date, datetime.time.min)
    end_dt = datetime.datetime.combine(selected_date, datetime.time.max)

    month_last_day = calendar.monthrange(calendar_date.year, calendar_date.month)[1]
    month_start_dt = datetime.datetime.combine(calendar_date, datetime.time.min)
    month_end_dt = datetime.datetime.combine(
        datetime.date(calendar_date.year, calendar_date.month, month_last_day),
        datetime.time.max
    )

    logs = (
        ReceivingLog.query
        .filter_by(company_id=current_user.company_id)
        .filter(ReceivingLog.datetime >= start_dt, ReceivingLog.datetime <= end_dt)
        .order_by(ReceivingLog.datetime.asc())
        .all()
    )

    available_dates_rows = (
        db.session.query(func.date(ReceivingLog.datetime))
        .filter_by(company_id=current_user.company_id)
        .filter(ReceivingLog.datetime >= month_start_dt, ReceivingLog.datetime <= month_end_dt)
        .distinct()
        .all()
    )

    available_dates = []
    for row in available_dates_rows:
        row_value = row[0]
        if isinstance(row_value, datetime.date):
            available_dates.append(row_value.strftime('%Y-%m-%d'))
        else:
            available_dates.append(str(row_value))

    calendar_instance = calendar.Calendar(firstweekday=6)
    calendar_weeks = calendar_instance.monthdatescalendar(calendar_date.year, calendar_date.month)

    prev_month_date = (calendar_date.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    next_month_date = (calendar_date.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)

    return render_template(
        'receiving_logs_print.html',
        title='Daily Receiving Log Printout',
        logs=logs,
        selected_date=selected_date,
        now=datetime.datetime.utcnow(),
        calendar_date=calendar_date,
        calendar_month_label=calendar_date.strftime('%B %Y'),
        calendar_month_str=calendar_date.strftime('%Y-%m'),
        calendar_weeks=calendar_weeks,
        available_dates=available_dates,
        prev_month_str=prev_month_date.strftime('%Y-%m'),
        next_month_str=next_month_date.strftime('%Y-%m')
    )

# View individual receiving log
@main.route('/receiving_log/<int:log_id>')
@login_required
def view_receiving_log(log_id):

    """
    View details of a single receiving log entry, including market price comparison if available.
    """

    log = ReceivingLog.query.filter_by(id=log_id, company_id=current_user.company_id).first_or_404()
    
    # Get master customer price even if no price_paid is set yet
    # This allows the modal to show market reference
    market_data = log.get_master_customer_price()
    master_price = market_data[0] if market_data else None
    master_price_date = market_data[1] if market_data else None
    
    return render_template(
        'view_receiving_log.html',
        title=f'Receiving Log - {log.raw_product.name if log.raw_product else "Log"}',
        log=log,
        master_price=master_price,
        master_price_date=master_price_date,
        now=datetime.datetime.utcnow()
    )

# Edit receiving log (for adding price paid by management)
@main.route('/edit_receiving_log/<int:log_id>', methods=['POST'])
@login_required
def edit_receiving_log(log_id):

    """
    Edit a receiving log entry, specifically to add or update the price paid information.
    """

    log = ReceivingLog.query.filter_by(id=log_id, company_id=current_user.company_id).first_or_404()
    
    # Get price_paid from form
    price_paid_str = request.form.get('price_paid', '').strip()
    
    # Validate and convert price_paid
    if price_paid_str:
        try:
            price_paid = float(price_paid_str)
            if price_paid < 0:
                flash('Price paid must be a positive number.', 'danger')
                return redirect(url_for('main.view_receiving_log', log_id=log_id))
            log.price_paid = price_paid
        except ValueError:
            flash('Invalid price format. Please enter a valid number.', 'danger')
            return redirect(url_for('main.view_receiving_log', log_id=log_id))
    else:
        # If empty, set to None to remove price
        log.price_paid = None
    
    db.session.commit()
    try:
        maybe_create_receiving_log_outlier_notification(log, commit=True)
    except Exception:
        current_app.logger.exception('Failed to create receiving log outlier notification')
    flash('Receiving log updated successfully!', 'success')
    return redirect(url_for('main.view_receiving_log', log_id=log_id))

# Email receiving log
@main.route('/email_receiving_log/<int:log_id>', methods=['POST'])
@login_required
def email_receiving_log(log_id):

    """
    Email the details of a receiving log entry to a specified recipient, with an optional custom message.
    """

    log = ReceivingLog.query.filter_by(id=log_id, company_id=current_user.company_id).first_or_404()
    
    recipient = request.form.get('recipient', '').strip()
    subject = request.form.get('subject', '').strip()
    additional_message = request.form.get('message', '').strip()
    
    if not recipient:
        flash('Recipient email address is required.', 'danger')
        return redirect(url_for('main.view_receiving_log', log_id=log_id))
    
    # Set default subject if not provided
    if not subject:
        product_name = log.raw_product.name if log.raw_product else 'Product'
        date_str = log.datetime.strftime('%Y-%m-%d') if log.datetime else ''
        subject = f'Receiving Log - {product_name} - {date_str}'
    
    # Build email body
    body_parts = []
    
    if additional_message:
        body_parts.append(additional_message)
        body_parts.append('<br><br><hr><br>')
    
    # Add log details
    body_parts.append(f'<h2>Receiving Log Details</h2>')
    body_parts.append(f'<p><strong>Log ID:</strong> #{log.id}</p>')
    body_parts.append(f'<p><strong>Date & Time:</strong> {log.datetime.strftime("%Y-%m-%d %H:%M") if log.datetime else "N/A"}</p>')
    body_parts.append('<br>')
    
    body_parts.append('<h3>Product Information</h3>')
    body_parts.append(f'<p><strong>Raw Product:</strong> {log.raw_product.name if log.raw_product else "N/A"}</p>')
    body_parts.append(f'<p><strong>Brand Name:</strong> {log.brand_name.name if log.brand_name else "N/A"}</p>')
    body_parts.append(f'<p><strong>Pack Size:</strong> {log.pack_size} {log.pack_size_unit}</p>')
    body_parts.append(f'<p><strong>Quantity Received:</strong> {log.quantity_received} units</p>')
    body_parts.append(f'<p><strong>Total:</strong> {log.quantity_received * log.pack_size:.2f} {log.pack_size_unit}</p>')
    
    # Add price information if available
    if log.price_paid:
        body_parts.append(f'<p><strong>Price Paid:</strong> ${log.price_paid:.2f} per {log.pack_size_unit}</p>')
    
    body_parts.append('<br>')
    
    body_parts.append('<h3>Quality & Status</h3>')
    body_parts.append(f'<p><strong>Temperature:</strong> {log.temperature:.1f}°F</p>')
    body_parts.append(f'<p><strong>Status:</strong> {log.hold_or_used.upper()}</p>')
    body_parts.append(f'<p><strong>Country of Origin:</strong> {log.country_of_origin}</p>')
    if log.returned:
        body_parts.append(f'<p><strong>Returned By:</strong> {log.returned}</p>')
    body_parts.append('<br>')
    
    body_parts.append('<h3>Source Information</h3>')
    body_parts.append(f'<p><strong>Seller:</strong> {log.seller.name if log.seller else "N/A"}</p>')
    body_parts.append(f'<p><strong>Grower/Distributor:</strong> {log.grower_or_distributor.name if log.grower_or_distributor else "N/A"}</p>')
    if log.grower_or_distributor and (log.grower_or_distributor.city or log.grower_or_distributor.state):
        location_parts = []
        if log.grower_or_distributor.city:
            location_parts.append(log.grower_or_distributor.city)
        if log.grower_or_distributor.state:
            location_parts.append(log.grower_or_distributor.state)
        body_parts.append(f'<p><strong>Location:</strong> {", ".join(location_parts)}</p>')
    body_parts.append('<br>')
    
    body_parts.append('<h3>Receiving Details</h3>')
    body_parts.append(f'<p><strong>Received By:</strong> {log.received_by}</p>')
    
    if log.images:
        body_parts.append('<br>')
        body_parts.append(f'<p><em>Note: This log includes {len(log.images)} image(s). Please view the log online to see the images.</em></p>')
        body_parts.append(f'<p><a href="{url_for("main.view_receiving_log", log_id=log.id, _external=True)}">View Full Log with Images</a></p>')
    
    body = ''.join(body_parts)
    
    # Send email
    sender = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('EMAIL_USER')
    
    msg = EmailMessage(
        subject=subject,
        body=body,
        to=[recipient],
        from_email=sender
    )
    msg.content_subtype = 'html'
    
    try:
        msg.send()
        flash(f'Receiving log emailed to {recipient}.', 'success')
    except Exception as e:
        flash(f'Failed to send email: {str(e)}', 'danger')
    
    return redirect(url_for('main.view_receiving_log', log_id=log_id))

# Generate and download receiving log as PDF
@main.route('/receiving_log/<int:log_id>/pdf')
@login_required
def download_receiving_log_pdf(log_id):

    """
    Generate a PDF document for a receiving log entry and send it as a downloadable file.
    """

    log = ReceivingLog.query.filter_by(id=log_id, company_id=current_user.company_id).first_or_404()
    
    # Generate PDF
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    
    # Company header
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Southern Produce Processors Inc.", ln=1, align="C")
    
    # Title
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Receiving Log", ln=1, align="C")
    
    # Date generated
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 8, f"Generated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}", ln=1, align="C")
    pdf.ln(5)
    
    # Log header info
    pdf.set_font("Arial", "B", 12)
    product_name = log.raw_product.name if log.raw_product else 'N/A'
    pdf.cell(0, 8, product_name, ln=1)
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 6, f"Received: {log.datetime.strftime('%B %d, %Y at %I:%M %p') if log.datetime else 'N/A'}", ln=1)
    pdf.cell(0, 6, f"Log ID: #{log.id}", ln=1)
    pdf.ln(5)
    
    # Column widths for the table
    col1_width = 70  # Label column
    col2_width = 110  # Value column
    table_width = col1_width + col2_width  # Total table width: 180mm
    row_height = 8
    
    # Helper function to add a table row
    def add_table_row(label, value, border=1):
        pdf.set_font("Arial", "B", 10)
        pdf.cell(col1_width, row_height, label, border=border, align="L")
        pdf.set_font("Arial", "", 10)
        pdf.cell(col2_width, row_height, value, border=border, align="L", ln=1)
    
    # Product Information Section
    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(200, 220, 255)  # Light blue background
    pdf.cell(table_width, row_height, "Product Information", border=1, ln=1, align="L", fill=True)
    
    add_table_row("Raw Product", product_name)
    add_table_row("Brand Name", log.brand_name.name if log.brand_name else 'N/A')
    add_table_row("Pack Size", f"{log.pack_size} {log.pack_size_unit}")
    add_table_row("Quantity Received", f"{log.quantity_received} units")
    add_table_row("Total Weight/Count", f"{log.quantity_received * log.pack_size:.2f} {log.pack_size_unit}")
    
    # Add price information if available
    if log.price_paid:
        add_table_row("Price Paid", f"${log.price_paid:.2f} per {log.pack_size_unit}")
    
    pdf.ln(3)
    
    # Quality & Status Section
    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(table_width, row_height, "Quality & Status", border=1, ln=1, align="L", fill=True)
    
    add_table_row("Temperature", f"{log.temperature:.1f} degrees F")
    add_table_row("Status", log.hold_or_used.upper())
    add_table_row("Country of Origin", log.country_of_origin)
    if log.returned:
        add_table_row("Returned By", log.returned)
    
    pdf.ln(3)
    
    # Source Information Section
    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(table_width, row_height, "Source Information", border=1, ln=1, align="L", fill=True)
    
    add_table_row("Seller", log.seller.name if log.seller else 'N/A')
    
    grower_name = log.grower_or_distributor.name if log.grower_or_distributor else 'N/A'
    add_table_row("Grower/Distributor", grower_name)
    
    if log.grower_or_distributor and (log.grower_or_distributor.city or log.grower_or_distributor.state):
        location_parts = []
        if log.grower_or_distributor.city:
            location_parts.append(log.grower_or_distributor.city)
        if log.grower_or_distributor.state:
            location_parts.append(log.grower_or_distributor.state)
        add_table_row("Location", ", ".join(location_parts))
    
    pdf.ln(3)
    
    # Receiving Details Section
    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(table_width, row_height, "Receiving Details", border=1, ln=1, align="L", fill=True)
    
    add_table_row("Received By", log.received_by)
    add_table_row("Date & Time", log.datetime.strftime('%Y-%m-%d %H:%M') if log.datetime else 'N/A')
    
    pdf.ln(5)
    
    # Images note
    if log.images:
        pdf.set_font("Arial", "I", 9)
        pdf.multi_cell(0, 5, f"Note: This log includes {len(log.images)} image(s). Images are not included in this PDF. Please view the log online to see the images.")
    
    # Generate PDF bytes
    pdf_bytes = bytes(pdf.output(dest='S'))
    
    # Create response
    resp = make_response(pdf_bytes)
    resp.headers['Content-Type'] = 'application/pdf'
    
    # Generate filename
    product_name_safe = ''.join(c for c in product_name if c.isalnum() or c in (' ', '-', '_')).strip()
    date_str = log.datetime.strftime('%Y%m%d') if log.datetime else 'unknown'
    filename = f"receiving_log_{product_name_safe}_{date_str}.pdf"
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return resp

# Brand Names - display and manage brand names
@main.route('/brand_names')
@login_required
def brand_names():

    """
    Display all brand names with optional search and pagination.
    """

    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 15
    use_pagination = request.args.get('paginate', '0').lower() in ('1', 'true', 'yes')

    base_query = BrandName.query.filter_by(company_id=current_user.company_id)
    
    if q:
        base_query = base_query.filter(BrandName.name.ilike(f'%{q}%'))
    
    if use_pagination:
        pagination = base_query.order_by(BrandName.name.asc()).paginate(page=page, per_page=per_page, error_out=False)
        brands = pagination.items
    else:
        brands = base_query.order_by(BrandName.name.asc()).all()
        pagination = None

    form = AddBrandName()
    delete_form = DeleteForm()

    return render_template(
        'brand_names.html',
        title='Brand Names',
        brands=brands,
        form=form,
        delete_form=delete_form,
        q=q,
        pagination=pagination,
        use_pagination=use_pagination
    )

@main.route('/add_brand_name', methods=['POST'])
@login_required
def add_brand_name():

    """
    Add a new brand name to the database after validating the form input.
    """

    form = AddBrandName()
    if form.validate_on_submit():
        brand = BrandName(name=form.name.data, company_id=current_user.company_id)
        db.session.add(brand)
        db.session.commit()
        flash(f'Brand name "{form.name.data}" has been added successfully!', 'success')
    else:
        flash('Invalid data submitted.', 'danger')
    return redirect(url_for('main.brand_names'))

@main.route('/delete_brand_name/<int:brand_id>', methods=['POST'])
@login_required
def delete_brand_name(brand_id):
    brand = BrandName.query.filter_by(id=brand_id, company_id=current_user.company_id).first()
    if not brand:
        flash('Brand name not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.brand_names'))
    
    # Check if brand is referenced by any receiving logs
    receiving_log_count = ReceivingLog.query.filter_by(brand_name_id=brand_id).count()
    if receiving_log_count > 0:
        flash(f'Cannot delete "{brand.name}" - it is used by {receiving_log_count} receiving log(s). Please remove those references first.', 'warning')
        return redirect(url_for('main.brand_names'))
    
    db.session.delete(brand)
    db.session.commit()
    flash(f'Brand name "{brand.name}" has been deleted.', 'success')
    return redirect(url_for('main.brand_names'))

# Sellers - display and manage sellers
@main.route('/sellers')
@login_required
def sellers():

    """
    Display all sellers with optional search and pagination.
    """

    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 15
    use_pagination = request.args.get('paginate', '0').lower() in ('1', 'true', 'yes')

    base_query = Seller.query.filter_by(company_id=current_user.company_id)
    
    if q:
        base_query = base_query.filter(Seller.name.ilike(f'%{q}%'))
    
    if use_pagination:
        pagination = base_query.order_by(Seller.name.asc()).paginate(page=page, per_page=per_page, error_out=False)
        sellers_list = pagination.items
    else:
        sellers_list = base_query.order_by(Seller.name.asc()).all()
        pagination = None

    form = AddSeller()
    delete_form = DeleteForm()

    return render_template(
        'sellers.html',
        title='Sellers',
        sellers=sellers_list,
        form=form,
        delete_form=delete_form,
        q=q,
        pagination=pagination,
        use_pagination=use_pagination
    )

@main.route('/add_seller', methods=['POST'])
@login_required
def add_seller():

    """
    Add a new seller to the database after validating the form input.
    """

    form = AddSeller()
    if form.validate_on_submit():
        seller = Seller(name=form.name.data, company_id=current_user.company_id)
        db.session.add(seller)
        db.session.commit()
        flash(f'Seller "{form.name.data}" has been added successfully!', 'success')
    else:
        flash('Invalid data submitted.', 'danger')
    return redirect(url_for('main.sellers'))

@main.route('/delete_seller/<int:seller_id>', methods=['POST'])
@login_required
def delete_seller(seller_id):

    """
    Delete a seller from the database after confirming it exists and belongs to the current user's company.
    """

    seller = Seller.query.filter_by(id=seller_id, company_id=current_user.company_id).first()
    if not seller:
        flash('Seller not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.sellers'))
    
    # Check if seller is referenced by any receiving logs
    receiving_log_count = ReceivingLog.query.filter_by(seller_id=seller_id).count()
    if receiving_log_count > 0:
        flash(f'Cannot delete "{seller.name}" - it is used by {receiving_log_count} receiving log(s). Please remove those references first.', 'warning')
        return redirect(url_for('main.sellers'))
    
    db.session.delete(seller)
    db.session.commit()
    flash(f'Seller "{seller.name}" has been deleted.', 'success')
    return redirect(url_for('main.sellers'))

# Growers/Distributors - display and manage growers/distributors
@main.route('/growers_distributors')
@login_required
def growers_distributors():

    """
    Display all growers/distributors with optional search and pagination.
    """

    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 15
    use_pagination = request.args.get('paginate', '0').lower() in ('1', 'true', 'yes')

    base_query = GrowerOrDistributor.query.filter_by(company_id=current_user.company_id)
    
    if q:
        base_query = base_query.filter(
            (GrowerOrDistributor.name.ilike(f'%{q}%')) |
            (GrowerOrDistributor.city.ilike(f'%{q}%')) |
            (GrowerOrDistributor.state.ilike(f'%{q}%'))
        )
    
    if use_pagination:
        pagination = base_query.order_by(GrowerOrDistributor.name.asc()).paginate(page=page, per_page=per_page, error_out=False)
        growers = pagination.items
    else:
        growers = base_query.order_by(GrowerOrDistributor.name.asc()).all()
        pagination = None

    form = AddGrowerOrDistributor()
    delete_form = DeleteForm()

    return render_template(
        'growers_distributors.html',
        title='Growers/Distributors',
        growers=growers,
        form=form,
        delete_form=delete_form,
        q=q,
        pagination=pagination,
        use_pagination=use_pagination
    )

@main.route('/add_grower_distributor', methods=['POST'])
@login_required
def add_grower_distributor():

    """
    Add a new grower/distributor to the database after validating the form input.
    """

    form = AddGrowerOrDistributor()
    if form.validate_on_submit():
        grower = GrowerOrDistributor(
            name=form.name.data,
            city=form.city.data,
            state=form.state.data,
            company_id=current_user.company_id
        )
        db.session.add(grower)
        db.session.commit()
        flash(f'Grower/Distributor "{form.name.data}" has been added successfully!', 'success')
    else:
        flash('Invalid data submitted.', 'danger')
    return redirect(url_for('main.growers_distributors'))

@main.route('/delete_grower_distributor/<int:grower_id>', methods=['POST'])
@login_required
def delete_grower_distributor(grower_id):

    """
    Delete a grower/distributor from the database after confirming it exists and belongs to the current user's company.
    """

    grower = GrowerOrDistributor.query.filter_by(id=grower_id, company_id=current_user.company_id).first()
    if not grower:
        flash('Grower/Distributor not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('main.growers_distributors'))
    
    # Check if grower is referenced by any receiving logs
    receiving_log_count = ReceivingLog.query.filter_by(grower_or_distributor_id=grower_id).count()
    if receiving_log_count > 0:
        flash(f'Cannot delete "{grower.name}" - it is used by {receiving_log_count} receiving log(s). Please remove those references first.', 'warning')
        return redirect(url_for('main.growers_distributors'))
    
    db.session.delete(grower)
    db.session.commit()
    flash(f'Grower/Distributor "{grower.name}" has been deleted.', 'success')
    return redirect(url_for('main.growers_distributors'))

@main.route('/receiving_images/<path:filename>')
@optional_api_key_or_login
def get_receiving_image(filename):
    """
    Serve a receiving image file, with company-scoped access control.
    Only users/API keys from the company that owns the image can access it.
    """
    from werkzeug.utils import secure_filename
    import os

    # Prevent directory traversal
    safe_filename = secure_filename(filename)
    if safe_filename != filename:
        from flask import abort
        abort(400, 'Invalid filename')

    # Get company ID
    company_id = g.company_id if hasattr(g, 'company_id') else current_user.company_id

    # Look up the image to verify it belongs to this company
    image = ReceivingImage.query.filter_by(filename=filename, company_id=company_id).first()
    if not image:
        from flask import abort
        abort(403, 'Access denied')

    return send_from_directory(current_app.config['RECEIVING_IMAGES_DIR'], filename)