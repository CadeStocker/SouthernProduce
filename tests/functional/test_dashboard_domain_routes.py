# Copyright Cade Stocker 2026
"""Functional tests for the per-domain dashboard endpoints.

Covers the contract each panel relies on: login required, the
``{summary, rows}`` shape, date-range handling, entity-name resolution, and
company scoping.
"""

from datetime import datetime, timedelta

import pytest

from app import db
from app.models.analytics import AnalyticsFact


# Every domain panel endpoint returns {'summary': {...}, 'rows': [...]}.
PANEL_ROUTES = (
    '/api/dashboard/sales',
    '/api/dashboard/pricing',
    '/api/dashboard/efficiency',
    '/api/dashboard/receiving',
    '/api/dashboard/inventory',
)

# Endpoints returning a bare list.
LIST_ROUTES = (
    '/api/dashboard/revenue_trend',
    '/api/dashboard/top_customers',
    '/api/dashboard/top_items',
    '/api/dashboard/price_dispersion',
    '/api/dashboard/cost_trend',
    '/api/dashboard/receiving_costs',
    '/api/dashboard/suppliers',
    '/api/dashboard/raw_product_costs',
    '/api/dashboard/inventory_levels',
    '/api/dashboard/stale_inventory',
    '/api/dashboard/anomalies',
)

ALL_ROUTES = PANEL_ROUTES + LIST_ROUTES


@pytest.mark.parametrize('route', ALL_ROUTES)
def test_endpoint_requires_login(client, route):
    rv = client.get(route, follow_redirects=False)
    assert rv.status_code in (302, 401), route


@pytest.mark.parametrize('route', PANEL_ROUTES)
def test_panel_returns_summary_and_rows(client, logged_in_user, app, route):
    """Panels answer with the shape the template's loadPanel helper expects."""
    with app.app_context():
        rv = client.get(route)
        assert rv.status_code == 200, route
        payload = rv.get_json()
        assert isinstance(payload, dict), route
        assert isinstance(payload['summary'], dict), route
        assert isinstance(payload['rows'], list), route


@pytest.mark.parametrize('route', LIST_ROUTES)
def test_list_endpoint_returns_a_list(client, logged_in_user, app, route):
    with app.app_context():
        rv = client.get(route)
        assert rv.status_code == 200, route
        assert isinstance(rv.get_json(), list), route


@pytest.mark.parametrize('route', ALL_ROUTES)
def test_endpoint_survives_a_malformed_date_range(client, logged_in_user, app, route):
    """Query strings are user input; a bad date falls back to the default window."""
    with app.app_context():
        rv = client.get(route + '?start_date=not-a-date&end_date=also-bad')
        assert rv.status_code == 200, route


@pytest.mark.parametrize('route', ALL_ROUTES)
def test_endpoint_survives_an_inverted_date_range(client, logged_in_user, app, route):
    with app.app_context():
        rv = client.get(route + '?start_date=2026-08-30&end_date=2026-08-01')
        assert rv.status_code == 200, route


def test_efficiency_reports_man_hours_per_case(client, logged_in_user, app):
    with app.app_context():
        today = datetime.utcnow().date()
        db.session.add(AnalyticsFact(
            fact_type='labor',
            company_id=logged_in_user.company_id,
            date=today,
            source_table='daily_log',
            source_id=1,
            quantity=500.0,      # cases
            labor_hours=100.0,
            cost=2500.0,
            revenue=10000.0,
        ))
        db.session.commit()

        payload = client.get('/api/dashboard/efficiency?days=7').get_json()

        assert payload['summary']['man_hours_per_case'] == pytest.approx(0.2)
        assert payload['summary']['cost_per_case'] == pytest.approx(5.0)
        assert payload['summary']['labor_ratio'] == pytest.approx(0.25)
        assert payload['rows'][0]['cases'] == 500.0


def test_receiving_reports_spend_from_the_cost_column(client, logged_in_user, app):
    with app.app_context():
        today = datetime.utcnow().date()
        db.session.add(AnalyticsFact(
            fact_type='receiving',
            company_id=logged_in_user.company_id,
            date=today,
            source_table='receiving_log',
            source_id=1,
            cost=400.0,
            quantity=100.0,
        ))
        db.session.commit()

        payload = client.get('/api/dashboard/receiving?days=7').get_json()

        assert payload['summary']['total_cost'] == 400.0
        assert payload['summary']['cost_per_unit'] == pytest.approx(4.0)
        assert payload['rows'][0]['total_cost'] == 400.0


