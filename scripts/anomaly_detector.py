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
    def __init__(self, session):
        self.db = session
        from app.models import (
            PriceHistory,
            CurrentItemPrice,
            CostHistory,
            ItemTotalCost,
            EntityStat,
            Anomaly,
            JobRun,
        )
        self.PriceHistory = PriceHistory
        self.CurrentItemPrice = CurrentItemPrice
        self.CostHistory = CostHistory
        self.ItemTotalCost = ItemTotalCost
        self.EntityStat = EntityStat
        self.Anomaly = Anomaly
        self.JobRun = JobRun

        # rule tuning
        self.margin_threshold = 0.20
        self.ewma_alpha = 0.1

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

    def record_anomaly(self, entity_type, entity_id, metric, expected, actual, z_score=None, rule=None, dollar_impact=None, explanation=None, severity=None):
        """
        some heuristics for describing how 'bad' an anomaly is and records it to db
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

            # update entity stats for price
            try:
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
    app = make_app()
    with app.app_context():
        detector = AnomalyDetector(db)
        detector.run()


if __name__ == '__main__':
    main()
