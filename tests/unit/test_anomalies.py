import pytest
from datetime import datetime

from app import db


def test_entitystat_ewma_update(app):
    from app.models.anomalies import EntityStat

    with app.app_context():
        stat = EntityStat(entity_type='item', entity_id=1, metric='price', window='ewma')
        db.session.add(stat)
        db.session.commit()

        # first update initializes mean/stddev
        stat.update_ewma(10.0, alpha=0.5)
        assert stat.mean == pytest.approx(10.0)
        assert stat.stddev == pytest.approx(0.0)
        assert stat.count == 1


def test_check_statistical_anomaly_creates_record(app):
    from app.models.anomalies import EntityStat, Anomaly
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        # seed a stat with mean 10, stddev 1
        stat = EntityStat(entity_type='item', entity_id=2, metric='price', window='ewma', mean=10.0, stddev=1.0, count=10, last_value=10.0, last_updated=datetime.utcnow())
        db.session.add(stat)
        db.session.commit()

        detector = AnomalyDetector(db)
        # use a value far from mean to trigger z-score > 2.5
        detector.check_statistical_anomaly('item', 2, 'price', 13.0, stat)

        # anomaly should be recorded
        a = Anomaly.query.filter_by(entity_type='item', entity_id=2, metric='price', rule_triggered='statistical_zscore').first()
        assert a is not None
        assert abs(a.z_score) >= 2.5


def test_process_price_history_flags_price_below_cost(app):
    from app.models.pricing import PriceHistory, CurrentItemPrice
    from app.models.inventory import ItemTotalCost
    from app.models.anomalies import Anomaly
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        # create item total cost (expected cost = 15)
        itc = ItemTotalCost(item_id=3, date=datetime.utcnow().date(), ranch_cost=0.0, total_cost=15.0, packaging_cost=0.0, raw_product_cost=0.0, labor_cost=0.0, designation_cost=0.0, company_id=1)
        db.session.add(itc)
        db.session.commit()

        # add price history with price below cost
        ph = PriceHistory(item_id=3, date=datetime.utcnow().date(), company_id=1, customer_id=1, price=10.0)
        db.session.add(ph)
        db.session.commit()

        detector = AnomalyDetector(db)
        detector.process_price_history()
        db.session.commit()

        a = Anomaly.query.filter_by(entity_type='item', entity_id=3).filter(Anomaly.rule_triggered.in_(['price_below_cost','price_vs_cost'])).first()
        assert a is not None
        assert a.rule_triggered in ('price_below_cost','price_vs_cost')


def test_data_insights_page_requires_login(client):
    # without being logged in, should redirect to login
    rv = client.get('/data_insights', follow_redirects=False)
    assert rv.status_code in (302, 401)


def test_data_insights_page_shows_with_login(client, logged_in_user):
    # client is logged in via the logged_in_user fixture
    rv = client.get('/data_insights')
    assert rv.status_code == 200
    assert b'Data Insights' in rv.data
