# Copyright Cade Stocker 2026
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.services import analytics_reports
from datetime import datetime, timedelta

dashboard = Blueprint('dashboard', __name__)


@dashboard.route('/dashboard')
@login_required
def analytics_dashboard():
    """Main analytics dashboard with KPIs and charts."""
    company_id = current_user.company_id
    today = datetime.utcnow().date()

    # Last 30 days for trending
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).date()

    # Get today's summary
    today_summary = analytics_reports.get_daily_summary(company_id, today)

    # Get period totals for last 30 days
    period_totals = analytics_reports.get_period_totals(company_id, thirty_days_ago, today)

    # Get data for charts (API will fetch these)
    return render_template(
        'dashboard.html',
        today_summary=today_summary,
        period_totals=period_totals,
        thirty_days_ago=thirty_days_ago,
        today=today,
    )


@dashboard.route('/api/dashboard/revenue_trend')
@login_required
def api_revenue_trend():
    """Get revenue trend data for chart."""
    company_id = current_user.company_id
    days = request.args.get('days', 30, type=int)
    start_date = (datetime.utcnow() - timedelta(days=days)).date()
    end_date = datetime.utcnow().date()

    trend = analytics_reports.get_daily_revenue_trend(company_id, start_date, end_date)
    return jsonify([
        {
            'date': row['date'].isoformat(),
            'revenue': float(row['revenue']),
            'quantity': float(row['quantity']),
        }
        for row in trend
    ])


@dashboard.route('/api/dashboard/top_customers')
@login_required
def api_top_customers():
    """Get top customers by revenue."""
    company_id = current_user.company_id
    limit = request.args.get('limit', 10, type=int)
    days = request.args.get('days', 30, type=int)
    start_date = (datetime.utcnow() - timedelta(days=days)).date()
    end_date = datetime.utcnow().date()

    from app.models import Customer
    customers_data = analytics_reports.get_top_customers_by_revenue(
        company_id, start_date, end_date, limit
    )

    result = []
    for row in customers_data:
        customer = Customer.query.get(row['customer_id']) if row['customer_id'] else None
        result.append({
            'customer_id': row['customer_id'],
            'customer_name': customer.name if customer else 'Unknown',
            'revenue': float(row['revenue']),
            'quantity': float(row['quantity']),
        })
    return jsonify(result)


@dashboard.route('/api/dashboard/top_items')
@login_required
def api_top_items():
    """Get top items by sales volume."""
    company_id = current_user.company_id
    limit = request.args.get('limit', 10, type=int)
    days = request.args.get('days', 30, type=int)
    start_date = (datetime.utcnow() - timedelta(days=days)).date()
    end_date = datetime.utcnow().date()

    from app.models import Item
    items_data = analytics_reports.get_top_items_by_sales_volume(
        company_id, start_date, end_date, limit
    )

    result = []
    for row in items_data:
        item = Item.query.get(row['item_id']) if row['item_id'] else None
        result.append({
            'item_id': row['item_id'],
            'item_name': item.name if item else 'Unknown',
            'quantity': float(row['quantity']),
            'revenue': float(row['revenue']),
        })
    return jsonify(result)


@dashboard.route('/api/dashboard/receiving_costs')
@login_required
def api_receiving_costs():
    """Get receiving costs trend."""
    company_id = current_user.company_id
    days = request.args.get('days', 30, type=int)
    start_date = (datetime.utcnow() - timedelta(days=days)).date()
    end_date = datetime.utcnow().date()

    costs = analytics_reports.get_receiving_costs(company_id, start_date, end_date)
    return jsonify([
        {
            'date': row['date'].isoformat(),
            'total_cost': float(row['total_cost']),
            'quantity': float(row['quantity']),
        }
        for row in costs
    ])
