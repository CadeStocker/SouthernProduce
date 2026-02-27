import pytest
from datetime import date, timedelta, datetime
from producepricer import db
from producepricer.models import (
    Company, User, Customer, Item, PriceSheet, PriceHistory, 
    UnitOfWeight, ItemDesignation, RawProduct
)
from producepricer.blueprints.pricing import _generate_price_sheet_pdf_bytes
from flask_login import login_user
import pdfplumber
import io

@pytest.fixture
def pdf_test_setup(app):
    """Setup for PDF generation tests"""
    with app.app_context():
        # Create company and user
        company = Company(name="PDF Test Co", admin_email="pdf@test.com")
        db.session.add(company)
        db.session.commit()
        
        user = User(
            first_name="PDF",
            last_name="Tester",
            email="tester@pdf.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()
        
        # Create items
        raw = RawProduct(name="Raw Item", company_id=company.id)
        db.session.add(raw)
        db.session.commit()
        
        item1 = Item(
            name="Changed Price Item",
            code="CPI001",
            item_designation=ItemDesignation.RETAIL,
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=1,
            company_id=company.id
        )
        item1.raw_products.append(raw)
        
        item2 = Item(
            name="Unchanged Price Item",
            code="UPI001",
            item_designation=ItemDesignation.RETAIL,
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=1,
            company_id=company.id
        )
        item2.raw_products.append(raw)
        
        item3 = Item(
            name="New Item",
            code="NI001",
            item_designation=ItemDesignation.RETAIL,
            unit_of_weight=UnitOfWeight.POUND,
            packaging_id=1,
            company_id=company.id
        )
        item3.raw_products.append(raw)
        
        db.session.add_all([item1, item2, item3])
        db.session.commit()
        
        # Create customer
        customer = Customer(name="PDF Customer", email="cust@pdf.com", company_id=company.id)
        db.session.add(customer)
        db.session.commit()
        
        yield {
            'app': app,
            'user': user,
            'company': company,
            'customer': customer,
            'items': [item1, item2, item3]
        }

def test_price_change_indicator(pdf_test_setup):
    """
    Test that the PDF correctly indicates price changes based on value comparison
    rather than just date.
    """
    setup = pdf_test_setup
    app = setup['app']
    user = setup['user']
    company = setup['company']
    customer = setup['customer']
    item_changed, item_unchanged, item_new = setup['items']
    
    with app.test_request_context():
        login_user(user)
        
        today = date.today()
        eight_days_ago = today - timedelta(days=8)
        
        # 1. Setup "Changed Price Item"
        # Old price: 10.00, New price: 12.00 -> Should have *
        ph1_old = PriceHistory(
            item_id=item_changed.id,
            date=eight_days_ago,
            company_id=company.id,
            customer_id=customer.id,
            price=10.00
        )
        ph1_new = PriceHistory(
            item_id=item_changed.id,
            date=today,
            company_id=company.id,
            customer_id=customer.id,
            price=12.00
        )
        
        # 2. Setup "Unchanged Price Item"
        # Old price: 15.00, New price: 15.00 -> Should NOT have *
        ph2_old = PriceHistory(
            item_id=item_unchanged.id,
            date=eight_days_ago,
            company_id=company.id,
            customer_id=customer.id,
            price=15.00
        )
        ph2_new = PriceHistory(
            item_id=item_unchanged.id,
            date=today,
            company_id=company.id,
            customer_id=customer.id,
            price=15.00
        )
        
        # 3. Setup "New Item"
        # Only new price: 20.00 -> Should have * (treated as changed/new)
        ph3_new = PriceHistory(
            item_id=item_new.id,
            date=today,
            company_id=company.id,
            customer_id=customer.id,
            price=20.00
        )
        
        db.session.add_all([ph1_old, ph1_new, ph2_old, ph2_new, ph3_new])
        db.session.commit()
        
        # Create Price Sheet
        sheet = PriceSheet(name="Test Sheet", date=today, company_id=company.id, customer_id=customer.id)
        sheet.items.append(item_changed)
        sheet.items.append(item_unchanged)
        sheet.items.append(item_new)
        db.session.add(sheet)
        db.session.commit()
        
        # Generate PDF
        pdf_bytes = _generate_price_sheet_pdf_bytes(sheet)
        
        # Analyze PDF
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[0]
            text = page.extract_text()
            table = page.extract_table()
            
            # Debug print
            print("\nPDF Text Content:")
            print(text)
            print("\nPDF Table Content:")
            for row in table:
                print(row)
            
            # Verify headers
            headers = table[0]
            assert "Product" in headers
            assert "Price" in headers
            assert "Changed" in headers
            
            # Find rows for each item
            row_changed = None
            row_unchanged = None
            row_new = None
            
            for row in table[1:]: # Skip header
                if item_changed.name in row[0]:
                    row_changed = row
                elif item_unchanged.name in row[0]:
                    row_unchanged = row
                elif item_new.name in row[0]:
                    row_new = row
            
            # Assertions
            
            # 1. Changed Item should have *
            assert row_changed is not None
            assert row_changed[1] == "$12.00"
            assert "*" in row_changed[2], "Changed item should be marked with *"
            
            # 2. Unchanged Item should NOT have *
            assert row_unchanged is not None
            assert row_unchanged[1] == "$15.00"
            assert row_unchanged[2] == "" or row_unchanged[2] is None, "Unchanged item should NOT be marked with *"
            
            # 3. New Item should have *
            assert row_new is not None
            assert row_new[1] == "$20.00"
            assert "*" in row_new[2], "New item should be marked with *"

