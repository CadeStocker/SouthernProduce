# Copyright Cade Stocker 2026
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.blueprints._blueprint import main
from app.models import (
    DailyLog, PayGroups, WeeklyLaborEntry, FilmUsage, SalesRecord, Customer,
)
from app.models.core import LABOR_APP_DESIGNATION_NAMES
from app import db
from datetime import date, datetime, time, timedelta

# Overtime is paid at time-and-a-half, so effective hours are weighted to match
# the LaborApp's AnalysisView.LaborTotals.adjustedHours calculation.
OVERTIME_MULTIPLIER = 1.5

MONTH_ABBREVIATIONS = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

DASHBOARD_TABS = ('overview', 'labor', 'sales', 'film')

# Preset ranges offered in the dashboard toolbar, mirroring DateRange.presets in
# the LaborApp. Each entry maps to the number of days back from today, or None
# for a special case handled in _resolve_date_range.
RANGE_PRESETS = (
    ('today', 'Today'),
    ('7d', '7D'),
    ('30d', '30D'),
    ('90d', '90D'),
    ('ytd', 'YTD'),
    ('all', 'All'),
)


def _safe_divide(numerator, denominator):
    """Divide, returning 0 when the denominator is zero or missing."""
    return numerator / denominator if denominator else 0


def _pretty_date(value):
    """Format a date as e.g. 'Jul 5, 2026' without platform-specific strftime flags."""
    return f"{MONTH_ABBREVIATIONS[value.month - 1]} {value.day}, {value.year}"


def _format_metric(value, fmt):
    """Render a metric value the same way MetricFormat does in the LaborApp."""
    if fmt == 'currency':
        return f"${value:,.0f}"
    if fmt == 'integer':
        return f"{value:,.0f}"
    if fmt == 'decimal':
        return f"{value:,.1f}"
    if fmt == 'percent':
        return f"{value:.1f}%"
    if fmt == 'ratio':
        return f"{value:.3f}"
    return f"{value}"


def _metric(label, value, fmt, caption=None):
    """Build a plain metric tile."""
    return {
        'label': label,
        'display': _format_metric(value, fmt),
        'caption': caption,
    }


def _delta_metric(label, value, previous, fmt, higher_is_better):
    """Build a metric tile with a percentage change indicator vs. the prior period."""
    change = None
    improving = None
    if previous:
        change = (value - previous) / abs(previous) * 100
        improving = change >= 0 if higher_is_better else change <= 0

    return {
        'label': label,
        'display': _format_metric(value, fmt),
        'change': abs(change) if change is not None else None,
        'change_up': change >= 0 if change is not None else None,
        'improving': improving,
    }


def _resolve_date_range():
    """Resolve the requested date range from query args.

    Returns (range_key, start, end, label) where start is None for "all time".
    """
    today = date.today()
    range_key = request.args.get('range', '30d')

    def parse(param):
        raw = request.args.get(param, '').strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            flash(f'Invalid {param.replace("_", " ")}. Use YYYY-MM-DD.', 'warning')
            return None

    if range_key == 'custom':
        start = parse('start_date')
        end = parse('end_date') or today
        if start and start > end:
            flash('Start date is after end date — dates were swapped.', 'warning')
            start, end = end, start
    elif range_key == 'all':
        start, end = None, today
    elif range_key == 'ytd':
        start, end = date(today.year, 1, 1), today
    elif range_key == 'today':
        start, end = today, today
    else:
        days = {'7d': 7, '30d': 30, '90d': 90}.get(range_key)
        if days is None:
            range_key, days = '30d', 30
        start, end = today - timedelta(days=days), today

    if start is None:
        label = 'All Time'
    elif start == end:
        label = _pretty_date(start)
    else:
        label = f"{_pretty_date(start)} – {_pretty_date(end)}"

    return range_key, start, end, label


def _labor_totals(logs):
    """Aggregate daily labor logs, mirroring LaborTotals in the LaborApp."""
    cases = sum(l.items for l in logs)
    sales = sum(l.sales for l in logs)
    hours = sum(l.labor_hours for l in logs)
    overtime = sum(l.overtime_hours for l in logs)
    payroll = sum(l.payroll_cost for l in logs)
    adjusted_hours = hours + overtime * OVERTIME_MULTIPLIER

    return {
        'cases': cases,
        'sales': sales,
        'hours': hours,
        'overtime': overtime,
        'payroll': payroll,
        'days': len(logs),
        'adjusted_hours': adjusted_hours,
        'labor_ratio': _safe_divide(adjusted_hours, cases),
        'labor_percent_of_sales': _safe_divide(payroll, sales) * 100,
        'man_hour_cost': _safe_divide(payroll, adjusted_hours),
        'revenue_per_case': _safe_divide(sales, cases),
        'cases_per_hour': _safe_divide(cases, adjusted_hours),
    }


