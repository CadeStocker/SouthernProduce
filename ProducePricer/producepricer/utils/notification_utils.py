# Copyright Cade Stocker 2026
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


def create_new_api_key_notification(api_key, commit=True):
    """Notify all company users when a new API key/device is added."""
    created_by = api_key.created_by.first_name if api_key.created_by else 'Someone'
    title = 'New device added'
    message = f"Device '{api_key.device_name}' was added by {created_by}."
    
    try:
        link_url = url_for('main.api_keys')
    except RuntimeError:
        # No request context
        link_url = None
    
    return create_company_notification(
        api_key.company_id,
        title,
        message,
        category='info',
        link_url=link_url,
        commit=commit
    )


def create_api_key_expiration_notification(api_key, commit=True):
    """Notify all company users when an API key is expiring soon."""
    title = 'API key expiring soon'
    message = f"Device '{api_key.device_name}' API key expires in 7 days."
    
    try:
        link_url = url_for('main.api_keys')
    except RuntimeError:
        # No request context
        link_url = None
    
    return create_company_notification(
        api_key.company_id,
        title,
        message,
        category='warning',
        link_url=link_url,
        commit=commit
    )


def maybe_create_price_change_notification(raw_product_id, new_cost, old_cost, company_id, commit=True):
    """Notify if a raw product price changes significantly (>20% by default)."""
    if old_cost is None or old_cost == 0:
        # Can't calculate percentage change without prior cost
        return None
    
    try:
        threshold = float(current_app.config.get('NOTIFICATION_PRICE_CHANGE_PERCENT_THRESHOLD', 20.0))
    except (TypeError, ValueError):
        threshold = 20.0
    
    percentage_change = ((new_cost - old_cost) / old_cost) * 100
    
    if abs(percentage_change) < threshold:
        return None  # Change is not significant enough
    
    from producepricer.models import RawProduct
    raw_product = RawProduct.query.get(raw_product_id)
    if not raw_product:
        return None
    
    product_name = raw_product.name
    direction = 'increased' if percentage_change > 0 else 'decreased'
    category = 'warning' if percentage_change > 0 else 'success'
    
    title = 'Significant price change detected'
    message = (
        f"{product_name} price {direction} by {abs(percentage_change):.1f}% "
        f"(${old_cost:.2f} → ${new_cost:.2f})."
    )
    
    try:
        link_url = url_for('main.raw_product', raw_product_id=raw_product_id)
    except RuntimeError:
        # No request context
        link_url = None
    
    return create_company_notification(
        company_id,
        title,
        message,
        category=category,
        link_url=link_url,
        commit=commit
    )


def check_and_notify_expiring_api_keys():
    """Check for API keys expiring in the next 7 days and send notifications."""
    from datetime import datetime, timedelta
    from producepricer.models import APIKey
    
    soon = datetime.utcnow() + timedelta(days=7)
    expiring_keys = APIKey.query.filter(
        APIKey.expires_at.isnot(None),
        APIKey.expires_at <= soon,
        APIKey.is_active == True
    ).all()
    
    notifications = []
    for api_key in expiring_keys:
        # Check if we already have a recent notification for this key
        # (to avoid duplicate notifications)
        recent_notif = Notification.query.filter(
            Notification.company_id == api_key.company_id,
            Notification.title.like('%API key expiring%'),
            Notification.message.like(f"%{api_key.device_name}%"),
            Notification.created_at >= datetime.utcnow() - timedelta(days=1)
        ).first()
        
        if not recent_notif:
            notifs = create_api_key_expiration_notification(api_key, commit=True)
            notifications.extend(notifs)
    
    return notifications
