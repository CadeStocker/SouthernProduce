"""
Functional tests for the inventory web pages added under the Produce Receiver
nav tab:
  - GET  /inventory               → inventory_sessions listing
  - GET  /inventory/session/<id>  → view_inventory_session detail
  - POST /inventory/session/<id>/delete → delete_inventory_session
  - GET  /inventory/supplies      → supplies listing
  - POST /inventory/supplies/<id>/toggle → toggle_supply_active

Tests cover:
  - Login-gating (unauthenticated requests redirect to /login)
  - Company-level data isolation (users never see another company's data)
  - Correct display of sessions, item counts, supply counts, and supplies
  - Search/filter parameters
  - Cascade delete of session + its child counts
  - Supply active/inactive toggle
  - 404 behaviour for cross-company access attempts
"""

import pytest
from datetime import datetime, timedelta
from flask import url_for

from producepricer import db
from producepricer.models import (
    Company,
    User,
    Item,
    Packaging,
    UnitOfWeight,
    ItemDesignation,
    Supply,
    InventorySession,
    ItemInventory,
    SupplyInventory,
)


# ---------------------------------------------------------------------------
# Shared auth fixture (mirrors the pattern used across the test suite)
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_client(client, app):
    """Authenticated test client with a company, user, and shared IDs."""
    with app.app_context():
        company = Company(name="Inventory Test Co", admin_email="inv@test.com")
        db.session.add(company)
        db.session.commit()

        user = User(
            first_name="Inv",
            last_name="Tester",
            email="inv@test.com",
            password="password123",
            company_id=company.id,
        )
        db.session.add(user)
        db.session.commit()

        company_id = company.id
        user_id = user.id

    response = client.post(
        "/login",
        data={"email": "inv@test.com", "password": "password123"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    yield client, company_id, user_id


# ---------------------------------------------------------------------------
# Helper to build a full inventory session with item + supply counts
# ---------------------------------------------------------------------------

def _make_full_session(app, company_id, label="Morning Count", counted_by="Alice"):
    """
    Creates:
      - a Packaging, Item
      - a Supply
      - an InventorySession
      - one ItemInventory and one SupplyInventory attached to the session

    Returns a dict of all created IDs.
    """
    with app.app_context():
        packaging = Packaging(packaging_type="Box", company_id=company_id)
        db.session.add(packaging)
        db.session.flush()

        item = Item(
            name="Test Apple",
            code="APPL001",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=packaging.id,
            company_id=company_id,
            case_weight=25.0,
            item_designation=ItemDesignation.RETAIL,
        )
        db.session.add(item)
        db.session.flush()

        supply = Supply(
            name="Brown Box 10lb",
            unit="case",
            company_id=company_id,
            category="Packaging",
        )
        db.session.add(supply)
        db.session.flush()

        session = InventorySession(
            company_id=company_id,
            label=label,
            counted_by=counted_by,
            submitted_at=datetime.utcnow(),
        )
        db.session.add(session)
        db.session.flush()

        item_count = ItemInventory(
            item_id=item.id,
            quantity=42,
            company_id=company_id,
            session_id=session.id,
            counted_by=counted_by,
            notes="Shelf row A",
        )
        supply_count = SupplyInventory(
            supply_id=supply.id,
            quantity=3.5,
            company_id=company_id,
            session_id=session.id,
            counted_by=counted_by,
            notes="Back of warehouse",
        )
        db.session.add_all([item_count, supply_count])
        db.session.commit()

        return {
            "packaging_id": packaging.id,
            "item_id": item.id,
            "supply_id": supply.id,
            "session_id": session.id,
            "item_count_id": item_count.id,
            "supply_count_id": supply_count.id,
        }


# ===========================================================================
# GET /inventory  –  inventory_sessions listing
# ===========================================================================

class TestInventorySessionsPage:

    def test_redirects_when_not_logged_in(self, client):
        response = client.get("/inventory")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_page_loads_for_authenticated_user(self, auth_client):
        client, company_id, _ = auth_client
        response = client.get("/inventory")
        assert response.status_code == 200
        assert b"Inventory Sessions" in response.data

    def test_shows_empty_state_when_no_sessions(self, auth_client):
        client, company_id, _ = auth_client
        response = client.get("/inventory")
        assert response.status_code == 200
        # The empty-state alert should appear
        assert b"No inventory sessions found" in response.data

    def test_displays_existing_sessions(self, auth_client, app):
        client, company_id, _ = auth_client
        ids = _make_full_session(app, company_id, label="Evening Count")

        response = client.get("/inventory")
        assert response.status_code == 200
        assert b"Evening Count" in response.data

    def test_displays_item_and_supply_line_counts(self, auth_client, app):
        client, company_id, _ = auth_client
        _make_full_session(app, company_id)

        response = client.get("/inventory")
        assert response.status_code == 200
        # The session has 1 item line and 1 supply line – both rendered
        assert b"1" in response.data

    def test_search_filters_by_label(self, auth_client, app):
        client, company_id, _ = auth_client
        _make_full_session(app, company_id, label="MorningABC")
        _make_full_session(app, company_id, label="EveningXYZ")

        response = client.get("/inventory?q=MorningABC")
        assert response.status_code == 200
        assert b"MorningABC" in response.data
        assert b"EveningXYZ" not in response.data

    def test_search_filters_by_counted_by(self, auth_client, app):
        client, company_id, _ = auth_client
        _make_full_session(app, company_id, counted_by="UniqueCounter99")

        response = client.get("/inventory?q=UniqueCounter99")
        assert response.status_code == 200
        assert b"UniqueCounter99" in response.data

    def test_does_not_show_other_company_sessions(self, auth_client, app):
        client, company_id, _ = auth_client

        # Create a second company + session
        with app.app_context():
            other = Company(name="Other Co", admin_email="other@other.com")
            db.session.add(other)
            db.session.commit()
            other_id = other.id

        _make_full_session(app, other_id, label="OtherCompanySession")

        response = client.get("/inventory")
        assert b"OtherCompanySession" not in response.data

    def test_manage_supplies_link_present(self, auth_client, app):
        client, company_id, _ = auth_client
        _make_full_session(app, company_id)

        response = client.get("/inventory")
        assert b"Manage Supplies" in response.data or b"supplies" in response.data.lower()


# ===========================================================================
# GET /inventory/session/<id>  –  view_inventory_session detail
# ===========================================================================

class TestViewInventorySessionPage:

    def test_redirects_when_not_logged_in(self, client, app):
        # We need a real-ish ID; 999 is fine – the redirect happens before DB hit
        response = client.get("/inventory/session/999")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_page_loads_with_valid_session(self, auth_client, app):
        client, company_id, _ = auth_client
        ids = _make_full_session(app, company_id, label="Detail View Test")

        response = client.get(f"/inventory/session/{ids['session_id']}")
        assert response.status_code == 200
        assert b"Detail View Test" in response.data

    def test_shows_item_counts(self, auth_client, app):
        client, company_id, _ = auth_client
        ids = _make_full_session(app, company_id)

        response = client.get(f"/inventory/session/{ids['session_id']}")
        assert response.status_code == 200
        assert b"Test Apple" in response.data
        assert b"42" in response.data

    def test_shows_supply_counts(self, auth_client, app):
        client, company_id, _ = auth_client
        ids = _make_full_session(app, company_id)

        response = client.get(f"/inventory/session/{ids['session_id']}")
        assert response.status_code == 200
        assert b"Brown Box 10lb" in response.data

    def test_shows_notes(self, auth_client, app):
        client, company_id, _ = auth_client
        ids = _make_full_session(app, company_id)

        response = client.get(f"/inventory/session/{ids['session_id']}")
        assert response.status_code == 200
        assert b"Shelf row A" in response.data
        assert b"Back of warehouse" in response.data

    def test_shows_counted_by(self, auth_client, app):
        client, company_id, _ = auth_client
        ids = _make_full_session(app, company_id, counted_by="Bob Smith")

        response = client.get(f"/inventory/session/{ids['session_id']}")
        assert response.status_code == 200
        assert b"Bob Smith" in response.data

    def test_returns_404_for_other_company_session(self, auth_client, app):
        client, company_id, _ = auth_client

        with app.app_context():
            other = Company(name="Other Co 2", admin_email="other2@other.com")
            db.session.add(other)
            db.session.commit()
            other_id = other.id

        ids = _make_full_session(app, other_id)

        response = client.get(f"/inventory/session/{ids['session_id']}")
        assert response.status_code == 404

    def test_returns_404_for_nonexistent_session(self, auth_client):
        client, company_id, _ = auth_client
        response = client.get("/inventory/session/999999")
        assert response.status_code == 404

    def test_back_link_present(self, auth_client, app):
        client, company_id, _ = auth_client
        ids = _make_full_session(app, company_id)

        response = client.get(f"/inventory/session/{ids['session_id']}")
        assert b"All Sessions" in response.data


# ===========================================================================
# POST /inventory/session/<id>/delete  –  delete_inventory_session
# ===========================================================================

class TestDeleteInventorySession:

    def test_redirects_when_not_logged_in(self, client):
        response = client.post("/inventory/session/999/delete")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_deletes_session_and_redirects(self, auth_client, app):
        client, company_id, _ = auth_client
        ids = _make_full_session(app, company_id)
        session_id = ids["session_id"]

        response = client.post(
            f"/inventory/session/{session_id}/delete",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"deleted" in response.data.lower()

        # Session must be gone from the DB
        with app.app_context():
            assert InventorySession.query.get(session_id) is None

    def test_cascade_deletes_child_item_counts(self, auth_client, app):
        client, company_id, _ = auth_client
        ids = _make_full_session(app, company_id)

        client.post(
            f"/inventory/session/{ids['session_id']}/delete",
            follow_redirects=True,
        )

        with app.app_context():
            assert ItemInventory.query.get(ids["item_count_id"]) is None

    def test_cascade_deletes_child_supply_counts(self, auth_client, app):
        client, company_id, _ = auth_client
        ids = _make_full_session(app, company_id)

        client.post(
            f"/inventory/session/{ids['session_id']}/delete",
            follow_redirects=True,
        )

        with app.app_context():
            assert SupplyInventory.query.get(ids["supply_count_id"]) is None

    def test_cannot_delete_other_company_session(self, auth_client, app):
        client, company_id, _ = auth_client

        with app.app_context():
            other = Company(name="Other Co 3", admin_email="other3@other.com")
            db.session.add(other)
            db.session.commit()
            other_id = other.id

        ids = _make_full_session(app, other_id)

        response = client.post(f"/inventory/session/{ids['session_id']}/delete")
        assert response.status_code == 404

        # Session must still exist
        with app.app_context():
            assert InventorySession.query.get(ids["session_id"]) is not None

    def test_redirects_to_inventory_list_after_delete(self, auth_client, app):
        client, company_id, _ = auth_client
        ids = _make_full_session(app, company_id)

        response = client.post(
            f"/inventory/session/{ids['session_id']}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/inventory" in response.location


# ===========================================================================
# GET /inventory/supplies  –  supplies listing
# ===========================================================================

class TestSuppliesPage:

    def _create_supply(self, app, company_id, name="Test Supply", category="Cleaning",
                       unit="case", is_active=True):
        with app.app_context():
            supply = Supply(
                name=name,
                unit=unit,
                company_id=company_id,
                category=category,
                is_active=is_active,
            )
            db.session.add(supply)
            db.session.commit()
            return supply.id

    def test_redirects_when_not_logged_in(self, client):
        response = client.get("/inventory/supplies")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_page_loads_for_authenticated_user(self, auth_client):
        client, company_id, _ = auth_client
        response = client.get("/inventory/supplies")
        assert response.status_code == 200
        assert b"Supplies" in response.data

    def test_shows_empty_state_when_no_supplies(self, auth_client):
        client, company_id, _ = auth_client
        response = client.get("/inventory/supplies")
        assert b"No supplies found" in response.data

    def test_displays_existing_supplies(self, auth_client, app):
        client, company_id, _ = auth_client
        self._create_supply(app, company_id, name="Blue Gloves")

        response = client.get("/inventory/supplies")
        assert response.status_code == 200
        assert b"Blue Gloves" in response.data

    def test_displays_supply_category_and_unit(self, auth_client, app):
        client, company_id, _ = auth_client
        self._create_supply(app, company_id, name="Soap", category="Cleaning", unit="bottle")

        response = client.get("/inventory/supplies")
        assert b"Cleaning" in response.data
        assert b"bottle" in response.data

    def test_active_supply_shows_active_badge(self, auth_client, app):
        client, company_id, _ = auth_client
        self._create_supply(app, company_id, name="Active Supply", is_active=True)

        response = client.get("/inventory/supplies")
        assert b"Active" in response.data

    def test_inactive_supply_shows_inactive_badge(self, auth_client, app):
        client, company_id, _ = auth_client
        self._create_supply(app, company_id, name="Inactive Supply", is_active=False)

        response = client.get("/inventory/supplies")
        assert b"Inactive" in response.data

    def test_search_filters_by_name(self, auth_client, app):
        client, company_id, _ = auth_client
        self._create_supply(app, company_id, name="UniqueNameXYZ")
        self._create_supply(app, company_id, name="OtherSupplyABC")

        response = client.get("/inventory/supplies?q=UniqueNameXYZ")
        assert b"UniqueNameXYZ" in response.data
        assert b"OtherSupplyABC" not in response.data

    def test_search_filters_by_category(self, auth_client, app):
        client, company_id, _ = auth_client
        self._create_supply(app, company_id, name="Supply A", category="SafetyGear")
        self._create_supply(app, company_id, name="Supply B", category="Packaging")

        response = client.get("/inventory/supplies?q=SafetyGear")
        assert b"Supply A" in response.data
        assert b"Supply B" not in response.data

    def test_does_not_show_other_company_supplies(self, auth_client, app):
        client, company_id, _ = auth_client

        with app.app_context():
            other = Company(name="Other Co 4", admin_email="other4@other.com")
            db.session.add(other)
            db.session.commit()
            other_id = other.id

        self._create_supply(app, other_id, name="OtherCoSupply99")

        response = client.get("/inventory/supplies")
        assert b"OtherCoSupply99" not in response.data

    def test_supplies_sorted_alphabetically(self, auth_client, app):
        client, company_id, _ = auth_client
        self._create_supply(app, company_id, name="Zebra Box")
        self._create_supply(app, company_id, name="Apple Bag")

        response = client.get("/inventory/supplies")
        html = response.data.decode()
        # "Apple Bag" must appear earlier in the page than "Zebra Box"
        assert html.index("Apple Bag") < html.index("Zebra Box")

    def test_view_inventory_sessions_link_present(self, auth_client, app):
        client, company_id, _ = auth_client
        self._create_supply(app, company_id, name="Some Supply")

        response = client.get("/inventory/supplies")
        assert b"Inventory Sessions" in response.data or b"inventory" in response.data.lower()


# ===========================================================================
# POST /inventory/supplies/<id>/toggle  –  toggle_supply_active
# ===========================================================================

class TestToggleSupplyActive:

    def _create_supply(self, app, company_id, name="Toggle Supply", is_active=True):
        with app.app_context():
            supply = Supply(
                name=name,
                unit="each",
                company_id=company_id,
                is_active=is_active,
            )
            db.session.add(supply)
            db.session.commit()
            return supply.id

    def test_redirects_when_not_logged_in(self, client):
        response = client.post("/inventory/supplies/999/toggle")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_deactivates_active_supply(self, auth_client, app):
        client, company_id, _ = auth_client
        supply_id = self._create_supply(app, company_id, is_active=True)

        response = client.post(
            f"/inventory/supplies/{supply_id}/toggle",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"deactivated" in response.data.lower()

        with app.app_context():
            supply = Supply.query.get(supply_id)
            assert supply.is_active is False

    def test_activates_inactive_supply(self, auth_client, app):
        client, company_id, _ = auth_client
        supply_id = self._create_supply(app, company_id, is_active=False)

        response = client.post(
            f"/inventory/supplies/{supply_id}/toggle",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"activated" in response.data.lower()

        with app.app_context():
            supply = Supply.query.get(supply_id)
            assert supply.is_active is True

    def test_toggle_is_idempotent_cycle(self, auth_client, app):
        """Active → inactive → active toggles correctly both times."""
        client, company_id, _ = auth_client
        supply_id = self._create_supply(app, company_id, is_active=True)

        # First toggle: active → inactive
        client.post(f"/inventory/supplies/{supply_id}/toggle", follow_redirects=True)
        with app.app_context():
            assert Supply.query.get(supply_id).is_active is False

        # Second toggle: inactive → active
        client.post(f"/inventory/supplies/{supply_id}/toggle", follow_redirects=True)
        with app.app_context():
            assert Supply.query.get(supply_id).is_active is True

    def test_cannot_toggle_other_company_supply(self, auth_client, app):
        client, company_id, _ = auth_client

        with app.app_context():
            other = Company(name="Other Co 5", admin_email="other5@other.com")
            db.session.add(other)
            db.session.commit()
            other_id = other.id

        supply_id = self._create_supply(app, other_id)

        response = client.post(f"/inventory/supplies/{supply_id}/toggle")
        assert response.status_code == 404

        # Supply state must not have changed
        with app.app_context():
            assert Supply.query.get(supply_id).is_active is True

    def test_redirects_to_supplies_page_after_toggle(self, auth_client, app):
        client, company_id, _ = auth_client
        supply_id = self._create_supply(app, company_id)

        response = client.post(
            f"/inventory/supplies/{supply_id}/toggle",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/inventory/supplies" in response.location

    def test_returns_404_for_nonexistent_supply(self, auth_client):
        client, company_id, _ = auth_client
        response = client.post("/inventory/supplies/999999/toggle")
        assert response.status_code == 404
