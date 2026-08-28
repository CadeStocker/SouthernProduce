"""Tests for dashboard analytics report functions."""
import pytest
from datetime import datetime, timedelta, date
from app import db
from app.models.analytics import AnalyticsFact


def test_get_daily_revenue_trend_empty(app):
    """Test revenue trend with no data."""
    from app.services import analytics_reports

    with app.app_context():
        company_id = 1
        trend = analytics_reports.get_daily_revenue_trend(company_id)
        assert trend == []


def test_get_daily_revenue_trend_single_day(app):
    """Test revenue trend with single day of data."""
    from app.services import analytics_reports

    with app.app_context():
        company_id = 1
        today = datetime.utcnow().date()

        # Add a fact
        fact = AnalyticsFact(
            fact_type='item_sale',
            company_id=company_id,
            date=today,
            source_table='sales_record',
            source_id=1,
            revenue=100.0,
            quantity=10.0
        )
        db.session.add(fact)
        db.session.commit()

        trend = analytics_reports.get_daily_revenue_trend(company_id)
        assert len(trend) == 1
        assert trend[0]['date'] == today
        assert trend[0]['revenue'] == 100.0
        assert trend[0]['quantity'] == 10.0


def test_get_daily_revenue_trend_multiple_days(app):
    """Test revenue trend aggregates by date."""
    from app.services import analytics_reports

    with app.app_context():
        company_id = 1
        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)

        # Add facts for two days
        for i, day in enumerate([yesterday, today]):
            for j in range(2):
                fact = AnalyticsFact(
                    fact_type='item_sale',
                    company_id=company_id,
                    date=day,
                    source_table='sales_record',
                    source_id=f'{i}_{j}',
                    revenue=50.0,
                    quantity=5.0
                )
                db.session.add(fact)
        db.session.commit()

        trend = analytics_reports.get_daily_revenue_trend(company_id)
        assert len(trend) == 2
        assert trend[0]['revenue'] == 100.0  # 2 sales * 50
        assert trend[0]['quantity'] == 10.0
        assert trend[1]['revenue'] == 100.0
        assert trend[1]['quantity'] == 10.0


def test_get_daily_revenue_trend_date_filter(app):
    """Test revenue trend respects date range."""
    from app.services import analytics_reports

    with app.app_context():
        company_id = 1
        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)

        # Add facts for three days
        for day in [two_days_ago, yesterday, today]:
            fact = AnalyticsFact(
                fact_type='item_sale',
                company_id=company_id,
                date=day,
                source_table='sales_record',
                source_id=day.isoformat(),
                revenue=100.0,
                quantity=10.0
            )
            db.session.add(fact)
        db.session.commit()

        # Query only last 2 days
        trend = analytics_reports.get_daily_revenue_trend(
            company_id,
            start_date=yesterday,
            end_date=today
        )
        assert len(trend) == 2
        assert trend[0]['date'] == yesterday
        assert trend[1]['date'] == today


def test_get_top_customers_by_revenue(app):
    """Test customer ranking by revenue."""
    from app.services import analytics_reports

    with app.app_context():
        company_id = 1
        today = datetime.utcnow().date()

        # Add sales for two customers
        for customer_id in [1, 2]:
            for i in range(2):
                fact = AnalyticsFact(
                    fact_type='item_sale',
                    company_id=company_id,
                    date=today,
                    customer_id=customer_id,
                    source_table='sales_record',
                    source_id=f'{customer_id}_{i}',
                    revenue=100.0 if customer_id == 1 else 50.0,
                    quantity=10.0
                )
                db.session.add(fact)
        db.session.commit()

        customers = analytics_reports.get_top_customers_by_revenue(company_id, limit=10)
        assert len(customers) == 2
        assert customers[0]['customer_id'] == 1
        assert customers[0]['revenue'] == 200.0  # 2 sales * 100
        assert customers[1]['customer_id'] == 2
        assert customers[1]['revenue'] == 100.0  # 2 sales * 50


def test_get_top_items_by_sales_volume(app):
    """Test item ranking by quantity sold."""
    from app.services import analytics_reports

    with app.app_context():
        company_id = 1
        today = datetime.utcnow().date()

        # Add sales for two items
        for item_id in [1, 2]:
            for i in range(2):
                fact = AnalyticsFact(
                    fact_type='item_sale',
                    company_id=company_id,
                    date=today,
                    item_id=item_id,
                    source_table='sales_record',
                    source_id=f'{item_id}_{i}',
                    revenue=100.0,
                    quantity=100.0 if item_id == 1 else 50.0
                )
                db.session.add(fact)
        db.session.commit()

        items = analytics_reports.get_top_items_by_sales_volume(company_id, limit=10)
        assert len(items) == 2
        assert items[0]['item_id'] == 1
        assert items[0]['quantity'] == 200.0  # 2 sales * 100
        assert items[1]['item_id'] == 2
        assert items[1]['quantity'] == 100.0  # 2 sales * 50


