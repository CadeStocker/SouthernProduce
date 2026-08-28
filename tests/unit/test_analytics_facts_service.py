# Copyright Cade Stocker 2026
"""
Unit tests for the centralized analytics fact writer.
Tests dimension/measure mapping, source lineage, date derivation, and the
idempotency guarantee for every record_* function in app.services.analytics_facts.
"""

import pytest
from datetime import date, datetime
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import AnalyticsFact, ItemInventory, SalesRecord
from app.services.analytics_facts import (
    record_item_sale,
    record_customer_order,
    record_receiving,
    record_inventory_snapshot,
    record_labor_summary,
    record_weekly_labor_summary,
    record_cost_margin,
)


def _fact(fact_type, source_table, source_id):
    return AnalyticsFact.query.filter_by(
        fact_type=fact_type, source_table=source_table, source_id=source_id
    ).one()


class TestRecordItemSale:
    """record_item_sale maps a SalesRecord onto an item_sale fact."""

    def test_maps_dimensions_measures_and_lineage(self, analytics_env):
        sale = analytics_env.sale(quantity=10, unit_price=5.0)
        record_item_sale(sale)
        db.session.commit()

        fact = _fact('item_sale', 'sales_record', sale.id)
        assert fact.company_id == analytics_env.company.id
        assert fact.date == date(2026, 8, 27)
        assert fact.customer_id == analytics_env.customer.id
        assert fact.quantity == 10
        assert fact.revenue == 50.0
        assert fact.source_table == 'sales_record'
        assert fact.source_id == sale.id

    def test_unused_measures_default_to_zero(self, analytics_env):
        """Measures a sale cannot populate stay 0.0 so facts aggregate cleanly."""
        sale = analytics_env.sale()
        record_item_sale(sale)
        db.session.commit()

        fact = _fact('item_sale', 'sales_record', sale.id)
        assert fact.cost == 0.0
        assert fact.margin == 0.0
        assert fact.labor_hours == 0.0

    def test_item_id_is_null_until_sales_record_tracks_items(self, analytics_env):
        """Known limitation: SalesRecord only carries item_designation_id."""
        sale = analytics_env.sale()
        record_item_sale(sale)
        db.session.commit()

        assert _fact('item_sale', 'sales_record', sale.id).item_id is None

    def test_sale_without_customer_leaves_customer_null(self, analytics_env):
        sale = analytics_env.sale(with_customer=False)
        record_item_sale(sale)
        db.session.commit()

        assert _fact('item_sale', 'sales_record', sale.id).customer_id is None

    def test_derives_date_from_sale_datetime(self, analytics_env):
        sale = analytics_env.sale(sale_date=datetime(2026, 7, 4, 23, 59))
        record_item_sale(sale)
        db.session.commit()

        assert _fact('item_sale', 'sales_record', sale.id).date == date(2026, 7, 4)


class TestRecordCustomerOrder:
    """record_customer_order derives the order-grain fact from the same source."""

    def test_maps_customer_revenue_and_lineage(self, analytics_env):
        sale = analytics_env.sale(quantity=4, unit_price=25.0)
        record_customer_order(sale)
        db.session.commit()

        fact = _fact('customer_order', 'sales_record', sale.id)
        assert fact.customer_id == analytics_env.customer.id
        assert fact.quantity == 4
        assert fact.revenue == 100.0
        assert fact.source_table == 'sales_record'

    def test_coexists_with_item_sale_fact_for_same_source_row(self, analytics_env):
        """Both fact types share a source row; fact_type keeps them distinct."""
        sale = analytics_env.sale()
        record_item_sale(sale)
        record_customer_order(sale)
        db.session.commit()

        facts = AnalyticsFact.query.filter_by(
            source_table='sales_record', source_id=sale.id
        ).all()
        assert {f.fact_type for f in facts} == {'item_sale', 'customer_order'}


