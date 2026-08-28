from flask import Blueprint, render_template, request, current_app, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app.models import Anomaly
from app import db
from datetime import datetime
import threading

insights = Blueprint('insights', __name__)


@insights.route('/data_insights')
@login_required
def data_insights():
    """List recent anomalies for review and management."""
    # basic list: most recent 200
    anomalies = Anomaly.query.order_by(Anomaly.detected_at.desc()).limit(200).all()

    # Resolve entity ids to friendly names/links where possible
    entity_map = {}
    # collect ids per entity_type
    ids_by_type = {}
    for a in anomalies:
        ids_by_type.setdefault(a.entity_type, set()).add(a.entity_id)

    try:
        from app.models.inventory import RawProduct, Item
        # RawProducts
        rids = ids_by_type.get('raw_product') or set()
        if rids:
            rows = RawProduct.query.filter(RawProduct.id.in_(list(rids))).all()
            for r in rows:
                entity_map.setdefault('raw_product', {})[r.id] = {
                    'label': f"{r.name}",
                    'url': url_for('main.view_raw_product', raw_product_id=r.id)
                }
        # Items
        iids = ids_by_type.get('item') or set()
        if iids:
            rows = Item.query.filter(Item.id.in_(list(iids))).all()
            for it in rows:
                entity_map.setdefault('item', {})[it.id] = {
                    'label': f"{it.name}",
                    'url': url_for('main.view_item', item_id=it.id)
                }
    except Exception:
        # best-effort; if resolution fails we'll fall back to raw display
        current_app.logger.exception('Failed to resolve entity names for data insights')

    return render_template('data_insights.html', anomalies=anomalies, entity_map=entity_map)


@insights.route('/analytics_data')
@login_required
def analytics_data():
    """View detailed analytics and business metrics."""
    from app.services import analytics_reports
    from datetime import timedelta

    company_id = current_user.company_id

    # Parse date range from query params
    days = request.args.get('days', 30, type=int)
    start_date = (datetime.utcnow() - timedelta(days=days)).date()
    end_date = datetime.utcnow().date()

    # Get various metrics
    revenue_trend = analytics_reports.get_daily_revenue_trend(company_id, start_date, end_date)
    top_customers = analytics_reports.get_top_customers_by_revenue(company_id, start_date, end_date, 20)
    top_items = analytics_reports.get_top_items_by_sales_volume(company_id, start_date, end_date, 20)
    receiving_costs = analytics_reports.get_receiving_costs(company_id, start_date, end_date)

    period_totals = analytics_reports.get_period_totals(company_id, start_date, end_date)

    # Resolve entity names for display
    from app.models import Customer, Item

    customers_by_id = {c.id: c.name for c in Customer.query.filter(
        Customer.id.in_([row['customer_id'] for row in top_customers if row['customer_id']])
    ).all()}

    items_by_id = {i.id: i.name for i in Item.query.filter(
        Item.id.in_([row['item_id'] for row in top_items if row['item_id']])
    ).all()}

    return render_template(
        'analytics_data.html',
        revenue_trend=revenue_trend,
        top_customers=[(row['customer_id'], customers_by_id.get(row['customer_id'], 'Unknown'), row['revenue'])
                       for row in top_customers],
        top_items=[(row['item_id'], items_by_id.get(row['item_id'], 'Unknown'), row['quantity'], row['revenue'])
                   for row in top_items],
        receiving_costs=receiving_costs,
        period_totals=period_totals,
        days=days,
        start_date=start_date,
        end_date=end_date,
    )


@insights.route('/api/anomalies/<int:anomaly_id>/mark_reviewed', methods=['POST'])
@login_required
def mark_anomaly_reviewed(anomaly_id):
    """Mark an anomaly as reviewed by the current user."""
    anomaly = Anomaly.query.get_or_404(anomaly_id)

    data = request.get_json(silent=True) or {}
    notes = data.get('notes', '').strip()

    anomaly.status = 'reviewed'
    anomaly.reviewed_at = datetime.utcnow()
    anomaly.reviewed_by_id = current_user.id
    if notes:
        anomaly.notes = notes

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Anomaly marked as reviewed',
        'anomaly_id': anomaly_id,
        'status': anomaly.status,
        'reviewed_by': current_user.first_name + ' ' + current_user.last_name,
        'reviewed_at': anomaly.reviewed_at.isoformat() if anomaly.reviewed_at else None
    })


@insights.route('/api/anomalies/<int:anomaly_id>/mark_fixed', methods=['POST'])
@login_required
def mark_anomaly_fixed(anomaly_id):
    """Mark an anomaly as fixed by the current user."""
    anomaly = Anomaly.query.get_or_404(anomaly_id)

    data = request.get_json(silent=True) or {}
    notes = data.get('notes', '').strip()

    anomaly.status = 'fixed'
    anomaly.fixed_at = datetime.utcnow()
    anomaly.fixed_by_id = current_user.id
    if notes:
        anomaly.notes = notes

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Anomaly marked as fixed',
        'anomaly_id': anomaly_id,
        'status': anomaly.status,
        'fixed_by': current_user.first_name + ' ' + current_user.last_name,
        'fixed_at': anomaly.fixed_at.isoformat() if anomaly.fixed_at else None
    })


@insights.route('/api/anomalies/<int:anomaly_id>/mark_open', methods=['POST'])
@login_required
def mark_anomaly_open(anomaly_id):
    """Revert an anomaly back to open status."""
    anomaly = Anomaly.query.get_or_404(anomaly_id)

    anomaly.status = 'open'
    anomaly.reviewed_at = None
    anomaly.reviewed_by_id = None
    anomaly.fixed_at = None
    anomaly.fixed_by_id = None
    anomaly.notes = None

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Anomaly reverted to open status',
        'anomaly_id': anomaly_id,
        'status': anomaly.status
    })


@insights.route('/data_insights/run', methods=['POST'])
@login_required
def run_insights_now():
    """Trigger the anomaly detector to run in background (manual trigger)."""

    try:
        from scripts.anomaly_detector import AnomalyDetector
        app = current_app._get_current_object()
        company_id = current_user.company_id

        def _run():
            try:
                with app.app_context():
                    detector = AnomalyDetector(db, company_id=company_id)
                    detector.run()
                    app.logger.info(f'Anomaly detector manual run finished for company {company_id}')
            except Exception:
                try:
                    with app.app_context():
                        app.logger.exception('Anomaly detector manual run failed')
                except Exception:
                    import traceback, sys
                    traceback.print_exc(file=sys.stderr)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        flash('Anomaly detector started (running in background).', 'success')
    except Exception:
        current_app.logger.exception('Failed to start anomaly detector')
        flash('Failed to start anomaly detector.', 'danger')

    return redirect(url_for('insights.data_insights'))
