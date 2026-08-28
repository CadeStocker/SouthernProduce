# Copyright Cade Stocker 2026

"""Read-side queries for the cross-domain analytics layer.

Organized by business domain (see ``analytics_domains``):

* Shared helpers
* Cross-domain (data health, period comparison)
* Sales & customers
* Pricing & margin
* Labor & efficiency
* Receiving & suppliers
* Inventory

Most functions aggregate AnalyticsFact rows directly instead of joining the
underlying operational tables. A few pricing/inventory questions have no fact
grain yet (price spread across customers, stale-count detection) and read the
operational table; those are marked in their docstrings so it's clear which
queries would move to facts if the grain is added later.

Every function is company-scoped and takes an optional inclusive date range.
Rows come back pre-ordered so callers can render without re-sorting.
"""

from datetime import timedelta

from app import db
from app.models.analytics import AnalyticsFact
from app.services.analytics_domains import DOMAINS


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _date_filters(query, start_date=None, end_date=None):
    if start_date is not None:
        query = query.filter(AnalyticsFact.date >= start_date)
    if end_date is not None:
        query = query.filter(AnalyticsFact.date <= end_date)
    return query


def _facts(company_id, fact_type, start_date=None, end_date=None, source_table=None):
    """Base filtered query over one fact type, for callers to aggregate."""
    query = AnalyticsFact.query.filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == fact_type,
    )
    if source_table is not None:
        query = query.filter(AnalyticsFact.source_table == source_table)
    return _date_filters(query, start_date, end_date)


def _aggregate(company_id, fact_type, columns, start_date=None, end_date=None,
               source_table=None, extra_filters=()):
    """Grouped aggregate over one fact type. ``columns`` are SQL expressions."""
    query = db.session.query(*columns).filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == fact_type,
    )
    if source_table is not None:
        query = query.filter(AnalyticsFact.source_table == source_table)
    for condition in extra_filters:
        query = query.filter(condition)
    return _date_filters(query, start_date, end_date)


def _ratio(numerator, denominator):
    """Safe division that returns None rather than 0.0 when undefined.

    None means "not computable", which the UI renders as an em dash. Returning
    0.0 here would make a day with no cases look like perfect efficiency.
    """
    if not denominator:
        return None
    return (numerator or 0.0) / denominator


# ---------------------------------------------------------------------------
# Cross-domain
# ---------------------------------------------------------------------------

def get_domain_data_health(company_id):
    """Per-domain fact coverage: is data actually flowing for each area?

    Returns one dict per domain in ``DOMAINS`` order:
    [{'domain': str, 'label': str, 'fact_count': int, 'first_date': date|None,
      'last_date': date|None}, ...]

    A domain with ``fact_count == 0`` is wired up but has no data yet, which is
    the common cause of an empty dashboard panel.
    """
    rows = db.session.query(
        AnalyticsFact.fact_type,
        db.func.count(AnalyticsFact.id),
        db.func.min(AnalyticsFact.date),
        db.func.max(AnalyticsFact.date),
    ).filter(
        AnalyticsFact.company_id == company_id,
    ).group_by(AnalyticsFact.fact_type).all()

    by_fact_type = {
        fact_type: {'count': count or 0, 'first': first, 'last': last}
        for fact_type, count, first, last in rows
    }

    health = []
    for domain in DOMAINS:
        counts = [by_fact_type.get(ft) for ft in domain['fact_types']]
        present = [c for c in counts if c]
        health.append({
            'domain': domain['key'],
            'label': domain['label'],
            'blurb': domain['blurb'],
            'icon': domain['icon'],
            'fact_count': sum(c['count'] for c in present),
            'first_date': min((c['first'] for c in present if c['first']), default=None),
            'last_date': max((c['last'] for c in present if c['last']), default=None),
        })
    return health


def get_cross_domain_summary(company_id, start_date, end_date):
    """One headline number per domain for the dashboard's overview row.

    Returns a dict keyed by domain:
    {'sales': {...}, 'pricing': {...}, 'efficiency': {...},
     'receiving': {...}, 'inventory': {...}}

    Each value is that domain's own summary dict, so panels and KPI tiles read
    from the same numbers.
    """
    return {
        'sales': get_sales_summary(company_id, start_date, end_date),
        'pricing': get_margin_summary(company_id, start_date, end_date),
        'efficiency': get_efficiency_summary(company_id, start_date, end_date),
        'receiving': get_receiving_summary(company_id, start_date, end_date),
        'inventory': get_inventory_summary(company_id, as_of=end_date),
    }