class TestRecordReceiving:
    """record_receiving maps a ReceivingLog onto a receiving fact."""

    def test_maps_supplier_raw_product_and_lineage(self, analytics_env):
        log = analytics_env.receiving(quantity=20, price_paid=2.5)
        record_receiving(log)
        db.session.commit()

        fact = _fact('receiving', 'receiving_log', log.id)
        assert fact.company_id == analytics_env.company.id
        assert fact.date == date(2026, 8, 26)
        assert fact.raw_product_id == analytics_env.raw_product.id
        assert fact.supplier_id == analytics_env.grower.id
        assert fact.quantity == 20
        assert fact.source_id == log.id

    def test_extends_unit_price_into_total_cost(self, analytics_env):
        """price_paid is per-unit, so cost is price_paid * quantity_received."""
        log = analytics_env.receiving(quantity=20, price_paid=2.5)
        record_receiving(log)
        db.session.commit()

        assert _fact('receiving', 'receiving_log', log.id).cost == 50.0

    def test_missing_price_paid_records_zero_cost(self, analytics_env):
        """price_paid is nullable; the fact must stay numeric for aggregation."""
        log = analytics_env.receiving(quantity=20, price_paid=None)
        record_receiving(log)
        db.session.commit()

        fact = _fact('receiving', 'receiving_log', log.id)
        assert fact.cost == 0.0
        assert fact.quantity == 20

    def test_zero_quantity_records_zero_cost(self, analytics_env):
        log = analytics_env.receiving(quantity=0, price_paid=2.5)
        record_receiving(log)
        db.session.commit()

        fact = _fact('receiving', 'receiving_log', log.id)
        assert fact.quantity == 0
        assert fact.cost == 0.0

    def test_no_revenue_or_labor_on_receiving_facts(self, analytics_env):
        log = analytics_env.receiving()
        record_receiving(log)
        db.session.commit()

        fact = _fact('receiving', 'receiving_log', log.id)
        assert fact.revenue == 0.0
        assert fact.labor_hours == 0.0
        assert fact.customer_id is None


class TestRecordInventorySnapshot:
    """record_inventory_snapshot maps an ItemInventory count onto a snapshot fact."""

    def test_maps_item_quantity_and_lineage(self, analytics_env):
        count = analytics_env.inventory_count(quantity=42)
        record_inventory_snapshot(count)
        db.session.commit()

        fact = _fact('inventory_snapshot', 'inventory_count', count.id)
        assert fact.company_id == analytics_env.company.id
        assert fact.date == date(2026, 8, 25)
        assert fact.item_id == analytics_env.item.id
        assert fact.quantity == 42
        assert fact.source_table == 'inventory_count'

    def test_uses_column_default_count_date_when_not_supplied(self, analytics_env):
        """Callers flush before recording, so the DB default is already applied."""
        count = ItemInventory(
            item_id=analytics_env.item.id, quantity=7, company_id=analytics_env.company.id
        )
        db.session.add(count)
        db.session.flush()

        record_inventory_snapshot(count)
        db.session.commit()

        fact = _fact('inventory_snapshot', 'inventory_count', count.id)
        assert fact.date == count.count_date.date()

    def test_snapshot_carries_no_money_measures(self, analytics_env):
        count = analytics_env.inventory_count()
        record_inventory_snapshot(count)
        db.session.commit()

        fact = _fact('inventory_snapshot', 'inventory_count', count.id)
        assert fact.revenue == 0.0
        assert fact.cost == 0.0


class TestRecordLaborSummary:
    """record_labor_summary maps a DailyLog onto a labor fact."""

    def test_maps_sales_payroll_and_hours(self, analytics_env):
        log = analytics_env.daily_log(sales=10000.0, payroll_cost=2500.0, labor_hours=180.0)
        record_labor_summary(log)
        db.session.commit()

        fact = _fact('labor', 'daily_log', log.id)
        assert fact.company_id == analytics_env.company.id
        assert fact.date == date(2026, 8, 24)
        assert fact.revenue == 10000.0
        assert fact.cost == 2500.0
        assert fact.labor_hours == 180.0
        assert fact.source_table == 'daily_log'

    def test_uses_log_date_directly(self, analytics_env):
        log = analytics_env.daily_log(log_date=date(2026, 1, 15))
        record_labor_summary(log)
        db.session.commit()

        assert _fact('labor', 'daily_log', log.id).date == date(2026, 1, 15)


