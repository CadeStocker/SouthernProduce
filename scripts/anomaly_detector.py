"""Cross-domain anomaly detector (rule-based + EWMA statistics).

Run manually or from cron: `python scripts/anomaly_detector.py`.

Structure
---------
``DetectorRun`` owns the shared machinery: per-company incremental watermarks,
EWMA statistics, z-score testing, anomaly recording and notification. Each
business domain gets a small ``BaseDetector`` subclass that declares which table
it walks and what it considers wrong. ``DETECTORS`` is the registry.

Adding a detector
-----------------
1. Subclass ``BaseDetector``, set ``domain`` (a key from
   ``services.analytics_domains``), ``source_table``, ``model_name`` and the
   company/date columns.
2. Implement ``check(row)``, calling ``self.flag(...)`` for rules and
   ``self.track(...)`` for metrics that should be compared to their own history.
3. Append the class to ``DETECTORS``.

Everything else — watermarking, scoping to one company, notification
throttling — is inherited. A detector that raises is logged and skipped so one
bad domain cannot stop the others.
"""

import logging
from datetime import datetime

from app import create_app, db


logger = logging.getLogger(__name__)


def make_app():
    # create and configure Flask app context for DB access
    return create_app()


# Tunables, overridable via Flask config with the same (upper-cased) name.
DEFAULT_THRESHOLDS = {
    # statistics
    'ewma_alpha': 0.1,
    'z_threshold': 2.5,
    # pricing
    'margin_threshold': 0.20,
    'price_consistency_pct': 0.10,
    # efficiency
    'max_man_hours_per_case': 0.75,
    'max_labor_ratio': 0.35,
    'max_overtime_share': 0.20,
    # receiving
    'receiving_price_variance_pct': 15.0,
    'min_receiving_temp': 28.0,
    'max_receiving_temp': 45.0,
    # inventory
    'inventory_swing_pct': 50.0,
}


class BaseDetector:
    """One domain's worth of checks over one incrementally-walked table.

    Subclasses declare the table and implement ``check``. The base class walks
    only rows belonging to ``run.company_id`` that are newer than the last
    watermark for this (source_table, company) pair.
    """

    domain = None
    source_table = None
    model_name = None
    # Column holding the owning company; None means the table is not scoped.
    company_column = 'company_id'

    def __init__(self, run):
        self.run = run
        self.db = run.db
        self.company_id = run.company_id

    # -- configuration -----------------------------------------------------

    def threshold(self, name):
        return self.run.threshold(name)

    @property
    def model(self):
        from app import models
        return getattr(models, self.model_name)

    # -- row selection -----------------------------------------------------

    def rows(self):
        """New rows for this company since the last run, oldest first."""
        model = self.model
        job_run = self.run.get_jobrun(self.source_table)
        last_id = job_run.last_processed_id or 0

        query = model.query.filter(model.id > last_id)
        if self.company_column:
            query = query.filter(
                getattr(model, self.company_column) == self.company_id
            )
        return job_run, query.order_by(model.id).all()

    def run_checks(self):
        job_run, rows = self.rows()
        max_seen = job_run.last_processed_id or 0

        for row in rows:
            max_seen = max(max_seen, row.id)
            try:
                self.check(row)
            except Exception:
                logger.exception(
                    'Detector %s failed on %s id=%s',
                    type(self).__name__, self.source_table, row.id,
                )

        job_run.touch(last_id=max_seen, last_at=datetime.utcnow())
        self.db.session.add(job_run)
        return len(rows)

    def check(self, row):  # pragma: no cover - abstract
        raise NotImplementedError

    # -- recording ---------------------------------------------------------

    def flag(self, entity_type, entity_id, metric, expected, actual, rule,
             explanation, dollar_impact=None, severity=None, z_score=None):
        """Record a rule-based finding for this domain."""
        return self.run.record_anomaly(
            domain=self.domain,
            entity_type=entity_type,
            entity_id=entity_id,
            metric=metric,
            expected=expected,
            actual=actual,
            z_score=z_score,
            rule=rule,
            dollar_impact=dollar_impact,
            explanation=explanation,
            severity=severity,
        )

    def track(self, entity_type, entity_id, metric, value, impact_multiplier=1.0,
              unit=''):
        """Compare a value to its own history, then fold it into that history.

        The z-score test runs against the statistics as they were *before* this
        value, so a single large jump is caught rather than partly absorbed into
        the mean it is being compared against.
        """
        if value is None:
            return
        self.run.check_statistical_anomaly(
            entity_type, entity_id, metric, value,
            domain=self.domain, impact_multiplier=impact_multiplier, unit=unit,
        )
        self.run.upsert_entity_stat(entity_type, entity_id, metric, value)


