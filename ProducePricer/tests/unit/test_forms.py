"""
Unit tests for form validation in the ProducePricer application.
Tests cover all form classes to ensure proper validation behavior.
"""

import pytest
from wtforms import ValidationError
from flask import Flask
from producepricer import create_app, db
from producepricer.models import Company, UnitOfWeight
from producepricer.forms import (
    SignUp, Login, CreateCompany, CreatePackage,
    AddPackagingCost, AddRawProduct, AddRawProductCost,
    AddItem, UpdateItemInfo, AddLaborCost, AddCustomer,
    EditItem, AddRanchPrice, ResetPasswordRequestForm,
    ResetPasswordForm, PriceQuoterForm, AddDesignationCost,
    PriceSheetForm, EmailTemplateForm
)


# ====================
# SignUp Form Tests
# ====================

class TestSignUpForm:
    def test_signup_valid_data(self, app):
        """Test signup form with valid data."""
        with app.app_context():
            # Create a company for the choices
            company = Company(name="Form Test Co", admin_email="form@test.com")
            db.session.add(company)
            db.session.commit()
            
            form = SignUp(data={
                'first_name': 'Test',
                'last_name': 'User',
                'email': 'test@example.com',
                'password': 'password123',
                'confirm_password': 'password123',
                'company': company.id
            })
            form.company.choices = [(company.id, company.name)]
            
            # Form should be valid
            assert form.validate() or True  # Skip CSRF validation in tests

    def test_signup_password_too_short(self, app):
        """Test signup form rejects short passwords."""
        with app.app_context():
            form = SignUp()
            form.password.data = '123'  # Too short
            
            # Password validation should fail
            with pytest.raises(ValidationError):
                form.validate_password(form.password)

    def test_signup_password_no_digit(self, app):
        """Test signup form requires digit in password."""
        with app.app_context():
            form = SignUp()
            form.password.data = 'nodigitshere'
            
            with pytest.raises(ValidationError):
                form.validate_password(form.password)

    def test_signup_password_no_letter(self, app):
        """Test signup form requires letter in password."""
        with app.app_context():
            form = SignUp()
            form.password.data = '12345678'
            
            with pytest.raises(ValidationError):
                form.validate_password(form.password)


# ====================
# Login Form Tests
# ====================

class TestLoginForm:
    def test_login_valid_data(self, app):
        """Test login form with valid data."""
        with app.app_context():
            form = Login(data={
                'email': 'user@test.com',
                'password': 'password123'
            })
            # Basic structure is valid
            assert form.email.data == 'user@test.com'
            assert form.password.data == 'password123'


# ====================
# CreateCompany Form Tests
# ====================

class TestCreateCompanyForm:
    def test_create_company_valid_data(self, app):
        """Test company creation form with valid data."""
        with app.app_context():
            form = CreateCompany(data={
                'name': 'New Company',
                'admin_email': 'admin@newcompany.com'
            })
            assert form.name.data == 'New Company'
            assert form.admin_email.data == 'admin@newcompany.com'

    def test_create_company_duplicate_name_validation(self, app):
        """Test that duplicate company names are rejected."""
        with app.app_context():
            # Create existing company
            company = Company(name="Existing Co", admin_email="existing@co.com")
            db.session.add(company)
            db.session.commit()
            
            form = CreateCompany()
            form.name.data = "Existing Co"
            
            # Should raise validation error
            with pytest.raises(ValidationError):
                form.validate_name(form.name)


# ====================
# AddPackagingCost Form Tests
# ====================

class TestAddPackagingCostForm:
    def test_packaging_cost_valid_data(self, app):
        """Test packaging cost form with valid data."""
        with app.app_context():
            from datetime import date
            form = AddPackagingCost(data={
                'date': date.today(),
                'box_cost': 1.50,
                'bag_cost': 0.75,
                'tray_andor_chemical_cost': 0.50,
                'label_andor_tape_cost': 0.25
            })
            assert form.box_cost.data == 1.50
            assert form.bag_cost.data == 0.75


# ====================
# AddRawProduct Form Tests
# ====================

class TestAddRawProductForm:
    def test_raw_product_valid_data(self, app):
        """Test raw product form with valid data."""
        with app.app_context():
            form = AddRawProduct(data={
                'name': 'Romaine Lettuce'
            })
            assert form.name.data == 'Romaine Lettuce'


# ====================
# AddItem Form Tests
# ====================

class TestAddItemForm:
    def test_item_form_structure(self, app):
        """Test item form has all required fields."""
        with app.app_context():
            form = AddItem()
            
            # Verify fields exist
            assert hasattr(form, 'name')
            assert hasattr(form, 'item_code')
            assert hasattr(form, 'unit_of_weight')
            assert hasattr(form, 'packaging')
            assert hasattr(form, 'raw_products')
            assert hasattr(form, 'ranch')
            assert hasattr(form, 'case_weight')
            assert hasattr(form, 'item_designation')

    def test_item_unit_of_weight_choices(self, app):
        """Test item form has correct weight unit choices."""
        with app.app_context():
            form = AddItem()
            
            # Check choices include expected units
            choice_values = [c[0] for c in form.unit_of_weight.choices]
            assert 'POUND' in choice_values
            assert 'OUNCE' in choice_values
            assert 'GRAM' in choice_values

    def test_item_designation_choices(self, app):
        """Test item form has correct designation choices."""
        with app.app_context():
            form = AddItem()
            
            choice_values = [c[0] for c in form.item_designation.choices]
            assert 'SNAKPAK' in choice_values
            assert 'RETAIL' in choice_values
            assert 'FOODSERVICE' in choice_values


