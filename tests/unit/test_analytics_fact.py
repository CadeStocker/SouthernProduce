from datetime import date

from app import db
from app.models import AnalyticsFact, Company


def test_analytics_fact_stores_dimensions_measures_and_source(app):
    with app.app_context():
        company = Company(name='Analytics Company', admin_email='analytics@example.com')
        db.session.add(company)
        db.session.flush()

        fact = AnalyticsFact(
            fact_type='item_sale',
            company_id=company.id,
            date=date(2026, 8, 27),
            item_id=12,
            customer_id=4,
            quantity=10,
            revenue=250,
            cost=150,
            margin=100,
            labor_hours=2.5,
            source_table='sales_record',
            source_id=99,
        )
        db.session.add(fact)
        db.session.commit()

        saved = db.session.get(AnalyticsFact, fact.id)
        assert saved.fact_type == 'item_sale'
        assert saved.quantity == 10
        assert saved.margin == 100
        assert saved.source_table == 'sales_record'


def test_analytics_fact_rejects_unknown_fact_type(app):
    with app.app_context():
        company = Company(name='Analytics Company', admin_email='invalid@example.com')
        db.session.add(company)
        db.session.flush()
        db.session.add(AnalyticsFact(fact_type='unknown', company_id=company.id))

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return

        raise AssertionError('unknown fact types must be rejected')

def test_analytics_fact_accepts_every_supported_fact_type(app):
    with app.app_context():
        company = Company(name='Analytics Company', admin_email='types@example.com')
        db.session.add(company)
        db.session.flush()

        fact_types = [
            'item_sale', 'cost_margin', 'receiving',
            'labor', 'inventory_snapshot', 'customer_order',
        ]
        for index, fact_type in enumerate(fact_types):
            db.session.add(AnalyticsFact(
                fact_type=fact_type,
                company_id=company.id,
                source_table='backfill',
                source_id=index,
            ))
        db.session.commit()

        assert AnalyticsFact.query.count() == len(fact_types)


def test_analytics_fact_measures_default_to_zero(app):
    """Facts must aggregate without NULL handling in every report query."""
    with app.app_context():
        company = Company(name='Analytics Company', admin_email='defaults@example.com')
        db.session.add(company)
        db.session.flush()

        fact = AnalyticsFact(fact_type='labor', company_id=company.id)
        db.session.add(fact)
        db.session.commit()

        saved = db.session.get(AnalyticsFact, fact.id)
        assert saved.quantity == 0
        assert saved.revenue == 0
        assert saved.cost == 0
        assert saved.margin == 0
        assert saved.labor_hours == 0


def test_analytics_fact_defaults_date_to_today(app):
    with app.app_context():
        company = Company(name='Analytics Company', admin_email='today@example.com')
        db.session.add(company)
        db.session.flush()

        fact = AnalyticsFact(fact_type='labor', company_id=company.id)
        db.session.add(fact)
        db.session.commit()

        assert db.session.get(AnalyticsFact, fact.id).date == date.today()


def test_analytics_fact_leaves_inapplicable_dimensions_null(app):
    """A labor fact has no item/customer/supplier/raw product grain."""
    with app.app_context():
        company = Company(name='Analytics Company', admin_email='nulls@example.com')
        db.session.add(company)
        db.session.flush()

        fact = AnalyticsFact(fact_type='labor', company_id=company.id, labor_hours=8.0)
        db.session.add(fact)
        db.session.commit()

        saved = db.session.get(AnalyticsFact, fact.id)
        assert saved.item_id is None
        assert saved.customer_id is None
        assert saved.supplier_id is None
        assert saved.raw_product_id is None
        assert saved.location is None