def compare_periods(current, previous):
    """Percent change between two summary dicts, per shared numeric key.

    Returns {key: pct_change_or_None}. Used to put "vs. prior period" deltas on
    tiles without every summary function having to know about comparison.
    """
    deltas = {}
    for key, current_value in (current or {}).items():
        previous_value = (previous or {}).get(key)
        if not isinstance(current_value, (int, float)) or not isinstance(previous_value, (int, float)):
            continue
        if not previous_value:
            deltas[key] = None
            continue
        deltas[key] = (current_value - previous_value) / abs(previous_value) * 100.0
    return deltas


def previous_period(start_date, end_date):
    """The equally-long window immediately before [start_date, end_date]."""
    span = (end_date - start_date)
    return (start_date - span - timedelta(days=1), start_date - timedelta(days=1))


# ---------------------------------------------------------------------------
# Sales & customers
# ---------------------------------------------------------------------------

def get_daily_revenue_trend(company_id, start_date=None, end_date=None):
    """Revenue and quantity per day from item_sale facts.

    Returns a list of dicts ordered by date ascending:
    [{'date': date, 'revenue': float, 'quantity': float}, ...]
    """
    query = _aggregate(
        company_id, 'item_sale',
        (AnalyticsFact.date, db.func.sum(AnalyticsFact.revenue), db.func.sum(AnalyticsFact.quantity)),
        start_date, end_date,
    ).group_by(AnalyticsFact.date).order_by(AnalyticsFact.date)

    return [
        {'date': row_date, 'revenue': revenue or 0.0, 'quantity': quantity or 0.0}
        for row_date, revenue, quantity in query.all()
    ]


def get_top_customers_by_revenue(company_id, start_date=None, end_date=None, limit=10):
    """Customers ranked by total revenue from item_sale facts.

    Facts without a customer_id (e.g. anonymous/counter sales) are excluded.
    Returns a list of dicts ordered by revenue descending:
    [{'customer_id': int, 'revenue': float, 'quantity': float}, ...]
    """
    query = _aggregate(
        company_id, 'item_sale',
        (AnalyticsFact.customer_id, db.func.sum(AnalyticsFact.revenue), db.func.sum(AnalyticsFact.quantity)),
        start_date, end_date,
        extra_filters=(AnalyticsFact.customer_id.isnot(None),),
    ).group_by(AnalyticsFact.customer_id).order_by(db.func.sum(AnalyticsFact.revenue).desc()).limit(limit)

    return [
        {'customer_id': customer_id, 'revenue': revenue or 0.0, 'quantity': quantity or 0.0}
        for customer_id, revenue, quantity in query.all()
    ]


def get_top_items_by_sales_volume(company_id, start_date=None, end_date=None, limit=10):
    """Top items ranked by units sold.

    Returns a list of dicts ordered by quantity descending:
    [{'item_id': int, 'quantity': float, 'revenue': float}, ...]

    Note: SalesRecord currently stores item_designation_id rather than item_id,
    so item_sale facts have a NULL item_id and this returns [] until that grain
    exists. Kept because the query is correct the moment it does.
    """
    query = _aggregate(
        company_id, 'item_sale',
        (AnalyticsFact.item_id, db.func.sum(AnalyticsFact.quantity), db.func.sum(AnalyticsFact.revenue)),
        start_date, end_date,
        extra_filters=(AnalyticsFact.item_id.isnot(None),),
    ).group_by(AnalyticsFact.item_id).order_by(db.func.sum(AnalyticsFact.quantity).desc()).limit(limit)

    return [
        {'item_id': item_id, 'quantity': quantity or 0.0, 'revenue': revenue or 0.0}
        for item_id, quantity, revenue in query.all()
    ]


def get_daily_summary(company_id, date):
    """Sales totals for a single date.

    Returns {'revenue': float, 'quantity': float, 'transaction_count': int}
    """
    revenue, quantity, count = _aggregate(
        company_id, 'item_sale',
        (db.func.sum(AnalyticsFact.revenue), db.func.sum(AnalyticsFact.quantity),
         db.func.count(db.distinct(AnalyticsFact.id))),
        date, date,
    ).first()

    return {
        'revenue': revenue or 0.0,
        'quantity': quantity or 0.0,
        'transaction_count': count or 0,
    }