def test_inventory_reports_count_to_count_movement(client, logged_in_user, app):
    with app.app_context():
        from app.models import Packaging, Item, UnitOfWeight

        packaging = Packaging(packaging_type='Box', company_id=logged_in_user.company_id)
        db.session.add(packaging)
        db.session.flush()
        item = Item(name='Sliced Apples', code='APL1', unit_of_weight=UnitOfWeight.POUND,
                    packaging_id=packaging.id, company_id=logged_in_user.company_id)
        db.session.add(item)
        db.session.flush()

        today = datetime.utcnow().date()
        for offset, quantity in ((5, 100.0), (0, 10.0)):
            db.session.add(AnalyticsFact(
                fact_type='inventory_snapshot',
                company_id=logged_in_user.company_id,
                date=today - timedelta(days=offset),
                source_table='inventory_count',
                source_id=offset + 1,
                item_id=item.id,
                quantity=quantity,
            ))
        db.session.commit()

        payload = client.get('/api/dashboard/inventory?days=30').get_json()

        assert payload['summary']['total_units'] == 10.0
        row = payload['rows'][0]
        assert row['item_name'] == 'Sliced Apples'   # resolved, not "Unknown"
        assert row['change'] == -90.0
        assert row['change_pct'] == pytest.approx(-90.0)


def test_pricing_pairs_cost_with_current_price(client, logged_in_user, app):
    with app.app_context():
        from app.models import Packaging, Item, UnitOfWeight, CurrentItemPrice

        packaging = Packaging(packaging_type='Box', company_id=logged_in_user.company_id)
        db.session.add(packaging)
        db.session.flush()
        item = Item(name='Diced Onion', code='ON1', unit_of_weight=UnitOfWeight.POUND,
                    packaging_id=packaging.id, company_id=logged_in_user.company_id)
        db.session.add(item)
        db.session.flush()

        db.session.add(AnalyticsFact(
            fact_type='cost_margin',
            company_id=logged_in_user.company_id,
            date=datetime.utcnow().date(),
            source_table='item_total_cost',
            source_id=1,
            item_id=item.id,
            cost=8.0,
        ))
        db.session.add(CurrentItemPrice(item_id=item.id,
                                        company_id=logged_in_user.company_id, price=10.0))
        db.session.commit()

        payload = client.get('/api/dashboard/pricing?days=30').get_json()

        row = payload['rows'][0]
        assert row['item_name'] == 'Diced Onion'
        assert row['cost'] == 8.0
        assert row['price'] == 10.0
        assert row['margin'] == pytest.approx(2.0)
        assert row['margin_pct'] == pytest.approx(20.0)
        assert payload['summary']['items_costed'] == 1


def test_panels_are_scoped_to_the_users_company(client, logged_in_user, app):
    """Another company's facts must never appear in these responses."""
    with app.app_context():
        from app.models import Company

        other = Company(name='Other Co', admin_email='other@example.com')
        db.session.add(other)
        db.session.flush()

        today = datetime.utcnow().date()
        db.session.add(AnalyticsFact(
            fact_type='receiving',
            company_id=other.id,
            date=today,
            source_table='receiving_log',
            source_id=1,
            cost=99999.0,
            quantity=1.0,
        ))
        db.session.commit()

        payload = client.get('/api/dashboard/receiving?days=7').get_json()

        assert payload['summary']['total_cost'] == 0.0
        assert payload['rows'] == []


def test_anomalies_endpoint_is_scoped_and_ranked_by_impact(client, logged_in_user, app):
    with app.app_context():
        from app.models import Company
        from app.models.anomalies import Anomaly

        other = Company(name='Other Co', admin_email='other@example.com')
        db.session.add(other)
        db.session.flush()

        db.session.add_all([
            Anomaly(domain='pricing', company_id=logged_in_user.company_id,
                    entity_type='item', entity_id=1, metric='margin_pct',
                    severity='low', dollar_impact=10.0, status='open'),
            Anomaly(domain='efficiency', company_id=logged_in_user.company_id,
                    entity_type='company', entity_id=1, metric='labor_ratio',
                    severity='high', dollar_impact=5000.0, status='open'),
            Anomaly(domain='pricing', company_id=other.id,
                    entity_type='item', entity_id=2, metric='margin_pct',
                    severity='high', dollar_impact=99999.0, status='open'),
        ])
        db.session.commit()

        rows = client.get('/api/dashboard/anomalies').get_json()

        assert [row['metric'] for row in rows] == ['labor_ratio', 'margin_pct']
        assert rows[0]['domain_label'] == 'Labor & Efficiency'
        assert all(row['dollar_impact'] != 99999.0 for row in rows)


