"""One-time backfill of AnalyticsFact rows from existing operational tables.

Run manually or from a shell: `flask backfill-analytics-facts`.

Safe to re-run: record_* functions in app.services.analytics_facts are
idempotent, keyed on (fact_type, source_table, source_id).
"""

from app import db
from app.models import (
    SalesRecord,
    ReceivingLog,
    ItemInventory,
    DailyLog,
    WeeklyLaborEntry,
    ItemTotalCost,
)
from app.services.analytics_facts import (
    record_item_sale,
    record_customer_order,
    record_receiving,
    record_inventory_snapshot,
    record_labor_summary,
    record_weekly_labor_summary,
    record_cost_margin,
)


class AnalyticsFactBackfill:
    def __init__(self, session):
        self.db = session

    def _backfill(self, model, record_fns, batch_size=500):
        count = 0
        query = model.query.order_by(model.id)
        for row in query.yield_per(batch_size):
            for record_fn in record_fns:
                record_fn(row)
            count += 1
            if count % batch_size == 0:
                self.db.session.commit()
        self.db.session.commit()
        return count

    def run(self):
        totals = {
            'sales_record': self._backfill(SalesRecord, (record_item_sale, record_customer_order)),
            'receiving_log': self._backfill(ReceivingLog, (record_receiving,)),
            'inventory_count': self._backfill(ItemInventory, (record_inventory_snapshot,)),
            'daily_log': self._backfill(DailyLog, (record_labor_summary,)),
            'weekly_labor_summary': self._backfill(WeeklyLaborEntry, (record_weekly_labor_summary,)),
            'item_total_cost': self._backfill(ItemTotalCost, (record_cost_margin,)),
        }
        return totals