def get_period_totals(company_id, start_date, end_date):
    """Sales totals for a date range.

    Returns {'revenue', 'quantity', 'days', 'avg_daily_revenue'}
    """
    revenue, quantity, days = _aggregate(
        company_id, 'item_sale',
        (db.func.sum(AnalyticsFact.revenue), db.func.sum(AnalyticsFact.quantity),
         db.func.count(db.distinct(AnalyticsFact.date))),
        start_date, end_date,
    ).first()

    return {
        'revenue': revenue or 0.0,
        'quantity': quantity or 0.0,
        'days': days or 0,
        'avg_daily_revenue': (revenue or 0.0) / max(days or 1, 1),
    }


def get_sales_summary(company_id, start_date, end_date):
    """Sales domain headline numbers, shaped for KPI tiles and comparison."""
    totals = get_period_totals(company_id, start_date, end_date)
    return {
        'revenue': totals['revenue'],
        'quantity': totals['quantity'],
        'days': totals['days'],
        'avg_daily_revenue': totals['avg_daily_revenue'],
        'avg_unit_price': _ratio(totals['revenue'], totals['quantity']),
    }


# ---------------------------------------------------------------------------
# Pricing & margin
# ---------------------------------------------------------------------------

def get_item_cost_trend(company_id, start_date=None, end_date=None):
    """Average and total landed item cost per day from cost_margin facts.

    Returns [{'date': date, 'avg_cost': float, 'total_cost': float,
              'item_count': int}, ...] ordered by date ascending.
    """
    query = _aggregate(
        company_id, 'cost_margin',
        (AnalyticsFact.date, db.func.avg(AnalyticsFact.cost),
         db.func.sum(AnalyticsFact.cost), db.func.count(db.distinct(AnalyticsFact.item_id))),
        start_date, end_date,
    ).group_by(AnalyticsFact.date).order_by(AnalyticsFact.date)

    return [
        {
            'date': row_date,
            'avg_cost': avg_cost or 0.0,
            'total_cost': total_cost or 0.0,
            'item_count': item_count or 0,
        }
        for row_date, avg_cost, total_cost, item_count in query.all()
    ]


def get_item_margin_snapshot(company_id, as_of=None, limit=None):
    """Current price vs. most recent landed cost, per item.

    Joins each item's latest cost_margin fact (on or before ``as_of``) to its
    CurrentItemPrice. Returns rows ordered by margin percent ascending, so the
    thinnest-margin items — the ones worth acting on — come first:

    [{'item_id': int, 'cost': float, 'cost_date': date, 'price': float|None,
      'margin': float|None, 'margin_pct': float|None}, ...]

    Items with no current price are included with price/margin None rather than
    dropped: a costed item that nobody has priced is itself a finding.
    """
    from app.models.pricing import CurrentItemPrice

    latest = db.session.query(
        AnalyticsFact.item_id.label('item_id'),
        db.func.max(AnalyticsFact.date).label('cost_date'),
    ).filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == 'cost_margin',
        AnalyticsFact.item_id.isnot(None),
    )
    if as_of is not None:
        latest = latest.filter(AnalyticsFact.date <= as_of)
    latest = latest.group_by(AnalyticsFact.item_id).subquery()

    rows = db.session.query(
        AnalyticsFact.item_id,
        latest.c.cost_date,
        db.func.max(AnalyticsFact.cost),
    ).join(
        latest,
        db.and_(
            AnalyticsFact.item_id == latest.c.item_id,
            AnalyticsFact.date == latest.c.cost_date,
        ),
    ).filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == 'cost_margin',
    ).group_by(AnalyticsFact.item_id, latest.c.cost_date).all()

    prices = {
        price.item_id: price.price
        for price in CurrentItemPrice.query.filter_by(company_id=company_id).all()
    }

    snapshot = []
    for item_id, cost_date, cost in rows:
        price = prices.get(item_id)
        margin = (price - (cost or 0.0)) if price is not None else None
        snapshot.append({
            'item_id': item_id,
            'cost': cost or 0.0,
            'cost_date': cost_date,
            'price': price,
            'margin': margin,
            'margin_pct': (margin / price * 100.0) if price else None,
        })

    # None margin_pct (unpriced items) sorts first — it needs attention most.
    snapshot.sort(key=lambda row: (row['margin_pct'] is not None, row['margin_pct'] or 0.0))
    return snapshot[:limit] if limit else snapshot


