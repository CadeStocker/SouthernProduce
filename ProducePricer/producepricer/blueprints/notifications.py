from datetime import datetime
from flask import jsonify, request
from flask_login import login_required, current_user
from producepricer import db
from producepricer.models import Notification
from producepricer.blueprints._blueprint import main


@main.route('/notifications/poll')
@login_required
def poll_notifications():
    limit_param = request.args.get('limit', 10)
    try:
        limit = max(1, min(int(limit_param), 50))
    except (TypeError, ValueError):
        limit = 10

    notifications = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )

    unread_count = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .filter(Notification.read_at.is_(None))
        .count()
    )

    return jsonify({
        'unread_count': unread_count,
        'notifications': [
            {
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'category': n.category,
                'link_url': n.link_url,
                'created_at': n.created_at.isoformat(),
                'created_at_label': n.created_at.strftime('%Y-%m-%d %H:%M'),
                'read_at': n.read_at.isoformat() if n.read_at else None
            }
            for n in notifications
        ]
    })


@main.route('/notifications/mark_read', methods=['POST'])
@login_required
def mark_notifications_read():
    payload = request.get_json(silent=True) or {}
    ids = payload.get('ids', [])
    if not isinstance(ids, list) or not ids:
        return jsonify({'updated': 0})

    now = datetime.utcnow()
    updated = (
        Notification.query
        .filter(Notification.user_id == current_user.id)
        .filter(Notification.id.in_(ids))
        .filter(Notification.read_at.is_(None))
        .update({'read_at': now}, synchronize_session=False)
    )
    db.session.commit()

    return jsonify({'updated': updated})
