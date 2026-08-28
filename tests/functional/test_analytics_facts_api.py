# Copyright Cade Stocker 2026
"""
Functional tests proving the operational API write paths populate AnalyticsFact.
Covers every endpoint wired to app.services.analytics_facts, that facts share the
request transaction, and that failed requests leave no facts behind.
"""

import pytest
from datetime import date, datetime, timedelta

from app import db
from app.models import (
    AnalyticsFact,
    APIKey,
    Company,
    User,
    Packaging,
    Item,
    RawProduct,
    BrandName,
    Seller,
    GrowerOrDistributor,
    Supply,
    Customer,
    DesignationCost,
    PayGroups,
    ReceivingLog,
    SalesRecord,
    ItemInventory,
    DailyLog,
    WeeklyLaborEntry,
    UnitOfWeight,
    ItemDesignation,
)

API_KEY = 'analytics-facts-functional-key'
HEADERS = {'X-API-Key': API_KEY}

# SalesRecordCreateSchema rejects future sale dates, so anchor to a past instant
# rather than a literal that would break depending on the time of day.
SALE_DT = datetime.now() - timedelta(days=7)


@pytest.fixture
def env(app):
    """Create a company with an API key and all reference data the writes need."""
    with app.app_context():
        company = Company(name='Fact Co', admin_email='facts@example.com')
        db.session.add(company)
        db.session.flush()

        user = User(
            first_name='Fact', last_name='Tester',
            email='tester@example.com', password='hashed',
            company_id=company.id,
        )
        db.session.add(user)
        db.session.flush()

        db.session.add(APIKey(
            key=API_KEY, device_name='iPad',
            company_id=company.id, created_by_user_id=user.id,
        ))

        packaging = Packaging(packaging_type='Box', company_id=company.id)
        raw_product = RawProduct(name='Lettuce', company_id=company.id)
        brand = BrandName(name='Brand', company_id=company.id)
        seller = Seller(name='Seller', company_id=company.id)
        grower = GrowerOrDistributor(
            name='Grower', company_id=company.id, city='Salinas', state='CA'
        )
        customer = Customer(name='Customer', email='cust@example.com', company_id=company.id)
        designation = DesignationCost(
            item_designation=ItemDesignation.FOODSERVICE,
            cost=1.0, date=date(2026, 8, 1), company_id=company.id,
        )
        pay_group = PayGroups(company_id=company.id, name='Packing')
        supply = Supply(name='Film Roll', unit='roll', company_id=company.id)
        db.session.add_all([
            packaging, raw_product, brand, seller, grower,
            customer, designation, pay_group, supply,
        ])
        db.session.flush()

        item = Item(
            name='Sliced Apples', code='APL001',
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id, company_id=company.id, case_weight=25.0,
        )
        second_item = Item(
            name='Diced Carrots', code='CAR001',
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id, company_id=company.id, case_weight=30.0,
        )
        db.session.add_all([item, second_item])
        db.session.commit()

        yield {
            'company_id': company.id,
            'raw_product_id': raw_product.id,
            'brand_id': brand.id,
            'seller_id': seller.id,
            'grower_id': grower.id,
            'customer_id': customer.id,
            'designation_id': designation.id,
            'pay_group_id': pay_group.id,
            'supply_id': supply.id,
            'item_id': item.id,
            'second_item_id': second_item.id,
        }


def _facts(app, **filters):
    with app.app_context():
        return AnalyticsFact.query.filter_by(**filters).all()


def _receiving_payload(env, **overrides):
    payload = {
        'raw_product_id': env['raw_product_id'],
        'pack_size_unit': 'lb',
        'pack_size': 10.0,
        'brand_name_id': env['brand_id'],
        'quantity_received': 20,
        'seller_id': env['seller_id'],
        'temperature': 35.0,
        'hold_or_used': 'used',
        'grower_or_distributor_id': env['grower_id'],
        'country_of_origin': 'USA',
        'received_by': 'Tester',
        'datetime': '2026-08-26T09:00:00',
        'price_paid': 2.5,
    }
    payload.update(overrides)
    return payload


def _sales_payload(env, **overrides):
    payload = {
        'customer_id': env['customer_id'],
        'item_designation_id': env['designation_id'],
        'quantity_sold': 10,
        'unit_price': 5.0,
        'total_price': 50.0,
        'sale_date': SALE_DT.isoformat(),
    }
    payload.update(overrides)
    return payload