def get_margin_summary(company_id, start_date=None, end_date=None, thin_margin_pct=20.0):
    """Pricing domain headline numbers.

    Returns {'items_costed', 'avg_margin_pct', 'thin_margin_count',
             'below_cost_count', 'unpriced_count', 'avg_cost'}

    ``thin_margin_pct`` mirrors the detector's margin threshold so the tile and
    the anomaly list agree on what "thin" means.
    """
    snapshot = get_item_margin_snapshot(company_id, as_of=end_date)
    priced = [row for row in snapshot if row['margin_pct'] is not None]

    cost_trend = get_item_cost_trend(company_id, start_date, end_date)
    avg_cost = _ratio(
        sum(row['avg_cost'] for row in cost_trend), len(cost_trend)
    ) if cost_trend else None

    return {
        'items_costed': len(snapshot),
        'avg_margin_pct': _ratio(sum(row['margin_pct'] for row in priced), len(priced)),
        'thin_margin_count': sum(1 for row in priced if 0 <= row['margin_pct'] < thin_margin_pct),
        'below_cost_count': sum(1 for row in priced if row['margin_pct'] < 0),
        'unpriced_count': len(snapshot) - len(priced),
        'avg_cost': avg_cost,
    }


def get_price_dispersion(company_id, start_date=None, end_date=None, limit=10):
    """Per item, how far apart the prices quoted to different customers are.

    Reads PriceHistory directly: customer-level quoted price has no fact grain
    yet, since price_history rows are quotes rather than events.

    Returns rows ordered by spread percent descending:
    [{'item_id': int, 'customer_count': int, 'min_price': float,
      'max_price': float, 'avg_price': float, 'spread_pct': float}, ...]

    A wide spread is not automatically wrong (tiered pricing is normal) but it
    is where mispricing hides.
    """
    from app.models.pricing import PriceHistory

    query = db.session.query(
        PriceHistory.item_id,
        db.func.count(db.distinct(PriceHistory.customer_id)),
        db.func.min(PriceHistory.price),
        db.func.max(PriceHistory.price),
        db.func.avg(PriceHistory.price),
    ).filter(PriceHistory.company_id == company_id)

    if start_date is not None:
        query = query.filter(PriceHistory.date >= start_date)
    if end_date is not None:
        query = query.filter(PriceHistory.date <= end_date)

    query = query.group_by(PriceHistory.item_id)

    rows = []
    for item_id, customer_count, min_price, max_price, avg_price in query.all():
        if not min_price or customer_count < 2:
            continue
        rows.append({
            'item_id': item_id,
            'customer_count': customer_count or 0,
            'min_price': min_price or 0.0,
            'max_price': max_price or 0.0,
            'avg_price': avg_price or 0.0,
            'spread_pct': ((max_price - min_price) / min_price * 100.0),
        })

    rows.sort(key=lambda row: row['spread_pct'], reverse=True)
    return rows[:limit] if limit else rows


# ---------------------------------------------------------------------------
# Labor & efficiency
# ---------------------------------------------------------------------------

