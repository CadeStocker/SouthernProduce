"""Functional tests for dashboard and analytics routes."""
import pytest
from datetime import datetime, timedelta
from app import db
from app.models.analytics import AnalyticsFact


def test_dashboard_requires_login(client):
    """Dashboard should redirect to login if not authenticated."""
    rv = client.get('/dashboard', follow_redirects=False)
    assert rv.status_code in (302, 401)


def test_dashboard_loads_when_logged_in(client, logged_in_user, app):
    """Dashboard should load successfully for logged-in users."""
    with app.app_context():
        rv = client.get('/dashboard')
        assert rv.status_code == 200
        assert b'Analytics Dashboard' in rv.data
        # The dashboard covers every domain, not just sales.
        for section in (b'Pricing', b'Efficiency', b'Receiving', b'Inventory', b'Sales'):
            assert section in rv.data


def test_dashboard_displays_kpi_cards(client, logged_in_user, app):
    """Dashboard should display KPI cards with data."""
    with app.app_context():
        company_id = logged_in_user.company_id

        # Add some data
        today = datetime.utcnow().date()
        fact = AnalyticsFact(
            fact_type='item_sale',
            company_id=company_id,
            date=today,
            source_table='sales_record',
            source_id=1,
            revenue=1000.0,
            quantity=50.0
        )
        db.session.add(fact)
        db.session.commit()

        rv = client.get('/dashboard')
        assert rv.status_code == 200
        assert b'$' in rv.data  # Should show currency


def test_dashboard_chart_script_present(client, logged_in_user, app):
    """Dashboard should include Chart.js scripts for rendering."""
    with app.app_context():
        rv = client.get('/dashboard')
        assert rv.status_code == 200
        assert b'chart.js' in rv.data or b'Chart' in rv.data


def test_analytics_data_requires_login(client):
    """Analytics data page should redirect to login if not authenticated."""
    rv = client.get('/analytics_data', follow_redirects=False)
    assert rv.status_code in (302, 401)


def test_analytics_data_loads_when_logged_in(client, logged_in_user, app):
    """Analytics data page should load successfully."""
    with app.app_context():
        rv = client.get('/analytics_data')
        assert rv.status_code == 200
        assert b'Analytics Data' in rv.data


def test_analytics_data_default_date_range(client, logged_in_user, app):
    """Analytics data should default to 30-day range."""
    with app.app_context():
        rv = client.get('/analytics_data')
        assert rv.status_code == 200
        # Should have 30 selected (checked by form state)
        assert b'value="30"' in rv.data and b'selected' in rv.data


def test_analytics_data_date_filter_7_days(client, logged_in_user, app):
    """Analytics data should accept 7-day filter."""
    with app.app_context():
        rv = client.get('/analytics_data?days=7')
        assert rv.status_code == 200
        assert b'value="7"' in rv.data and b'selected' in rv.data


def test_analytics_data_date_filter_90_days(client, logged_in_user, app):
    """Analytics data should accept 90-day filter."""
    with app.app_context():
        rv = client.get('/analytics_data?days=90')
        assert rv.status_code == 200
        assert b'value="90"' in rv.data and b'selected' in rv.data


def test_analytics_data_displays_tables(client, logged_in_user, app):
    """Analytics data should display metric tables."""
    with app.app_context():
        rv = client.get('/analytics_data')
        assert rv.status_code == 200
        # Should have table headers
        assert b'<table' in rv.data
        assert b'Date' in rv.data or b'Revenue' in rv.data or b'Customer' in rv.data


def test_analytics_data_shows_period_summary(client, logged_in_user, app):
    """Analytics data should display period summary cards."""
    with app.app_context():
        company_id = logged_in_user.company_id

        # Add data
        today = datetime.utcnow().date()
        fact = AnalyticsFact(
            fact_type='item_sale',
            company_id=company_id,
            date=today,
            source_table='sales_record',
            source_id=1,
            revenue=500.0,
            quantity=25.0
        )
        db.session.add(fact)
        db.session.commit()

        rv = client.get('/analytics_data')
        assert rv.status_code == 200
        # Should show currency in response
        assert b'$' in rv.data


def test_api_revenue_trend_requires_login(client):
    """Revenue trend API should require authentication."""
    rv = client.get('/api/dashboard/revenue_trend', follow_redirects=False)
    assert rv.status_code in (302, 401)


def test_api_revenue_trend_returns_json(client, logged_in_user, app):
    """Revenue trend API should return valid JSON."""
    import json

    with app.app_context():
        company_id = logged_in_user.company_id

        # Add data
        today = datetime.utcnow().date()
        fact = AnalyticsFact(
            fact_type='item_sale',
            company_id=company_id,
            date=today,
            source_table='sales_record',
            source_id=1,
            revenue=500.0,
            quantity=25.0
        )
        db.session.add(fact)
        db.session.commit()

        rv = client.get('/api/dashboard/revenue_trend?days=30')
        assert rv.status_code == 200
        data = json.loads(rv.data)
        assert isinstance(data, list)
        if len(data) > 0:
            assert 'date' in data[0]
            assert 'revenue' in data[0]
            assert 'quantity' in data[0]


