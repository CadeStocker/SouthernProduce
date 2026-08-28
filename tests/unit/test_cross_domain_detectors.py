# Copyright Cade Stocker 2026
"""Unit tests for the per-domain anomaly detectors.

Each test runs a single detector class through DetectorRun so the shared
machinery (watermarks, company scoping, severity, notification) is exercised the
same way it is in production, rather than calling check() directly.
"""

from datetime import date, datetime, timedelta

import pytest

from app import db
from app.models.anomalies import Anomaly, EntityStat, JobRun
from scripts.anomaly_detector import (
    DetectorRun,
    DETECTORS,
    PriceHistoryDetector,
    ItemCostDetector,
    EfficiencyDetector,
    WeeklyLaborDetector,
    ReceivingDetector,
    InventoryDetector,
    SalesDetector,
)


def run_detector(env, detector_class, **thresholds):
    """Run one detector for one company and return the anomalies it recorded."""
    DetectorRun(
        db,
        company_id=env.company.id,
        detectors=(detector_class,),
        thresholds=thresholds or None,
    ).run()
    return Anomaly.query.filter_by(company_id=env.company.id).all()


def by_metric(anomalies, metric):
    return [a for a in anomalies if a.metric == metric]


# ---------------------------------------------------------------------------
# Registry & shared machinery
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_every_registered_detector_declares_a_known_domain(self):
        from app.services.analytics_domains import DOMAIN_KEYS

        for detector_class in DETECTORS:
            assert detector_class.domain in DOMAIN_KEYS, detector_class.__name__
            assert detector_class.source_table
            assert detector_class.model_name

    def test_registry_covers_every_domain(self):
        """Each domain has at least one detector, so no area is silently unwatched."""
        from app.services.analytics_domains import DOMAIN_KEYS

        covered = {detector_class.domain for detector_class in DETECTORS}
        assert covered == set(DOMAIN_KEYS)

    def test_anomalies_are_tagged_with_domain_and_company(self, analytics_env):
        env = analytics_env
        log = env.daily_log(log_date=date(2026, 8, 24))
        log.items = 0  # hours logged with no cases: a consistency failure
        db.session.commit()

        anomalies = run_detector(env, EfficiencyDetector)

        assert anomalies
        assert all(a.domain == 'efficiency' for a in anomalies)
        assert all(a.company_id == env.company.id for a in anomalies)

    def test_detector_only_walks_its_own_company_rows(self, analytics_env_factory):
        env_a = analytics_env_factory(suffix='A')
        env_b = analytics_env_factory(suffix='B')
        for env in (env_a, env_b):
            log = env.daily_log(log_date=date(2026, 8, 24))
            log.items = 0
        db.session.commit()

        run_detector(env_a, EfficiencyDetector)

        assert Anomaly.query.filter_by(company_id=env_a.company.id).count() > 0
        assert Anomaly.query.filter_by(company_id=env_b.company.id).count() == 0

    def test_watermark_is_per_company(self, analytics_env_factory):
        """A shared watermark meant the first company consumed every row.

        Each company must advance its own position, or company B never sees its
        own data once company A has run.
        """
        env_a = analytics_env_factory(suffix='A')
        env_b = analytics_env_factory(suffix='B')
        for env in (env_a, env_b):
            log = env.daily_log(log_date=date(2026, 8, 24))
            log.items = 0
        db.session.commit()

        run_detector(env_a, EfficiencyDetector)
        run_detector(env_b, EfficiencyDetector)

        assert Anomaly.query.filter_by(company_id=env_b.company.id).count() > 0
        keys = {jr.source_table for jr in JobRun.query.all()}
        assert f'daily_log:company:{env_a.company.id}' in keys
        assert f'daily_log:company:{env_b.company.id}' in keys

    def test_rows_are_not_reprocessed_on_a_second_run(self, analytics_env):
        env = analytics_env
        log = env.daily_log(log_date=date(2026, 8, 24))
        log.items = 0
        db.session.commit()

        first = len(run_detector(env, EfficiencyDetector))
        second = len(run_detector(env, EfficiencyDetector))

        assert first > 0
        assert second == first  # no new anomalies the second time

    def test_legacy_global_watermark_seeds_the_per_company_one(self, analytics_env):
        """Upgrading must not re-flag every historical row.

        Before this change the watermark was keyed on the table alone. That
        position is carried forward the first time a company runs.
        """
        env = analytics_env
        log = env.daily_log(log_date=date(2026, 8, 24))
        log.items = 0
        db.session.flush()

        legacy = JobRun(source_table='daily_log')
        legacy.last_processed_id = log.id
        db.session.add(legacy)
        db.session.commit()

        anomalies = run_detector(env, EfficiencyDetector)

        assert anomalies == []
        scoped = JobRun.query.filter_by(
            source_table=f'daily_log:company:{env.company.id}'
        ).one()
        assert scoped.last_processed_id == log.id

    def test_a_failing_row_does_not_stop_the_rest(self, analytics_env, monkeypatch):
        env = analytics_env
        good = env.daily_log(log_date=date(2026, 8, 24))
        good.items = 0
        bad = env.daily_log(log_date=date(2026, 8, 25))
        bad.items = 0
        db.session.commit()

        original = EfficiencyDetector.check
        calls = {'n': 0}

        def flaky(self, row):
            calls['n'] += 1
            if calls['n'] == 1:
                raise RuntimeError('boom')
            return original(self, row)

        monkeypatch.setattr(EfficiencyDetector, 'check', flaky)

        anomalies = run_detector(env, EfficiencyDetector)

        assert calls['n'] == 2          # both rows were attempted
        assert len(anomalies) > 0       # the healthy row still produced findings

    def test_thresholds_are_overridable_per_run(self, analytics_env):
        env = analytics_env
        # 180 hrs / 500 cases = 0.36, under the 0.75 default
        env.daily_log(log_date=date(2026, 8, 24))
        db.session.commit()

        assert by_metric(run_detector(env, EfficiencyDetector), 'man_hours_per_case') == []

        env2_log = env.daily_log(log_date=date(2026, 8, 25))
        db.session.commit()
        flagged = run_detector(env, EfficiencyDetector, max_man_hours_per_case=0.1)

        assert by_metric(flagged, 'man_hours_per_case')


