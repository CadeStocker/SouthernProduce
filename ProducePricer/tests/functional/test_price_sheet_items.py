"""
Tests for adding and removing items from a price sheet.
Covers:
  - add_items_to_sheet  (POST /edit_price_sheet/<id>/add_items)
  - remove_item_from_sheet (POST /edit_price_sheet/<id>/remove_item/<item_id>)
"""

import pytest
from datetime import date
from producepricer import db
from producepricer.models import Company, User, Customer, Item, PriceSheet, UnitOfWeight, Packaging


# ====================
# Fixtures
# ====================

@pytest.fixture
def setup_data(app):
    """Create a company, user, customer, packaging, two items, and a price sheet."""
    with app.app_context():
        company = Company(name="Sheet Items Co", admin_email="si@test.com")
        db.session.add(company)
        db.session.commit()

        user = User(
            first_name="Sheet",
            last_name="Tester",
            email="si@test.com",
            password="password",
            company_id=company.id,
        )
        db.session.add(user)

        customer = Customer(
            name="SI Customer",
            email="sic@test.com",
            company_id=company.id,
        )
        db.session.add(customer)

        pkg = Packaging(packaging_type="Bin", company_id=company.id)
        db.session.add(pkg)
        db.session.commit()

        item_a = Item(
            name="Apple",
            code="A01",
            alternate_code="ALT-A01",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=pkg.id,
            company_id=company.id,
        )
        item_b = Item(
            name="Banana",
            code="B01",
            alternate_code="ALT-B01",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=pkg.id,
            company_id=company.id,
        )
        db.session.add_all([item_a, item_b])
        db.session.commit()

        # Sheet starts with only item_a
        sheet = PriceSheet(
            name="Fruit Sheet",
            date=date(2026, 1, 1),
            valid_from=date(2026, 1, 1),
            company_id=company.id,
            customer_id=customer.id,
        )
        sheet.items.append(item_a)
        db.session.add(sheet)
        db.session.commit()

        return {
            "company_id": company.id,
            "user_id": user.id,
            "customer_id": customer.id,
            "item_a_id": item_a.id,
            "item_b_id": item_b.id,
            "sheet_id": sheet.id,
        }


@pytest.fixture
def logged_in_client(client, app, setup_data):
    """Return an authenticated test client."""
    with app.app_context():
        client.post(
            "/login",
            data={"email": "si@test.com", "password": "password"},
            follow_redirects=True,
        )
    return client


# ====================
# add_items_to_sheet
# ====================

