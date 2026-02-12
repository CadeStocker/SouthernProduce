import json
import re
import datetime

import pytest

from producepricer import db
from producepricer.models import (
    Packaging,
    RawProduct,
    CostHistory,
    Item,
    ItemInfo,
)


def _seed_packaging_and_raws(company_id):
    packaging = Packaging(packaging_type="Test Box", company_id=company_id)
    raw1 = RawProduct(name="Raw Alpha", company_id=company_id)
    raw2 = RawProduct(name="Raw Beta", company_id=company_id)
    db.session.add_all([packaging, raw1, raw2])
    db.session.flush()
    return packaging, [raw1, raw2]


def _add_cost_history(raw_product, company_id, amount, days_ago=0):
    entry = CostHistory(
        raw_product_id=raw_product.id,
        cost=amount,
        date=datetime.date.today() - datetime.timedelta(days=days_ago),
        company_id=company_id,
    )
    db.session.add(entry)
    db.session.flush()
    return entry


def _create_item_with_raws(company_id, packaging, raw_products):
    item = Item(
        name="MultiRaw Item",
        code="MULTI",
        case_weight=10.0,
        ranch=False,
        packaging_id=packaging.id,
        unit_of_weight="POUND",
        company_id=company_id,
    )
    db.session.add(item)
    db.session.flush()
    for raw in raw_products:
        item.raw_products.append(raw)
    info = ItemInfo(
        item_id=item.id,
        product_yield=20,
        labor_hours=2,
        date=datetime.datetime.utcnow().date(),
        company_id=company_id,
    )
    db.session.add(info)
    db.session.flush()
    return item


class TestPriceQuoterAveraging:
    def test_raw_cost_lookup_exposes_latest_cost_per_product(self, client, logged_in_user, app):
        raw_ids = []
        with app.app_context():
            packaging, raw_products = _seed_packaging_and_raws(logged_in_user.company_id)
            # Add cost histories for each raw product
            _add_cost_history(raw_products[0], logged_in_user.company_id, 10.0, days_ago=1)
            _add_cost_history(raw_products[1], logged_in_user.company_id, 20.5, days_ago=2)
            db.session.commit()
            raw_ids = [raw.id for raw in raw_products]

        response = client.get('/price_quoter')
        assert response.status_code == 200
        text = response.get_data(as_text=True)

        match = re.search(r"const rawProductCosts = (\{.*?\});", text)
        assert match, "rawProductCosts JSON should be present in the template script"
        lookup = json.loads(match.group(1))

        assert str(raw_ids[0]) in lookup
        assert str(raw_ids[1]) in lookup
        assert lookup[str(raw_ids[0])] == pytest.approx(10.0)
        assert lookup[str(raw_ids[1])] == pytest.approx(20.5)

    def test_selecting_item_prefills_average_raw_cost(self, client, logged_in_user, app):
        item_id = None
        with app.app_context():
            packaging, raw_products = _seed_packaging_and_raws(logged_in_user.company_id)
            _add_cost_history(raw_products[0], logged_in_user.company_id, 8.0, days_ago=1)
            _add_cost_history(raw_products[1], logged_in_user.company_id, 12.0, days_ago=0)
            db.session.commit()
            item = _create_item_with_raws(logged_in_user.company_id, packaging, raw_products)
            db.session.commit()
            item_id = item.id

        response = client.get(f'/price_quoter?item_id={item_id}')
        text = response.get_data(as_text=True)
        assert response.status_code == 200

        match = re.search(r'id="raw-product-cost"[^>]*value="([^"]*)"', text)
        assert match, "raw product cost input should include a value attribute"
        value = float(match.group(1))
        expected = (8.0 + 12.0) / 2
        assert value == pytest.approx(expected)
