# Copyright Cade Stocker 2026
"""
Unit tests for app.services.analytics_reports.

These are read-only: they build item_sale facts via the same writer used in
production (record_item_sale), then verify the aggregate query results
against hand-calculated expected values.
"""

from datetime import date, datetime

from app import db
from app.services.analytics_facts import record_item_sale
from app.services.analytics_reports import (
    get_daily_revenue_trend,
    get_top_customers_by_revenue,
)


class TestGetDailyRevenueTrend:
    def test_sums_revenue_and_quantity_per_day(self, analytics_env):
        env = analytics_env
        sale_a = env.sale(quantity=10, unit_price=5.0, sale_date=datetime(2026, 8, 20, 9, 0))
        sale_b = env.sale(quantity=4, unit_price=5.0, sale_date=datetime(2026, 8, 20, 15, 0))
        sale_c = env.sale(quantity=3, unit_price=10.0, sale_date=datetime(2026, 8, 21, 9, 0))
        for sale in (sale_a, sale_b, sale_c):
            record_item_sale(sale)
        db.session.commit()

        trend = get_daily_revenue_trend(env.company.id)

        assert trend == [
            {'date': date(2026, 8, 20), 'revenue': 70.0, 'quantity': 14.0},
            {'date': date(2026, 8, 21), 'revenue': 30.0, 'quantity': 3.0},
        ]

    def test_filters_by_date_range(self, analytics_env):
        env = analytics_env
        early = env.sale(quantity=1, unit_price=1.0, sale_date=datetime(2026, 8, 1, 9, 0))
        in_range = env.sale(quantity=2, unit_price=1.0, sale_date=datetime(2026, 8, 15, 9, 0))
        late = env.sale(quantity=3, unit_price=1.0, sale_date=datetime(2026, 8, 30, 9, 0))
        for sale in (early, in_range, late):
            record_item_sale(sale)
        db.session.commit()

        trend = get_daily_revenue_trend(env.company.id, start_date=date(2026, 8, 10), end_date=date(2026, 8, 20))

        assert trend == [{'date': date(2026, 8, 15), 'revenue': 2.0, 'quantity': 2.0}]

    def test_ignores_other_companies(self, analytics_env_factory):
        env_a = analytics_env_factory(suffix='A')
        env_b = analytics_env_factory(suffix='B')
        record_item_sale(env_a.sale(quantity=5, unit_price=2.0))
        record_item_sale(env_b.sale(quantity=100, unit_price=100.0))
        db.session.commit()

        trend = get_daily_revenue_trend(env_a.company.id)

        assert trend == [{'date': date(2026, 8, 27), 'revenue': 10.0, 'quantity': 5.0}]

    def test_no_facts_returns_empty_list(self, analytics_env):
        assert get_daily_revenue_trend(analytics_env.company.id) == []


class TestGetTopCustomersByRevenue:
    def test_ranks_customers_by_revenue_descending(self, analytics_env_factory):
        env = analytics_env_factory()
        from app.models import Customer

        big_customer = Customer(name='Big Buyer', email='big@example.com', company_id=env.company.id)
        db.session.add(big_customer)
        db.session.flush()

        small_sale = env.sale(quantity=1, unit_price=10.0)  # goes to env.customer
        big_sale_1 = env.sale(quantity=10, unit_price=10.0)
        big_sale_1.customer_id = big_customer.id
        big_sale_2 = env.sale(quantity=5, unit_price=10.0)
        big_sale_2.customer_id = big_customer.id
        db.session.flush()

        for sale in (small_sale, big_sale_1, big_sale_2):
            record_item_sale(sale)
        db.session.commit()

        ranking = get_top_customers_by_revenue(env.company.id)

        assert ranking == [
            {'customer_id': big_customer.id, 'revenue': 150.0, 'quantity': 15.0},
            {'customer_id': env.customer.id, 'revenue': 10.0, 'quantity': 1.0},
        ]

    def test_excludes_sales_without_a_customer(self, analytics_env):
        env = analytics_env
        anonymous_sale = env.sale(quantity=99, unit_price=99.0, with_customer=False)
        named_sale = env.sale(quantity=1, unit_price=1.0)
        record_item_sale(anonymous_sale)
        record_item_sale(named_sale)
        db.session.commit()

        ranking = get_top_customers_by_revenue(env.company.id)

        assert ranking == [{'customer_id': env.customer.id, 'revenue': 1.0, 'quantity': 1.0}]

    def test_respects_limit(self, analytics_env_factory):
        env = analytics_env_factory()
        from app.models import Customer

        for i in range(3):
            customer = Customer(name=f'Cust {i}', email=f'cust{i}@example.com', company_id=env.company.id)
            db.session.add(customer)
            db.session.flush()
            sale = env.sale(quantity=1, unit_price=float(i + 1))
            sale.customer_id = customer.id
            db.session.flush()
            record_item_sale(sale)
        db.session.commit()

        ranking = get_top_customers_by_revenue(env.company.id, limit=2)

        assert len(ranking) == 2
        assert ranking[0]['revenue'] == 3.0
        assert ranking[1]['revenue'] == 2.0