# ---------------------------------------------------------------------------
# Pricing & margin
# ---------------------------------------------------------------------------

class PriceHistoryDetector(BaseDetector):
    """Quoted customer prices: non-positive, below cost, thin margin, drift."""

    domain = 'pricing'
    source_table = 'price_history'
    model_name = 'PriceHistory'

    def check(self, row):
        item_id = row.item_id
        price = row.price

        if price is None or price <= 0:
            self.flag(
                'item', item_id, 'price', expected=None, actual=price,
                rule='negative_or_zero_value',
                explanation=f"price is non-positive for item {item_id} (price={price})",
            )
            return

        item_cost = self.run.latest_item_cost(item_id)
        if item_cost is not None:
            self._check_against_cost(item_id, price, item_cost)

        current = self.run.current_item_price(item_id)
        if current and current.price and price:
            pct_diff = abs(price - current.price) / current.price if current.price else 0
            if pct_diff > self.threshold('price_consistency_pct'):
                self.flag(
                    'item', item_id, 'data_consistency_price',
                    expected=current.price, actual=price,
                    rule='data_consistency',
                    dollar_impact=abs(price - current.price),
                    explanation=(
                        f"PriceHistory price ({price}) differs from CurrentItemPrice "
                        f"({current.price}) by {pct_diff:.1%} for item {item_id}"
                    ),
                )

        self.track('item', item_id, 'price', price,
                   impact_multiplier=self.run.price_impact_volume(item_id), unit='$')

    def _check_against_cost(self, item_id, price, expected_cost):
        if price <= expected_cost:
            self.flag(
                'item', item_id, 'price_vs_cost', expected=expected_cost, actual=price,
                rule='price_below_cost', dollar_impact=abs(price - expected_cost),
                explanation=f"price ({price}) <= total_cost ({expected_cost}) for item {item_id}",
            )

        margin_pct = (price - expected_cost) / price
        if margin_pct < self.threshold('margin_threshold'):
            self.flag(
                'item', item_id, 'margin_pct', expected=self.threshold('margin_threshold'),
                actual=margin_pct, rule='margin_below_threshold',
                dollar_impact=abs(price - expected_cost),
                explanation=(
                    f"margin {margin_pct:.2%} below threshold "
                    f"{self.threshold('margin_threshold'):.2%} for item {item_id}"
                ),
            )


class CurrentPriceDetector(BaseDetector):
    """The single source of truth for list price: non-positive or below cost."""

    domain = 'pricing'
    source_table = 'current_item_price'
    model_name = 'CurrentItemPrice'

    def check(self, row):
        item_id = row.item_id
        price = row.price

        if price is None or price <= 0:
            self.flag(
                'item', item_id, 'price', expected=None, actual=price,
                rule='negative_or_zero_value',
                explanation=f"current price non-positive for item {item_id} (price={price})",
            )
            return

        item_cost = self.run.latest_item_cost(item_id)
        if item_cost is not None and price <= item_cost:
            self.flag(
                'item', item_id, 'price_vs_cost', expected=item_cost, actual=price,
                rule='price_below_cost', dollar_impact=abs(price - item_cost),
                explanation=f"current price ({price}) <= total_cost ({item_cost}) for item {item_id}",
            )

        self.track('item', item_id, 'price', price,
                   impact_multiplier=self.run.price_impact_volume(item_id), unit='$')