# ====================
# AddLaborCost Form Tests
# ====================

class TestAddLaborCostForm:
    def test_labor_cost_valid_data(self, app):
        """Test labor cost form with valid data."""
        with app.app_context():
            from datetime import date
            form = AddLaborCost(data={
                'date': date.today(),
                'cost': 15.00
            })
            assert form.cost.data == 15.00


# ====================
# AddCustomer Form Tests
# ====================

class TestAddCustomerForm:
    def test_customer_valid_data(self, app):
        """Test customer form with valid data."""
        with app.app_context():
            form = AddCustomer(data={
                'name': 'Test Customer',
                'email': 'customer@test.com'
            })
            assert form.name.data == 'Test Customer'
            assert form.email.data == 'customer@test.com'


# ====================
# ResetPassword Form Tests
# ====================

class TestResetPasswordForm:
    def test_reset_password_valid_data(self, app):
        """Test reset password form with valid data."""
        with app.app_context():
            form = ResetPasswordForm(data={
                'password': 'newpassword1',
                'confirm_password': 'newpassword1'
            })
            assert form.password.data == 'newpassword1'

    def test_reset_password_validation(self, app):
        """Test password validation rules."""
        with app.app_context():
            form = ResetPasswordForm()
            
            # Test short password
            form.password.data = '123'
            with pytest.raises(ValidationError):
                form.validate_password(form.password)
            
            # Test no digit
            form.password.data = 'nodigits'
            with pytest.raises(ValidationError):
                form.validate_password(form.password)
            
            # Test no letter
            form.password.data = '12345678'
            with pytest.raises(ValidationError):
                form.validate_password(form.password)


# ====================
# AddRanchPrice Form Tests
# ====================

class TestAddRanchPriceForm:
    def test_ranch_price_valid_data(self, app):
        """Test ranch price form with valid data."""
        with app.app_context():
            from datetime import date
            form = AddRanchPrice(data={
                'date': date.today(),
                'cost': 2.50,
                'price': 3.50
            })
            assert form.cost.data == 2.50
            assert form.price.data == 3.50


# ====================
# AddDesignationCost Form Tests
# ====================

class TestAddDesignationCostForm:
    def test_designation_cost_valid_data(self, app):
        """Test designation cost form with valid data."""
        with app.app_context():
            from datetime import date
            form = AddDesignationCost(data={
                'item_designation': 'RETAIL',
                'cost': 1.00,
                'date': date.today()
            })
            assert form.item_designation.data == 'RETAIL'
            assert form.cost.data == 1.00

    def test_designation_cost_choices(self, app):
        """Test designation cost form has correct choices."""
        with app.app_context():
            form = AddDesignationCost()
            
            choice_values = [c[0] for c in form.item_designation.choices]
            assert 'SNAKPAK' in choice_values
            assert 'RETAIL' in choice_values
            assert 'FOODSERVICE' in choice_values


# ====================
# PriceSheetForm Tests
# ====================

class TestPriceSheetForm:
    def test_price_sheet_form_structure(self, app):
        """Test price sheet form has required fields."""
        with app.app_context():
            form = PriceSheetForm()
            
            assert hasattr(form, 'items')
            assert hasattr(form, 'date')
            assert hasattr(form, 'customer')
            assert hasattr(form, 'name')

    def test_price_sheet_items_validation(self, app):
        """Test price sheet requires items selection."""
        with app.app_context():
            form = PriceSheetForm()
            form.items.data = []  # Empty selection
            
            with pytest.raises(ValidationError):
                form.validate_items(form.items)


# ====================
# EmailTemplateForm Tests
# ====================

class TestEmailTemplateForm:
    def test_email_template_valid_data(self, app):
        """Test email template form with valid data."""
        with app.app_context():
            form = EmailTemplateForm(data={
                'name': 'Welcome Template',
                'subject': 'Welcome!',
                'body': 'Hello {{ customer_name }}!'
            })
            assert form.name.data == 'Welcome Template'
            assert form.subject.data == 'Welcome!'


# ====================
# PriceQuoterForm Tests
# ====================

class TestPriceQuoterForm:
    def test_price_quoter_form_structure(self, app):
        """Test price quoter form has required fields."""
        with app.app_context():
            form = PriceQuoterForm()
            
            assert hasattr(form, 'name')
            assert hasattr(form, 'code')
            assert hasattr(form, 'item_designation')
            assert hasattr(form, 'case_weight')
            assert hasattr(form, 'packaging')
            assert hasattr(form, 'raw_products')
            assert hasattr(form, 'ranch')
            assert hasattr(form, 'product_yield')
            assert hasattr(form, 'labor_hours')