def test_api_revenue_trend_respects_days_parameter(client, logged_in_user, app):
    """Revenue trend API should respect days parameter."""
    import json
    from datetime import timedelta

    with app.app_context():
        company_id = logged_in_user.company_id

        # Add data for multiple days
        for i in range(35):
            day = datetime.utcnow().date() - timedelta(days=i)
            fact = AnalyticsFact(
                fact_type='item_sale',
                company_id=company_id,
                date=day,
                source_table='sales_record',
                source_id=i,
                revenue=100.0,
                quantity=10.0
            )
            db.session.add(fact)
        db.session.commit()

        # Query 7 days
        rv = client.get('/api/dashboard/revenue_trend?days=7')
        assert rv.status_code == 200
        data = json.loads(rv.data)
        # Should have at most 8 days (7 + today, or fewer if no data)
        assert len(data) <= 8


def test_api_top_customers_returns_json(client, logged_in_user, app):
    """Top customers API should return valid JSON."""
    import json

    with app.app_context():
        company_id = logged_in_user.company_id

        # Add customer data
        fact = AnalyticsFact(
            fact_type='item_sale',
            company_id=company_id,
            customer_id=1,
            date=datetime.utcnow().date(),
            source_table='sales_record',
            source_id=1,
            revenue=500.0,
            quantity=25.0
        )
        db.session.add(fact)
        db.session.commit()

        rv = client.get('/api/dashboard/top_customers?limit=10&days=30')
        assert rv.status_code == 200
        data = json.loads(rv.data)
        assert isinstance(data, list)


def test_api_top_items_returns_json(client, logged_in_user, app):
    """Top items API should return valid JSON."""
    import json

    with app.app_context():
        company_id = logged_in_user.company_id

        # Add item data
        fact = AnalyticsFact(
            fact_type='item_sale',
            company_id=company_id,
            item_id=1,
            date=datetime.utcnow().date(),
            source_table='sales_record',
            source_id=1,
            revenue=500.0,
            quantity=100.0
        )
        db.session.add(fact)
        db.session.commit()

        rv = client.get('/api/dashboard/top_items?limit=10&days=30')
        assert rv.status_code == 200
        data = json.loads(rv.data)
        assert isinstance(data, list)


def test_api_receiving_costs_returns_json(client, logged_in_user, app):
    """Receiving costs API should return valid JSON."""
    import json

    with app.app_context():
        company_id = logged_in_user.company_id

        # Add receiving data
        fact = AnalyticsFact(
            fact_type='receiving',
            company_id=company_id,
            date=datetime.utcnow().date(),
            source_table='receiving_log',
            source_id=1,
            revenue=250.0,
            quantity=100.0
        )
        db.session.add(fact)
        db.session.commit()

        rv = client.get('/api/dashboard/receiving_costs?days=30')
        assert rv.status_code == 200
        data = json.loads(rv.data)
        assert isinstance(data, list)


def test_api_endpoints_isolated_by_company(client, logged_in_user, app):
    """API endpoints should only return data for logged-in user's company."""
    import json

    with app.app_context():
        user_company = logged_in_user.company_id
        other_company = 999

        # Add data for user's company
        fact1 = AnalyticsFact(
            fact_type='item_sale',
            company_id=user_company,
            date=datetime.utcnow().date(),
            source_table='sales_record',
            source_id=1,
            revenue=500.0,
            quantity=50.0
        )
        db.session.add(fact1)

        # Add data for other company
        fact2 = AnalyticsFact(
            fact_type='item_sale',
            company_id=other_company,
            date=datetime.utcnow().date(),
            source_table='sales_record',
            source_id=2,
            revenue=1000.0,
            quantity=100.0
        )
        db.session.add(fact2)
        db.session.commit()

        rv = client.get('/api/dashboard/revenue_trend?days=30')
        assert rv.status_code == 200
        data = json.loads(rv.data)
        # Should only see user's company data
        if len(data) > 0:
            assert data[0]['revenue'] == 500.0  # user's data, not other company


def test_dashboard_link_to_analytics_data(client, logged_in_user, app):
    """Dashboard should have link to analytics data page."""
    with app.app_context():
        rv = client.get('/dashboard')
        assert rv.status_code == 200
        assert b'/analytics_data' in rv.data or b'Detailed Analytics' in rv.data


def test_analytics_data_link_to_dashboard(client, logged_in_user, app):
    """Analytics data page should have link back to dashboard."""
    with app.app_context():
        rv = client.get('/analytics_data')
        assert rv.status_code == 200
        assert b'/dashboard' in rv.data or b'Dashboard' in rv.data


def test_analytics_data_link_to_anomalies(client, logged_in_user, app):
    """Analytics data page should have link to anomalies."""
    with app.app_context():
        rv = client.get('/analytics_data')
        assert rv.status_code == 200
        assert b'/data_insights' in rv.data or b'Anomalies' in rv.data
