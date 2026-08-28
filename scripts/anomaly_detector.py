"""Simple anomaly detector runner (rule-based + EWMA stats).

Run manually or from cron: `python scripts/anomaly_detector.py`.

This initial implementation implements rule-based checks and incremental
EWMA updates for PriceHistory, CurrentItemPrice, and CostHistory.
"""

from datetime import datetime
from app import create_app, db


def make_app():
    # create and configure Flask app context for DB access
    return create_app()


class AnomalyDetector:
    def __init__(self, session, company_id=None):
        self.db = session
        self.company_id = company_id
        from app.models import (
            PriceHistory,
            CurrentItemPrice,
            CostHistory,
            ItemTotalCost,
            EntityStat,
            Anomaly,
            JobRun,
            Company,
        )
        self.PriceHistory = PriceHistory
        self.CurrentItemPrice = CurrentItemPrice
        self.CostHistory = CostHistory
        self.ItemTotalCost = ItemTotalCost
        self.EntityStat = EntityStat
        self.Anomaly = Anomaly
        self.JobRun = JobRun
        self.Company = Company

        # rule tuning
        self.margin_threshold = 0.20
        self.ewma_alpha = 0.1
        # statistical tuning
        self.z_threshold = 2.5

    def get_jobrun(self, source_table):
        """
        track most recent processed ID for each source table to allow incremental processing
        """

        jr = self.JobRun.query.filter_by(source_table=source_table).first()
        if not jr:
            jr = self.JobRun(source_table=source_table)
            self.db.session.add(jr)
            self.db.session.commit()
        return jr

    def upsert_entity_stat(self, entity_type, entity_id, metric, value, alpha=None):
        """
        update the stats for given metric
        """

        alpha = alpha if alpha is not None else self.ewma_alpha
        stat = self.EntityStat.query.filter_by(entity_type=entity_type, entity_id=entity_id, metric=metric, window='ewma').first()
        if not stat:
            stat = self.EntityStat(entity_type=entity_type, entity_id=entity_id, metric=metric, window='ewma')
            self.db.session.add(stat)
            self.db.session.flush()
        stat.update_ewma(value, alpha=alpha)
        self.db.session.add(stat)

    def check_statistical_anomaly(self, entity_type, entity_id, metric, value, stat):
        """
        Compute z-score against existing stat (prior to including new value) and record anomaly if threshold exceeded.
        """
        if not stat or stat.mean is None or stat.stddev is None or stat.count < 2:
            return

        try:
            std = stat.stddev
            if not std or std == 0:
                return
            z = (float(value) - float(stat.mean)) / float(std)
        except Exception:
            return

        if abs(z) >= self.z_threshold:
            expected = stat.mean
            # heuristic dollar impact: use ItemTotalCost.total_cost when available for prices
            dollar_impact = None
            if metric in ('price', 'price_vs_cost'):
                try:
                    itc = self.ItemTotalCost.query.filter_by(item_id=entity_id).order_by(self.ItemTotalCost.date.desc()).first()
                    volume = itc.total_cost if itc and itc.total_cost else 1
                except Exception:
                    volume = 1
                dollar_impact = abs(float(value) - float(expected)) * float(volume)
            else:
                dollar_impact = abs(float(value) - float(expected))

            explanation = (
                f"{metric} for {entity_type} {entity_id} is {('higher' if float(value) > float(expected) else 'lower')} "
                f"by {abs(float(value) - float(expected)):.2f} (z={z:.2f}) vs EWMA mean {expected:.2f}."
            )
            self.record_anomaly(entity_type, entity_id, metric, expected=expected, actual=value, z_score=z, rule='statistical_zscore', dollar_impact=dollar_impact, explanation=explanation)

    def record_anomaly(self, entity_type, entity_id, metric, expected, actual, z_score=None, rule=None, dollar_impact=None, explanation=None, severity=None):
        """
        Record anomaly with severity heuristics. Creates notifications if company_id is set.
        """

        if severity is None:
            # simple heuristic for severity
            sev = 'low'
            if rule == 'data_consistency' or rule == 'price_below_cost':
                sev = 'high'
            elif dollar_impact and dollar_impact > 1000:
                sev = 'high'
            elif dollar_impact and dollar_impact > 100:
                sev = 'medium'
            else:
                sev = 'low'
        else:
            sev = severity

        anomaly = self.Anomaly(
            entity_type=entity_type,
            entity_id=entity_id,
            metric=metric,
            expected_value=expected,
            actual_value=actual,
            z_score=z_score,
            rule_triggered=rule,
            severity=sev,
            dollar_impact=dollar_impact,
            explanation=explanation,
            detected_at=datetime.utcnow(),
        )
        self.db.session.add(anomaly)
        self.db.session.flush()  # Ensure anomaly has an ID for notifications

        # Create notifications if company_id is available
        if self.company_id:
            self._create_notification_for_anomaly(anomaly)

    def _create_notification_for_anomaly(self, anomaly):
        """Create a notification for the anomaly if conditions are met."""
        try:
            from app.utils.notification_utils import should_notify_anomaly, create_anomaly_notification

            if should_notify_anomaly(anomaly, self.company_id):
                create_anomaly_notification(anomaly, self.company_id, commit=False)
        except Exception as e:
            # Log but don't fail the detector if notification creation fails
            import logging
            logging.error(f"Failed to create anomaly notification: {e}")

    def process_price_history(self):
        """
        look at all price history records since last run and check for anomalies, updating stats as we go
        """

        jr = self.get_jobrun('price_history')
        last_id = jr.last_processed_id or 0
        query = self.PriceHistory.query.filter(self.PriceHistory.id > last_id).order_by(self.PriceHistory.id)
        max_seen = last_id

        for row in query.all():
            max_seen = max(max_seen, row.id)
            item_id = row.item_id
            price = row.price

            # negative or zero check
            if price is None or price <= 0:
                explanation = f"price is non-positive for item {item_id} (price={price})"
                self.record_anomaly('item', item_id, 'price', expected=None, actual=price, rule='negative_or_zero_value', explanation=explanation)

            # find latest item total cost if available
            itc = self.ItemTotalCost.query.filter_by(item_id=item_id).order_by(self.ItemTotalCost.date.desc()).first()
            if itc:
                expected_cost = itc.total_cost
                # price_below_cost
                if price <= expected_cost:
                    explanation = f"price ({price}) <= total_cost ({expected_cost}) for item {item_id}"
                    self.record_anomaly('item', item_id, 'price_vs_cost', expected=expected_cost, actual=price, rule='price_below_cost', explanation=explanation, dollar_impact=abs(price - expected_cost))

                # margin below threshold
                try:
                    margin_pct = (price - expected_cost) / price if price and price != 0 else None
                except Exception:
                    margin_pct = None
                if margin_pct is not None and margin_pct < self.margin_threshold:
                    explanation = f"margin {margin_pct:.2%} below threshold {self.margin_threshold:.2%} for item {item_id}"
                    self.record_anomaly('item', item_id, 'margin_pct', expected=None, actual=margin_pct, rule='margin_below_threshold', explanation=explanation, dollar_impact=abs(price - expected_cost))

            # cross-app consistency: compare price history price vs current item price
            try:
                cip = self.CurrentItemPrice.query.filter_by(item_id=item_id).first()
                if cip and cip.price and price:
                    # percent difference
                    pct_diff = abs(price - cip.price) / cip.price if cip.price != 0 else 0
                    if pct_diff > 0.10:
                        explanation = f"PriceHistory price ({price}) differs from CurrentItemPrice ({cip.price}) by {pct_diff:.1%} for item {item_id}"
                        self.record_anomaly('item', item_id, 'data_consistency_price', expected=cip.price, actual=price, rule='data_consistency', explanation=explanation, dollar_impact=abs(price - cip.price))
            except Exception:
                pass

            # update entity stats for price
            try:
                # check statistical anomaly against existing stats before updating
                stat = self.EntityStat.query.filter_by(entity_type='item', entity_id=item_id, metric='price', window='ewma').first()
                self.check_statistical_anomaly('item', item_id, 'price', price, stat)
                self.upsert_entity_stat('item', item_id, 'price', price)
            except Exception:
                pass

        # update watermark
        jr.touch(last_id=max_seen if max_seen > last_id else last_id, last_at=datetime.utcnow())
        self.db.session.add(jr)

    def process_current_prices(self):
        """
        look at all current item prices since last run and check for anomalies, updating stats as we go
        """

        jr = self.get_jobrun('current_item_price')
        last_id = jr.last_processed_id or 0
        query = self.CurrentItemPrice.query.filter(self.CurrentItemPrice.id > last_id).order_by(self.CurrentItemPrice.id)
        max_seen = last_id
        for row in query.all():
            max_seen = max(max_seen, row.id)
            item_id = row.item_id
            price = row.price

            if price is None or price <= 0:
                explanation = f"current price non-positive for item {item_id} (price={price})"
                self.record_anomaly('item', item_id, 'price', expected=None, actual=price, rule='negative_or_zero_value', explanation=explanation)

            itc = self.ItemTotalCost.query.filter_by(item_id=item_id).order_by(self.ItemTotalCost.date.desc()).first()
            if itc:
                expected_cost = itc.total_cost
                if price <= expected_cost:
                    explanation = f"current price ({price}) <= total_cost ({expected_cost}) for item {item_id}"
                    self.record_anomaly('item', item_id, 'price_vs_cost', expected=expected_cost, actual=price, rule='price_below_cost', explanation=explanation, dollar_impact=abs(price - expected_cost))

            try:
                stat = self.EntityStat.query.filter_by(entity_type='item', entity_id=item_id, metric='price', window='ewma').first()
                self.check_statistical_anomaly('item', item_id, 'price', price, stat)
                self.upsert_entity_stat('item', item_id, 'price', price)
            except Exception:
                pass

        jr.touch(last_id=max_seen if max_seen > last_id else last_id, last_at=datetime.utcnow())
        self.db.session.add(jr)

    def process_cost_history(self):
        """
        look at all cost history records since last run and check for anomalies, updating stats as we go
        """

        jr = self.get_jobrun('cost_history')
        last_id = jr.last_processed_id or 0
        query = self.CostHistory.query.filter(self.CostHistory.id > last_id).order_by(self.CostHistory.id)
        max_seen = last_id
        for row in query.all():
            max_seen = max(max_seen, row.id)
            raw_id = row.raw_product_id
            cost = row.cost

            if cost is None or cost <= 0:
                explanation = f"raw product cost non-positive for raw_product {raw_id} (cost={cost})"
                self.record_anomaly('raw_product', raw_id, 'cost', expected=None, actual=cost, rule='negative_or_zero_value', explanation=explanation)

            # update stats for raw product cost
            try:
                stat = self.EntityStat.query.filter_by(entity_type='raw_product', entity_id=raw_id, metric='cost', window='ewma').first()
                self.check_statistical_anomaly('raw_product', raw_id, 'cost', cost, stat)
                self.upsert_entity_stat('raw_product', raw_id, 'cost', cost)
            except Exception:
                pass

        jr.touch(last_id=max_seen if max_seen > last_id else last_id, last_at=datetime.utcnow())
        self.db.session.add(jr)

    def run(self):
        # run all processors in order: price_history, current_price, cost_history
        self.process_price_history()
        self.process_current_prices()
        self.process_cost_history()
        # commit everything
        try:
            self.db.session.commit()
        except Exception as e:
            self.db.session.rollback()
            print('Error committing anomalies:', e)


def main():
    """Run anomaly detector for all companies.

    When run as a background job, we detect anomalies for all companies and
    notify all users in each company.
    """
    app = make_app()
    with app.app_context():
        from app.models import Company
        companies = Company.query.all()

        for company in companies:
            try:
                detector = AnomalyDetector(db, company_id=company.id)
                detector.run()
            except Exception as e:
                print(f'Error running detector for company {company.id}: {e}')

        db.session.commit()


if __name__ == '__main__':
    main()
