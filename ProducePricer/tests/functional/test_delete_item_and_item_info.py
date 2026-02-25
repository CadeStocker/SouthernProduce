"""
Tests for:
  - delete_item route (including the price_sheet_backup regression)
  - update_item route (updating labor hours and yield via UpdateItemInfo form)
"""
import pytest
import re
from datetime import date
from flask import url_for
from producepricer import db
from producepricer.models import (
    User, Company, Item, ItemInfo, LaborCost, Packaging,
    UnitOfWeight, ItemDesignation, PriceSheet, PriceSheetBackup,
    Customer, price_sheet_backup_items,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csrf(client, url):
    """GET a page and extract the CSRF token from it."""
    resp = client.get(url)
    match = re.search(r'name="csrf_token" value="([^"]+)"', resp.data.decode())
    return match.group(1) if match else None


def _make_item(app, company_id, name="Test Item", code="TST-001"):
    """Create a minimal item (with packaging) and return its id."""
    with app.app_context():
        packaging = Packaging(packaging_type="Test Box", company_id=company_id)
        db.session.add(packaging)
        db.session.commit()

        item = Item(
            name=name,
            code=code,
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id,
            company_id=company_id,
            item_designation=ItemDesignation.FOODSERVICE,
        )
        db.session.add(item)
        db.session.commit()
        return item.id


# ---------------------------------------------------------------------------
# Local fixture – mirrors the pattern used in test_item.py
# ---------------------------------------------------------------------------

@pytest.fixture
def logged_in_user(client, app):
    """Create a company + user, log them in, and return a data helper."""
    with app.app_context():
        company = Company(name="Delete Test Co", admin_email="admin@deletetest.com")
        db.session.add(company)
        db.session.commit()

        user = User(
            first_name="Del",
            last_name="User",
            email="del@deletetest.com",
            password="password",
            company_id=company.id,
        )
        db.session.add(user)
        db.session.commit()

        user_id = user.id
        company_id = company.id
        login_url = url_for("main.login")

    client.post(
        login_url,
        data={"email": "del@deletetest.com", "password": "password"},
        follow_redirects=True,
    )

    class Helper:
        def __init__(self):
            self.id = user_id
            self.company_id = company_id
            self.email = "del@deletetest.com"
            self.is_active = True
            self.is_authenticated = True
            self.is_anonymous = False

        def get_id(self):
            return str(self.id)

        def get_user(self):
            with app.app_context():
                return db.session.get(User, self.id)

    return Helper()


# ===========================================================================
# DELETE ITEM TESTS
# ===========================================================================

class TestDeleteItem:

    def test_delete_item_success(self, client, app, logged_in_user):
        """Deleting an existing item returns 200 and shows success flash."""
        item_id = _make_item(app, logged_in_user.company_id)

        csrf = _csrf(client, url_for("main.items"))
        resp = client.post(
            url_for("main.delete_item", item_id=item_id),
            data={"csrf_token": csrf} if csrf else {},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"deleted" in resp.data

        with app.app_context():
            assert db.session.get(Item, item_id) is None

    def test_delete_item_also_removes_item_info(self, client, app, logged_in_user):
        """Deleting an item cascades to its ItemInfo rows."""
        item_id = _make_item(app, logged_in_user.company_id, name="Item With Info", code="IWI-001")

        with app.app_context():
            info = ItemInfo(
                product_yield=90.0,
                labor_hours=1.5,
                date=date(2025, 6, 1),
                item_id=item_id,
                company_id=logged_in_user.company_id,
            )
            db.session.add(info)
            db.session.commit()

        csrf = _csrf(client, url_for("main.items"))
        client.post(
            url_for("main.delete_item", item_id=item_id),
            data={"csrf_token": csrf} if csrf else {},
            follow_redirects=True,
        )

        with app.app_context():
            assert db.session.get(Item, item_id) is None
            assert ItemInfo.query.filter_by(item_id=item_id).first() is None

    def test_delete_item_with_price_sheet_backup_association(self, client, app, logged_in_user):
        """
        Regression: deleting an item that appears in a PriceSheetBackup must NOT
        raise 'no such table: price_sheet_backup' (the original production bug).
        The backup association row should be removed and the item deleted cleanly.
        """
        item_id = _make_item(app, logged_in_user.company_id, name="Backed-Up Item", code="BKP-001")

        with app.app_context():
            # Create the customer and price sheet required by PriceSheetBackup FKs
            customer = Customer(
                name="Backup Customer",
                email="backup@test.com",
                company_id=logged_in_user.company_id,
            )
            db.session.add(customer)
            db.session.commit()

            price_sheet = PriceSheet(
                name="Original Sheet",
                date=date(2025, 1, 1),
                company_id=logged_in_user.company_id,
                customer_id=customer.id,
            )
            db.session.add(price_sheet)
            db.session.commit()

            item = db.session.get(Item, item_id)
            backup = PriceSheetBackup(
                original_price_sheet_id=price_sheet.id,
                name="Sheet Backup",
                date=date(2025, 1, 1),
                company_id=logged_in_user.company_id,
                customer_id=customer.id,
                items=[item],
            )
            db.session.add(backup)
            db.session.commit()

            backup_id = backup.id

        csrf = _csrf(client, url_for("main.items"))
        resp = client.post(
            url_for("main.delete_item", item_id=item_id),
            data={"csrf_token": csrf} if csrf else {},
            follow_redirects=True,
        )

        # Must not be a 500
        assert resp.status_code == 200
        assert b"deleted" in resp.data

        with app.app_context():
            assert db.session.get(Item, item_id) is None
            # Association row must be gone
            row = db.session.execute(
                price_sheet_backup_items.select().where(
                    price_sheet_backup_items.c.item_id == item_id
                )
            ).first()
            assert row is None
            # The backup itself should still exist (we only removed the item reference)
            assert db.session.get(PriceSheetBackup, backup_id) is not None

    def test_delete_item_wrong_company_is_rejected(self, client, app, logged_in_user):
        """A user cannot delete an item belonging to a different company."""
        with app.app_context():
            other_company = Company(name="Other Co", admin_email="other@co.com")
            db.session.add(other_company)
            db.session.commit()

            packaging = Packaging(packaging_type="Box", company_id=other_company.id)
            db.session.add(packaging)
            db.session.commit()

            other_item = Item(
                name="Other Co's Item",
                code="OTH-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging.id,
                company_id=other_company.id,
                item_designation=ItemDesignation.FOODSERVICE,
            )
            db.session.add(other_item)
            db.session.commit()
            other_item_id = other_item.id

        csrf = _csrf(client, url_for("main.items"))
        resp = client.post(
            url_for("main.delete_item", item_id=other_item_id),
            data={"csrf_token": csrf} if csrf else {},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"not found" in resp.data or b"permission" in resp.data

        # Item must still exist
        with app.app_context():
            assert db.session.get(Item, other_item_id) is not None

    def test_delete_nonexistent_item_shows_error(self, client, app, logged_in_user):
        """Attempting to delete an item that does not exist returns a flash error."""
        csrf = _csrf(client, url_for("main.items"))
        resp = client.post(
            url_for("main.delete_item", item_id=999999),
            data={"csrf_token": csrf} if csrf else {},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"not found" in resp.data or b"permission" in resp.data


# ===========================================================================
# UPDATE ITEM INFO (labor hours & yield) TESTS
# ===========================================================================

class TestUpdateItemInfo:

    def test_update_item_info_creates_new_item_info_row(self, client, app, logged_in_user):
        """
        POSTing valid labor_hours + product_yield to /update_item/<id>
        creates a new ItemInfo row in the database.
        """
        item_id = _make_item(app, logged_in_user.company_id, name="Yield Item", code="YLD-001")

        # update_item.html doesn't exist in the test environment; grab CSRF from items page
        csrf = _csrf(client, url_for("main.items"))
        resp = client.post(
            url_for("main.update_item", item_id=item_id),
            data={
                "csrf_token": csrf or "",
                "product_yield": "88.5",
                "labor_hours": "3.0",
                "date": "2025-07-01",
            },
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"updated successfully" in resp.data

        with app.app_context():
            info = (
                ItemInfo.query.filter_by(item_id=item_id)
                .order_by(ItemInfo.date.desc())
                .first()
            )
            assert info is not None
            assert info.product_yield == pytest.approx(88.5)
            assert info.labor_hours == pytest.approx(3.0)

    def test_update_item_info_stores_most_recent_values(self, client, app, logged_in_user):
        """
        Submitting a second update creates a new row; the most recent row
        reflects the latest submitted values.
        """
        item_id = _make_item(app, logged_in_user.company_id, name="History Item", code="HST-001")

        # update_item.html doesn't exist in the test environment; grab CSRF from items page
        csrf = _csrf(client, url_for("main.items"))

        # First update
        client.post(
            url_for("main.update_item", item_id=item_id),
            data={
                "csrf_token": csrf or "",
                "product_yield": "80.0",
                "labor_hours": "2.0",
                "date": "2025-06-01",
            },
            follow_redirects=True,
        )

        # Second update (newer date, different values)
        csrf = _csrf(client, url_for("main.items"))
        client.post(
            url_for("main.update_item", item_id=item_id),
            data={
                "csrf_token": csrf or "",
                "product_yield": "92.0",
                "labor_hours": "4.5",
                "date": "2025-07-01",
            },
            follow_redirects=True,
        )

        with app.app_context():
            rows = (
                ItemInfo.query.filter_by(item_id=item_id)
                .order_by(ItemInfo.date.desc())
                .all()
            )
            assert len(rows) == 2
            # Most recent row
            assert rows[0].product_yield == pytest.approx(92.0)
            assert rows[0].labor_hours == pytest.approx(4.5)
            # Older row preserved
            assert rows[1].product_yield == pytest.approx(80.0)
            assert rows[1].labor_hours == pytest.approx(2.0)

    def test_update_item_info_wrong_company_is_rejected(self, client, app, logged_in_user):
        """
        A user cannot update yield/labor hours for an item in a different company.
        """
        with app.app_context():
            other_company = Company(name="Yield Other Co", admin_email="yo@co.com")
            db.session.add(other_company)
            db.session.commit()

            packaging = Packaging(packaging_type="Box", company_id=other_company.id)
            db.session.add(packaging)
            db.session.commit()

            other_item = Item(
                name="Other Yield Item",
                code="OYI-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging.id,
                company_id=other_company.id,
                item_designation=ItemDesignation.RETAIL,
            )
            db.session.add(other_item)
            db.session.commit()
            other_item_id = other_item.id

        csrf = _csrf(client, url_for("main.items"))
        resp = client.post(
            url_for("main.update_item", item_id=other_item_id),
            data={
                "csrf_token": csrf or "",
                "product_yield": "99.0",
                "labor_hours": "1.0",
                "date": "2025-07-01",
            },
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"not found" in resp.data or b"permission" in resp.data

        with app.app_context():
            assert ItemInfo.query.filter_by(item_id=other_item_id).first() is None

    def test_update_item_info_nonexistent_item(self, client, app, logged_in_user):
        """POSTing to update_item for a non-existent item shows an error."""
        csrf = _csrf(client, url_for("main.items"))
        resp = client.post(
            url_for("main.update_item", item_id=999999),
            data={
                "csrf_token": csrf or "",
                "product_yield": "85.0",
                "labor_hours": "2.0",
                "date": "2025-07-01",
            },
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"not found" in resp.data or b"permission" in resp.data

    def test_update_item_info_zero_values_accepted(self, client, app, logged_in_user):
        """
        Zero is a valid value for both product_yield and labor_hours
        (edge case — the fields have no minimum validator).
        """
        item_id = _make_item(app, logged_in_user.company_id, name="Zero Item", code="ZRO-001")

        # update_item.html doesn't exist in the test environment; grab CSRF from items page
        csrf = _csrf(client, url_for("main.items"))
        resp = client.post(
            url_for("main.update_item", item_id=item_id),
            data={
                "csrf_token": csrf or "",
                "product_yield": "0.0",
                "labor_hours": "0.0",
                "date": "2025-08-01",
            },
            follow_redirects=True,
        )

        assert resp.status_code == 200

        with app.app_context():
            info = ItemInfo.query.filter_by(item_id=item_id).first()
            assert info is not None
            assert info.product_yield == pytest.approx(0.0)
            assert info.labor_hours == pytest.approx(0.0)
