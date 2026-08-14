# Copyright Cade Stocker 2026
import io
from unittest.mock import patch


def test_save_parsed_prices_creates_rawproduct_and_cost(app, client, logged_in_user):
    with app.app_context():
        from app import db
        from app.models import RawProduct, CostHistory

        # Ensure DB starts empty
        assert db.session.query(RawProduct).count() == 0

    # Build payload with a new name that doesn't exist
    payload = {
        "effective_date": "2026-01-01",
        "items_to_create": [
            {
                "matched_product_id": None,
                "matched_product_name": "Unique New Product",
                "name_from_pdf": "Unique New Product",
                "price_from_pdf": 4.25
            }
        ]
    }

    rv = client.post('/api/save_parsed_prices', json=payload)
    assert rv.status_code == 200
    j = rv.get_json()
    assert j.get('success') is True

    with app.app_context():
        from app import db
        from app.models import RawProduct, CostHistory

        rp = db.session.query(RawProduct).filter_by(name="Unique New Product", company_id=logged_in_user.company_id).first()
        assert rp is not None

        ch = db.session.query(CostHistory).filter_by(raw_product_id=rp.id, company_id=logged_in_user.company_id).first()
        assert ch is not None
        assert abs(ch.cost - 4.25) < 0.001


def test_save_parsed_prices_skips_duplicate_cost(app, client, logged_in_user):
    with app.app_context():
        from app import db
        from app.models import RawProduct, CostHistory
        from datetime import date

        rp = RawProduct(name="Duplicate Product", company_id=logged_in_user.company_id)
        db.session.add(rp)
        db.session.commit()

        # create existing cost with a proper date object
        existing = CostHistory(cost=2.50, date=date(2026, 1, 1), company_id=logged_in_user.company_id, raw_product_id=rp.id)
        db.session.add(existing)
        db.session.commit()
        rp_id = rp.id

    payload = {
        "effective_date": "2026-01-01",
        "items_to_create": [
            {
                "matched_product_id": rp_id,
                "matched_product_name": "Duplicate Product",
                "name_from_pdf": "Duplicate Product",
                "price_from_pdf": 2.50
            }
        ]
    }

    rv = client.post('/api/save_parsed_prices', json=payload)
    assert rv.status_code == 200
    j = rv.get_json()
    assert j.get('success') is True
    # message should indicate skipped duplicates
    assert 'Skipped' in j.get('message') or 'Skipped' in j.get('message')