def _daily_log_payload(**overrides):
    payload = {
        'date': '2026-08-24',
        'items': 500,
        'sales': 10000.0,
        'labor_hours': 180.0,
        'overtime_hours': 12.0,
        'payroll_cost': 2500.0,
        'number_of_employees': 20,
        'labor_ratio': 0.25,
        'sales_over_labor_cost': 4.0,
        'average_man_hour_cost': 13.9,
        'average_case_cost': 5.0,
        'average_hours_per_employee': 9.0,
    }
    payload.update(overrides)
    return payload


def _weekly_labor_payload(env, **overrides):
    payload = {
        'week_start_date': '2026-08-17',
        'pay_group_id': env['pay_group_id'],
        'regular_hours': 400.0,
        'overtime_hours': 35.5,
        'pay': 9000.0,
        'percent_of_sales': 0.22,
        'cost_per_hour': 20.7,
        'number_in_pay_group': 15,
        'number_with_overtime': 4,
        'average_hours_per_employee': 29.0,
    }
    payload.update(overrides)
    return payload


class TestReceivingLogEndpoint:
    """POST /api/receiving/receiving_logs writes a receiving fact."""

    def test_creates_receiving_fact(self, client, app, env):
        response = client.post(
            '/api/receiving/receiving_logs',
            json=_receiving_payload(env),
            headers=HEADERS,
        )
        assert response.status_code == 201
        log_id = response.get_json()['id']

        facts = _facts(app, fact_type='receiving', source_id=log_id)
        assert len(facts) == 1
        fact = facts[0]
        assert fact.source_table == 'receiving_log'
        assert fact.company_id == env['company_id']
        assert fact.date == date(2026, 8, 26)
        assert fact.raw_product_id == env['raw_product_id']
        assert fact.supplier_id == env['grower_id']
        assert fact.quantity == 20
        assert fact.cost == 50.0

    def test_fact_written_when_price_paid_is_omitted(self, client, app, env):
        payload = _receiving_payload(env)
        payload.pop('price_paid')
        response = client.post(
            '/api/receiving/receiving_logs', json=payload, headers=HEADERS
        )
        assert response.status_code == 201

        facts = _facts(app, fact_type='receiving', source_id=response.get_json()['id'])
        assert len(facts) == 1
        assert facts[0].cost == 0.0

    def test_rejected_request_writes_no_fact(self, client, app, env):
        response = client.post(
            '/api/receiving/receiving_logs',
            json=_receiving_payload(env, hold_or_used='not_a_status'),
            headers=HEADERS,
        )
        assert response.status_code == 400
        assert _facts(app, fact_type='receiving') == []

    def test_unauthenticated_request_writes_no_fact(self, client, app, env):
        response = client.post(
            '/api/receiving/receiving_logs', json=_receiving_payload(env)
        )
        assert response.status_code in (401, 403)
        assert _facts(app, fact_type='receiving') == []


class TestSalesRecordEndpoint:
    """POST /api/sales/records writes both sale-grain and order-grain facts."""

    def test_creates_item_sale_and_customer_order_facts(self, client, app, env):
        response = client.post(
            '/api/sales/records', json=_sales_payload(env), headers=HEADERS
        )
        assert response.status_code == 201
        sale_id = response.get_json()['sale_record']['id']

        facts = _facts(app, source_table='sales_record', source_id=sale_id)
        assert {f.fact_type for f in facts} == {'item_sale', 'customer_order'}
        for fact in facts:
            assert fact.company_id == env['company_id']
            assert fact.date == SALE_DT.date()
            assert fact.customer_id == env['customer_id']
            assert fact.quantity == 10
            assert fact.revenue == 50.0

    def test_sale_without_customer_still_writes_facts(self, client, app, env):
        response = client.post(
            '/api/sales/records',
            json=_sales_payload(env, customer_id=0),
            headers=HEADERS,
        )
        assert response.status_code == 201
        sale_id = response.get_json()['sale_record']['id']

        facts = _facts(app, source_table='sales_record', source_id=sale_id)
        assert len(facts) == 2
        assert all(f.customer_id is None for f in facts)

    def test_rejected_request_writes_no_fact(self, client, app, env):
        response = client.post(
            '/api/sales/records',
            json=_sales_payload(env, quantity_sold=-5),
            headers=HEADERS,
        )
        assert response.status_code == 400
        assert _facts(app, source_table='sales_record') == []

    def test_unknown_customer_writes_no_fact(self, client, app, env):
        response = client.post(
            '/api/sales/records',
            json=_sales_payload(env, customer_id=999999),
            headers=HEADERS,
        )
        assert response.status_code == 404
        assert _facts(app, source_table='sales_record') == []


