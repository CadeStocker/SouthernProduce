from flask import Blueprint, render_template, request, current_app, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app.models import Anomaly
from app import db
from app.services.analytics_domains import DOMAINS, DOMAIN_KEYS
from datetime import datetime
import threading

insights = Blueprint('insights', __name__)


@insights.route('/data_insights')
@login_required
def data_insights():
    """List recent anomalies for review and management.

    Scoped to the current user's company, and optionally to one domain via
    ``?domain=`` so the dashboard's per-area counts can link straight here.
    """
    company_id = current_user.company_id
    selected_domain = request.args.get('domain')
    if selected_domain not in DOMAIN_KEYS:
        selected_domain = None

    query = Anomaly.query.filter(Anomaly.company_id == company_id)
    if selected_domain:
        query = query.filter(Anomaly.domain == selected_domain)

    anomalies = query.order_by(Anomaly.detected_at.desc()).limit(200).all()

    # Counts per domain for the filter chips, independent of the current filter.
    domain_counts = dict(
        db.session.query(Anomaly.domain, db.func.count(Anomaly.id))
        .filter(Anomaly.company_id == company_id, Anomaly.status == 'open')
        .group_by(Anomaly.domain).all()
    )

    # Resolve entity ids to friendly names/links where possible
    entity_map = {}
    # collect ids per entity_type
    ids_by_type = {}
    for a in anomalies:
        ids_by_type.setdefault(a.entity_type, set()).add(a.entity_id)

    # Each entry maps an anomaly entity_type onto the model that names it and,
    # where one exists, the detail route to link to. Detectors across the newer
    # domains report against companies, pay groups, customers and designations,
    # so all of them get resolved here rather than falling back to "item #12".
    def _resolvers():
        from app.models.inventory import RawProduct, Item
        from app.models.auth import Company
        from app.models.customers import Customer
        from app.models.labor import PayGroups
        from app.models.pricing import DesignationCost

        return {
            'raw_product': (RawProduct, lambda row: row.name,
                            lambda row: url_for('main.view_raw_product', raw_product_id=row.id)),
            'item': (Item, lambda row: row.name,
                     lambda row: url_for('main.view_item', item_id=row.id)),
            'customer': (Customer, lambda row: row.name,
                         lambda row: url_for('main.customer_detail', customer_id=row.id)),
            'company': (Company, lambda row: f'{row.name} (plant-wide)', None),
            'pay_group': (PayGroups, lambda row: f'Pay group: {row.name}', None),
            'item_designation': (DesignationCost,
                                 lambda row: f'Designation: {row.item_designation.value}', None),
        }

    try:
        for entity_type, (model, label_of, url_of) in _resolvers().items():
            ids = ids_by_type.get(entity_type) or set()
            if not ids:
                continue
            for row in model.query.filter(model.id.in_(list(ids))).all():
                entity_map.setdefault(entity_type, {})[row.id] = {
                    'label': label_of(row),
                    'url': url_of(row) if url_of else None,
                }
    except Exception:
        # best-effort; if resolution fails we'll fall back to raw display
        current_app.logger.exception('Failed to resolve entity names for data insights')

    return render_template(
        'data_insights.html',
        anomalies=anomalies,
        entity_map=entity_map,
        domains=DOMAINS,
        domain_counts=domain_counts,
        domain_labels={domain['key']: domain['label'] for domain in DOMAINS},
        selected_domain=selected_domain,
    )


