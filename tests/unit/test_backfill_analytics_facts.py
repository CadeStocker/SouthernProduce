# Copyright Cade Stocker 2026
"""
Tests for the one-time analytics fact backfill.
Covers coverage of every source table, reported counts, re-run safety, and
coexistence with facts already written by the live API paths.
"""

import pytest

from app import db
from app.models import AnalyticsFact, ReceivingLog
from app.services.analytics_facts import record_item_sale, record_receiving
from scripts.backfill_analytics_facts import AnalyticsFactBackfill


@pytest.fixture
def populated(analytics_env):
    """Historical operational rows that predate the analytics fact layer."""
    env = analytics_env
    rows = {
        'sale': env.sale(quantity=10, unit_price=5.0),
        'receiving': env.receiving(quantity=20, price_paid=2.5),
        'inventory': env.inventory_count(quantity=42),
        'daily': env.daily_log(),
        'weekly': env.weekly_labor(),
        'cost': env.item_cost(total_cost=12.75),
    }
    db.session.commit()

    # Nothing has written facts yet -- this is the pre-backfill state.
    assert AnalyticsFact.query.count() == 0
    return env, rows


def _run_backfill():
    return AnalyticsFactBackfill(db).run()


class TestBackfillCoverage:
    """Every wired source table is read and turned into facts."""

    def test_creates_a_fact_for_every_source_row(self, populated):
        _run_backfill()

        # sales_record yields two facts (item_sale + customer_order); the other
        # five tables yield one each.
        assert AnalyticsFact.query.count() == 7

    def test_populates_each_expected_fact_type(self, populated):
        _run_backfill()

        types = sorted(f.fact_type for f in AnalyticsFact.query.all())
        assert types == sorted([
            'item_sale', 'customer_order', 'receiving',
            'inventory_snapshot', 'labor', 'labor', 'cost_margin',
        ])

    def test_records_source_lineage_for_every_fact(self, populated):
        env, rows = populated
        _run_backfill()

        lineage = {(f.fact_type, f.source_table, f.source_id) for f in AnalyticsFact.query.all()}
        assert lineage == {
            ('item_sale', 'sales_record', rows['sale'].id),
            ('customer_order', 'sales_record', rows['sale'].id),
            ('receiving', 'receiving_log', rows['receiving'].id),
            ('inventory_snapshot', 'inventory_count', rows['inventory'].id),
            ('labor', 'daily_log', rows['daily'].id),
            ('labor', 'weekly_labor_summary', rows['weekly'].id),
            ('cost_margin', 'item_total_cost', rows['cost'].id),
        }

    def test_backfilled_measures_match_the_source_rows(self, populated):
        env, rows = populated
        _run_backfill()

        sale_fact = AnalyticsFact.query.filter_by(fact_type='item_sale').one()
        assert sale_fact.revenue == 50.0
        assert sale_fact.quantity == 10
        assert sale_fact.customer_id == env.customer.id

        receiving_fact = AnalyticsFact.query.filter_by(fact_type='receiving').one()
        assert receiving_fact.cost == 50.0
        assert receiving_fact.supplier_id == env.grower.id

        cost_fact = AnalyticsFact.query.filter_by(fact_type='cost_margin').one()
        assert cost_fact.cost == 12.75
        assert cost_fact.item_id == env.item.id

        weekly_fact = AnalyticsFact.query.filter_by(source_table='weekly_labor_summary').one()
        assert weekly_fact.labor_hours == 435.5

    def test_all_facts_carry_their_companies_id(self, populated):
        env, _ = populated
        _run_backfill()

        assert all(f.company_id == env.company.id for f in AnalyticsFact.query.all())

    def test_facts_are_committed_not_left_pending(self, populated):
        """The command must persist its work without the caller committing."""
        _run_backfill()
        db.session.rollback()

        assert AnalyticsFact.query.count() == 7


class TestBackfillReportedCounts:
    """run() returns per-table counts for the CLI to echo."""

    def test_reports_rows_processed_per_source_table(self, populated):
        totals = _run_backfill()

        assert totals == {
            'sales_record': 1,
            'receiving_log': 1,
            'inventory_count': 1,
            'daily_log': 1,
            'weekly_labor_summary': 1,
            'item_total_cost': 1,
        }

    def test_counts_scale_with_source_rows(self, analytics_env):
        for _ in range(3):
            analytics_env.sale()
        analytics_env.receiving()
        db.session.commit()

        totals = _run_backfill()
        assert totals['sales_record'] == 3
        assert totals['receiving_log'] == 1

    def test_reports_zeros_on_an_empty_database(self, analytics_env):
        """Reference data exists but no operational rows do."""
        db.session.commit()
        totals = _run_backfill()

        assert set(totals.values()) == {0}
        assert AnalyticsFact.query.count() == 0