class RawProductCostDetector(BaseDetector):
    """Raw product cost history: non-positive values and cost spikes."""

    domain = 'pricing'
    source_table = 'cost_history'
    model_name = 'CostHistory'

    def check(self, row):
        raw_id = row.raw_product_id
        cost = row.cost

        if cost is None or cost <= 0:
            self.flag(
                'raw_product', raw_id, 'cost', expected=None, actual=cost,
                rule='negative_or_zero_value',
                explanation=f"raw product cost non-positive for raw_product {raw_id} (cost={cost})",
            )
            return

        self.track('raw_product', raw_id, 'cost', cost, unit='$')


class ItemCostDetector(BaseDetector):
    """Landed item cost: component shares that don't add up, and cost spikes."""

    domain = 'pricing'
    source_table = 'item_total_cost'
    model_name = 'ItemTotalCost'

    def check(self, row):
        item_id = row.item_id
        total = row.total_cost

        if total is None or total <= 0:
            self.flag(
                'item', item_id, 'total_cost', expected=None, actual=total,
                rule='negative_or_zero_value',
                explanation=f"total cost non-positive for item {item_id} (total_cost={total})",
            )
            return

        components = sum(value or 0.0 for value in (
            row.ranch_cost, row.packaging_cost, row.raw_product_cost,
            row.labor_cost, row.designation_cost,
        ))
        # A penny of float drift is expected; a real mismatch means a component
        # was updated without recomputing the total.
        if abs(components - total) > 0.01:
            self.flag(
                'item', item_id, 'cost_components', expected=components, actual=total,
                rule='data_consistency', dollar_impact=abs(components - total),
                explanation=(
                    f"total_cost ({total:.2f}) does not match the sum of its components "
                    f"({components:.2f}) for item {item_id}"
                ),
            )

        self.track('item', item_id, 'total_cost', total, unit='$')


# ---------------------------------------------------------------------------
# Labor & efficiency
# ---------------------------------------------------------------------------