@insights.route('/analytics_data')
@login_required
def analytics_data():
    """Row-level detail behind the dashboard, for every domain.

    The dashboard shows the shape of each domain; this page is the table you
    export or read down when a panel raises a question. Everything is rendered
    server-side so it prints and copies cleanly.
    """
    from app.services import analytics_reports
    from datetime import timedelta

    company_id = current_user.company_id

    # Parse date range from query params
    days = request.args.get('days', 30, type=int)
    start_date = (datetime.utcnow() - timedelta(days=days)).date()
    end_date = datetime.utcnow().date()

    from app.models import Customer, Item, RawProduct, GrowerOrDistributor

    def name_map(model, ids):
        ids = [i for i in ids if i]
        if not ids:
            return {}
        return {row.id: row.name for row in model.query.filter(model.id.in_(ids)).all()}

    # Sales
    revenue_trend = analytics_reports.get_daily_revenue_trend(company_id, start_date, end_date)
    top_customers = analytics_reports.get_top_customers_by_revenue(company_id, start_date, end_date, 20)
    top_items = analytics_reports.get_top_items_by_sales_volume(company_id, start_date, end_date, 20)
    period_totals = analytics_reports.get_period_totals(company_id, start_date, end_date)

    # Pricing & margin
    margins = analytics_reports.get_item_margin_snapshot(company_id, as_of=end_date, limit=50)
    dispersion = analytics_reports.get_price_dispersion(company_id, start_date, end_date, 20)

    # Labor & efficiency
    efficiency_trend = analytics_reports.get_efficiency_trend(company_id, start_date, end_date)

    # Receiving & suppliers
    receiving_costs = analytics_reports.get_receiving_cost_trend(company_id, start_date, end_date)
    suppliers = analytics_reports.get_top_suppliers_by_spend(company_id, start_date, end_date, 20)
    raw_product_costs = analytics_reports.get_raw_product_cost_per_unit(company_id, start_date, end_date, 20)

    # Inventory
    inventory_levels = analytics_reports.get_inventory_levels(company_id, as_of=end_date, limit=50)
    inventory_movement = analytics_reports.get_inventory_movement(company_id, start_date, end_date, 20)

    customers_by_id = name_map(Customer, [row['customer_id'] for row in top_customers])
    items_by_id = name_map(Item, (
        [row['item_id'] for row in top_items]
        + [row['item_id'] for row in margins]
        + [row['item_id'] for row in dispersion]
        + [row['item_id'] for row in inventory_levels]
        + [row['item_id'] for row in inventory_movement]
    ))
    suppliers_by_id = name_map(GrowerOrDistributor, [row['supplier_id'] for row in suppliers])
    raw_products_by_id = name_map(RawProduct, [row['raw_product_id'] for row in raw_product_costs])

    def with_name(rows, key, names):
        return [{**row, 'name': names.get(row[key], 'Unknown')} for row in rows]

    return render_template(
        'analytics_data.html',
        # Sales
        revenue_trend=revenue_trend,
        top_customers=[(row['customer_id'], customers_by_id.get(row['customer_id'], 'Unknown'), row['revenue'])
                       for row in top_customers],
        top_items=[(row['item_id'], items_by_id.get(row['item_id'], 'Unknown'), row['quantity'], row['revenue'])
                   for row in top_items],
        period_totals=period_totals,
        sales_summary=analytics_reports.get_sales_summary(company_id, start_date, end_date),
        # Pricing
        margins=with_name(margins, 'item_id', items_by_id),
        dispersion=with_name(dispersion, 'item_id', items_by_id),
        margin_summary=analytics_reports.get_margin_summary(company_id, start_date, end_date),
        # Efficiency
        efficiency_trend=efficiency_trend,
        efficiency_summary=analytics_reports.get_efficiency_summary(company_id, start_date, end_date),
        # Receiving
        receiving_costs=receiving_costs,
        suppliers=with_name(suppliers, 'supplier_id', suppliers_by_id),
        raw_product_costs=with_name(raw_product_costs, 'raw_product_id', raw_products_by_id),
        receiving_summary=analytics_reports.get_receiving_summary(company_id, start_date, end_date),
        # Inventory
        inventory_levels=with_name(inventory_levels, 'item_id', items_by_id),
        inventory_movement=with_name(inventory_movement, 'item_id', items_by_id),
        inventory_summary=analytics_reports.get_inventory_summary(company_id, as_of=end_date),
        # Shared
        data_health=analytics_reports.get_domain_data_health(company_id),
        days=days,
        start_date=start_date,
        end_date=end_date,
    )


def _company_anomaly_or_404(anomaly_id):
    """Fetch an anomaly, 404-ing unless it belongs to the current company.

    Scoped rather than a bare get_or_404 so an id from another tenant is
    indistinguishable from one that does not exist.
    """
    return Anomaly.query.filter(
        Anomaly.id == anomaly_id,
        Anomaly.company_id == current_user.company_id,
    ).first_or_404()


@insights.route('/api/anomalies/<int:anomaly_id>/mark_reviewed', methods=['POST'])
@login_required
def mark_anomaly_reviewed(anomaly_id):
    """Mark an anomaly as reviewed by the current user."""
    anomaly = _company_anomaly_or_404(anomaly_id)

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
    anomaly = _company_anomaly_or_404(anomaly_id)

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
    anomaly = _company_anomaly_or_404(anomaly_id)

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
