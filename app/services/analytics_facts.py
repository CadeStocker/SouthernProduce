# Copyright Cade Stocker 2026

"""Centralized writer for AnalyticsFact rows.

Operational write paths (API routes, blueprint views) call these functions
right after creating/flushing their own record, inside the same request
transaction. 

Callers are responsible for flushing the source record first so
it has a primary key, and for committing afterwards.

Every function is idempotent: re-running it for the same source row (e.g. a
retried request, or the backfill command) updates the existing fact in place
instead of creating a duplicate, backed by the uq_analytics_fact_source
constraint on (fact_type, source_table, source_id).
"""

from app import db
from app.models.analytics import AnalyticsFact


def _upsert_fact(fact_type, company_id, source_table, source_id, date=None, **measures):
    """
    Places the fact handling for duplicates
    """

    fact = AnalyticsFact.query.filter_by(
        fact_type=fact_type, source_table=source_table, source_id=source_id,
    ).first()

    if fact is None:
        fact = AnalyticsFact(
            fact_type=fact_type,
            company_id=company_id,
            date=date,
            source_table=source_table,
            source_id=source_id,
            **measures,
        )
        db.session.add(fact)
        return fact

    fact.company_id = company_id
    if date is not None:
        fact.date = date
    for field, value in measures.items():
        setattr(fact, field, value)
    return fact


def record_item_sale(sales_record):
    """Fact for a single sale line. Item-level detail is unavailable until
    SalesRecord tracks item_id instead of item_designation_id."""
    return _upsert_fact(
        fact_type='item_sale',
        company_id=sales_record.company_id,
        source_table='sales_record',
        source_id=sales_record.id,
        date=sales_record.sale_date.date(),
        customer_id=sales_record.customer_id,
        quantity=sales_record.quantity_sold,
        revenue=sales_record.total_price,
    )


def record_customer_order(sales_record):
    """Fact for the customer/order side of a sale, sourced from SalesRecord
    until a dedicated order model exists."""
    return _upsert_fact(
        fact_type='customer_order',
        company_id=sales_record.company_id,
        source_table='sales_record',
        source_id=sales_record.id,
        date=sales_record.sale_date.date(),
        customer_id=sales_record.customer_id,
        quantity=sales_record.quantity_sold,
        revenue=sales_record.total_price,
    )


def record_receiving(receiving_log):
    quantity = receiving_log.quantity_received or 0
    cost = (receiving_log.price_paid or 0.0) * quantity
    return _upsert_fact(
        fact_type='receiving',
        company_id=receiving_log.company_id,
        source_table='receiving_log',
        source_id=receiving_log.id,
        date=receiving_log.datetime.date(),
        raw_product_id=receiving_log.raw_product_id,
        supplier_id=receiving_log.grower_or_distributor_id,
        quantity=quantity,
        cost=cost,
    )


def record_inventory_snapshot(inventory_count):
    return _upsert_fact(
        fact_type='inventory_snapshot',
        company_id=inventory_count.company_id,
        source_table='inventory_count',
        source_id=inventory_count.id,
        date=inventory_count.count_date.date(),
        item_id=inventory_count.item_id,
        quantity=inventory_count.quantity,
    )


def record_labor_summary(daily_log):
    """Fact for one day of labor.

    ``quantity`` carries the case count for the day so efficiency ratios
    (man-hours per case, payroll per case) can be computed from facts alone
    without rejoining DailyLog.
    """
    return _upsert_fact(
        fact_type='labor',
        company_id=daily_log.company_id,
        source_table='daily_log',
        source_id=daily_log.id,
        date=daily_log.date,
        quantity=daily_log.items or 0,
        revenue=daily_log.sales,
        cost=daily_log.payroll_cost,
        labor_hours=daily_log.labor_hours,
    )


def record_weekly_labor_summary(weekly_labor_entry):
    return _upsert_fact(
        fact_type='labor',
        company_id=weekly_labor_entry.company_id,
        source_table='weekly_labor_summary',
        source_id=weekly_labor_entry.id,
        date=weekly_labor_entry.week_start_date,
        cost=weekly_labor_entry.pay,
        labor_hours=weekly_labor_entry.regular_hours + weekly_labor_entry.overtime_hours,
    )


def record_cost_margin(item_total_cost):
    return _upsert_fact(
        fact_type='cost_margin',
        company_id=item_total_cost.company_id,
        source_table='item_total_cost',
        source_id=item_total_cost.id,
        date=item_total_cost.date,
        item_id=item_total_cost.item_id,
        cost=item_total_cost.total_cost,
    )