def test_add_item_to_sheet(logged_in_client, app, setup_data):
    """A new item can be added to a price sheet via the add_items route."""
    sheet_id = setup_data["sheet_id"]
    item_b_id = setup_data["item_b_id"]

    resp = logged_in_client.post(
        f"/edit_price_sheet/{sheet_id}/add_items",
        data={"new_items": [str(item_b_id)]},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Added 1 item(s) to sheet." in resp.data

    with app.app_context():
        sheet = db.session.get(PriceSheet, sheet_id)
        item_ids = {i.id for i in sheet.items}
        assert item_b_id in item_ids


def test_add_item_already_on_sheet_is_idempotent(logged_in_client, app, setup_data):
    """Adding an item that is already on the sheet does not duplicate it."""
    sheet_id = setup_data["sheet_id"]
    item_a_id = setup_data["item_a_id"]

    logged_in_client.post(
        f"/edit_price_sheet/{sheet_id}/add_items",
        data={"new_items": [str(item_a_id)]},
        follow_redirects=True,
    )

    with app.app_context():
        sheet = db.session.get(PriceSheet, sheet_id)
        count = sum(1 for i in sheet.items if i.id == item_a_id)
        assert count == 1


def test_add_items_wrong_company_rejected(logged_in_client, app, setup_data):
    """Cannot add items that belong to a different company."""
    with app.app_context():
        other_company = Company(name="Other Co", admin_email="other@co.com")
        db.session.add(other_company)
        db.session.commit()
        pkg = Packaging(packaging_type="Bag", company_id=other_company.id)
        db.session.add(pkg)
        db.session.commit()
        foreign_item = Item(
            name="Foreign",
            code="F01",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=pkg.id,
            company_id=other_company.id,
        )
        db.session.add(foreign_item)
        db.session.commit()
        foreign_id = foreign_item.id

    sheet_id = setup_data["sheet_id"]

    logged_in_client.post(
        f"/edit_price_sheet/{sheet_id}/add_items",
        data={"new_items": [str(foreign_id)]},
        follow_redirects=True,
    )

    with app.app_context():
        sheet = db.session.get(PriceSheet, sheet_id)
        item_ids = {i.id for i in sheet.items}
        assert foreign_id not in item_ids


# ====================
# remove_item_from_sheet
# ====================

def test_remove_item_from_sheet(logged_in_client, app, setup_data):
    """An item can be removed from a price sheet."""
    sheet_id = setup_data["sheet_id"]
    item_a_id = setup_data["item_a_id"]

    resp = logged_in_client.post(
        f"/edit_price_sheet/{sheet_id}/remove_item/{item_a_id}",
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"removed from sheet." in resp.data

    with app.app_context():
        sheet = db.session.get(PriceSheet, sheet_id)
        item_ids = {i.id for i in sheet.items}
        assert item_a_id not in item_ids


def test_remove_item_not_on_sheet_shows_warning(logged_in_client, app, setup_data):
    """Removing an item that is not on the sheet shows a warning flash."""
    sheet_id = setup_data["sheet_id"]
    item_b_id = setup_data["item_b_id"]  # was never added

    resp = logged_in_client.post(
        f"/edit_price_sheet/{sheet_id}/remove_item/{item_b_id}",
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"was not on this sheet." in resp.data


def test_remove_item_does_not_delete_item_from_db(logged_in_client, app, setup_data):
    """Removing an item from a sheet does not delete the Item record itself."""
    sheet_id = setup_data["sheet_id"]
    item_a_id = setup_data["item_a_id"]

    logged_in_client.post(
        f"/edit_price_sheet/{sheet_id}/remove_item/{item_a_id}",
        follow_redirects=True,
    )

    with app.app_context():
        item = db.session.get(Item, item_a_id)
        assert item is not None


def test_remove_item_wrong_company_returns_404(logged_in_client, app, setup_data):
    """Cannot remove an item that belongs to another company (404)."""
    with app.app_context():
        other_company = Company(name="Remove Other Co", admin_email="ro@co.com")
        db.session.add(other_company)
        db.session.commit()
        pkg = Packaging(packaging_type="Crate", company_id=other_company.id)
        db.session.add(pkg)
        db.session.commit()
        foreign_item = Item(
            name="ForeignRemove",
            code="FR01",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=pkg.id,
            company_id=other_company.id,
        )
        db.session.add(foreign_item)
        db.session.commit()
        foreign_id = foreign_item.id

    sheet_id = setup_data["sheet_id"]

    resp = logged_in_client.post(
        f"/edit_price_sheet/{sheet_id}/remove_item/{foreign_id}",
        follow_redirects=True,
    )

    assert resp.status_code == 404


def test_remove_item_requires_login(client, app, setup_data):
    """Unauthenticated requests to remove an item are redirected to login."""
    sheet_id = setup_data["sheet_id"]
    item_a_id = setup_data["item_a_id"]

    resp = client.post(
        f"/edit_price_sheet/{sheet_id}/remove_item/{item_a_id}",
        follow_redirects=False,
    )

    # Flask-Login redirects to the login page
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_add_items_requires_login(client, app, setup_data):
    """Unauthenticated requests to add items are redirected to login."""
    sheet_id = setup_data["sheet_id"]
    item_b_id = setup_data["item_b_id"]

    resp = client.post(
        f"/edit_price_sheet/{sheet_id}/add_items",
        data={"new_items": [str(item_b_id)]},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_edit_price_sheet_shows_alternate_code_column(logged_in_client, setup_data):
    """Edit sheet page shows alternate code column/value."""
    sheet_id = setup_data["sheet_id"]

    resp = logged_in_client.get(f"/edit_price_sheet/{sheet_id}", follow_redirects=True)

    assert resp.status_code == 200
    assert b"Alternate Code" in resp.data
    assert b"ALT-A01" in resp.data


def test_view_price_sheet_shows_alternate_code_column(logged_in_client, setup_data):
    """View sheet page shows alternate code column/value."""
    sheet_id = setup_data["sheet_id"]

    resp = logged_in_client.get(f"/view_price_sheet/{sheet_id}", follow_redirects=True)

    assert resp.status_code == 200
    assert b"Alternate Code" in resp.data
    assert b"ALT-A01" in resp.data
