from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from producepricer.blueprints._blueprint import main
from producepricer.models import InventorySession, ItemInventory, SupplyInventory, Supply, Item
from producepricer import db


@main.route('/inventory')
@login_required
def inventory_sessions():
    q = request.args.get('q', '').strip()
    query = InventorySession.query.filter_by(company_id=current_user.company_id)
    if q:
        query = query.filter(
            InventorySession.label.ilike(f'%{q}%') |
            InventorySession.counted_by.ilike(f'%{q}%')
        )
    sessions = query.order_by(InventorySession.submitted_at.desc()).all()
    return render_template('inventory_sessions.html', sessions=sessions, q=q)


@main.route('/inventory/session/<int:session_id>')
@login_required
def view_inventory_session(session_id):
    session = InventorySession.query.filter_by(
        id=session_id, company_id=current_user.company_id
    ).first_or_404()
    item_counts = ItemInventory.query.filter_by(
        session_id=session_id, company_id=current_user.company_id
    ).all()
    supply_counts = SupplyInventory.query.filter_by(
        session_id=session_id, company_id=current_user.company_id
    ).all()
    return render_template(
        'view_inventory_session.html',
        session=session,
        item_counts=item_counts,
        supply_counts=supply_counts
    )


@main.route('/inventory/session/<int:session_id>/delete', methods=['POST'])
@login_required
def delete_inventory_session(session_id):
    session = InventorySession.query.filter_by(
        id=session_id, company_id=current_user.company_id
    ).first_or_404()
    db.session.delete(session)
    db.session.commit()
    flash('Inventory session deleted.', 'success')
    return redirect(url_for('main.inventory_sessions'))


@main.route('/inventory/supplies')
@login_required
def supplies():
    q = request.args.get('q', '').strip()
    query = Supply.query.filter_by(company_id=current_user.company_id)
    if q:
        query = query.filter(
            Supply.name.ilike(f'%{q}%') |
            Supply.category.ilike(f'%{q}%')
        )
    all_supplies = query.order_by(Supply.name.asc()).all()
    return render_template('supplies.html', supplies=all_supplies, q=q)


@main.route('/inventory/supplies/<int:supply_id>/toggle', methods=['POST'])
@login_required
def toggle_supply_active(supply_id):
    supply = Supply.query.filter_by(
        id=supply_id, company_id=current_user.company_id
    ).first_or_404()
    supply.is_active = not supply.is_active
    db.session.commit()
    state = 'activated' if supply.is_active else 'deactivated'
    flash(f'"{supply.name}" {state}.', 'success')
    return redirect(url_for('main.supplies'))
