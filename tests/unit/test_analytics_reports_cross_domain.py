# Copyright Cade Stocker 2026
"""Unit tests for the non-sales report functions in analytics_reports.

Facts are built through the production writers in analytics_facts wherever one
exists, so these tests fail if a writer and its reader ever disagree about which
column a measure lives in — the defect that made every receiving and labor figure
on the dashboard read as zero.
"""

from datetime import date, datetime, timedelta

from app import db
from app.models.analytics import AnalyticsFact
from app.services.analytics_facts import (
    record_receiving,
    record_labor_summary,
    record_weekly_labor_summary,
    record_inventory_snapshot,
    record_cost_margin,
    record_item_sale,
)
from app.services import analytics_reports as reports


# ---------------------------------------------------------------------------
# Labor & efficiency
# ---------------------------------------------------------------------------

class TestEfficiencyTrend:
    def test_computes_per_case_ratios_from_daily_logs(self, analytics_env):
        env = analytics_env
        # 500 cases, 180 hours, $2500 payroll, $10000 sales
        record_labor_summary(env.daily_log(log_date=date(2026, 8, 24)))
        db.session.commit()

        trend = reports.get_efficiency_trend(env.company.id)

        assert len(trend) == 1
        row = trend[0]
        assert row['cases'] == 500.0
        assert row['labor_hours'] == 180.0
        assert row['man_hours_per_case'] == 180.0 / 500.0
        assert row['cost_per_case'] == 2500.0 / 500.0
        assert row['cases_per_man_hour'] == 500.0 / 180.0
        assert row['labor_ratio'] == 2500.0 / 10000.0

    def test_excludes_weekly_facts_so_hours_are_not_double_counted(self, analytics_env):
        """Weekly pay-group rows cover the same hours as the daily logs.

        Summing both would inflate every efficiency ratio, so the daily view
        filters to daily_log.
        """
        env = analytics_env
        record_labor_summary(env.daily_log(log_date=date(2026, 8, 24)))
        record_weekly_labor_summary(env.weekly_labor(week_start=date(2026, 8, 24)))
        db.session.commit()

        trend = reports.get_efficiency_trend(env.company.id)

        assert len(trend) == 1
        assert trend[0]['labor_hours'] == 180.0  # not 180 + 435.5

    def test_ratios_are_none_when_no_cases_were_produced(self, analytics_env):
        """A day with hours but no cases has no cost per case.

        Returning 0.0 would render as perfect efficiency, which is the opposite
        of what happened.
        """
        env = analytics_env
        log = env.daily_log(log_date=date(2026, 8, 24))
        log.items = 0
        db.session.flush()
        record_labor_summary(log)
        db.session.commit()

        row = reports.get_efficiency_trend(env.company.id)[0]

        assert row['man_hours_per_case'] is None
        assert row['cost_per_case'] is None
        assert row['labor_hours'] == 180.0  # the hours themselves are still real

    def test_summary_uses_period_totals_not_daily_averages(self, analytics_env):
        """One low-volume day must not skew the period ratio.

        Day A: 1000 cases / 100 hrs. Day B: 10 cases / 10 hrs.
        Averaging the daily ratios gives (0.1 + 1.0) / 2 = 0.55.
        The honest period figure is 110 hrs / 1010 cases = 0.109.
        """
        env = analytics_env
        busy = env.daily_log(log_date=date(2026, 8, 24), labor_hours=100.0)
        busy.items = 1000
        quiet = env.daily_log(log_date=date(2026, 8, 25), labor_hours=10.0)
        quiet.items = 10
        db.session.flush()
        record_labor_summary(busy)
        record_labor_summary(quiet)
        db.session.commit()

        summary = reports.get_efficiency_summary(env.company.id)

        assert summary['cases'] == 1010.0
        assert summary['labor_hours'] == 110.0
        assert abs(summary['man_hours_per_case'] - 110.0 / 1010.0) < 1e-9

    def test_ignores_other_companies(self, analytics_env_factory):
        env_a = analytics_env_factory(suffix='A')
        env_b = analytics_env_factory(suffix='B')
        record_labor_summary(env_a.daily_log(log_date=date(2026, 8, 24)))
        record_labor_summary(env_b.daily_log(log_date=date(2026, 8, 24), labor_hours=9999.0))
        db.session.commit()

        assert reports.get_efficiency_summary(env_a.company.id)['labor_hours'] == 180.0

    def test_no_facts_returns_empty(self, analytics_env):
        assert reports.get_efficiency_trend(analytics_env.company.id) == []
        assert reports.get_efficiency_summary(analytics_env.company.id)['cases'] == 0.0