def get_efficiency_trend(company_id, start_date=None, end_date=None, source_table='daily_log'):
    """Daily labor efficiency ratios from labor facts.

    Returns [{'date', 'cases', 'labor_hours', 'labor_cost', 'sales',
              'man_hours_per_case', 'cost_per_case', 'cases_per_man_hour',
              'labor_ratio'}, ...] ordered by date ascending.

    ``source_table`` defaults to 'daily_log' on purpose: labor facts come from
    both daily_log and weekly_labor_summary, and summing both would double-count
    hours. Pass 'weekly_labor_summary' for the pay-group weekly view, or None to
    aggregate everything (only meaningful for cost totals).

    Ratios are None when their denominator is zero — a day with hours logged but
    no cases produced shows as "no ratio", not as zero cost per case.
    """
    query = _aggregate(
        company_id, 'labor',
        (AnalyticsFact.date, db.func.sum(AnalyticsFact.quantity),
         db.func.sum(AnalyticsFact.labor_hours), db.func.sum(AnalyticsFact.cost),
         db.func.sum(AnalyticsFact.revenue)),
        start_date, end_date, source_table=source_table,
    ).group_by(AnalyticsFact.date).order_by(AnalyticsFact.date)

    trend = []
    for row_date, cases, hours, cost, sales in query.all():
        cases = cases or 0.0
        hours = hours or 0.0
        cost = cost or 0.0
        sales = sales or 0.0
        trend.append({
            'date': row_date,
            'cases': cases,
            'labor_hours': hours,
            'labor_cost': cost,
            'sales': sales,
            'man_hours_per_case': _ratio(hours, cases),
            'cost_per_case': _ratio(cost, cases),
            'cases_per_man_hour': _ratio(cases, hours),
            'labor_ratio': _ratio(cost, sales),
        })
    return trend


def get_efficiency_summary(company_id, start_date=None, end_date=None, source_table='daily_log'):
    """Labor domain headline numbers for the period.

    Ratios are computed from period totals rather than averaged across days, so
    a low-volume day cannot skew the number.

    Returns {'cases', 'labor_hours', 'labor_cost', 'sales', 'days',
             'man_hours_per_case', 'cost_per_case', 'cases_per_man_hour',
             'labor_ratio', 'sales_per_man_hour'}
    """
    cases, hours, cost, sales, days = _aggregate(
        company_id, 'labor',
        (db.func.sum(AnalyticsFact.quantity), db.func.sum(AnalyticsFact.labor_hours),
         db.func.sum(AnalyticsFact.cost), db.func.sum(AnalyticsFact.revenue),
         db.func.count(db.distinct(AnalyticsFact.date))),
        start_date, end_date, source_table=source_table,
    ).first()

    cases = cases or 0.0
    hours = hours or 0.0
    cost = cost or 0.0
    sales = sales or 0.0

    return {
        'cases': cases,
        'labor_hours': hours,
        'labor_cost': cost,
        'sales': sales,
        'days': days or 0,
        'man_hours_per_case': _ratio(hours, cases),
        'cost_per_case': _ratio(cost, cases),
        'cases_per_man_hour': _ratio(cases, hours),
        'labor_ratio': _ratio(cost, sales),
        'sales_per_man_hour': _ratio(sales, hours),
    }


def get_labor_summary(company_id, start_date=None, end_date=None, source_table=None):
    """Labor cost and hours per day.

    Returns [{'date': date, 'labor_cost': float, 'hours': float}, ...] ordered
    by date ascending. ``source_table`` is None by default so this keeps
    reporting total payroll across every labor source; use
    ``get_efficiency_trend`` when you need per-case ratios.
    """
    query = _aggregate(
        company_id, 'labor',
        (AnalyticsFact.date, db.func.sum(AnalyticsFact.cost), db.func.sum(AnalyticsFact.labor_hours)),
        start_date, end_date, source_table=source_table,
    ).group_by(AnalyticsFact.date).order_by(AnalyticsFact.date)

    return [
        {'date': row_date, 'labor_cost': cost or 0.0, 'hours': hours or 0.0}
        for row_date, cost, hours in query.all()
    ]


# ---------------------------------------------------------------------------
# Receiving & suppliers
# ---------------------------------------------------------------------------

def get_receiving_cost_trend(company_id, start_date=None, end_date=None):
    """Inbound spend per day from receiving facts.

    Returns [{'date': date, 'total_cost': float, 'quantity': float,
              'cost_per_unit': float|None}, ...] ordered by date ascending.
    """
    query = _aggregate(
        company_id, 'receiving',
        (AnalyticsFact.date, db.func.sum(AnalyticsFact.cost), db.func.sum(AnalyticsFact.quantity)),
        start_date, end_date,
    ).group_by(AnalyticsFact.date).order_by(AnalyticsFact.date)

    return [
        {
            'date': row_date,
            'total_cost': cost or 0.0,
            'quantity': quantity or 0.0,
            'cost_per_unit': _ratio(cost, quantity),
        }
        for row_date, cost, quantity in query.all()
    ]


# Kept as the pre-existing name used by templates and the detailed analytics page.
get_receiving_costs = get_receiving_cost_trend


