"""Tests for anomaly notification throttling and creation."""
import pytest
from datetime import datetime, timedelta
from app import db
from app.models import Anomaly, Notification, Company


def test_should_notify_anomaly_high_severity_always(app):
    """High severity anomalies should always trigger notifications."""
    from app.utils.notification_utils import should_notify_anomaly

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        # Create high severity anomaly
        anomaly = Anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            severity='high',
            expected_value=10.0,
            actual_value=20.0,
        )
        db.session.add(anomaly)
        db.session.commit()

        # Should notify without checking history
        assert should_notify_anomaly(anomaly, company.id) is True


def test_should_notify_anomaly_throttle_medium(app):
    """Medium severity anomalies throttled by 24-hour window."""
    from app.utils.notification_utils import should_notify_anomaly

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        # Create recent notification
        notif = Notification(
            user_id=1,
            company_id=company.id,
            title='Data Anomaly: price',
            message='item #1: price anomaly',
            category='warning'
        )
        db.session.add(notif)
        db.session.commit()

        # Create medium severity anomaly
        anomaly = Anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            severity='medium',
            expected_value=10.0,
            actual_value=20.0,
        )
        db.session.add(anomaly)
        db.session.commit()

        # Should NOT notify due to recent notification
        assert should_notify_anomaly(anomaly, company.id) is False


def test_should_notify_anomaly_throttle_expired(app):
    """Medium severity anomalies notify if 24+ hours have passed."""
    from app.utils.notification_utils import should_notify_anomaly

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        # Create old notification (25 hours ago)
        old_time = datetime.utcnow() - timedelta(hours=25)
        notif = Notification(
            user_id=1,
            company_id=company.id,
            title='Data Anomaly: price',
            message='item #1: price anomaly',
            category='warning',
            created_at=old_time
        )
        db.session.add(notif)
        db.session.commit()

        # Create medium severity anomaly
        anomaly = Anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            severity='medium',
            expected_value=10.0,
            actual_value=20.0,
        )
        db.session.add(anomaly)
        db.session.commit()

        # Should notify since window expired
        assert should_notify_anomaly(anomaly, company.id) is True


def test_should_notify_anomaly_throttle_per_entity(app):
    """Throttling is per entity, not per metric."""
    from app.utils.notification_utils import should_notify_anomaly

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        # Create notification for item #1
        notif = Notification(
            user_id=1,
            company_id=company.id,
            title='Data Anomaly: price',
            message='item #1: price anomaly',
            category='warning'
        )
        db.session.add(notif)
        db.session.commit()

        # Different item should notify
        anomaly = Anomaly(
            entity_type='item',
            entity_id=2,  # Different item
            metric='price',
            severity='medium',
            expected_value=10.0,
            actual_value=20.0,
        )
        db.session.add(anomaly)
        db.session.commit()

        assert should_notify_anomaly(anomaly, company.id) is True


def test_create_anomaly_notification(app):
    """Test notification creation for anomaly."""
    from app.utils.notification_utils import create_anomaly_notification
    from app.models import User

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        # Create user for notification
        user = User(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()

        # Create anomaly
        anomaly = Anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            severity='high',
            expected_value=10.0,
            actual_value=20.0,
            explanation='Price significantly higher than expected'
        )
        db.session.add(anomaly)
        db.session.commit()

        # Create notification
        notifs = create_anomaly_notification(anomaly, company.id, commit=True)

        assert len(notifs) == 1
        assert notifs[0].company_id == company.id
        assert notifs[0].user_id == user.id
        assert 'price' in notifs[0].title
        assert notifs[0].category == 'danger'  # high severity


def test_create_anomaly_notification_medium_severity(app):
    """Test notification category for medium severity."""
    from app.utils.notification_utils import create_anomaly_notification
    from app.models import User

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

        anomaly = Anomaly(
            entity_type='item',
            entity_id=1,
            metric='margin',
            severity='medium',
            expected_value=20.0,
            actual_value=15.0,
        )
        db.session.add(anomaly)
        db.session.commit()

        notifs = create_anomaly_notification(anomaly, company.id, commit=True)

        assert notifs[0].category == 'warning'  # medium severity


def test_create_anomaly_notification_low_severity(app):
    """Test notification category for low severity."""
    from app.utils.notification_utils import create_anomaly_notification
    from app.models import User

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

        anomaly = Anomaly(
            entity_type='item',
            entity_id=1,
            metric='quantity',
            severity='low',
            expected_value=100.0,
            actual_value=95.0,
        )
        db.session.add(anomaly)
        db.session.commit()

        notifs = create_anomaly_notification(anomaly, company.id, commit=True)

        assert notifs[0].category == 'info'  # low severity


def test_create_anomaly_notification_multi_user(app):
    """Test notification sent to all company users."""
    from app.utils.notification_utils import create_anomaly_notification
    from app.models import User

    with app.app_context():
        company = Company(name="Test Co", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()

        # Create multiple users
        for i in range(3):
            user = User(
                first_name=f"User{i}",
                last_name="Test",
                email=f"user{i}@example.com",
                password="password",
                company_id=company.id
            )
            db.session.add(user)
        db.session.commit()

        anomaly = Anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            severity='high',
            expected_value=10.0,
            actual_value=20.0,
        )
        db.session.add(anomaly)
        db.session.commit()

        notifs = create_anomaly_notification(anomaly, company.id, commit=True)

        # Should have one notification per user
        assert len(notifs) == 3
        user_ids = {n.user_id for n in notifs}
        assert len(user_ids) == 3


def test_notification_includes_link_to_insights(app):
    """Test notification includes link to data insights page."""
    from app.utils.notification_utils import create_anomaly_notification
    from app.models import User

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

        anomaly = Anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            severity='high',
            expected_value=10.0,
            actual_value=20.0,
        )
        db.session.add(anomaly)
        db.session.commit()

        notifs = create_anomaly_notification(anomaly, company.id, commit=True)

        assert notifs[0].link_url is not None
        assert 'data_insights' in notifs[0].link_url


def test_notification_includes_severity_icon(app):
    """Test notification title includes severity indicator."""
    from app.utils.notification_utils import create_anomaly_notification
    from app.models import User

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

        anomaly = Anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            severity='high',
            expected_value=10.0,
            actual_value=20.0,
        )
        db.session.add(anomaly)
        db.session.commit()

        notifs = create_anomaly_notification(anomaly, company.id, commit=True)

        assert '🔴' in notifs[0].title  # High severity icon


def test_notification_no_commit_by_default(app):
    """Test notification not committed if commit=False."""
    from app.utils.notification_utils import create_anomaly_notification
    from app.models import User

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

        anomaly = Anomaly(
            entity_type='item',
            entity_id=1,
            metric='price',
            severity='high',
            expected_value=10.0,
            actual_value=20.0,
        )
        db.session.add(anomaly)
        db.session.commit()

        # Create without commit
        notifs = create_anomaly_notification(anomaly, company.id, commit=False)

        # Should still be in session but not committed
        assert len(notifs) == 1

        # Rollback and check notification is gone
        db.session.rollback()
        count = Notification.query.count()
        assert count == 0