class TestRecordWeeklyLaborSummary:
    """record_weekly_labor_summary maps a WeeklyLaborEntry onto a labor fact."""

    def test_sums_regular_and_overtime_hours(self, analytics_env):
        entry = analytics_env.weekly_labor(regular_hours=400.0, overtime_hours=35.5)
        record_weekly_labor_summary(entry)
        db.session.commit()

        assert _fact('labor', 'weekly_labor_summary', entry.id).labor_hours == 435.5

    def test_maps_pay_to_cost_and_week_start_to_date(self, analytics_env):
        entry = analytics_env.weekly_labor(week_start=date(2026, 8, 17), pay=9000.0)
        record_weekly_labor_summary(entry)
        db.session.commit()

        fact = _fact('labor', 'weekly_labor_summary', entry.id)
        assert fact.cost == 9000.0
        assert fact.date == date(2026, 8, 17)
        assert fact.revenue == 0.0

    def test_daily_and_weekly_labor_facts_do_not_collide(self, analytics_env):
        """Both write fact_type='labor'; source_table disambiguates them even
        when the two source rows happen to share an id."""
        log = analytics_env.daily_log()
        entry = analytics_env.weekly_labor()
        record_labor_summary(log)
        record_weekly_labor_summary(entry)
        db.session.commit()

        labor_facts = AnalyticsFact.query.filter_by(fact_type='labor').all()
        assert len(labor_facts) == 2
        assert {f.source_table for f in labor_facts} == {'daily_log', 'weekly_labor_summary'}


class TestRecordCostMargin:
    """record_cost_margin maps an ItemTotalCost onto a cost_margin fact."""

    def test_maps_item_total_cost_and_lineage(self, analytics_env):
        cost = analytics_env.item_cost(total_cost=12.75, cost_date=date(2026, 8, 23))
        record_cost_margin(cost)
        db.session.commit()

        fact = _fact('cost_margin', 'item_total_cost', cost.id)
        assert fact.company_id == analytics_env.company.id
        assert fact.date == date(2026, 8, 23)
        assert fact.item_id == analytics_env.item.id
        assert fact.cost == 12.75
        assert fact.source_table == 'item_total_cost'

    def test_revenue_and_margin_unset_without_a_paired_sale(self, analytics_env):
        cost = analytics_env.item_cost()
        record_cost_margin(cost)
        db.session.commit()

        fact = _fact('cost_margin', 'item_total_cost', cost.id)
        assert fact.revenue == 0.0
        assert fact.margin == 0.0


