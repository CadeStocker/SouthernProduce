# Copyright Cade Stocker 2026
"""Cross-domain analytics dashboard.

The page renders one section per entry in ``services.analytics_domains``. Each
section is filled by its own JSON endpoint below so a slow or empty domain never
blocks the rest of the page.

To add a domain panel: add the domain to ``analytics_domains``, write its report
queries in ``analytics_reports``, then add one endpoint here that returns
``{'summary': {...}, 'rows': [...]}``. The template's ``loadPanel`` helper needs
no changes as long as the shape matches.
"""

from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app import db
from app.models.anomalies import Anomaly
from app.services import analytics_reports
from app.services.analytics_domains import DOMAINS, DOMAIN_KEYS, label_for_domain

dashboard = Blueprint('dashboard', __name__)

DEFAULT_DAYS = 30


def _requested_range():
    """Resolve the date range for a request.

    Explicit ``start_date``/``end_date`` win; otherwise fall back to the last
    ``days`` days. Malformed dates fall back to the default window rather than
    500-ing, since these come straight from query strings.
    """
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')

    if start_str and end_str:
        try:
            start = datetime.fromisoformat(start_str).date()
            end = datetime.fromisoformat(end_str).date()
            if start <= end:
                return start, end
        except ValueError:
            pass

    days = request.args.get('days', DEFAULT_DAYS, type=int) or DEFAULT_DAYS
    end = datetime.utcnow().date()
    return end - timedelta(days=days), end


def _iso(value):
    return value.isoformat() if value is not None else None


def _panel(summary, rows):
    """The shape every domain endpoint returns."""
    return jsonify({'summary': summary, 'rows': rows})


def _names(model, ids):
    """Map id -> name for a set of ids, skipping Nones."""
    ids = [i for i in ids if i]
    if not ids:
        return {}
    return {row.id: row.name for row in model.query.filter(model.id.in_(ids)).all()}


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@dashboard.route('/dashboard')
@login_required
def analytics_dashboard():
    """Cross-domain dashboard: KPIs and panels for every business area."""
    company_id = current_user.company_id
    start_date, end_date = _requested_range()

    summary = analytics_reports.get_cross_domain_summary(company_id, start_date, end_date)

    previous_start, previous_end = analytics_reports.previous_period(start_date, end_date)
    previous = analytics_reports.get_cross_domain_summary(company_id, previous_start, previous_end)
    deltas = {
        domain: analytics_reports.compare_periods(summary[domain], previous[domain])
        for domain in summary
    }

    return render_template(
        'dashboard.html',
        domains=DOMAINS,
        summary=summary,
        deltas=deltas,
        data_health=analytics_reports.get_domain_data_health(company_id),
        anomaly_summary=_anomaly_summary(company_id),
        today_summary=analytics_reports.get_daily_summary(company_id, datetime.utcnow().date()),
        start_date=start_date,
        end_date=end_date,
        previous_start=previous_start,
        previous_end=previous_end,
    )


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------

@dashboard.route('/api/dashboard/sales')
@login_required
def api_sales():
    """Daily revenue trend plus the period's sales headline numbers."""
    company_id = current_user.company_id
    start_date, end_date = _requested_range()

    return _panel(
        analytics_reports.get_sales_summary(company_id, start_date, end_date),
        [
            {'date': _iso(row['date']), 'revenue': row['revenue'], 'quantity': row['quantity']}
            for row in analytics_reports.get_daily_revenue_trend(company_id, start_date, end_date)
        ],
    )


@dashboard.route('/api/dashboard/revenue_trend')
@login_required
def api_revenue_trend():
    """Daily revenue trend as a bare list (kept for existing chart callers)."""
    company_id = current_user.company_id
    start_date, end_date = _requested_range()

    return jsonify([
        {'date': _iso(row['date']), 'revenue': float(row['revenue']), 'quantity': float(row['quantity'])}
        for row in analytics_reports.get_daily_revenue_trend(company_id, start_date, end_date)
    ])


