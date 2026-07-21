# Copyright Cade Stocker 2026
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.blueprints._blueprint import main
from app.models import DailyLog, PayGroups, WeeklyLaborEntry, FilmUsage, SalesByDesignation
from app import db
from datetime import date


@main.route('/labor/daily_logs')
@login_required
def labor_daily_logs():
    """View daily labor logs for the company."""
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    query = DailyLog.query.filter_by(company_id=current_user.company_id)

    if start_date:
        try:
            query = query.filter(DailyLog.date >= date.fromisoformat(start_date))
        except ValueError:
            flash('Invalid start date format. Use YYYY-MM-DD.', 'warning')

    if end_date:
        try:
            query = query.filter(DailyLog.date <= date.fromisoformat(end_date))
        except ValueError:
            flash('Invalid end date format. Use YYYY-MM-DD.', 'warning')

    logs = query.order_by(DailyLog.date.desc(), DailyLog.id.desc()).all()

    return render_template(
        'labor_daily_logs.html',
        logs=logs,
        start_date=start_date,
        end_date=end_date,
    )


@main.route('/labor/daily_logs/<int:log_id>/delete', methods=['POST'])
@login_required
def delete_labor_daily_log(log_id):
    """Delete a daily log entry."""
    log = DailyLog.query.filter_by(id=log_id, company_id=current_user.company_id).first_or_404()
    db.session.delete(log)
    db.session.commit()
    flash('Daily log deleted.', 'success')
    return redirect(url_for('main.labor_daily_logs'))


@main.route('/labor/pay_groups')
@login_required
def labor_pay_groups():
    """View and manage pay groups for the company."""
    pay_groups = PayGroups.query.filter_by(
        company_id=current_user.company_id
    ).order_by(PayGroups.name).all()
    return render_template('labor_pay_groups.html', pay_groups=pay_groups)


@main.route('/labor/pay_groups/create', methods=['POST'])
@login_required
def create_labor_pay_group():
    """Create a new pay group."""
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip() or None

    if not name:
        flash('Pay group name is required.', 'danger')
        return redirect(url_for('main.labor_pay_groups'))

    existing = PayGroups.query.filter_by(
        company_id=current_user.company_id, name=name
    ).first()
    if existing:
        flash(f'A pay group named "{name}" already exists.', 'warning')
        return redirect(url_for('main.labor_pay_groups'))

    pay_group = PayGroups(
        company_id=current_user.company_id,
        name=name,
        description=description,
    )
    db.session.add(pay_group)
    db.session.commit()
    flash(f'Pay group "{name}" created.', 'success')
    return redirect(url_for('main.labor_pay_groups'))


@main.route('/labor/pay_groups/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_labor_pay_group(group_id):
    """Delete a pay group."""
    pay_group = PayGroups.query.filter_by(
        id=group_id, company_id=current_user.company_id
    ).first_or_404()

    # Check if any weekly entries reference this pay group
    entry_count = WeeklyLaborEntry.query.filter_by(pay_group_id=group_id).count()
    if entry_count > 0:
        flash(
            f'Cannot delete "{pay_group.name}" — it has {entry_count} weekly labor '
            f'entr{"y" if entry_count == 1 else "ies"} associated with it.',
            'danger'
        )
        return redirect(url_for('main.labor_pay_groups'))

    db.session.delete(pay_group)
    db.session.commit()
    flash(f'Pay group "{pay_group.name}" deleted.', 'success')
    return redirect(url_for('main.labor_pay_groups'))


@main.route('/labor/weekly_entries')
@login_required
def labor_weekly_entries():
    """View weekly labor entries for the company."""
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    pay_group_id = request.args.get('pay_group_id', type=int)

    query = WeeklyLaborEntry.query.filter_by(company_id=current_user.company_id)

    if pay_group_id:
        query = query.filter_by(pay_group_id=pay_group_id)

    if start_date:
        try:
            query = query.filter(WeeklyLaborEntry.week_start_date >= date.fromisoformat(start_date))
        except ValueError:
            flash('Invalid start date format. Use YYYY-MM-DD.', 'warning')

    if end_date:
        try:
            query = query.filter(WeeklyLaborEntry.week_start_date <= date.fromisoformat(end_date))
        except ValueError:
            flash('Invalid end date format. Use YYYY-MM-DD.', 'warning')

    entries = query.order_by(
        WeeklyLaborEntry.week_start_date.desc(), WeeklyLaborEntry.id.desc()
    ).all()

    pay_groups = PayGroups.query.filter_by(
        company_id=current_user.company_id
    ).order_by(PayGroups.name).all()

    pay_group_map = {pg.id: pg.name for pg in pay_groups}

    return render_template(
        'labor_weekly_entries.html',
        entries=entries,
        pay_groups=pay_groups,
        pay_group_map=pay_group_map,
        start_date=start_date,
        end_date=end_date,
        selected_pay_group_id=pay_group_id,
    )


@main.route('/labor/weekly_entries/<int:entry_id>/delete', methods=['POST'])
@login_required
def delete_labor_weekly_entry(entry_id):
    """Delete a weekly labor entry."""
    entry = WeeklyLaborEntry.query.filter_by(
        id=entry_id, company_id=current_user.company_id
    ).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    flash('Weekly labor entry deleted.', 'success')
    return redirect(url_for('main.labor_weekly_entries'))


@main.route('/labor/film_usage')
@login_required
def labor_film_usage():
    """View film usage records for the company."""
    year_filter = request.args.get('year', type=int)

    query = FilmUsage.query.filter_by(company_id=current_user.company_id)
    if year_filter:
        query = query.filter_by(year=year_filter)

    records = query.order_by(FilmUsage.year.desc(), FilmUsage.month.desc()).all()

    # Build list of distinct years for the filter dropdown
    all_records = FilmUsage.query.filter_by(company_id=current_user.company_id).all()
    years = sorted({r.year for r in all_records}, reverse=True)

    return render_template(
        'labor_film_usage.html',
        records=records,
        years=years,
        year_filter=year_filter,
    )

@main.route('/labor/film_usage/<int:record_id>/delete', methods=['POST'])
@login_required
def delete_labor_film_usage(record_id):
    """Delete a film usage record."""
    record = FilmUsage.query.filter_by(
        id=record_id, company_id=current_user.company_id
    ).first_or_404()
    db.session.delete(record)
    db.session.commit()
    flash('Film usage record deleted.', 'success')
    return redirect(url_for('main.labor_film_usage'))