class TestIdempotency:
    """Every writer must be safe to re-run for the same source row."""

    def test_repeated_calls_do_not_duplicate_any_fact_type(self, analytics_env):
        sale = analytics_env.sale()
        log = analytics_env.receiving()
        count = analytics_env.inventory_count()
        daily = analytics_env.daily_log()
        weekly = analytics_env.weekly_labor()
        cost = analytics_env.item_cost()

        for _ in range(3):
            record_item_sale(sale)
            record_customer_order(sale)
            record_receiving(log)
            record_inventory_snapshot(count)
            record_labor_summary(daily)
            record_weekly_labor_summary(weekly)
            record_cost_margin(cost)
            db.session.commit()

        # 7 writers, one fact each.
        assert AnalyticsFact.query.count() == 7

    def test_returns_the_same_fact_row_on_re_record(self, analytics_env):
        sale = analytics_env.sale()
        first = record_item_sale(sale)
        db.session.commit()
        second = record_item_sale(sale)
        db.session.commit()

        assert first.id == second.id

    def test_re_record_updates_measures_in_place(self, analytics_env):
        """A corrected source row should refresh the fact, not duplicate it."""
        sale = analytics_env.sale(quantity=10, unit_price=5.0)
        record_item_sale(sale)
        db.session.commit()

        sale.quantity_sold = 3
        sale.unit_price = 4.0
        sale.total_price = 12.0
        db.session.flush()
        record_item_sale(sale)
        db.session.commit()

        fact = _fact('item_sale', 'sales_record', sale.id)
        assert fact.quantity == 3
        assert fact.revenue == 12.0
        assert AnalyticsFact.query.filter_by(fact_type='item_sale').count() == 1

    def test_re_record_refreshes_date_and_dimensions(self, analytics_env):
        sale = analytics_env.sale(sale_date=datetime(2026, 8, 27, 10, 0))
        record_item_sale(sale)
        db.session.commit()

        sale.sale_date = datetime(2026, 8, 28, 10, 0)
        sale.customer_id = None
        db.session.flush()
        record_item_sale(sale)
        db.session.commit()

        fact = _fact('item_sale', 'sales_record', sale.id)
        assert fact.date == date(2026, 8, 28)
        assert fact.customer_id is None

    def test_distinct_source_rows_produce_distinct_facts(self, analytics_env):
        first = analytics_env.sale(quantity=1)
        second = analytics_env.sale(quantity=2)
        record_item_sale(first)
        record_item_sale(second)
        db.session.commit()

        facts = AnalyticsFact.query.filter_by(fact_type='item_sale').all()
        assert len(facts) == 2
        assert {f.source_id for f in facts} == {first.id, second.id}


class TestUniqueConstraint:
    """The service relies on a DB constraint, not just application logic."""

    def test_duplicate_lineage_is_rejected_by_the_database(self, analytics_env):
        sale = analytics_env.sale()
        record_item_sale(sale)
        db.session.commit()

        # Bypass the service to prove the constraint is enforced in the schema.
        db.session.add(AnalyticsFact(
            fact_type='item_sale',
            company_id=analytics_env.company.id,
            source_table='sales_record',
            source_id=sale.id,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_same_source_id_across_tables_is_allowed(self, analytics_env):
        """source_table is part of the key, so ids from different tables coexist."""
        db.session.add_all([
            AnalyticsFact(
                fact_type='receiving', company_id=analytics_env.company.id,
                source_table='receiving_log', source_id=1,
            ),
            AnalyticsFact(
                fact_type='receiving', company_id=analytics_env.company.id,
                source_table='legacy_receiving_log', source_id=1,
            ),
        ])
        db.session.commit()

        assert AnalyticsFact.query.filter_by(fact_type='receiving').count() == 2


class TestCompanyScoping:
    """Facts must stay attributable to the company that owns the source row."""

    def test_facts_carry_the_source_rows_company(self, analytics_env_factory):
        env_one = analytics_env_factory(suffix='-1')
        env_two = analytics_env_factory(suffix='-2')

        sale_one = env_one.sale()
        sale_two = env_two.sale()
        record_item_sale(sale_one)
        record_item_sale(sale_two)
        db.session.commit()

        assert _fact('item_sale', 'sales_record', sale_one.id).company_id == env_one.company.id
        assert _fact('item_sale', 'sales_record', sale_two.id).company_id == env_two.company.id
        assert AnalyticsFact.query.filter_by(company_id=env_one.company.id).count() == 1


class TestTransactionSemantics:
    """Facts join the caller's transaction rather than committing on their own."""

    def test_fact_is_not_persisted_until_the_caller_commits(self, analytics_env):
        sale = analytics_env.sale()
        record_item_sale(sale)

        # Still pending: rolling back the request must discard the fact too.
        db.session.rollback()
        assert AnalyticsFact.query.count() == 0

    def test_rollback_discards_fact_and_source_together(self, analytics_env):
        sale = analytics_env.sale()
        sale_id = sale.id
        record_item_sale(sale)
        db.session.rollback()

        assert db.session.get(SalesRecord, sale_id) is None
        assert AnalyticsFact.query.count() == 0
