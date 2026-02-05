"""
Tests for updating price sheet dates (valid_from, valid_to).
"""

import pytest
from datetime import date, timedelta
from producepricer import db
from producepricer.models import Company, User, Customer, PriceSheet, Item, UnitOfWeight, Packaging

# ====================
# Fixtures
# ====================

@pytest.fixture
def setup_data(app):
    """Setup basic data: Company, User, Customer, Item, Packaging."""
    with app.app_context():
        # Company
        company = Company(name="Test Company", admin_email="admin@test.com")
        db.session.add(company)
        db.session.commit()

        # User
        user = User(
            first_name="Test",
            last_name="Admin",
            email="admin@test.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)

        # Customer
        customer = Customer(
            name="Test Customer",
            email="customer@test.com",
            company_id=company.id
        )
        db.session.add(customer)

        # Packaging (Needed for Item)
        pkg = Packaging(packaging_type="Box", company_id=company.id)
        db.session.add(pkg)
        db.session.commit()

        # Item
        item = Item(
            name="Test Item",
            code="123",
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=pkg.id,
            company_id=company.id
        )
        db.session.add(item)
        db.session.commit()

        return {
            'company_id': company.id,
            'user_id': user.id,
            'customer_id': customer.id,
            'item_id': item.id
        }

@pytest.fixture
def logged_in_client(client, app, setup_data):
    """Return a logged-in client."""
    with app.app_context():
        # Log in
        client.post('/login', data={
            'email': "admin@test.com",
            'password': "password"
        })
    return client

# ====================
# Tests
# ====================

def test_update_dates_success(client, logged_in_client, app, setup_data):
    """Test successfully updating valid_from and valid_to dates."""
    with app.app_context():
        # Create a price sheet
        sheet = PriceSheet(
            name="Sheet 1",
            date=date(2025, 1, 1),
            valid_from=date(2025, 1, 1),
            valid_to=date(2025, 1, 31),
            company_id=setup_data['company_id'],
            customer_id=setup_data['customer_id']
        )
        db.session.add(sheet)
        db.session.commit()
        sheet_id = sheet.id

    # New dates
    new_from = "2025-02-01"
    new_to = "2025-02-28"

    response = logged_in_client.post(f'/edit_price_sheet/{sheet_id}', data={
        'update_dates': '1',
        'valid_from': new_from,
        'valid_to': new_to
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Price Sheet dates updated successfully!' in response.data

    with app.app_context():
        updated_sheet = db.session.get(PriceSheet, sheet_id)
        assert str(updated_sheet.valid_from) == new_from
        assert str(updated_sheet.valid_to) == new_to
        # Check that sheet.date was also synced (as per implementation)
        assert str(updated_sheet.date) == new_from

def test_update_dates_invalid_range(client, logged_in_client, app, setup_data):
    """Test error when valid_to is before valid_from."""
    with app.app_context():
        sheet = PriceSheet(
            name="Sheet 2",
            date=date(2025, 1, 1),
            company_id=setup_data['company_id'],
            customer_id=setup_data['customer_id']
        )
        db.session.add(sheet)
        db.session.commit()
        sheet_id = sheet.id

    # Invalid range: To is before From
    invalid_from = "2025-03-10"
    invalid_to = "2025-03-01"

    response = logged_in_client.post(f'/edit_price_sheet/{sheet_id}', data={
        'update_dates': '1',
        'valid_from': invalid_from,
        'valid_to': invalid_to
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Error: Valid To date cannot be before Valid From date.' in response.data

    with app.app_context():
        # Verify dates were NOT updated
        updated_sheet = db.session.get(PriceSheet, sheet_id)
        # Should remain as original date (2025-01-01) or None depending on initialization
        assert str(updated_sheet.valid_from) == "2025-01-01"
        assert updated_sheet.valid_to is None

def test_update_dates_clear_valid_to(client, logged_in_client, app, setup_data):
    """Test clearing the valid_to date (making it open-ended)."""
    with app.app_context():
        sheet = PriceSheet(
            name="Sheet 3",
            date=date(2025, 1, 1),
            valid_from=date(2025, 1, 1),
            valid_to=date(2025, 1, 31),
            company_id=setup_data['company_id'],
            customer_id=setup_data['customer_id']
        )
        db.session.add(sheet)
        db.session.commit()
        sheet_id = sheet.id

    # Provide empty valid_to
    new_from = "2025-04-01"
    
    response = logged_in_client.post(f'/edit_price_sheet/{sheet_id}', data={
        'update_dates': '1',
        'valid_from': new_from,
        'valid_to': ''
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Price Sheet dates updated successfully!' in response.data

    with app.app_context():
        updated_sheet = db.session.get(PriceSheet, sheet_id)
        assert str(updated_sheet.valid_from) == new_from
        assert updated_sheet.valid_to is None