class TestInventoryCountEndpoint:
    """POST /api/inventory/inventory_counts writes an inventory_snapshot fact."""

    def test_creates_inventory_snapshot_fact(self, client, app, env):
        response = client.post(
            '/api/inventory/inventory_counts',
            json={
                'item_id': env['item_id'],
                'quantity': 42,
                'counted_by': 'Tester',
                'count_date': '2026-08-25T08:00:00',
            },
            headers=HEADERS,
        )
        assert response.status_code == 201
        count_id = response.get_json()['inventory_count']['id']

        facts = _facts(app, fact_type='inventory_snapshot', source_id=count_id)
        assert len(facts) == 1
        fact = facts[0]
        assert fact.source_table == 'inventory_count'
        assert fact.company_id == env['company_id']
        assert fact.item_id == env['item_id']
        assert fact.quantity == 42
        assert fact.date == date(2026, 8, 25)

    def test_fact_dated_from_default_count_date_when_omitted(self, client, app, env):
        response = client.post(
            '/api/inventory/inventory_counts',
            json={'item_id': env['item_id'], 'quantity': 5},
            headers=HEADERS,
        )
        assert response.status_code == 201
        count_id = response.get_json()['inventory_count']['id']

        with app.app_context():
            count = db.session.get(ItemInventory, count_id)
            fact = AnalyticsFact.query.filter_by(
                fact_type='inventory_snapshot', source_id=count_id
            ).one()
            assert fact.date == count.count_date.date()

    def test_rejected_request_writes_no_fact(self, client, app, env):
        response = client.post(
            '/api/inventory/inventory_counts',
            json={'item_id': env['item_id']},
            headers=HEADERS,
        )
        assert response.status_code == 400
        assert _facts(app, fact_type='inventory_snapshot') == []

    def test_unknown_item_writes_no_fact(self, client, app, env):
        response = client.post(
            '/api/inventory/inventory_counts',
            json={'item_id': 999999, 'quantity': 5},
            headers=HEADERS,
        )
        assert response.status_code == 404
        assert _facts(app, fact_type='inventory_snapshot') == []


class TestInventorySessionEndpoint:
    """POST /api/inventory/inventory_sessions writes one fact per item line."""

    def test_creates_one_fact_per_item_count(self, client, app, env):
        response = client.post(
            '/api/inventory/inventory_sessions',
            json={
                'label': 'Morning count',
                'counted_by': 'Tester',
                'submitted_at': '2026-08-25T08:00:00',
                'item_counts': [
                    {'item_id': env['item_id'], 'quantity': 40},
                    {'item_id': env['second_item_id'], 'quantity': 12},
                ],
                'supply_counts': [{'supply_id': env['supply_id'], 'quantity': 5}],
            },
            headers=HEADERS,
        )
        assert response.status_code == 201

        facts = _facts(app, fact_type='inventory_snapshot')
        assert len(facts) == 2
        assert {(f.item_id, f.quantity) for f in facts} == {
            (env['item_id'], 40), (env['second_item_id'], 12)
        }
        assert all(f.date == date(2026, 8, 25) for f in facts)
        assert all(f.source_table == 'inventory_count' for f in facts)

    def test_facts_reference_the_created_count_rows(self, client, app, env):
        response = client.post(
            '/api/inventory/inventory_sessions',
            json={
                'submitted_at': '2026-08-25T08:00:00',
                'item_counts': [{'item_id': env['item_id'], 'quantity': 40}],
            },
            headers=HEADERS,
        )
        assert response.status_code == 201

        with app.app_context():
            count_ids = {c.id for c in ItemInventory.query.all()}
            fact_source_ids = {
                f.source_id for f in
                AnalyticsFact.query.filter_by(fact_type='inventory_snapshot').all()
            }
            assert fact_source_ids == count_ids

    def test_supply_counts_do_not_create_facts(self, client, app, env):
        """Only finished-goods counts map onto inventory_snapshot facts."""
        response = client.post(
            '/api/inventory/inventory_sessions',
            json={
                'submitted_at': '2026-08-25T08:00:00',
                'item_counts': [],
                'supply_counts': [{'supply_id': env['supply_id'], 'quantity': 5}],
            },
            headers=HEADERS,
        )
        assert response.status_code == 201
        assert _facts(app, fact_type='inventory_snapshot') == []

    def test_unknown_item_rolls_back_the_whole_session(self, client, app, env):
        response = client.post(
            '/api/inventory/inventory_sessions',
            json={
                'submitted_at': '2026-08-25T08:00:00',
                'item_counts': [
                    {'item_id': env['item_id'], 'quantity': 40},
                    {'item_id': 999999, 'quantity': 1},
                ],
            },
            headers=HEADERS,
        )
        assert response.status_code == 404
        assert _facts(app, fact_type='inventory_snapshot') == []


