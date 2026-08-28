# Copyright Cade Stocker 2026

"""Read-side queries against AnalyticsFact.

Each function aggregates AnalyticsFact rows directly instead of joining the
underlying operational tables (SalesRecord, DailyLog, ItemTotalCost, ...).
Callers filter by company_id and an optional date range; rows are always
returned ordered so callers can render them without re-sorting.
"""

from app import db
from app.models.analytics import AnalyticsFact
from datetime import datetime, timedelta


def _date_filters(query, start_date=None, end_date=None):
    if start_date is not None:
        query = query.filter(AnalyticsFact.date >= start_date)
    if end_date is not None:
        query = query.filter(AnalyticsFact.date <= end_date)
    return query


def get_daily_revenue_trend(company_id, start_date=None, end_date=None):
    """Revenue and quantity per day from item_sale facts.

    Returns a list of dicts ordered by date ascending:
    [{'date': date, 'revenue': float, 'quantity': float}, ...]
    """
    query = db.session.query(
        AnalyticsFact.date,
        db.func.sum(AnalyticsFact.revenue),
        db.func.sum(AnalyticsFact.quantity),
    ).filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == 'item_sale',
    )
    query = _date_filters(query, start_date, end_date)
    query = query.group_by(AnalyticsFact.date).order_by(AnalyticsFact.date)

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
    query = db.session.query(
        AnalyticsFact.customer_id,
        db.func.sum(AnalyticsFact.revenue),
        db.func.sum(AnalyticsFact.quantity),
    ).filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == 'item_sale',
        AnalyticsFact.customer_id.isnot(None),
    )
    query = _date_filters(query, start_date, end_date)
    query = query.group_by(AnalyticsFact.customer_id).order_by(db.func.sum(AnalyticsFact.revenue).desc())
    query = query.limit(limit)

    return [
        {'customer_id': customer_id, 'revenue': revenue or 0.0, 'quantity': quantity or 0.0}
        for customer_id, revenue, quantity in query.all()
    ]


def get_top_items_by_sales_volume(company_id, start_date=None, end_date=None, limit=10):
    """Top items ranked by units sold.

    Returns a list of dicts ordered by quantity descending:
    [{'item_id': int, 'quantity': float, 'revenue': float}, ...]
    """
    query = db.session.query(
        AnalyticsFact.item_id,
        db.func.sum(AnalyticsFact.quantity),
        db.func.sum(AnalyticsFact.revenue),
    ).filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == 'item_sale',
        AnalyticsFact.item_id.isnot(None),
    )
    query = _date_filters(query, start_date, end_date)
    query = query.group_by(AnalyticsFact.item_id).order_by(db.func.sum(AnalyticsFact.quantity).desc())
    query = query.limit(limit)

    return [
        {'item_id': item_id, 'quantity': quantity or 0.0, 'revenue': revenue or 0.0}
        for item_id, quantity, revenue in query.all()
    ]


def get_daily_summary(company_id, date):
    """Get summary metrics for a specific date.

    Returns a dict with today's totals:
    {'revenue': float, 'quantity': float, 'transaction_count': int}
    """
    query = db.session.query(
        db.func.sum(AnalyticsFact.revenue),
        db.func.sum(AnalyticsFact.quantity),
        db.func.count(db.distinct(AnalyticsFact.id)),
    ).filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == 'item_sale',
        AnalyticsFact.date == date,
    )

    revenue, quantity, count = query.first()
    return {
        'revenue': revenue or 0.0,
        'quantity': quantity or 0.0,
        'transaction_count': count or 0,
    }


def get_period_totals(company_id, start_date, end_date):
    """Get aggregated metrics for a date range.

    Returns a dict with period totals:
    {'revenue': float, 'quantity': float, 'days': int}
    """
    query = db.session.query(
        db.func.sum(AnalyticsFact.revenue),
        db.func.sum(AnalyticsFact.quantity),
        db.func.count(db.distinct(AnalyticsFact.date)),
    ).filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == 'item_sale',
        AnalyticsFact.date >= start_date,
        AnalyticsFact.date <= end_date,
    )

    revenue, quantity, days = query.first()
    return {
        'revenue': revenue or 0.0,
        'quantity': quantity or 0.0,
        'days': days or 0,
        'avg_daily_revenue': (revenue or 0.0) / max(days or 1, 1),
    }


def get_receiving_costs(company_id, start_date=None, end_date=None):
    """Get receiving/cost facts aggregated by date.

    Returns a list of dicts ordered by date ascending:
    [{'date': date, 'total_cost': float, 'quantity': float}, ...]
    """
    query = db.session.query(
        AnalyticsFact.date,
        db.func.sum(AnalyticsFact.revenue),
        db.func.sum(AnalyticsFact.quantity),
    ).filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == 'receiving',
    )
    query = _date_filters(query, start_date, end_date)
    query = query.group_by(AnalyticsFact.date).order_by(AnalyticsFact.date)

    return [
        {'date': row_date, 'total_cost': revenue or 0.0, 'quantity': quantity or 0.0}
        for row_date, revenue, quantity in query.all()
    ]


def get_labor_summary(company_id, start_date=None, end_date=None):
    """Get labor cost facts aggregated by date.

    Returns a list of dicts ordered by date ascending:
    [{'date': date, 'labor_cost': float, 'hours': float}, ...]
    """
    query = db.session.query(
        AnalyticsFact.date,
        db.func.sum(AnalyticsFact.revenue),
        db.func.sum(AnalyticsFact.quantity),
    ).filter(
        AnalyticsFact.company_id == company_id,
        AnalyticsFact.fact_type == 'labor',
    )
    query = _date_filters(query, start_date, end_date)
    query = query.group_by(AnalyticsFact.date).order_by(AnalyticsFact.date)

    return [
        {'date': row_date, 'labor_cost': revenue or 0.0, 'hours': quantity or 0.0}
        for row_date, revenue, quantity in query.all()
    ]
