from flask import Blueprint, render_template, request, current_app, flash, redirect, url_for
from flask_login import login_required
from app.models import Anomaly
import threading

insights = Blueprint('insights', __name__)


@insights.route('/data_insights')
@login_required
def data_insights():
    """List recent data insights / anomalies."""
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


@insights.route('/data_insights/run', methods=['POST'])
@login_required
def run_insights_now():
    """Trigger the anomaly detector to run in background (manual trigger)."""
    try:
        from scripts.anomaly_detector import AnomalyDetector
        # run in background thread so request returns quickly
        def _run():
            try:
                detector = AnomalyDetector(current_app.extensions['sqlalchemy'])
                detector.run()
                current_app.logger.info('Anomaly detector manual run finished')
            except Exception:
                current_app.logger.exception('Anomaly detector manual run failed')

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        flash('Anomaly detector started (running in background).', 'success')
    except Exception:
        current_app.logger.exception('Failed to start anomaly detector')
        flash('Failed to start anomaly detector.', 'danger')

    return redirect(url_for('insights.data_insights'))
