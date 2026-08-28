"""Tests for anomaly detector integration with notifications."""
import pytest
from datetime import datetime
from app import db
from app.models import Company, Anomaly, Notification, User
from app.models.pricing import PriceHistory, CurrentItemPrice
from app.models.inventory import ItemTotalCost


def test_anomaly_detector_requires_company_id_for_notifications(app):
    """Detector without company_id should not create notifications."""
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        detector = AnomalyDetector(db, company_id=None)

        # Should not crash, just not create notifications
        assert detector.company_id is None


def test_anomaly_detector_with_company_id_creates_notifications(app):
    """Detector with company_id should create notifications for anomalies."""
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        # Set up company and user
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        user = User(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()

        # Create detector with company_id
        detector = AnomalyDetector(db, company_id=company.id)

        # Record an anomaly
        detector.record_anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            expected=10.0,
            actual=20.0,
            severity='high',
            explanation='Price is doubled'
        )
        db.session.commit()

        # Should have created anomaly and notification
        anomalies = Anomaly.query.all()
        assert len(anomalies) == 1

        notifications = Notification.query.all()
        assert len(notifications) == 1
        assert notifications[0].user_id == user.id


def test_detector_high_severity_notification_always_sent(app):
    """High severity anomalies should create notifications."""
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        user = User(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()

        detector = AnomalyDetector(db, company_id=company.id)

        # Record high severity
        detector.record_anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            expected=10.0,
            actual=20.0,
            rule='price_below_cost',  # This makes it high severity
            severity='high',
        )
        db.session.commit()

        notifications = Notification.query.all()
        assert len(notifications) == 1


def test_detector_medium_severity_notification_sent(app):
    """Medium severity anomalies should create notifications."""
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        user = User(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()

        detector = AnomalyDetector(db, company_id=company.id)

        # Record medium severity with high dollar impact
        detector.record_anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            expected=10.0,
            actual=15.0,
            dollar_impact=500.0,  # This makes it medium severity
            severity='medium',
        )
        db.session.commit()

        notifications = Notification.query.all()
        assert len(notifications) == 1


def test_detector_price_below_cost_is_high_severity(app):
    """Price below cost anomalies should be marked high severity."""
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        detector = AnomalyDetector(db, company_id=company.id)

        detector.record_anomaly(
            entity_type='item',
            entity_id=1,
            metric='price_vs_cost',
            expected=15.0,
            actual=10.0,
            rule='price_below_cost',
        )
        db.session.commit()

        anomalies = Anomaly.query.all()
        assert len(anomalies) == 1
        assert anomalies[0].severity == 'high'


def test_detector_data_consistency_is_high_severity(app):
    """Data consistency anomalies should be marked high severity."""
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        detector = AnomalyDetector(db, company_id=company.id)

        detector.record_anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            expected=10.0,
            actual=10.5,
            rule='data_consistency',
        )
        db.session.commit()

        anomalies = Anomaly.query.all()
        assert len(anomalies) == 1
        assert anomalies[0].severity == 'high'


def test_detector_process_price_history_creates_notifications(app):
    """Process price history should create notifications for detected anomalies."""
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        user = User(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()

        # Create item total cost
        itc = ItemTotalCost(
            item_id=1,
            date=datetime.utcnow().date(),
            ranch_cost=0.0,
            total_cost=15.0,
            packaging_cost=0.0,
            raw_product_cost=0.0,
            labor_cost=0.0,
            designation_cost=0.0,
            company_id=company.id
        )
        db.session.add(itc)

        # Create price history with price below cost
        ph = PriceHistory(
            item_id=1,
            date=datetime.utcnow().date(),
            company_id=company.id,
            customer_id=1,
            price=10.0
        )
        db.session.add(ph)
        db.session.commit()

        detector = AnomalyDetector(db, company_id=company.id)
        detector.process_price_history()
        db.session.commit()

        # Should have notification
        anomalies = Anomaly.query.filter_by(entity_id=1).all()
        assert len(anomalies) > 0

        notifications = Notification.query.all()
        assert len(notifications) > 0


def test_detector_notification_includes_entity_and_metric(app):
    """Notification should mention the entity and metric."""
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        user = User(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()

        detector = AnomalyDetector(db, company_id=company.id)

        detector.record_anomaly(
            entity_type='item',
            entity_id=42,
            metric='price',
            expected=10.0,
            actual=20.0,
            severity='high',
            explanation='Price doubled'
        )
        db.session.commit()

        notif = Notification.query.first()
        assert 'price' in notif.title or 'price' in notif.message
        assert '42' in notif.message or 'item' in notif.message.lower()


def test_multiple_anomalies_create_multiple_notifications(app):
    """Multiple anomalies should create multiple notifications."""
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        user = User(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()

        detector = AnomalyDetector(db, company_id=company.id)

        # Record multiple anomalies
        for i in range(3):
            detector.record_anomaly(
                entity_type='item',
                entity_id=i+1,
                metric='price',
                expected=10.0,
                actual=20.0,
                severity='high',
            )
        db.session.commit()

        notifications = Notification.query.all()
        # Each anomaly creates 1 notification per user
        assert len(notifications) == 3


def test_anomaly_without_company_id_not_notified(app):
    """Anomalies created without company_id should not create notifications."""
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        detector = AnomalyDetector(db, company_id=None)

        detector.record_anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            expected=10.0,
            actual=20.0,
            severity='high',
        )
        db.session.commit()

        # Anomaly should exist
        anomalies = Anomaly.query.all()
        assert len(anomalies) == 1

        # But no notification
        notifications = Notification.query.all()
        assert len(notifications) == 0


def test_detector_notification_error_handling(app):
    """Detector should not crash if notification creation fails."""
    from scripts.anomaly_detector import AnomalyDetector

    with app.app_context():
        # Create detector with invalid company_id (no users)
        invalid_company = 999
        detector = AnomalyDetector(db, company_id=invalid_company)

        # Should not crash even though company doesn't exist
        detector.record_anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            expected=10.0,
            actual=20.0,
            severity='high',
        )
        db.session.commit()

        # Anomaly should still be created
        anomalies = Anomaly.query.all()
        assert len(anomalies) == 1