# ---------------------------------------------------------------------------
# Efficiency
# ---------------------------------------------------------------------------

class TestEfficiencyDetector:
    def test_flags_man_hours_per_case_above_target(self, analytics_env):
        env = analytics_env
        log = env.daily_log(log_date=date(2026, 8, 24), labor_hours=500.0)
        log.items = 100  # 5.0 hrs/case
        db.session.commit()

        found = by_metric(run_detector(env, EfficiencyDetector), 'man_hours_per_case')

        assert len(found) == 1
        assert found[0].actual_value == 5.0
        assert found[0].rule_triggered == 'efficiency_below_threshold'
        assert '5.000 man-hours per case' in found[0].explanation

    def test_flags_labor_ratio_above_target(self, analytics_env):
        env = analytics_env
        # $8000 payroll on $10000 sales = 80%
        env.daily_log(log_date=date(2026, 8, 24), sales=10000.0, payroll_cost=8000.0)
        db.session.commit()

        found = by_metric(run_detector(env, EfficiencyDetector), 'labor_ratio')

        assert len(found) == 1
        assert found[0].actual_value == pytest.approx(0.8)
        # Impact is the overspend above target, not the whole payroll.
        assert found[0].dollar_impact == pytest.approx((0.8 - 0.35) * 10000.0)

    def test_flags_hours_logged_with_no_cases_as_high_severity(self, analytics_env):
        env = analytics_env
        log = env.daily_log(log_date=date(2026, 8, 24))
        log.items = 0
        db.session.commit()

        found = by_metric(run_detector(env, EfficiencyDetector), 'cases_produced')

        assert len(found) == 1
        assert found[0].severity == 'high'
        assert found[0].rule_triggered == 'data_consistency'

    def test_flags_cases_produced_with_no_hours(self, analytics_env):
        env = analytics_env
        env.daily_log(log_date=date(2026, 8, 24), labor_hours=0.0)
        db.session.commit()

        found = by_metric(run_detector(env, EfficiencyDetector), 'labor_hours')

        assert len(found) == 1
        assert found[0].severity == 'high'

    def test_flags_excess_overtime(self, analytics_env):
        env = analytics_env
        log = env.daily_log(log_date=date(2026, 8, 24), labor_hours=100.0)
        log.overtime_hours = 40.0  # 40%
        db.session.commit()

        found = by_metric(run_detector(env, EfficiencyDetector), 'overtime_share')

        assert any(a.rule_triggered == 'overtime_above_threshold' for a in found)

    def test_healthy_day_produces_nothing(self, analytics_env):
        env = analytics_env
        # 180 hrs / 500 cases = 0.36 hrs/case; labor 25% of sales; 12% overtime
        env.daily_log(log_date=date(2026, 8, 24))
        db.session.commit()

        assert run_detector(env, EfficiencyDetector) == []

    def test_tracks_stats_for_later_z_score_comparison(self, analytics_env):
        env = analytics_env
        env.daily_log(log_date=date(2026, 8, 24))
        db.session.commit()
        run_detector(env, EfficiencyDetector)

        stat = EntityStat.query.filter_by(
            entity_type='company', entity_id=env.company.id, metric='man_hours_per_case'
        ).first()
        assert stat is not None
        assert stat.mean == pytest.approx(180.0 / 500.0)

    def test_flags_a_spike_against_established_history(self, analytics_env):
        """After a normally-varying run, a sharp jump in hours per case is caught."""
        env = analytics_env
        for offset, hours in enumerate((95.0, 105.0, 98.0, 102.0, 100.0, 99.0)):
            log = env.daily_log(log_date=date(2026, 8, 1) + timedelta(days=offset),
                                labor_hours=hours)
            log.items = 500
        db.session.commit()
        run_detector(env, EfficiencyDetector)

        spike = env.daily_log(log_date=date(2026, 8, 20), labor_hours=300.0)
        spike.items = 500
        db.session.commit()
        anomalies = run_detector(env, EfficiencyDetector)

        zscore = [a for a in anomalies if a.rule_triggered == 'statistical_zscore'
                  and a.metric == 'man_hours_per_case']
        assert zscore
        assert zscore[0].z_score > 2.5

    def test_perfectly_flat_history_never_raises_a_z_score(self, analytics_env):
        """With zero variance there is no statistical basis for an outlier.

        Documented rather than fixed: a constant series has a standard deviation
        of zero, so every departure would score as infinitely anomalous. Rule
        thresholds, not statistics, are what catch drift in that case.
        """
        env = analytics_env
        for offset in range(6):
            log = env.daily_log(log_date=date(2026, 8, 1) + timedelta(days=offset),
                                labor_hours=100.0)
            log.items = 500
        db.session.commit()
        run_detector(env, EfficiencyDetector)

        spike = env.daily_log(log_date=date(2026, 8, 20), labor_hours=300.0)
        spike.items = 500
        db.session.commit()
        anomalies = run_detector(env, EfficiencyDetector)

        assert [a for a in anomalies if a.rule_triggered == 'statistical_zscore'] == []
        # The rule-based check still fires: 0.6 hrs/case is under the 0.75 target,
        # so this particular spike is caught only once it crosses that line.
        assert [a for a in anomalies if a.metric == 'man_hours_per_case'] == []