class EfficiencyDetector(BaseDetector):
    """Daily production efficiency: man-hours per case, payroll share, overtime.

    Anomalies are attributed to the company for the day rather than to an item,
    because DailyLog is a plant-wide roll-up.
    """

    domain = 'efficiency'
    source_table = 'daily_log'
    model_name = 'DailyLog'

    def check(self, row):
        cases = row.items or 0
        hours = row.labor_hours or 0.0
        payroll = row.payroll_cost or 0.0
        sales = row.sales or 0.0
        entity_id = row.company_id

        if hours > 0 and cases <= 0:
            self.flag(
                'company', entity_id, 'cases_produced', expected=None, actual=cases,
                rule='data_consistency', severity='high', dollar_impact=payroll,
                explanation=(
                    f"{hours:.1f} labor hours logged on {row.date} with no cases produced; "
                    f"payroll of ${payroll:.2f} has nothing to absorb it"
                ),
            )
        elif cases > 0 and hours <= 0:
            self.flag(
                'company', entity_id, 'labor_hours', expected=None, actual=hours,
                rule='data_consistency', severity='high',
                explanation=f"{cases} cases produced on {row.date} with no labor hours logged",
            )

        if cases > 0 and hours > 0:
            self._check_per_case(row, entity_id, cases, hours, payroll)

        if sales > 0 and payroll > 0:
            self._check_labor_ratio(row, entity_id, payroll, sales)

        if hours > 0:
            overtime_share = (row.overtime_hours or 0.0) / hours
            if overtime_share > self.threshold('max_overtime_share'):
                self.flag(
                    'company', entity_id, 'overtime_share',
                    expected=self.threshold('max_overtime_share'), actual=overtime_share,
                    rule='overtime_above_threshold',
                    dollar_impact=payroll * overtime_share,
                    explanation=(
                        f"overtime was {overtime_share:.1%} of hours on {row.date}, above the "
                        f"{self.threshold('max_overtime_share'):.0%} threshold"
                    ),
                )
            self.track('company', entity_id, 'overtime_share', overtime_share)

    def _check_per_case(self, row, entity_id, cases, hours, payroll):
        man_hours_per_case = hours / cases
        cost_per_case = payroll / cases
        limit = self.threshold('max_man_hours_per_case')

        if man_hours_per_case > limit:
            # Excess hours priced at the day's own average hourly cost.
            excess_hours = (man_hours_per_case - limit) * cases
            hourly = payroll / hours if hours else 0.0
            self.flag(
                'company', entity_id, 'man_hours_per_case',
                expected=limit, actual=man_hours_per_case,
                rule='efficiency_below_threshold',
                dollar_impact=excess_hours * hourly,
                explanation=(
                    f"{man_hours_per_case:.3f} man-hours per case on {row.date} exceeds the "
                    f"{limit:.3f} target across {cases} cases"
                ),
            )

        # Impact of a per-case move is that move times the day's volume.
        self.track('company', entity_id, 'man_hours_per_case', man_hours_per_case,
                   impact_multiplier=cases * (payroll / hours if hours else 0.0))
        self.track('company', entity_id, 'cost_per_case', cost_per_case,
                   impact_multiplier=cases, unit='$')

    def _check_labor_ratio(self, row, entity_id, payroll, sales):
        labor_ratio = payroll / sales
        limit = self.threshold('max_labor_ratio')

        if labor_ratio > limit:
            self.flag(
                'company', entity_id, 'labor_ratio', expected=limit, actual=labor_ratio,
                rule='labor_ratio_above_threshold',
                dollar_impact=(labor_ratio - limit) * sales,
                explanation=(
                    f"labor was {labor_ratio:.1%} of ${sales:,.2f} in sales on {row.date}, "
                    f"above the {limit:.0%} threshold"
                ),
            )

        self.track('company', entity_id, 'labor_ratio', labor_ratio, impact_multiplier=sales)


class WeeklyLaborDetector(BaseDetector):
    """Weekly pay-group summaries: hourly cost drift and overtime spread."""

    domain = 'efficiency'
    source_table = 'weekly_labor_summary'
    model_name = 'WeeklyLaborEntry'

    def check(self, row):
        entity_id = row.pay_group_id
        total_hours = (row.regular_hours or 0.0) + (row.overtime_hours or 0.0)

        if row.cost_per_hour is not None and row.cost_per_hour > 0:
            self.track('pay_group', entity_id, 'cost_per_hour', row.cost_per_hour,
                       impact_multiplier=total_hours, unit='$')

        if total_hours > 0:
            overtime_share = (row.overtime_hours or 0.0) / total_hours
            if overtime_share > self.threshold('max_overtime_share'):
                self.flag(
                    'pay_group', entity_id, 'overtime_share',
                    expected=self.threshold('max_overtime_share'), actual=overtime_share,
                    rule='overtime_above_threshold',
                    dollar_impact=(row.pay or 0.0) * overtime_share,
                    explanation=(
                        f"pay group {entity_id} ran {overtime_share:.1%} overtime for the week "
                        f"of {row.week_start_date}, above the "
                        f"{self.threshold('max_overtime_share'):.0%} threshold"
                    ),
                )

        if row.number_in_pay_group and row.number_in_pay_group > 0:
            self.track('pay_group', entity_id, 'average_hours_per_employee',
                       row.average_hours_per_employee)


# ---------------------------------------------------------------------------
# Receiving & suppliers
# ---------------------------------------------------------------------------