def _daily_labor_ratio(log):
    """Per-day labor ratio using overtime-weighted hours."""
    return _safe_divide(log.labor_hours + log.overtime_hours * OVERTIME_MULTIPLIER, log.items)


def _aggregate_sales(records, key_fn, name_fn):
    """Group sales records by a key, returning name/amount/quantity rows by revenue."""
    totals = {}
    for record in records:
        key = key_fn(record)
        amount, quantity = totals.get(key, (0.0, 0.0))
        totals[key] = (amount + record.total_price, quantity + record.quantity_sold)

    rows = [
        {'name': name_fn(key), 'amount': amount, 'quantity': quantity}
        for key, (amount, quantity) in totals.items()
    ]
    rows.sort(key=lambda row: row['amount'], reverse=True)

    grand_total = sum(row['amount'] for row in rows)
    for row in rows:
        row['percent'] = _safe_divide(row['amount'], grand_total) * 100
    return rows


@main.route('/labor/dashboard')
@login_required
def labor_dashboard():
    """Analysis dashboard mirroring the LaborApp's AnalysisView.

    Covers overview/labor/sales/film sections over a selectable date range,
    with each metric computed from the data the LaborApp submits via the API.
    """
    company_id = current_user.company_id
    range_key, start, end, range_label = _resolve_date_range()

    active_tab = request.args.get('tab', 'overview')
    if active_tab not in DASHBOARD_TABS:
        active_tab = 'overview'

    # Previous period of equal length, for the overview deltas.
    prev_start = prev_end = None
    if start is not None:
        span = end - start
        prev_start, prev_end = start - span - timedelta(days=1), start - timedelta(days=1)

    # ---- Daily labor logs ----
    log_query = DailyLog.query.filter_by(company_id=company_id)
    if start is not None:
        log_query = log_query.filter(DailyLog.date >= start, DailyLog.date <= end)
    logs = log_query.order_by(DailyLog.date).all()

    previous_logs = []
    if prev_start is not None:
        previous_logs = DailyLog.query.filter_by(company_id=company_id).filter(
            DailyLog.date >= prev_start, DailyLog.date <= prev_end
        ).order_by(DailyLog.date).all()

    totals = _labor_totals(logs)
    previous_totals = _labor_totals(previous_logs)

    # ---- Sales records ----
    sales_query = SalesRecord.query.filter_by(company_id=company_id)
    if start is not None:
        sales_query = sales_query.filter(
            SalesRecord.sale_date >= datetime.combine(start, time.min),
            SalesRecord.sale_date <= datetime.combine(end, time.max),
        )
    sales_records = sales_query.order_by(SalesRecord.sale_date).all()

    customer_names = {
        c.id: c.name for c in Customer.query.filter_by(company_id=company_id).all()
    }

    def designation_name(designation_id):
        return LABOR_APP_DESIGNATION_NAMES.get(designation_id, 'Other')

    def customer_name(customer_id):
        return customer_names.get(customer_id, 'Unassigned')

    by_designation = _aggregate_sales(
        sales_records, lambda r: r.item_designation_id, designation_name
    )
    by_customer = _aggregate_sales(
        sales_records, lambda r: r.customer_id, customer_name
    )[:8]

    sales_total = sum(r.total_price for r in sales_records)
    sales_units = sum(r.quantity_sold for r in sales_records)

    # ---- Film usage (not date-range filtered — compared year over year) ----
    film_records = FilmUsage.query.filter_by(company_id=company_id).order_by(
        FilmUsage.year, FilmUsage.month
    ).all()
    film_years = sorted({r.year for r in film_records})
    film_series = [
        {
            'year': str(year),
            'data': [
                next(
                    (r.number_of_cases for r in film_records if r.year == year and r.month == month),
                    None,
                )
                for month in range(1, 13)
            ],
        }
        for year in film_years
    ]
    film_year_totals = [
        _metric(str(year), sum(r.number_of_cases for r in film_records if r.year == year), 'integer')
        for year in film_years
    ]

    # ---- Metric tiles ----
    overview_metrics = [
        _delta_metric('Sales', totals['sales'], previous_totals['sales'], 'currency', True),
        _delta_metric('Cases', totals['cases'], previous_totals['cases'], 'integer', True),
        _delta_metric('Payroll', totals['payroll'], previous_totals['payroll'], 'currency', False),
        _delta_metric('Labor % of Sales', totals['labor_percent_of_sales'],
                      previous_totals['labor_percent_of_sales'], 'percent', False),
        _delta_metric('Labor Ratio', totals['labor_ratio'], previous_totals['labor_ratio'], 'ratio', False),
        _delta_metric('$/Case', totals['revenue_per_case'], previous_totals['revenue_per_case'], 'currency', True),
    ]

    labor_metrics = [
        _metric('Regular Hours', totals['hours'], 'decimal'),
        _metric('Overtime Hours', totals['overtime'], 'decimal'),
        _metric('Payroll', totals['payroll'], 'currency'),
        _metric('Cost / Man-Hour', totals['man_hour_cost'], 'currency'),
        _metric('Cases / Hour', totals['cases_per_hour'], 'ratio'),
        _metric('Days Tracked', totals['days'], 'integer'),
    ]

    sales_metrics = [
        _metric('Recorded Sales', sales_total, 'currency'),
        _metric('Units Sold', sales_units, 'integer'),
        _metric('Avg Sale', _safe_divide(sales_total, len(sales_records)), 'currency'),
    ]

    # ---- Chart series ----
    log_labels = [l.date.strftime('%Y-%m-%d') for l in logs]
    daily_ratios = [round(_daily_labor_ratio(l), 4) for l in logs]
    average_ratio = _safe_divide(sum(daily_ratios), len(daily_ratios))

    charts = {
        'labels': log_labels,
        'sales': [round(l.sales, 2) for l in logs],
        'payroll': [round(l.payroll_cost, 2) for l in logs],
        'labor_ratio': daily_ratios,
        'average_ratio': round(average_ratio, 4),
        'average_ratio_line': [round(average_ratio, 4)] * len(log_labels),
        'regular_hours': [round(l.labor_hours, 2) for l in logs],
        'overtime_hours': [round(l.overtime_hours, 2) for l in logs],
        'designation_labels': [row['name'] for row in by_designation],
        'designation_amounts': [round(row['amount'], 2) for row in by_designation],
        'customer_labels': [row['name'] for row in by_customer],
        'customer_amounts': [round(row['amount'], 2) for row in by_customer],
        'film_months': MONTH_ABBREVIATIONS,
        'film_series': film_series,
    }

    return render_template(
        'labor_dashboard.html',
        active_tab=active_tab,
        range_key=range_key,
        range_label=range_label,
        range_presets=RANGE_PRESETS,
        start_date=start.isoformat() if start else '',
        end_date=end.isoformat(),
        has_previous_period=start is not None,
        previous_days=previous_totals['days'],
        totals=totals,
        overview_metrics=overview_metrics,
        labor_metrics=labor_metrics,
        sales_metrics=sales_metrics,
        by_designation=by_designation,
        by_customer=by_customer,
        film_year_totals=film_year_totals,
        has_film=bool(film_records),
        charts=charts,
    )