# ---------------------------------------------------------------------------
# Receiving & suppliers
# ---------------------------------------------------------------------------

class TestReceivingReports:
    def test_cost_trend_reads_the_cost_column(self, analytics_env):
        env = analytics_env
        # 20 units at $2.50 => $50 cost
        record_receiving(env.receiving(quantity=20, price_paid=2.5,
                                      received_at=datetime(2026, 8, 26, 9, 0)))
        db.session.commit()

        trend = reports.get_receiving_cost_trend(env.company.id)

        assert trend == [{
            'date': date(2026, 8, 26),
            'total_cost': 50.0,
            'quantity': 20.0,
            'cost_per_unit': 2.5,
        }]

    def test_cost_per_unit_is_none_when_nothing_was_received(self, analytics_env):
        env = analytics_env
        log = env.receiving(quantity=0, price_paid=2.5)
        record_receiving(log)
        db.session.commit()

        assert reports.get_receiving_cost_trend(env.company.id)[0]['cost_per_unit'] is None

    def test_top_suppliers_ranks_by_spend(self, analytics_env):
        from app.models import GrowerOrDistributor

        env = analytics_env
        big = GrowerOrDistributor(name='Big Grower', company_id=env.company.id,
                                  city='Yuma', state='AZ')
        db.session.add(big)
        db.session.flush()

        small_log = env.receiving(quantity=10, price_paid=1.0)
        big_log = env.receiving(quantity=100, price_paid=5.0)
        big_log.grower_or_distributor_id = big.id
        db.session.flush()
        record_receiving(small_log)
        record_receiving(big_log)
        db.session.commit()

        ranking = reports.get_top_suppliers_by_spend(env.company.id)

        assert [row['supplier_id'] for row in ranking] == [big.id, env.grower.id]
        assert ranking[0]['total_cost'] == 500.0
        assert ranking[0]['cost_per_unit'] == 5.0
        assert ranking[0]['delivery_count'] == 1

    def test_raw_product_cost_per_unit(self, analytics_env):
        env = analytics_env
        record_receiving(env.receiving(quantity=10, price_paid=2.0))
        record_receiving(env.receiving(quantity=30, price_paid=4.0))
        db.session.commit()

        rows = reports.get_raw_product_cost_per_unit(env.company.id)

        assert len(rows) == 1
        # (10*2 + 30*4) / (10 + 30) = 140 / 40
        assert rows[0]['total_cost'] == 140.0
        assert rows[0]['quantity'] == 40.0
        assert rows[0]['cost_per_unit'] == 3.5
        assert rows[0]['delivery_count'] == 2

    def test_summary_counts_distinct_suppliers_and_products(self, analytics_env):
        env = analytics_env
        record_receiving(env.receiving(quantity=10, price_paid=2.0))
        record_receiving(env.receiving(quantity=10, price_paid=3.0))
        db.session.commit()

        summary = reports.get_receiving_summary(env.company.id)

        assert summary['total_cost'] == 50.0
        assert summary['delivery_count'] == 2
        assert summary['supplier_count'] == 1
        assert summary['raw_product_count'] == 1
        assert summary['cost_per_unit'] == 2.5


# ---------------------------------------------------------------------------
# Pricing & margin
# ---------------------------------------------------------------------------