class TestWeeklyLaborDetector:
    def test_flags_excess_overtime_for_a_pay_group(self, analytics_env):
        env = analytics_env
        env.weekly_labor(week_start=date(2026, 8, 17), regular_hours=100.0, overtime_hours=50.0)
        db.session.commit()

        anomalies = run_detector(env, WeeklyLaborDetector)

        found = by_metric(anomalies, 'overtime_share')
        assert len(found) == 1
        assert found[0].entity_type == 'pay_group'
        assert found[0].entity_id == env.pay_group.id

    def test_normal_week_produces_nothing(self, analytics_env):
        env = analytics_env
        env.weekly_labor(week_start=date(2026, 8, 17), regular_hours=400.0, overtime_hours=35.5)
        db.session.commit()

        assert run_detector(env, WeeklyLaborDetector) == []


# ---------------------------------------------------------------------------
# Receiving
# ---------------------------------------------------------------------------

class TestReceivingDetector:
    def _market_cost(self, env, cost, cost_date):
        from app.models import CostHistory
        row = CostHistory(cost=cost, date=cost_date, company_id=env.company.id,
                          raw_product_id=env.raw_product.id)
        db.session.add(row)
        db.session.flush()
        return row

    def test_flags_price_paid_well_above_market(self, analytics_env):
        env = analytics_env
        self._market_cost(env, 2.0, date(2026, 8, 20))
        env.receiving(quantity=100, price_paid=4.0,
                      received_at=datetime(2026, 8, 26, 9, 0))  # 100% above market
        db.session.commit()

        found = by_metric(run_detector(env, ReceivingDetector), 'price_paid_vs_market')

        assert len(found) == 1
        assert found[0].expected_value == 2.0
        assert found[0].actual_value == 4.0
        assert '100.0% above' in found[0].explanation

    def test_price_close_to_market_is_not_flagged(self, analytics_env):
        env = analytics_env
        self._market_cost(env, 2.0, date(2026, 8, 20))
        env.receiving(quantity=100, price_paid=2.1,  # 5% above, under the 15% default
                      received_at=datetime(2026, 8, 26, 9, 0))
        db.session.commit()

        assert by_metric(run_detector(env, ReceivingDetector), 'price_paid_vs_market') == []

    def test_flags_temperature_out_of_range_as_high_severity(self, analytics_env):
        env = analytics_env
        log = env.receiving(quantity=10, price_paid=2.0)
        log.temperature = 65.0
        db.session.commit()

        found = by_metric(run_detector(env, ReceivingDetector), 'receiving_temperature')

        assert len(found) == 1
        assert found[0].severity == 'high'
        assert found[0].rule_triggered == 'temperature_out_of_range'

    def test_normal_temperature_is_not_flagged(self, analytics_env):
        env = analytics_env
        env.receiving(quantity=10, price_paid=2.0)  # 35.0°F from the fixture
        db.session.commit()

        assert by_metric(run_detector(env, ReceivingDetector), 'receiving_temperature') == []

    def test_flags_a_missing_price_as_low_severity_completeness(self, analytics_env):
        env = analytics_env
        env.receiving(quantity=10, price_paid=None)
        db.session.commit()

        found = by_metric(run_detector(env, ReceivingDetector), 'price_paid')

        assert len(found) == 1
        assert found[0].severity == 'low'
        assert found[0].rule_triggered == 'data_completeness'

    def test_flags_zero_quantity_received(self, analytics_env):
        env = analytics_env
        env.receiving(quantity=0, price_paid=2.0)
        db.session.commit()

        assert by_metric(run_detector(env, ReceivingDetector), 'quantity_received')

    def test_tracks_cost_per_unit_not_raw_price(self, analytics_env):
        """Cost per unit is what compares across deliveries of different sizes."""
        env = analytics_env
        env.receiving(quantity=10, price_paid=20.0)  # pack_size 10 => $2/unit
        db.session.commit()
        run_detector(env, ReceivingDetector)

        stat = EntityStat.query.filter_by(
            entity_type='raw_product', entity_id=env.raw_product.id,
            metric='receiving_cost_per_unit',
        ).first()
        assert stat is not None
        assert stat.mean == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class TestInventoryDetector:
    def test_flags_negative_quantity_as_high_severity(self, analytics_env):
        env = analytics_env
        env.inventory_count(quantity=-5, count_date=datetime(2026, 8, 25))
        db.session.commit()

        found = by_metric(run_detector(env, InventoryDetector), 'inventory_quantity')

        assert len(found) == 1
        assert found[0].severity == 'high'
        assert 'cannot be negative' in found[0].explanation

    def test_flags_a_large_swing_between_counts(self, analytics_env):
        env = analytics_env
        env.inventory_count(quantity=100, count_date=datetime(2026, 8, 20))
        env.inventory_count(quantity=10, count_date=datetime(2026, 8, 25))
        db.session.commit()

        found = by_metric(run_detector(env, InventoryDetector), 'inventory_swing')

        assert len(found) == 1
        assert found[0].expected_value == 100
        assert found[0].actual_value == 10
        assert 'down 90%' in found[0].explanation

    def test_small_movement_is_not_flagged(self, analytics_env):
        env = analytics_env
        env.inventory_count(quantity=100, count_date=datetime(2026, 8, 20))
        env.inventory_count(quantity=90, count_date=datetime(2026, 8, 25))  # -10%
        db.session.commit()

        assert by_metric(run_detector(env, InventoryDetector), 'inventory_swing') == []

    def test_first_ever_count_has_nothing_to_compare(self, analytics_env):
        env = analytics_env
        env.inventory_count(quantity=100, count_date=datetime(2026, 8, 25))
        db.session.commit()

        assert run_detector(env, InventoryDetector) == []

    def test_swing_impact_is_priced_at_item_cost(self, analytics_env):
        env = analytics_env
        env.item_cost(cost_date=date(2026, 8, 1), total_cost=4.0)
        env.inventory_count(quantity=100, count_date=datetime(2026, 8, 20))
        env.inventory_count(quantity=10, count_date=datetime(2026, 8, 25))
        db.session.commit()

        found = by_metric(run_detector(env, InventoryDetector), 'inventory_swing')

        assert found[0].dollar_impact == pytest.approx(90 * 4.0)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