@dashboard.route('/api/dashboard/top_customers')
@login_required
def api_top_customers():
    """Customers ranked by revenue for the period."""
    from app.models import Customer

    company_id = current_user.company_id
    start_date, end_date = _requested_range()
    limit = request.args.get('limit', 10, type=int)

    rows = analytics_reports.get_top_customers_by_revenue(company_id, start_date, end_date, limit)
    names = _names(Customer, [row['customer_id'] for row in rows])

    return jsonify([
        {
            'customer_id': row['customer_id'],
            'customer_name': names.get(row['customer_id'], 'Unknown'),
            'revenue': float(row['revenue']),
            'quantity': float(row['quantity']),
        }
        for row in rows
    ])


@dashboard.route('/api/dashboard/top_items')
@login_required
def api_top_items():
    """Items ranked by units sold for the period."""
    from app.models import Item

    company_id = current_user.company_id
    start_date, end_date = _requested_range()
    limit = request.args.get('limit', 10, type=int)

    rows = analytics_reports.get_top_items_by_sales_volume(company_id, start_date, end_date, limit)
    names = _names(Item, [row['item_id'] for row in rows])

    return jsonify([
        {
            'item_id': row['item_id'],
            'item_name': names.get(row['item_id'], 'Unknown'),
            'quantity': float(row['quantity']),
            'revenue': float(row['revenue']),
        }
        for row in rows
    ])


# ---------------------------------------------------------------------------
# Pricing & margin
# ---------------------------------------------------------------------------

@dashboard.route('/api/dashboard/pricing')
@login_required
def api_pricing():
    """Thinnest-margin items: current price against latest landed cost."""
    from app.models import Item

    company_id = current_user.company_id
    start_date, end_date = _requested_range()
    limit = request.args.get('limit', 10, type=int)

    rows = analytics_reports.get_item_margin_snapshot(company_id, as_of=end_date, limit=limit)
    names = _names(Item, [row['item_id'] for row in rows])

    return _panel(
        analytics_reports.get_margin_summary(company_id, start_date, end_date),
        [
            {
                'item_id': row['item_id'],
                'item_name': names.get(row['item_id'], 'Unknown'),
                'cost': row['cost'],
                'cost_date': _iso(row['cost_date']),
                'price': row['price'],
                'margin': row['margin'],
                'margin_pct': row['margin_pct'],
            }
            for row in rows
        ],
    )


@dashboard.route('/api/dashboard/price_dispersion')
@login_required
def api_price_dispersion():
    """Items whose quoted prices vary most across customers."""
    from app.models import Item

    company_id = current_user.company_id
    start_date, end_date = _requested_range()
    limit = request.args.get('limit', 10, type=int)

    rows = analytics_reports.get_price_dispersion(company_id, start_date, end_date, limit)
    names = _names(Item, [row['item_id'] for row in rows])

    return jsonify([
        {**row, 'item_name': names.get(row['item_id'], 'Unknown')}
        for row in rows
    ])


@dashboard.route('/api/dashboard/cost_trend')
@login_required
def api_cost_trend():
    """Average landed item cost per day."""
    company_id = current_user.company_id
    start_date, end_date = _requested_range()

    return jsonify([
        {
            'date': _iso(row['date']),
            'avg_cost': row['avg_cost'],
            'total_cost': row['total_cost'],
            'item_count': row['item_count'],
        }
        for row in analytics_reports.get_item_cost_trend(company_id, start_date, end_date)
    ])


# ---------------------------------------------------------------------------
# Labor & efficiency
# ---------------------------------------------------------------------------

@dashboard.route('/api/dashboard/efficiency')
@login_required
def api_efficiency():
    """Man-hours per case and payroll share, per day and for the period."""
    company_id = current_user.company_id
    start_date, end_date = _requested_range()

    return _panel(
        analytics_reports.get_efficiency_summary(company_id, start_date, end_date),
        [
            {
                'date': _iso(row['date']),
                'cases': row['cases'],
                'labor_hours': row['labor_hours'],
                'labor_cost': row['labor_cost'],
                'sales': row['sales'],
                'man_hours_per_case': row['man_hours_per_case'],
                'cost_per_case': row['cost_per_case'],
                'cases_per_man_hour': row['cases_per_man_hour'],
                'labor_ratio': row['labor_ratio'],
            }
            for row in analytics_reports.get_efficiency_trend(company_id, start_date, end_date)
        ],
    )