class TestMarginReports:
    def _price(self, env, price):
        from app.models import CurrentItemPrice
        row = CurrentItemPrice(item_id=env.item.id, company_id=env.company.id, price=price)
        db.session.add(row)
        db.session.flush()
        return row

    def test_snapshot_pairs_latest_cost_with_current_price(self, analytics_env):
        env = analytics_env
        record_cost_margin(env.item_cost(cost_date=date(2026, 8, 20), total_cost=8.0))
        record_cost_margin(env.item_cost(cost_date=date(2026, 8, 23), total_cost=10.0))
        self._price(env, 20.0)
        db.session.commit()

        snapshot = reports.get_item_margin_snapshot(env.company.id)

        assert len(snapshot) == 1
        row = snapshot[0]
        assert row['cost'] == 10.0  # the newer cost, not the older one
        assert row['cost_date'] == date(2026, 8, 23)
        assert row['price'] == 20.0
        assert row['margin'] == 10.0
        assert row['margin_pct'] == 50.0

    def test_as_of_bounds_which_cost_counts(self, analytics_env):
        env = analytics_env
        record_cost_margin(env.item_cost(cost_date=date(2026, 8, 20), total_cost=8.0))
        record_cost_margin(env.item_cost(cost_date=date(2026, 8, 23), total_cost=10.0))
        self._price(env, 20.0)
        db.session.commit()

        snapshot = reports.get_item_margin_snapshot(env.company.id, as_of=date(2026, 8, 21))

        assert snapshot[0]['cost'] == 8.0

    def test_unpriced_items_are_kept_and_sort_first(self, analytics_env_factory):
        """A costed item nobody has priced is itself a finding, not noise."""
        from app.models import Item, UnitOfWeight

        env = analytics_env_factory()
        second = Item(name='Diced Onion', code='ON1', unit_of_weight=UnitOfWeight.POUND,
                      packaging_id=env.packaging.id, company_id=env.company.id)
        db.session.add(second)
        db.session.flush()

        record_cost_margin(env.item_cost(total_cost=10.0))
        priced_cost = env.item_cost(total_cost=5.0)
        priced_cost.item_id = second.id
        db.session.flush()
        record_cost_margin(priced_cost)

        from app.models import CurrentItemPrice
        db.session.add(CurrentItemPrice(item_id=second.id, company_id=env.company.id, price=10.0))
        db.session.commit()

        snapshot = reports.get_item_margin_snapshot(env.company.id)

        assert [row['item_id'] for row in snapshot] == [env.item.id, second.id]
        assert snapshot[0]['margin_pct'] is None
        assert snapshot[0]['price'] is None

    def test_thinnest_margin_sorts_ahead_of_healthy_margin(self, analytics_env_factory):
        from app.models import Item, UnitOfWeight, CurrentItemPrice

        env = analytics_env_factory()
        thin_item = Item(name='Thin', code='TH1', unit_of_weight=UnitOfWeight.POUND,
                         packaging_id=env.packaging.id, company_id=env.company.id)
        db.session.add(thin_item)
        db.session.flush()

        healthy = env.item_cost(total_cost=5.0)          # priced at 20 => 75%
        db.session.flush()
        record_cost_margin(healthy)
        thin = env.item_cost(total_cost=19.0)            # priced at 20 => 5%
        thin.item_id = thin_item.id
        db.session.flush()
        record_cost_margin(thin)

        db.session.add_all([
            CurrentItemPrice(item_id=env.item.id, company_id=env.company.id, price=20.0),
            CurrentItemPrice(item_id=thin_item.id, company_id=env.company.id, price=20.0),
        ])
        db.session.commit()

        snapshot = reports.get_item_margin_snapshot(env.company.id)

        assert snapshot[0]['item_id'] == thin_item.id
        assert snapshot[1]['item_id'] == env.item.id

    def test_summary_buckets_below_cost_thin_and_unpriced(self, analytics_env):
        env = analytics_env
        record_cost_margin(env.item_cost(total_cost=25.0))  # cost above the 20.0 price
        self._price(env, 20.0)
        db.session.commit()

        summary = reports.get_margin_summary(env.company.id)

        assert summary['items_costed'] == 1
        assert summary['below_cost_count'] == 1
        assert summary['thin_margin_count'] == 0  # below cost is its own bucket
        assert summary['unpriced_count'] == 0
        assert summary['avg_margin_pct'] == -25.0

    def test_price_dispersion_needs_at_least_two_customers(self, analytics_env):
        from app.models import Customer, PriceHistory

        env = analytics_env
        other = Customer(name='Other', email='other@example.com', company_id=env.company.id)
        db.session.add(other)
        db.session.flush()

        db.session.add_all([
            PriceHistory(item_id=env.item.id, date=date(2026, 8, 20),
                         company_id=env.company.id, customer_id=env.customer.id, price=10.0),
            PriceHistory(item_id=env.item.id, date=date(2026, 8, 21),
                         company_id=env.company.id, customer_id=other.id, price=15.0),
        ])
        db.session.commit()

        rows = reports.get_price_dispersion(env.company.id)

        assert len(rows) == 1
        assert rows[0]['customer_count'] == 2
        assert rows[0]['min_price'] == 10.0
        assert rows[0]['max_price'] == 15.0
        assert rows[0]['spread_pct'] == 50.0

    def test_price_dispersion_skips_single_customer_items(self, analytics_env):
        from app.models import PriceHistory

        env = analytics_env
        db.session.add(PriceHistory(item_id=env.item.id, date=date(2026, 8, 20),
                                    company_id=env.company.id,
                                    customer_id=env.customer.id, price=10.0))
        db.session.commit()

        assert reports.get_price_dispersion(env.company.id) == []


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class TestInventoryReports:
    def test_levels_use_the_most_recent_count_per_item(self, analytics_env):
        env = analytics_env
        record_inventory_snapshot(env.inventory_count(quantity=40, count_date=datetime(2026, 8, 20)))
        record_inventory_snapshot(env.inventory_count(quantity=25, count_date=datetime(2026, 8, 25)))
        db.session.commit()

        levels = reports.get_inventory_levels(env.company.id)

        assert levels == [{'item_id': env.item.id, 'count_date': date(2026, 8, 25), 'quantity': 25.0}]

    def test_movement_compares_the_two_most_recent_counts(self, analytics_env):
        env = analytics_env
        record_inventory_snapshot(env.inventory_count(quantity=40, count_date=datetime(2026, 8, 20)))
        record_inventory_snapshot(env.inventory_count(quantity=10, count_date=datetime(2026, 8, 25)))
        db.session.commit()

        movement = reports.get_inventory_movement(env.company.id)

        assert len(movement) == 1
        row = movement[0]
        assert row['previous_quantity'] == 40.0
        assert row['current_quantity'] == 10.0
        assert row['change'] == -30.0
        assert row['change_pct'] == -75.0

    def test_movement_skips_items_with_a_single_count(self, analytics_env):
        env = analytics_env
        record_inventory_snapshot(env.inventory_count(quantity=40))
        db.session.commit()

        assert reports.get_inventory_movement(env.company.id) == []

    def test_stale_inventory_uses_days_since_last_count(self, analytics_env):
        env = analytics_env
        record_inventory_snapshot(env.inventory_count(quantity=5, count_date=datetime(2026, 7, 1)))
        db.session.commit()

        stale = reports.get_stale_inventory(env.company.id, date(2026, 8, 25), stale_days=30)

        assert len(stale) == 1
        assert stale[0]['days_since_count'] == 55

    def test_recent_counts_are_not_stale(self, analytics_env):
        env = analytics_env
        record_inventory_snapshot(env.inventory_count(quantity=5, count_date=datetime(2026, 8, 24)))
        db.session.commit()

        assert reports.get_stale_inventory(env.company.id, date(2026, 8, 25), stale_days=30) == []

    def test_summary_counts_zero_and_negative_levels(self, analytics_env_factory):
        from app.models import Item, UnitOfWeight

        env = analytics_env_factory()
        empty_item = Item(name='Empty', code='EM1', unit_of_weight=UnitOfWeight.POUND,
                          packaging_id=env.packaging.id, company_id=env.company.id)
        db.session.add(empty_item)
        db.session.flush()

        record_inventory_snapshot(env.inventory_count(quantity=30, count_date=datetime(2026, 8, 25)))
        zero_count = env.inventory_count(quantity=0, count_date=datetime(2026, 8, 25))
        zero_count.item_id = empty_item.id
        db.session.flush()
        record_inventory_snapshot(zero_count)
        db.session.commit()

        summary = reports.get_inventory_summary(env.company.id, as_of=date(2026, 8, 25))

        assert summary['items_counted'] == 2
        assert summary['total_units'] == 30.0
        assert summary['zero_count'] == 1
        assert summary['negative_count'] == 0
        assert summary['last_count_date'] == date(2026, 8, 25)