class ReceivingDetector(BaseDetector):
    """Inbound deliveries: price vs. market, cost per unit, temperature, gaps."""

    domain = 'receiving'
    source_table = 'receiving_log'
    model_name = 'ReceivingLog'

    def check(self, row):
        raw_id = row.raw_product_id
        quantity = row.quantity_received or 0

        if quantity <= 0:
            self.flag(
                'raw_product', raw_id, 'quantity_received', expected=None, actual=quantity,
                rule='negative_or_zero_value',
                explanation=f"receiving log {row.id} recorded {quantity} units for raw_product {raw_id}",
            )

        self._check_temperature(row, raw_id)

        if row.price_paid is None:
            self.flag(
                'raw_product', raw_id, 'price_paid', expected=None, actual=None,
                rule='data_completeness', severity='low',
                explanation=(
                    f"receiving log {row.id} for raw_product {raw_id} has no price paid, so its "
                    f"cost cannot be compared to market or rolled into landed cost"
                ),
            )
            return

        self._check_against_market(row, raw_id, quantity)

        # Cost per unit is the comparable figure across deliveries of different
        # sizes; raw price_paid is not.
        pack_size = row.pack_size or 1.0
        cost_per_unit = row.price_paid / pack_size if pack_size else row.price_paid
        self.track('raw_product', raw_id, 'receiving_cost_per_unit', cost_per_unit,
                   impact_multiplier=quantity * pack_size, unit='$')
        self.track('raw_product', raw_id, 'quantity_received', float(quantity))

    def _check_temperature(self, row, raw_id):
        temperature = row.temperature
        if temperature is None:
            return
        low = self.threshold('min_receiving_temp')
        high = self.threshold('max_receiving_temp')
        if low <= temperature <= high:
            return
        self.flag(
            'raw_product', raw_id, 'receiving_temperature',
            expected=high if temperature > high else low, actual=temperature,
            rule='temperature_out_of_range', severity='high',
            explanation=(
                f"receiving log {row.id} recorded {temperature}°F for raw_product {raw_id}, "
                f"outside the acceptable {low}-{high}°F range"
            ),
        )

    def _check_against_market(self, row, raw_id, quantity):
        try:
            comparison = row.get_price_comparison()
        except Exception:
            logger.exception('Price comparison failed for receiving log %s', row.id)
            return

        if not comparison or not comparison.get('master_price'):
            return

        percentage = comparison.get('percentage') or 0.0
        if abs(percentage) < self.threshold('receiving_price_variance_pct'):
            return

        direction = 'above' if percentage > 0 else 'below'
        difference = comparison.get('difference') or 0.0
        self.flag(
            'raw_product', raw_id, 'price_paid_vs_market',
            expected=comparison['master_price'], actual=comparison['price_paid'],
            rule='receiving_price_off_market',
            dollar_impact=abs(difference) * (row.pack_size or 1.0) * quantity,
            explanation=(
                f"paid ${comparison['price_paid']:.2f} for raw_product {raw_id}, "
                f"{abs(percentage):.1f}% {direction} the ${comparison['master_price']:.2f} "
                f"market cost recorded {comparison.get('market_date')}"
            ),
        )


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class InventoryDetector(BaseDetector):
    """Finished-goods counts: impossible values and unexplained swings."""

    domain = 'inventory'
    source_table = 'inventory_count'
    model_name = 'ItemInventory'

    def check(self, row):
        item_id = row.item_id
        quantity = row.quantity

        if quantity is None or quantity < 0:
            self.flag(
                'item', item_id, 'inventory_quantity', expected=None, actual=quantity,
                rule='negative_or_zero_value', severity='high',
                explanation=(
                    f"inventory count {row.id} recorded {quantity} units of item {item_id}; "
                    f"on-hand quantity cannot be negative"
                ),
            )
            return

        self._check_swing(row, item_id, quantity)
        self.track('item', item_id, 'inventory_quantity', float(quantity),
                   impact_multiplier=self.run.latest_item_cost(item_id) or 0.0, unit='$')

    def _check_swing(self, row, item_id, quantity):
        previous = self.run.previous_inventory_count(item_id, row)
        if previous is None or not previous.quantity:
            return

        change_pct = (quantity - previous.quantity) / abs(previous.quantity) * 100.0
        if abs(change_pct) < self.threshold('inventory_swing_pct'):
            return

        unit_cost = self.run.latest_item_cost(item_id) or 0.0
        direction = 'up' if change_pct > 0 else 'down'
        self.flag(
            'item', item_id, 'inventory_swing',
            expected=previous.quantity, actual=quantity,
            rule='inventory_swing_above_threshold',
            dollar_impact=abs(quantity - previous.quantity) * unit_cost,
            explanation=(
                f"item {item_id} moved {direction} {abs(change_pct):.0f}% between counts "
                f"({previous.quantity} on {previous.count_date:%Y-%m-%d} to {quantity} on "
                f"{row.count_date:%Y-%m-%d})"
            ),
        )


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------