@main.route('/labor/daily_logs')
@login_required
def labor_daily_logs():
    """View daily labor logs for the company."""
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    query = DailyLog.query.filter_by(company_id=current_user.company_id)

    if start_date:
        try:
            query = query.filter(DailyLog.date >= date.fromisoformat(start_date))
        except ValueError:
            flash('Invalid start date format. Use YYYY-MM-DD.', 'warning')

    if end_date:
        try:
            query = query.filter(DailyLog.date <= date.fromisoformat(end_date))
        except ValueError:
            flash('Invalid end date format. Use YYYY-MM-DD.', 'warning')

    logs = query.order_by(DailyLog.date.desc(), DailyLog.id.desc()).all()

    return render_template(
        'labor_daily_logs.html',
        logs=logs,
        start_date=start_date,
        end_date=end_date,
    )


@main.route('/labor/daily_logs/<int:log_id>/delete', methods=['POST'])
@login_required
def delete_labor_daily_log(log_id):
    """Delete a daily log entry."""
    log = DailyLog.query.filter_by(id=log_id, company_id=current_user.company_id).first_or_404()
    db.session.delete(log)
    db.session.commit()
    flash('Daily log deleted.', 'success')
    return redirect(url_for('main.labor_daily_logs'))


@main.route('/labor/pay_groups')
@login_required
def labor_pay_groups():
    """View and manage pay groups for the company."""
    pay_groups = PayGroups.query.filter_by(
        company_id=current_user.company_id
    ).order_by(PayGroups.name).all()
    return render_template('labor_pay_groups.html', pay_groups=pay_groups)