def test_get_daily_summary(app):
    """Test daily summary metrics."""
    from app.services import analytics_reports

    with app.app_context():
        company_id = 1
        today = datetime.utcnow().date()

        # Add 3 sales for today
        for i in range(3):
            fact = AnalyticsFact(
                fact_type='item_sale',
                company_id=company_id,
                date=today,
                source_table='sales_record',
                source_id=f'today_{i}',
                revenue=100.0,
                quantity=10.0
            )
            db.session.add(fact)
        db.session.commit()

        summary = analytics_reports.get_daily_summary(company_id, today)
        assert summary['revenue'] == 300.0
        assert summary['quantity'] == 30.0
        assert summary['transaction_count'] == 3


def test_get_period_totals(app):
    """Test period aggregation and average calculation."""
    from app.services import analytics_reports

    with app.app_context():
        company_id = 1
        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)

        # Add sales for 2 days, 2 sales each day
        for day in [yesterday, today]:
            for i in range(2):
                fact = AnalyticsFact(
                    fact_type='item_sale',
                    company_id=company_id,
                    date=day,
                    source_table='sales_record',
                    source_id=f'{day}_{i}',
                    revenue=100.0,
                    quantity=10.0
                )
                db.session.add(fact)
        db.session.commit()

        totals = analytics_reports.get_period_totals(company_id, yesterday, today)
        assert totals['revenue'] == 400.0  # 4 sales * 100
        assert totals['quantity'] == 40.0  # 4 sales * 10
        assert totals['days'] == 2
        assert totals['avg_daily_revenue'] == 200.0


def test_get_receiving_costs(app):
    """Receiving spend aggregates the cost column that record_receiving writes."""
    from app.services import analytics_reports

    with app.app_context():
        company_id = 1
        today = datetime.utcnow().date()

        # Add receiving facts
        for i in range(2):
            fact = AnalyticsFact(
                fact_type='receiving',
                company_id=company_id,
                date=today,
                source_table='receiving_log',
                source_id=i,
                cost=50.0,
                quantity=100.0  # quantity received
            )
            db.session.add(fact)
        db.session.commit()

        costs = analytics_reports.get_receiving_cost_trend(company_id)
        assert len(costs) == 1
        assert costs[0]['total_cost'] == 100.0  # 2 * 50
        assert costs[0]['quantity'] == 200.0  # 2 * 100
        assert costs[0]['cost_per_unit'] == 0.5  # 100 / 200


def test_get_receiving_costs_ignores_revenue_column(app):
    """Regression: receiving spend lives in cost, never revenue.

    An earlier version of this report summed revenue, so every receiving figure
    on the dashboard read as $0.00 no matter how much had been received.
    """
    from app.services import analytics_reports

    with app.app_context():
        db.session.add(AnalyticsFact(
            fact_type='receiving',
            company_id=1,
            date=datetime.utcnow().date(),
            source_table='receiving_log',
            source_id=99,
            cost=250.0,
            revenue=999.0,  # never a receiving measure
            quantity=10.0,
        ))
        db.session.commit()

        costs = analytics_reports.get_receiving_cost_trend(1)
        assert costs[0]['total_cost'] == 250.0


def test_get_labor_summary(app):
    """Labor cost and hours come from the cost and labor_hours columns."""
    from app.services import analytics_reports

    with app.app_context():
        company_id = 1
        today = datetime.utcnow().date()

        # Add labor facts
        for i in range(2):
            fact = AnalyticsFact(
                fact_type='labor',
                company_id=company_id,
                date=today,
                source_table='daily_log',
                source_id=i,
                cost=50.0,
                labor_hours=8.0,
            )
            db.session.add(fact)
        db.session.commit()

        labor = analytics_reports.get_labor_summary(company_id)
        assert len(labor) == 1
        assert labor[0]['labor_cost'] == 100.0  # 2 * 50
        assert labor[0]['hours'] == 16.0  # 2 * 8


def test_reports_isolated_by_company(app):
    """Test that reports only return data for requested company."""
    from app.services import analytics_reports

    with app.app_context():
        today = datetime.utcnow().date()

        # Add sales for two companies
        for company_id in [1, 2]:
            fact = AnalyticsFact(
                fact_type='item_sale',
                company_id=company_id,
                date=today,
                source_table='sales_record',
                source_id=company_id,
                revenue=100.0,
                quantity=10.0
            )
            db.session.add(fact)
        db.session.commit()

        # Query company 1 - should only get 1 result
        trend_1 = analytics_reports.get_daily_revenue_trend(1)
        assert len(trend_1) == 1
        assert trend_1[0]['revenue'] == 100.0

        # Query company 2 - should only get 1 result
        trend_2 = analytics_reports.get_daily_revenue_trend(2)
        assert len(trend_2) == 1
        assert trend_2[0]['revenue'] == 100.0