# ---------------------------------------------------------------------------
# Receiving & suppliers
# ---------------------------------------------------------------------------

@dashboard.route('/api/dashboard/receiving')
@login_required
def api_receiving():
    """Inbound spend per day plus the period's receiving headline numbers."""
    company_id = current_user.company_id
    start_date, end_date = _requested_range()

    return _panel(
        analytics_reports.get_receiving_summary(company_id, start_date, end_date),
        [
            {
                'date': _iso(row['date']),
                'total_cost': row['total_cost'],
                'quantity': row['quantity'],
                'cost_per_unit': row['cost_per_unit'],
            }
            for row in analytics_reports.get_receiving_cost_trend(company_id, start_date, end_date)
        ],
    )


@dashboard.route('/api/dashboard/receiving_costs')
@login_required
def api_receiving_costs():
    """Inbound spend per day as a bare list (kept for existing table callers)."""
    company_id = current_user.company_id
    start_date, end_date = _requested_range()

    return jsonify([
        {
            'date': _iso(row['date']),
            'total_cost': float(row['total_cost']),
            'quantity': float(row['quantity']),
            'cost_per_unit': row['cost_per_unit'],
        }
        for row in analytics_reports.get_receiving_cost_trend(company_id, start_date, end_date)
    ])


@dashboard.route('/api/dashboard/suppliers')
@login_required
def api_suppliers():
    """Suppliers ranked by inbound spend."""
    from app.models import GrowerOrDistributor

    company_id = current_user.company_id
    start_date, end_date = _requested_range()
    limit = request.args.get('limit', 10, type=int)

    rows = analytics_reports.get_top_suppliers_by_spend(company_id, start_date, end_date, limit)
    names = _names(GrowerOrDistributor, [row['supplier_id'] for row in rows])

    return jsonify([
        {**row, 'supplier_name': names.get(row['supplier_id'], 'Unknown')}
        for row in rows
    ])


@dashboard.route('/api/dashboard/raw_product_costs')
@login_required
def api_raw_product_costs():
    """Cost per unit received, per raw product."""
    from app.models import RawProduct

    company_id = current_user.company_id
    start_date, end_date = _requested_range()
    limit = request.args.get('limit', 10, type=int)

    rows = analytics_reports.get_raw_product_cost_per_unit(company_id, start_date, end_date, limit)
    names = _names(RawProduct, [row['raw_product_id'] for row in rows])

    return jsonify([
        {**row, 'raw_product_name': names.get(row['raw_product_id'], 'Unknown')}
        for row in rows
    ])


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@dashboard.route('/api/dashboard/inventory')
@login_required
def api_inventory():
    """Biggest count-to-count movements plus inventory headline numbers."""
    from app.models import Item

    company_id = current_user.company_id
    start_date, end_date = _requested_range()
    limit = request.args.get('limit', 10, type=int)

    rows = analytics_reports.get_inventory_movement(company_id, start_date, end_date, limit)
    names = _names(Item, [row['item_id'] for row in rows])

    return _panel(
        analytics_reports.get_inventory_summary(company_id, as_of=end_date),
        [
            {
                'item_id': row['item_id'],
                'item_name': names.get(row['item_id'], 'Unknown'),
                'previous_quantity': row['previous_quantity'],
                'previous_date': _iso(row['previous_date']),
                'current_quantity': row['current_quantity'],
                'current_date': _iso(row['current_date']),
                'change': row['change'],
                'change_pct': row['change_pct'],
            }
            for row in rows
        ],
    )