def test_anomalies_endpoint_filters_by_domain(client, logged_in_user, app):
    with app.app_context():
        from app.models.anomalies import Anomaly

        db.session.add_all([
            Anomaly(domain='pricing', company_id=logged_in_user.company_id,
                    entity_type='item', entity_id=1, metric='margin_pct',
                    severity='low', status='open'),
            Anomaly(domain='inventory', company_id=logged_in_user.company_id,
                    entity_type='item', entity_id=1, metric='inventory_swing',
                    severity='low', status='open'),
        ])
        db.session.commit()

        rows = client.get('/api/dashboard/anomalies?domain=inventory').get_json()

        assert [row['metric'] for row in rows] == ['inventory_swing']


def test_anomalies_endpoint_excludes_resolved_findings(client, logged_in_user, app):
    with app.app_context():
        from app.models.anomalies import Anomaly

        db.session.add(Anomaly(domain='pricing', company_id=logged_in_user.company_id,
                               entity_type='item', entity_id=1, metric='margin_pct',
                               severity='high', status='fixed'))
        db.session.commit()

        assert client.get('/api/dashboard/anomalies').get_json() == []


def test_dashboard_page_shows_every_domain_section(client, logged_in_user, app):
    with app.app_context():
        rv = client.get('/dashboard')

        assert rv.status_code == 200
        body = rv.data
        for heading in (b'Pricing &amp; Margin', b'Labor &amp; Efficiency',
                        b'Receiving &amp; Suppliers', b'Inventory', b'Sales &amp; Customers'):
            assert heading in body, heading
        # The data-coverage panel names every domain so an empty section is
        # explainable rather than mysterious.
        assert b'Data Coverage' in body


def test_dashboard_page_honours_an_explicit_date_range(client, logged_in_user, app):
    with app.app_context():
        rv = client.get('/dashboard?start_date=2026-01-01&end_date=2026-01-31')

        assert rv.status_code == 200
        assert b'2026-01-01' in rv.data
        assert b'2026-01-31' in rv.data


def test_analytics_data_page_covers_every_domain(client, logged_in_user, app):
    with app.app_context():
        rv = client.get('/analytics_data?days=30')

        assert rv.status_code == 200
        for heading in (b'Margin by Item', b'Daily Efficiency', b'Daily Inbound Spend',
                        b'Count-to-Count Movement', b'Daily Revenue'):
            assert heading in rv.data, heading


def test_data_insights_filters_by_domain(client, logged_in_user, app):
    with app.app_context():
        from app.models.anomalies import Anomaly

        db.session.add_all([
            Anomaly(domain='pricing', company_id=logged_in_user.company_id,
                    entity_type='item', entity_id=1, metric='margin_pct',
                    severity='low', status='open',
                    explanation='PRICING FINDING'),
            Anomaly(domain='inventory', company_id=logged_in_user.company_id,
                    entity_type='item', entity_id=1, metric='inventory_swing',
                    severity='low', status='open',
                    explanation='INVENTORY FINDING'),
        ])
        db.session.commit()

        rv = client.get('/data_insights?domain=inventory')

        assert rv.status_code == 200
        assert b'INVENTORY FINDING' in rv.data
        assert b'PRICING FINDING' not in rv.data


def test_data_insights_hides_other_companies_anomalies(client, logged_in_user, app):
    with app.app_context():
        from app.models import Company
        from app.models.anomalies import Anomaly

        other = Company(name='Other Co', admin_email='other@example.com')
        db.session.add(other)
        db.session.flush()
        db.session.add(Anomaly(domain='pricing', company_id=other.id,
                               entity_type='item', entity_id=1, metric='margin_pct',
                               severity='high', status='open',
                               explanation='SOMEONE ELSES FINDING'))
        db.session.commit()

        rv = client.get('/data_insights')

        assert rv.status_code == 200
        assert b'SOMEONE ELSES FINDING' not in rv.data


def test_cannot_review_another_companys_anomaly(client, logged_in_user, app):
    """An id from another tenant must be indistinguishable from a missing one."""
    with app.app_context():
        from app.models import Company
        from app.models.anomalies import Anomaly

        other = Company(name='Other Co', admin_email='other@example.com')
        db.session.add(other)
        db.session.flush()
        anomaly = Anomaly(domain='pricing', company_id=other.id,
                          entity_type='item', entity_id=1, metric='margin_pct',
                          severity='high', status='open')
        db.session.add(anomaly)
        db.session.commit()
        anomaly_id = anomaly.id

        rv = client.post(f'/api/anomalies/{anomaly_id}/mark_reviewed', json={'notes': 'x'})

        assert rv.status_code == 404
        assert db.session.get(Anomaly, anomaly_id).status == 'open'
