from flask import current_app, url_for
from producepricer import db
from producepricer.models import Notification, User


def create_company_notification(company_id, title, message, category='info', link_url=None, commit=True):
    users = User.query.filter_by(company_id=company_id).all()
    notifications = [
        Notification(
            user_id=user.id,
            company_id=company_id,
            title=title,
            message=message,
            category=category,
            link_url=link_url
        )
        for user in users
    ]
    if notifications:
        db.session.add_all(notifications)
        if commit:
            db.session.commit()
    return notifications


def _get_outlier_threshold():
    try:
        return float(current_app.config.get('NOTIFICATION_OUTLIER_PERCENT_THRESHOLD', 10.0))
    except (TypeError, ValueError):
        return 10.0


def create_receiving_log_notification(log, commit=True):
    raw_name = log.raw_product.name if log.raw_product else 'Unknown product'
    title = 'New receiving log'
    message = f"{raw_name} - {log.quantity_received} units received by {log.received_by}."
    link_url = url_for('main.view_receiving_log', log_id=log.id)
    return create_company_notification(
        log.company_id,
        title,
        message,
        category='info',
        link_url=link_url,
        commit=commit
    )


def maybe_create_receiving_log_outlier_notification(log, commit=True):
    comparison = log.get_price_comparison()
    if not comparison or not comparison.get('master_price'):
        return None

    status = comparison.get('status')
    if status not in ('above_market', 'below_market'):
        return None

    percentage = comparison.get('percentage') or 0.0
    threshold = _get_outlier_threshold()
    if abs(percentage) < threshold:
        return None

    raw_name = log.raw_product.name if log.raw_product else 'Unknown product'
    direction = 'above' if status == 'above_market' else 'below'
    price_paid = comparison.get('price_paid') or 0.0
    market_cost = comparison.get('master_price') or 0.0
    title = 'Price outlier detected'
    message = (
        f"{raw_name}: {abs(percentage):.1f}% {direction} market "
        f"(${price_paid:.2f} vs ${market_cost:.2f})."
    )
    category = 'danger' if status == 'above_market' else 'success'
    link_url = url_for('main.view_receiving_log', log_id=log.id)

    return create_company_notification(
        log.company_id,
        title,
        message,
        category=category,
        link_url=link_url,
        commit=commit
    )