def get_top_suppliers_by_spend(company_id, start_date=None, end_date=None, limit=10):
    """Suppliers ranked by inbound spend.

    Returns [{'supplier_id': int, 'total_cost': float, 'quantity': float,
              'cost_per_unit': float|None, 'delivery_count': int}, ...]
    ordered by spend descending.
    """
    query = _aggregate(
        company_id, 'receiving',
        (AnalyticsFact.supplier_id, db.func.sum(AnalyticsFact.cost),
         db.func.sum(AnalyticsFact.quantity), db.func.count(AnalyticsFact.id)),
        start_date, end_date,
        extra_filters=(AnalyticsFact.supplier_id.isnot(None),),
    ).group_by(AnalyticsFact.supplier_id).order_by(db.func.sum(AnalyticsFact.cost).desc()).limit(limit)

    return [
        {
            'supplier_id': supplier_id,
            'total_cost': cost or 0.0,
            'quantity': quantity or 0.0,
            'cost_per_unit': _ratio(cost, quantity),
            'delivery_count': count or 0,
        }
        for supplier_id, cost, quantity, count in query.all()
    ]


def get_raw_product_cost_per_unit(company_id, start_date=None, end_date=None, limit=10):
    """Cost per unit received, per raw product.

    Returns [{'raw_product_id': int, 'total_cost': float, 'quantity': float,
              'cost_per_unit': float|None, 'delivery_count': int}, ...]
    ordered by spend descending — the products where a cost move matters most.
    """
    query = _aggregate(
        company_id, 'receiving',
        (AnalyticsFact.raw_product_id, db.func.sum(AnalyticsFact.cost),
         db.func.sum(AnalyticsFact.quantity), db.func.count(AnalyticsFact.id)),
        start_date, end_date,
        extra_filters=(AnalyticsFact.raw_product_id.isnot(None),),
    ).group_by(AnalyticsFact.raw_product_id).order_by(db.func.sum(AnalyticsFact.cost).desc()).limit(limit)

    return [
        {
            'raw_product_id': raw_product_id,
            'total_cost': cost or 0.0,
            'quantity': quantity or 0.0,
            'cost_per_unit': _ratio(cost, quantity),
            'delivery_count': count or 0,
        }
        for raw_product_id, cost, quantity, count in query.all()
    ]


def get_receiving_summary(company_id, start_date=None, end_date=None):
    """Receiving domain headline numbers.

    Returns {'total_cost', 'quantity', 'cost_per_unit', 'delivery_count',
             'supplier_count', 'raw_product_count', 'days'}
    """
    cost, quantity, deliveries, suppliers, products, days = _aggregate(
        company_id, 'receiving',
        (db.func.sum(AnalyticsFact.cost), db.func.sum(AnalyticsFact.quantity),
         db.func.count(AnalyticsFact.id), db.func.count(db.distinct(AnalyticsFact.supplier_id)),
         db.func.count(db.distinct(AnalyticsFact.raw_product_id)),
         db.func.count(db.distinct(AnalyticsFact.date))),
        start_date, end_date,
    ).first()

    return {
        'total_cost': cost or 0.0,
        'quantity': quantity or 0.0,
        'cost_per_unit': _ratio(cost, quantity),
        'delivery_count': deliveries or 0,
        'supplier_count': suppliers or 0,
        'raw_product_count': products or 0,
        'days': days or 0,
    }


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def get_inventory_levels(company_id, as_of=None, limit=None):
    """Latest counted quantity per item.

    Returns [{'item_id': int, 'quantity': float, 'count_date': date}, ...]
    ordered by quantity descending. ``as_of`` bounds which counts are
    considered, so historical snapshots are reproducible.
    """
    latest = db.session.query(
        AnalyticsFact.item_id.label('item_id'),
        db.func.max(AnalyticsFact.date).label('count_date'),
    ).filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == 'inventory_snapshot',
        AnalyticsFact.item_id.isnot(None),
    )
    if as_of is not None:
        latest = latest.filter(AnalyticsFact.date <= as_of)
    latest = latest.group_by(AnalyticsFact.item_id).subquery()

    query = db.session.query(
        AnalyticsFact.item_id,
        latest.c.count_date,
        db.func.sum(AnalyticsFact.quantity),
    ).join(
        latest,
        db.and_(
            AnalyticsFact.item_id == latest.c.item_id,
            AnalyticsFact.date == latest.c.count_date,
        ),
    ).filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == 'inventory_snapshot',
    ).group_by(AnalyticsFact.item_id, latest.c.count_date)

    levels = [
        {'item_id': item_id, 'count_date': count_date, 'quantity': quantity or 0.0}
        for item_id, count_date, quantity in query.all()
    ]
    levels.sort(key=lambda row: row['quantity'], reverse=True)
    return levels[:limit] if limit else levels