class TestBackfillIsRerunnable:
    """The command is idempotent, so a partial or repeated run is safe."""

    def test_second_run_creates_no_duplicates(self, populated):
        _run_backfill()
        _run_backfill()

        assert AnalyticsFact.query.count() == 7

    def test_repeated_runs_keep_the_same_fact_rows(self, populated):
        _run_backfill()
        first_ids = {f.id for f in AnalyticsFact.query.all()}

        _run_backfill()
        assert {f.id for f in AnalyticsFact.query.all()} == first_ids

    def test_second_run_still_reports_rows_it_visited(self, populated):
        _run_backfill()
        totals = _run_backfill()

        # Counts are rows processed, not rows inserted.
        assert totals['sales_record'] == 1

    def test_picks_up_rows_added_after_the_first_run(self, populated):
        env, _ = populated
        _run_backfill()
        assert AnalyticsFact.query.count() == 7

        env.receiving(quantity=5, price_paid=1.0)
        db.session.commit()
        _run_backfill()

        assert AnalyticsFact.query.filter_by(fact_type='receiving').count() == 2
        assert AnalyticsFact.query.count() == 8

    def test_refreshes_facts_when_a_source_row_was_corrected(self, populated):
        env, rows = populated
        _run_backfill()

        rows['receiving'].price_paid = 10.0
        db.session.commit()
        _run_backfill()

        fact = AnalyticsFact.query.filter_by(fact_type='receiving').one()
        assert fact.cost == 200.0


class TestBackfillAlongsideLiveWrites:
    """Backfilling a partially-migrated table must not duplicate live facts."""

    def test_does_not_duplicate_facts_already_written_by_the_api_path(self, populated):
        env, rows = populated

        # Simulate the live write paths having already recorded these two.
        record_item_sale(rows['sale'])
        record_receiving(rows['receiving'])
        db.session.commit()
        assert AnalyticsFact.query.count() == 2

        _run_backfill()

        assert AnalyticsFact.query.count() == 7
        assert AnalyticsFact.query.filter_by(fact_type='item_sale').count() == 1
        assert AnalyticsFact.query.filter_by(fact_type='receiving').count() == 1

    def test_fills_only_the_gaps_left_by_live_writes(self, populated):
        env, rows = populated
        record_item_sale(rows['sale'])
        db.session.commit()
        existing_id = AnalyticsFact.query.filter_by(fact_type='item_sale').one().id

        _run_backfill()

        # The pre-existing fact is reused, not replaced.
        assert AnalyticsFact.query.filter_by(fact_type='item_sale').one().id == existing_id


class TestBackfillBatching:
    """Batched commits must not drop or duplicate rows at the boundaries."""

    def test_handles_more_rows_than_one_batch(self, analytics_env):
        for _ in range(12):
            analytics_env.receiving()
        db.session.commit()

        processed = AnalyticsFactBackfill(db)._backfill(
            ReceivingLog, (record_receiving,), batch_size=5
        )

        assert processed == 12
        assert AnalyticsFact.query.filter_by(fact_type='receiving').count() == 12

    def test_batched_run_is_still_idempotent(self, analytics_env):
        for _ in range(12):
            analytics_env.receiving()
        db.session.commit()

        backfill = AnalyticsFactBackfill(db)
        backfill._backfill(ReceivingLog, (record_receiving,), batch_size=5)
        backfill._backfill(ReceivingLog, (record_receiving,), batch_size=5)

        assert AnalyticsFact.query.filter_by(fact_type='receiving').count() == 12


class TestBackfillCommandRegistration:
    """The backfill is reachable as a Flask CLI command."""

    def test_command_is_registered_on_the_app(self, app):
        assert 'backfill-analytics-facts' in app.cli.commands

    def test_command_runs_and_reports_each_table(self, app, populated):
        runner = app.test_cli_runner()
        result = runner.invoke(args=['backfill-analytics-facts'])

        assert result.exit_code == 0, result.output
        assert 'Analytics fact backfill complete' in result.output
        for source_table in (
            'sales_record', 'receiving_log', 'inventory_count',
            'daily_log', 'weekly_labor_summary', 'item_total_cost',
        ):
            assert f'{source_table}: 1 facts' in result.output

        # The command must actually have written the facts, not just reported.
        assert AnalyticsFact.query.count() == 7