class SalesDetector(BaseDetector):
    """Individual sales: non-positive values and unit prices off their history."""

    domain = 'sales'
    source_table = 'sales_record'
    model_name = 'SalesRecord'

    def check(self, row):
        quantity = row.quantity_sold or 0
        unit_price = row.unit_price

        if quantity <= 0:
            self.flag(
                'customer', row.customer_id or 0, 'quantity_sold',
                expected=None, actual=quantity, rule='negative_or_zero_value',
                explanation=f"sales record {row.id} recorded {quantity} units sold",
            )

        if unit_price is None or unit_price <= 0:
            self.flag(
                'customer', row.customer_id or 0, 'unit_price',
                expected=None, actual=unit_price, rule='negative_or_zero_value',
                explanation=f"sales record {row.id} recorded a unit price of {unit_price}",
            )
            return

        # Track price per designation: it is the finest grain SalesRecord has
        # until it carries item_id.
        self.track('item_designation', row.item_designation_id, 'unit_price',
                   unit_price, impact_multiplier=quantity, unit='$')


DETECTORS = (
    PriceHistoryDetector,
    CurrentPriceDetector,
    RawProductCostDetector,
    ItemCostDetector,
    EfficiencyDetector,
    WeeklyLaborDetector,
    ReceivingDetector,
    InventoryDetector,
    SalesDetector,
)


