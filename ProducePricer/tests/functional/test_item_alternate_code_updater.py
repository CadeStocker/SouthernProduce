from datetime import date
from flask import url_for

from producepricer import db
from producepricer.models import Company, Item, ItemDesignation, LaborCost, Packaging, UnitOfWeight, User


def _create_logged_in_user(client, app):
    with app.app_context():
        company = Company(name="Alt Code Co", admin_email="altcode@test.com")
        db.session.add(company)
        db.session.commit()

        user = User(
            first_name="Alt",
            last_name="Coder",
            email="altcode@test.com",
            password="password",
            company_id=company.id,
        )
        db.session.add(user)

        labor_cost = LaborCost(date=date.today(), labor_cost=15.0, company_id=company.id)
        packaging = Packaging(packaging_type="Alt Box", company_id=company.id)
        db.session.add_all([labor_cost, packaging])
        db.session.commit()

        company_id = company.id
        packaging_id = packaging.id

    client.post(
        "/login",
        data={"email": "altcode@test.com", "password": "password"},
        follow_redirects=True,
    )

    return {"company_id": company_id, "packaging_id": packaging_id}


def _create_item(name, code, company_id, packaging_id, alternate_code=None):
    item = Item(
        name=name,
        code=code,
        unit_of_weight=UnitOfWeight.POUND,
        packaging_id=packaging_id,
        company_id=company_id,
        item_designation=ItemDesignation.FOODSERVICE,
        alternate_code=alternate_code,
    )
    db.session.add(item)
    db.session.commit()
    return item


def test_items_page_shows_alternate_code_updater(client, app):
    setup = _create_logged_in_user(client, app)

    with app.app_context():
        _create_item("Updater Item", "UP-001", setup["company_id"], setup["packaging_id"])

    response = client.get(url_for("main.items"))

    assert response.status_code == 200
    assert b"Alternate Code Updater" in response.data
    assert b"Update One" in response.data
    assert b"Save Alternate Codes" in response.data


def test_bulk_update_item_alternate_codes(client, app):
    setup = _create_logged_in_user(client, app)

    with app.app_context():
        i1 = _create_item("Bulk Item One", "BK-001", setup["company_id"], setup["packaging_id"])
        i2 = _create_item("Bulk Item Two", "BK-002", setup["company_id"], setup["packaging_id"])
        i1_id = i1.id
        i2_id = i2.id

    response = client.post(
        url_for("main.update_item_alternate_codes"),
        data={
            f"alternate_code_{i1_id}": "ALT-BULK-1",
            f"alternate_code_{i2_id}": "ALT-BULK-2",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Updated alternate codes for" in response.data

    with app.app_context():
        updated_i1 = db.session.get(Item, i1_id)
        updated_i2 = db.session.get(Item, i2_id)
        assert updated_i1.alternate_code == "ALT-BULK-1"
        assert updated_i2.alternate_code == "ALT-BULK-2"


def test_update_item_alternate_code_by_name_exact_match(client, app):
    setup = _create_logged_in_user(client, app)

    with app.app_context():
        item = _create_item("Typed Item Name", "TN-001", setup["company_id"], setup["packaging_id"])
        item_id = item.id

    response = client.post(
        url_for("main.update_item_alternate_code_by_name"),
        data={"name": "Typed Item Name", "alternate_code": "ALT-TYPED-123"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Updated alternate code for" in response.data

    with app.app_context():
        updated = db.session.get(Item, item_id)
        assert updated.alternate_code == "ALT-TYPED-123"


def test_update_item_alternate_code_by_name_not_found(client, app):
    _create_logged_in_user(client, app)

    response = client.post(
        url_for("main.update_item_alternate_code_by_name"),
        data={"name": "No Such Item", "alternate_code": "ALT-NONE"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Item not found" in response.data


def test_items_search_matches_alternate_code(client, app):
    setup = _create_logged_in_user(client, app)

    with app.app_context():
        _create_item(
            "Search Alt Item",
            "SEA-001",
            setup["company_id"],
            setup["packaging_id"],
            alternate_code="AC-SEARCH-42",
        )
        _create_item(
            "Other Item",
            "OTH-001",
            setup["company_id"],
            setup["packaging_id"],
            alternate_code="DIFF-CODE",
        )

    response = client.get(url_for("main.items", q="SEARCH-42"))

    assert response.status_code == 200
    assert b"Search Alt Item" in response.data
    # The page includes a datalist with all item names for the updater,
    # so assert against the non-matching item's alternate code instead.
    assert b"DIFF-CODE" not in response.data