def get_inventory_trend(company_id, start_date=None, end_date=None):
    """Total counted units and items counted per count date.

    Returns [{'date': date, 'quantity': float, 'item_count': int}, ...] ordered
    by date ascending.
    """
    query = _aggregate(
        company_id, 'inventory_snapshot',
        (AnalyticsFact.date, db.func.sum(AnalyticsFact.quantity),
         db.func.count(db.distinct(AnalyticsFact.item_id))),
        start_date, end_date,
    ).group_by(AnalyticsFact.date).order_by(AnalyticsFact.date)

    return [
        {'date': row_date, 'quantity': quantity or 0.0, 'item_count': item_count or 0}
        for row_date, quantity, item_count in query.all()
    ]


def get_inventory_movement(company_id, start_date=None, end_date=None, limit=None):
    """Change in on-hand quantity between an item's two most recent counts.

    Returns rows ordered by absolute change descending:
    [{'item_id': int, 'previous_quantity': float, 'previous_date': date,
      'current_quantity': float, 'current_date': date, 'change': float,
      'change_pct': float|None}, ...]

    Items with only one count in range are skipped: there is nothing to compare.
    """
    facts = _facts(company_id, 'inventory_snapshot', start_date, end_date).filter(
        AnalyticsFact.item_id.isnot(None),
    ).order_by(AnalyticsFact.item_id, AnalyticsFact.date.desc()).all()

    by_item = {}
    for fact in facts:
        by_item.setdefault(fact.item_id, []).append(fact)

    movement = []
    for item_id, item_facts in by_item.items():
        if len(item_facts) < 2:
            continue
        current, previous = item_facts[0], item_facts[1]
        change = (current.quantity or 0.0) - (previous.quantity or 0.0)
        movement.append({
            'item_id': item_id,
            'previous_quantity': previous.quantity or 0.0,
            'previous_date': previous.date,
            'current_quantity': current.quantity or 0.0,
            'current_date': current.date,
            'change': change,
            'change_pct': _ratio(change * 100.0, previous.quantity or 0.0),
        })

    movement.sort(key=lambda row: abs(row['change']), reverse=True)
    return movement[:limit] if limit else movement


def get_stale_inventory(company_id, as_of, stale_days=30, limit=None):
    """Items whose most recent count is older than ``stale_days``.

    Returns [{'item_id': int, 'quantity': float, 'count_date': date,
              'days_since_count': int}, ...] ordered by staleness descending.
    """
    cutoff = as_of - timedelta(days=stale_days)
    stale = [
        {**row, 'days_since_count': (as_of - row['count_date']).days}
        for row in get_inventory_levels(company_id, as_of=as_of)
        if row['count_date'] and row['count_date'] < cutoff
    ]
    stale.sort(key=lambda row: row['days_since_count'], reverse=True)
    return stale[:limit] if limit else stale


def get_inventory_summary(company_id, as_of=None, stale_days=30):
    """Inventory domain headline numbers.

    Returns {'items_counted', 'total_units', 'zero_count', 'negative_count',
             'stale_count', 'last_count_date'}
    """
    levels = get_inventory_levels(company_id, as_of=as_of)
    last_count_date = max((row['count_date'] for row in levels if row['count_date']), default=None)

    stale_count = 0
    if as_of is not None:
        stale_count = len(get_stale_inventory(company_id, as_of, stale_days=stale_days))

    return {
        'items_counted': len(levels),
        'total_units': sum(row['quantity'] for row in levels),
        'zero_count': sum(1 for row in levels if row['quantity'] == 0),
        'negative_count': sum(1 for row in levels if row['quantity'] < 0),
        'stale_count': stale_count,
        'last_count_date': last_count_date,
    }