class TestDailyLogEndpoint:
    """POST /api/labor/daily_logs writes a labor fact."""

    def test_creates_labor_fact(self, client, app, env):
        response = client.post(
            '/api/labor/daily_logs', json=_daily_log_payload(), headers=HEADERS
        )
        assert response.status_code == 201
        log_id = response.get_json()['daily_log']['id']

        facts = _facts(app, source_table='daily_log', source_id=log_id)
        assert len(facts) == 1
        fact = facts[0]
        assert fact.fact_type == 'labor'
        assert fact.company_id == env['company_id']
        assert fact.date == date(2026, 8, 24)
        assert fact.revenue == 10000.0
        assert fact.cost == 2500.0
        assert fact.labor_hours == 180.0

    def test_rejected_request_writes_no_fact(self, client, app, env):
        response = client.post(
            '/api/labor/daily_logs',
            json=_daily_log_payload(labor_hours=-1),
            headers=HEADERS,
        )
        assert response.status_code == 400
        assert _facts(app, source_table='daily_log') == []


class TestWeeklyLaborEntryEndpoint:
    """POST /api/labor/weekly_labor_entries writes a labor fact."""

    def test_creates_labor_fact_with_summed_hours(self, client, app, env):
        response = client.post(
            '/api/labor/weekly_labor_entries',
            json=_weekly_labor_payload(env),
            headers=HEADERS,
        )
        assert response.status_code == 201
        entry_id = response.get_json()['weekly_labor_entry']['id']

        facts = _facts(app, source_table='weekly_labor_summary', source_id=entry_id)
        assert len(facts) == 1
        fact = facts[0]
        assert fact.fact_type == 'labor'
        assert fact.date == date(2026, 8, 17)
        assert fact.cost == 9000.0
        assert fact.labor_hours == 435.5

    def test_unknown_pay_group_writes_no_fact(self, client, app, env):
        response = client.post(
            '/api/labor/weekly_labor_entries',
            json=_weekly_labor_payload(env, pay_group_id=999999),
            headers=HEADERS,
        )
        assert response.status_code == 404
        assert _facts(app, source_table='weekly_labor_summary') == []


class TestFactsAcrossEndpoints:
    """Cross-endpoint behavior of the shared fact table."""

    def test_labor_facts_from_both_sources_coexist(self, client, app, env):
        daily = client.post(
            '/api/labor/daily_logs', json=_daily_log_payload(), headers=HEADERS
        )
        weekly = client.post(
            '/api/labor/weekly_labor_entries',
            json=_weekly_labor_payload(env), headers=HEADERS,
        )
        assert daily.status_code == 201
        assert weekly.status_code == 201

        facts = _facts(app, fact_type='labor')
        assert len(facts) == 2
        assert {f.source_table for f in facts} == {'daily_log', 'weekly_labor_summary'}

    def test_repeated_posts_create_one_fact_per_source_row(self, client, app, env):
        """Each POST creates a new source row, so each gets its own fact -- the
        idempotency key is source lineage, not payload equality."""
        for _ in range(3):
            assert client.post(
                '/api/receiving/receiving_logs',
                json=_receiving_payload(env), headers=HEADERS,
            ).status_code == 201

        with app.app_context():
            log_ids = {log.id for log in ReceivingLog.query.all()}
            facts = AnalyticsFact.query.filter_by(fact_type='receiving').all()
            assert len(facts) == 3
            assert {f.source_id for f in facts} == log_ids

    def test_every_operational_write_lands_in_one_fact_table(self, client, app, env):
        """The point of the layer: one query surface across all domains."""
        assert client.post(
            '/api/receiving/receiving_logs',
            json=_receiving_payload(env), headers=HEADERS,
        ).status_code == 201
        assert client.post(
            '/api/sales/records', json=_sales_payload(env), headers=HEADERS
        ).status_code == 201
        assert client.post(
            '/api/inventory/inventory_counts',
            json={'item_id': env['item_id'], 'quantity': 42}, headers=HEADERS,
        ).status_code == 201
        assert client.post(
            '/api/labor/daily_logs', json=_daily_log_payload(), headers=HEADERS
        ).status_code == 201
        assert client.post(
            '/api/labor/weekly_labor_entries',
            json=_weekly_labor_payload(env), headers=HEADERS,
        ).status_code == 201

        with app.app_context():
            types = [f.fact_type for f in AnalyticsFact.query.all()]
            assert sorted(types) == sorted([
                'receiving', 'item_sale', 'customer_order',
                'inventory_snapshot', 'labor', 'labor',
            ])
            assert all(
                f.company_id == env['company_id'] for f in AnalyticsFact.query.all()
            )