class DetectorRun:
    """Runs every registered detector for a single company.

    Shared machinery lives here so detectors stay small: watermarks, EWMA
    statistics, z-score testing, anomaly recording, notification and the
    per-run lookup caches.
    """

    def __init__(self, session, company_id=None, detectors=None, thresholds=None):
        self.db = session
        self.company_id = company_id
        self.detector_classes = detectors if detectors is not None else DETECTORS
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

        from app.models import (
            CurrentItemPrice, ItemTotalCost, ItemInventory, EntityStat, Anomaly, JobRun,
        )
        self.CurrentItemPrice = CurrentItemPrice
        self.ItemTotalCost = ItemTotalCost
        self.ItemInventory = ItemInventory
        self.EntityStat = EntityStat
        self.Anomaly = Anomaly
        self.JobRun = JobRun

        # Per-run caches; a detector may ask for the same item cost many times.
        self._item_cost_cache = {}
        self._current_price_cache = {}

    # -- configuration -----------------------------------------------------

    def threshold(self, name):
        """Threshold value, letting Flask config override the default."""
        try:
            from flask import current_app
            configured = current_app.config.get(f'ANOMALY_{name.upper()}')
            if configured is not None:
                return float(configured)
        except Exception:
            pass
        return self.thresholds[name]

    # -- watermarks --------------------------------------------------------

    def get_jobrun(self, source_table):
        """Per-company watermark for a source table.

        Keyed ``"<table>:company:<id>"`` so companies advance independently.
        Before Anomaly rows carried a company, a single global key was shared,
        which meant the first company processed everything and the rest saw
        nothing. When a legacy global key exists its position seeds the new
        per-company key, so upgrading does not re-flag years of history.
        """
        key = f'{source_table}:company:{self.company_id}'
        job_run = self.JobRun.query.filter_by(source_table=key).first()
        if job_run:
            return job_run

        legacy = self.JobRun.query.filter_by(source_table=source_table).first()
        job_run = self.JobRun(source_table=key)
        if legacy and legacy.last_processed_id:
            job_run.last_processed_id = legacy.last_processed_id
        self.db.session.add(job_run)
        self.db.session.flush()
        return job_run

    # -- shared lookups ----------------------------------------------------

    def latest_item_cost(self, item_id):
        """Most recent landed total cost for an item, or None."""
        if item_id in self._item_cost_cache:
            return self._item_cost_cache[item_id]

        row = self.ItemTotalCost.query.filter_by(item_id=item_id).order_by(
            self.ItemTotalCost.date.desc()
        ).first()
        cost = row.total_cost if row else None
        self._item_cost_cache[item_id] = cost
        return cost

    def current_item_price(self, item_id):
        if item_id not in self._current_price_cache:
            self._current_price_cache[item_id] = self.CurrentItemPrice.query.filter_by(
                item_id=item_id
            ).first()
        return self._current_price_cache[item_id]

    def price_impact_volume(self, item_id):
        """Rough volume to scale a per-unit price move into dollars.

        Landed cost is the best proxy the schema offers today; replace with
        period sales volume once item_sale facts carry item_id.
        """
        return self.latest_item_cost(item_id) or 1.0

    def previous_inventory_count(self, item_id, current):
        """The count immediately before ``current`` for the same item."""
        return self.ItemInventory.query.filter(
            self.ItemInventory.item_id == item_id,
            self.ItemInventory.company_id == current.company_id,
            self.ItemInventory.id != current.id,
            self.ItemInventory.count_date <= current.count_date,
        ).order_by(
            self.ItemInventory.count_date.desc(), self.ItemInventory.id.desc()
        ).first()

    # -- statistics --------------------------------------------------------

    def upsert_entity_stat(self, entity_type, entity_id, metric, value, alpha=None):
        """Fold a value into the EWMA statistics for (entity, metric)."""
        alpha = alpha if alpha is not None else self.threshold('ewma_alpha')
        stat = self.EntityStat.query.filter_by(
            entity_type=entity_type, entity_id=entity_id, metric=metric, window='ewma',
        ).first()
        if not stat:
            stat = self.EntityStat(
                entity_type=entity_type, entity_id=entity_id, metric=metric, window='ewma',
            )
            self.db.session.add(stat)
            self.db.session.flush()
        stat.update_ewma(value, alpha=alpha)
        self.db.session.add(stat)
        return stat

    def check_statistical_anomaly(self, entity_type, entity_id, metric, value, stat=None,
                                  domain=None, impact_multiplier=1.0, unit=''):
        """Flag ``value`` if it is more than z_threshold from its own history.

        Reads the statistics as they stand *before* ``value`` is folded in, and
        does nothing until at least two observations exist — with one point the
        standard deviation is zero and everything looks anomalous.

        ``stat`` may be passed by a caller that already loaded it; otherwise it
        is looked up here.
        """
        if stat is None:
            stat = self.EntityStat.query.filter_by(
                entity_type=entity_type, entity_id=entity_id, metric=metric, window='ewma',
            ).first()

        if not stat or stat.mean is None or stat.stddev is None or stat.count < 2:
            return None
        if not stat.stddev:
            return None

        try:
            z_score = (float(value) - float(stat.mean)) / float(stat.stddev)
        except (TypeError, ValueError, ZeroDivisionError):
            return None

        if abs(z_score) < self.threshold('z_threshold'):
            return None

        expected = float(stat.mean)
        deviation = abs(float(value) - expected)
        direction = 'higher' if float(value) > expected else 'lower'

        return self.record_anomaly(
            domain=domain,
            entity_type=entity_type,
            entity_id=entity_id,
            metric=metric,
            expected=expected,
            actual=value,
            z_score=z_score,
            rule='statistical_zscore',
            dollar_impact=deviation * float(impact_multiplier or 0.0),
            explanation=(
                f"{metric} for {entity_type} {entity_id} is {direction} by "
                f"{unit}{deviation:.2f} (z={z_score:.2f}) vs its EWMA mean of "
                f"{unit}{expected:.2f}."
            ),
        )

    # -- recording ---------------------------------------------------------

    def severity_for(self, rule, dollar_impact):
        """Severity heuristic: correctness rules are high, others scale by money."""
        if rule in ('data_consistency', 'price_below_cost', 'temperature_out_of_range'):
            return 'high'
        if rule == 'data_completeness':
            return 'low'
        if dollar_impact and dollar_impact > 1000:
            return 'high'
        if dollar_impact and dollar_impact > 100:
            return 'medium'
        return 'low'

    def record_anomaly(self, entity_type, entity_id, metric, expected, actual,
                       z_score=None, rule=None, dollar_impact=None, explanation=None,
                       severity=None, domain=None):
        """Persist an anomaly. ``domain`` is optional; findings without one show
        under "Unclassified" rather than being dropped."""
        anomaly = self.Anomaly(
            domain=domain,
            company_id=self.company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            metric=metric,
            expected_value=expected,
            actual_value=actual,
            z_score=z_score,
            rule_triggered=rule,
            severity=severity or self.severity_for(rule, dollar_impact),
            dollar_impact=dollar_impact,
            explanation=explanation,
            detected_at=datetime.utcnow(),
        )
        self.db.session.add(anomaly)
        self.db.session.flush()  # Ensure anomaly has an ID for notifications

        if self.company_id:
            self._create_notification_for_anomaly(anomaly)
        return anomaly

    def _create_notification_for_anomaly(self, anomaly):
        """Create a notification for the anomaly if throttling allows it."""
        try:
            from app.utils.notification_utils import (
                should_notify_anomaly, create_anomaly_notification,
            )
            if should_notify_anomaly(anomaly, self.company_id):
                create_anomaly_notification(anomaly, self.company_id, commit=False)
        except Exception:
            # Never let notification problems lose a detected anomaly.
            logger.exception('Failed to create anomaly notification')

    # -- entry point -------------------------------------------------------

    def run(self):
        """Run every registered detector, then commit once.

        A detector that blows up is logged and skipped; the rest still run and
        their findings are still saved.
        """
        processed = {}
        for detector_class in self.detector_classes:
            detector = detector_class(self)
            try:
                processed[detector_class.__name__] = detector.run_checks()
            except Exception:
                logger.exception('Detector %s failed', detector_class.__name__)
                processed[detector_class.__name__] = None

        try:
            self.db.session.commit()
        except Exception:
            self.db.session.rollback()
            logger.exception('Error committing anomalies for company %s', self.company_id)
            raise
        return processed


# Kept so existing callers (insights.run_insights_now, tests, cron) keep working.
AnomalyDetector = DetectorRun


def main():
    """Run every detector for every company.

    Each company is committed independently so one company's bad data cannot
    discard another's findings.
    """
    logging.basicConfig(level=logging.INFO)
    app = make_app()
    with app.app_context():
        from app.models import Company

        for company in Company.query.all():
            try:
                DetectorRun(db, company_id=company.id).run()
            except Exception:
                logger.exception('Error running detector for company %s', company.id)
                db.session.rollback()


if __name__ == '__main__':
    main()