@dashboard.route('/api/dashboard/inventory_levels')
@login_required
def api_inventory_levels():
    """Latest counted quantity per item."""
    from app.models import Item

    company_id = current_user.company_id
    _, end_date = _requested_range()
    limit = request.args.get('limit', 20, type=int)

    rows = analytics_reports.get_inventory_levels(company_id, as_of=end_date, limit=limit)
    names = _names(Item, [row['item_id'] for row in rows])

    return jsonify([
        {
            'item_id': row['item_id'],
            'item_name': names.get(row['item_id'], 'Unknown'),
            'quantity': row['quantity'],
            'count_date': _iso(row['count_date']),
        }
        for row in rows
    ])


@dashboard.route('/api/dashboard/stale_inventory')
@login_required
def api_stale_inventory():
    """Items whose most recent count is older than ``stale_days``."""
    from app.models import Item

    company_id = current_user.company_id
    _, end_date = _requested_range()
    stale_days = request.args.get('stale_days', 30, type=int)
    limit = request.args.get('limit', 20, type=int)

    rows = analytics_reports.get_stale_inventory(company_id, end_date, stale_days, limit)
    names = _names(Item, [row['item_id'] for row in rows])

    return jsonify([
        {
            'item_id': row['item_id'],
            'item_name': names.get(row['item_id'], 'Unknown'),
            'quantity': row['quantity'],
            'count_date': _iso(row['count_date']),
            'days_since_count': row['days_since_count'],
        }
        for row in rows
    ])


# ---------------------------------------------------------------------------
# Anomalies, across domains
# ---------------------------------------------------------------------------

def _anomaly_summary(company_id):
    """Open anomaly counts and dollar impact per domain, for the overview row.

    Strictly company-scoped. The migration that added ``company_id`` backfills
    it from each anomaly's entity, so pre-existing findings still appear; any
    whose entity no longer exists stay unattributed and are not shown here,
    which is the safe direction — never another tenant's data.
    """
    rows = db.session.query(
        Anomaly.domain,
        Anomaly.severity,
        db.func.count(Anomaly.id),
        db.func.sum(Anomaly.dollar_impact),
    ).filter(
        Anomaly.company_id == company_id,
        Anomaly.status == 'open',
    ).group_by(Anomaly.domain, Anomaly.severity).all()

    summary = {
        key: {'label': label_for_domain(key), 'open': 0, 'high': 0, 'medium': 0,
              'low': 0, 'dollar_impact': 0.0}
        for key in DOMAIN_KEYS + ('other',)
    }

    for domain, severity, count, impact in rows:
        bucket = summary.get(domain or 'other', summary['other'])
        bucket['open'] += count or 0
        if severity in ('high', 'medium', 'low'):
            bucket[severity] += count or 0
        bucket['dollar_impact'] += impact or 0.0

    return summary


@dashboard.route('/api/dashboard/anomalies')
@login_required
def api_anomalies():
    """Recent open anomalies, optionally filtered to one domain."""
    company_id = current_user.company_id
    domain = request.args.get('domain')
    limit = request.args.get('limit', 10, type=int)

    query = Anomaly.query.filter(
        Anomaly.company_id == company_id,
        Anomaly.status == 'open',
    )
    if domain:
        query = query.filter(Anomaly.domain == domain)

    # coalesce rather than NULLS LAST: portable across the SQLite/Postgres split.
    anomalies = query.order_by(
        db.func.coalesce(Anomaly.dollar_impact, 0.0).desc(), Anomaly.detected_at.desc()
    ).limit(limit).all()

    return jsonify([
        {
            'id': anomaly.id,
            'domain': anomaly.domain,
            'domain_label': label_for_domain(anomaly.domain),
            'entity_type': anomaly.entity_type,
            'entity_id': anomaly.entity_id,
            'metric': anomaly.metric,
            'severity': anomaly.severity,
            'dollar_impact': anomaly.dollar_impact,
            'explanation': anomaly.explanation,
            'detected_at': anomaly.detected_at.isoformat() if anomaly.detected_at else None,
        }
        for anomaly in anomalies
    ])