# ---------------------------------------------------------------------------
# Cross-domain
# ---------------------------------------------------------------------------

class TestCrossDomain:
    def test_data_health_reports_every_domain_even_with_no_data(self, analytics_env):
        env = analytics_env
        record_receiving(env.receiving(received_at=datetime(2026, 8, 26, 9, 0)))
        db.session.commit()

        health = {row['domain']: row for row in reports.get_domain_data_health(env.company.id)}

        assert set(health) == {'sales', 'pricing', 'efficiency', 'receiving', 'inventory'}
        assert health['receiving']['fact_count'] == 1
        assert health['receiving']['last_date'] == date(2026, 8, 26)
        # An untouched domain reports zero rather than being absent, so the UI
        # can say "no data yet" instead of silently omitting the panel.
        assert health['inventory']['fact_count'] == 0
        assert health['inventory']['last_date'] is None

    def test_cross_domain_summary_covers_all_domains(self, analytics_env):
        env = analytics_env
        record_item_sale(env.sale(quantity=4, unit_price=5.0,
                                  sale_date=datetime(2026, 8, 26, 9, 0)))
        record_labor_summary(env.daily_log(log_date=date(2026, 8, 26)))
        record_receiving(env.receiving(received_at=datetime(2026, 8, 26, 9, 0)))
        db.session.commit()

        summary = reports.get_cross_domain_summary(
            env.company.id, date(2026, 8, 20), date(2026, 8, 27)
        )

        assert set(summary) == {'sales', 'pricing', 'efficiency', 'receiving', 'inventory'}
        assert summary['sales']['revenue'] == 20.0
        assert summary['efficiency']['cases'] == 500.0
        assert summary['receiving']['total_cost'] == 50.0

    def test_previous_period_is_the_same_length_and_does_not_overlap(self):
        start, end = date(2026, 8, 21), date(2026, 8, 27)  # 7 days inclusive

        previous_start, previous_end = reports.previous_period(start, end)

        assert previous_end == date(2026, 8, 20)
        assert previous_start == date(2026, 8, 14)
        assert (previous_end - previous_start) == (end - start)

    def test_compare_periods_returns_percent_change(self):
        deltas = reports.compare_periods({'revenue': 150.0}, {'revenue': 100.0})
        assert deltas['revenue'] == 50.0

    def test_compare_periods_is_none_when_the_baseline_is_zero(self):
        """Growth from nothing has no percentage; the UI shows no delta."""
        assert reports.compare_periods({'revenue': 150.0}, {'revenue': 0.0})['revenue'] is None

    def test_compare_periods_skips_non_numeric_measures(self):
        deltas = reports.compare_periods(
            {'revenue': 150.0, 'avg_margin_pct': None},
            {'revenue': 100.0, 'avg_margin_pct': 20.0},
        )
        assert 'avg_margin_pct' not in deltas
        assert deltas['revenue'] == 50.0