@main.route('/labor/pay_groups/create', methods=['POST'])
@login_required
def create_labor_pay_group():
    """Create a new pay group."""
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip() or None

    if not name:
        flash('Pay group name is required.', 'danger')
        return redirect(url_for('main.labor_pay_groups'))

    existing = PayGroups.query.filter_by(
        company_id=current_user.company_id, name=name
    ).first()
    if existing:
        flash(f'A pay group named "{name}" already exists.', 'warning')
        return redirect(url_for('main.labor_pay_groups'))

    pay_group = PayGroups(
        company_id=current_user.company_id,
        name=name,
        description=description,
    )
    db.session.add(pay_group)
    db.session.commit()
    flash(f'Pay group "{name}" created.', 'success')
    return redirect(url_for('main.labor_pay_groups'))


@main.route('/labor/pay_groups/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_labor_pay_group(group_id):
    """Delete a pay group."""
    pay_group = PayGroups.query.filter_by(
        id=group_id, company_id=current_user.company_id
    ).first_or_404()

    # Check if any weekly entries reference this pay group
    entry_count = WeeklyLaborEntry.query.filter_by(pay_group_id=group_id).count()
    if entry_count > 0:
        flash(
            f'Cannot delete "{pay_group.name}" — it has {entry_count} weekly labor '
            f'entr{"y" if entry_count == 1 else "ies"} associated with it.',
            'danger'
        )
        return redirect(url_for('main.labor_pay_groups'))

    db.session.delete(pay_group)
    db.session.commit()
    flash(f'Pay group "{pay_group.name}" deleted.', 'success')
    return redirect(url_for('main.labor_pay_groups'))


@main.route('/labor/weekly_entries')
@login_required
def labor_weekly_entries():
    """View weekly labor entries for the company."""
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    pay_group_id = request.args.get('pay_group_id', type=int)

    query = WeeklyLaborEntry.query.filter_by(company_id=current_user.company_id)

    if pay_group_id:
        query = query.filter_by(pay_group_id=pay_group_id)

    if start_date:
        try:
            query = query.filter(WeeklyLaborEntry.week_start_date >= date.fromisoformat(start_date))
        except ValueError:
            flash('Invalid start date format. Use YYYY-MM-DD.', 'warning')

    if end_date:
        try:
            query = query.filter(WeeklyLaborEntry.week_start_date <= date.fromisoformat(end_date))
        except ValueError:
            flash('Invalid end date format. Use YYYY-MM-DD.', 'warning')

    entries = query.order_by(
        WeeklyLaborEntry.week_start_date.desc(), WeeklyLaborEntry.id.desc()
    ).all()

    pay_groups = PayGroups.query.filter_by(
        company_id=current_user.company_id
    ).order_by(PayGroups.name).all()

    pay_group_map = {pg.id: pg.name for pg in pay_groups}

    return render_template(
        'labor_weekly_entries.html',
        entries=entries,
        pay_groups=pay_groups,
        pay_group_map=pay_group_map,
        start_date=start_date,
        end_date=end_date,
        selected_pay_group_id=pay_group_id,
    )


@main.route('/labor/weekly_entries/<int:entry_id>/delete', methods=['POST'])
@login_required
def delete_labor_weekly_entry(entry_id):
    """Delete a weekly labor entry."""
    entry = WeeklyLaborEntry.query.filter_by(
        id=entry_id, company_id=current_user.company_id
    ).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    flash('Weekly labor entry deleted.', 'success')
    return redirect(url_for('main.labor_weekly_entries'))


@main.route('/labor/film_usage')
@login_required
def labor_film_usage():
    """View film usage records for the company."""
    year_filter = request.args.get('year', type=int)

    query = FilmUsage.query.filter_by(company_id=current_user.company_id)
    if year_filter:
        query = query.filter_by(year=year_filter)

    records = query.order_by(FilmUsage.year.desc(), FilmUsage.month.desc()).all()

    # Build list of distinct years for the filter dropdown
    all_records = FilmUsage.query.filter_by(company_id=current_user.company_id).all()
    years = sorted({r.year for r in all_records}, reverse=True)

    return render_template(
        'labor_film_usage.html',
        records=records,
        years=years,
        year_filter=year_filter,
    )

@main.route('/labor/film_usage/<int:record_id>/delete', methods=['POST'])
@login_required
def delete_labor_film_usage(record_id):
    """Delete a film usage record."""
    record = FilmUsage.query.filter_by(
        id=record_id, company_id=current_user.company_id
    ).first_or_404()
    db.session.delete(record)
    db.session.commit()
    flash('Film usage record deleted.', 'success')
    return redirect(url_for('main.labor_film_usage'))