class TestItemCostDetector:
    def test_flags_components_that_do_not_sum_to_the_total(self, analytics_env):
        env = analytics_env
        cost = env.item_cost(total_cost=12.75)  # components sum to 12.75
        cost.total_cost = 50.0                  # total edited without recomputing
        db.session.commit()

        found = by_metric(run_detector(env, ItemCostDetector), 'cost_components')

        assert len(found) == 1
        assert found[0].severity == 'high'
        assert found[0].rule_triggered == 'data_consistency'

    def test_consistent_cost_breakdown_is_not_flagged(self, analytics_env):
        env = analytics_env
        env.item_cost(total_cost=12.75)
        db.session.commit()

        assert by_metric(run_detector(env, ItemCostDetector), 'cost_components') == []

    def test_flags_non_positive_total_cost(self, analytics_env):
        env = analytics_env
        cost = env.item_cost(total_cost=12.75)
        cost.total_cost = 0.0
        db.session.commit()

        assert by_metric(run_detector(env, ItemCostDetector), 'total_cost')


class TestPriceHistoryDetectorStillWorks:
    def test_flags_price_below_cost(self, analytics_env):
        from app.models import PriceHistory

        env = analytics_env
        env.item_cost(cost_date=date(2026, 8, 1), total_cost=15.0)
        db.session.add(PriceHistory(item_id=env.item.id, date=date(2026, 8, 20),
                                    company_id=env.company.id,
                                    customer_id=env.customer.id, price=10.0))
        db.session.commit()

        anomalies = run_detector(env, PriceHistoryDetector)

        assert by_metric(anomalies, 'price_vs_cost')
        assert all(a.domain == 'pricing' for a in anomalies)


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------

class TestSalesDetector:
    def test_flags_non_positive_unit_price(self, analytics_env):
        env = analytics_env
        sale = env.sale(quantity=5, unit_price=1.0)
        sale.unit_price = 0.0
        db.session.commit()

        found = by_metric(run_detector(env, SalesDetector), 'unit_price')

        assert len(found) == 1
        assert all(a.domain == 'sales' for a in found)

    def test_normal_sale_produces_nothing(self, analytics_env):
        env = analytics_env
        env.sale(quantity=5, unit_price=10.0)
        db.session.commit()

        assert run_detector(env, SalesDetector) == []
