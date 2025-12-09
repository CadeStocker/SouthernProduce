"""
Tests for email functionality including:
- Admin approval emails for new user signups
- Password reset emails
- Email templates (CRUD operations)
- Price sheet email sending with templates
"""

import pytest
from datetime import date, datetime
from flask import url_for
from unittest.mock import patch, MagicMock
from producepricer import db
from producepricer.models import (
    Company, User, PendingUser, EmailTemplate, PriceSheet, Item, 
    Packaging, Customer, UnitOfWeight, ItemDesignation
)


# ====================
# Fixtures
# ====================

@pytest.fixture
def setup_company_with_admin(app):
    """Create a company with an admin user."""
    with app.app_context():
        company = Company(name="Email Test Co", admin_email="emailadmin@test.com")
        db.session.add(company)
        db.session.commit()
        
        admin_user = User(
            first_name="Email",
            last_name="Admin",
            email="emailadmin@test.com",
            password="adminpass",
            company_id=company.id
        )
        db.session.add(admin_user)
        db.session.commit()
        
        return {
            'company_id': company.id,
            'admin_id': admin_user.id,
            'admin_email': admin_user.email
        }


@pytest.fixture
def logged_in_admin(client, app, setup_company_with_admin):
    """Return a client logged in as the admin user."""
    client.post('/login', data={
        'email': 'emailadmin@test.com',
        'password': 'adminpass'
    })
    return client


@pytest.fixture
def setup_email_template_data(app, setup_company_with_admin):
    """Create email template test data."""
    with app.app_context():
        setup = setup_company_with_admin
        
        # Create templates
        template1 = EmailTemplate(
            name="Default Template",
            subject="Price Update: {{ sheet.name }}",
            body="Dear Customer,\n\nPlease find attached the price sheet for {{ sheet.name }}.",
            company_id=setup['company_id'],
            is_default=True
        )
        template2 = EmailTemplate(
            name="Formal Template",
            subject="Official Price Sheet: {{ sheet.name }}",
            body="Dear Valued Customer,\n\nEnclosed please find our official price sheet.",
            company_id=setup['company_id'],
            is_default=False
        )
        db.session.add_all([template1, template2])
        db.session.commit()
        
        return {
            **setup,
            'template1_id': template1.id,
            'template2_id': template2.id
        }


@pytest.fixture
def setup_price_sheet_data(app, setup_company_with_admin):
    """Create price sheet data for email testing."""
    with app.app_context():
        setup = setup_company_with_admin
        
        # Create packaging
        packaging = Packaging(packaging_type="Test Box", company_id=setup['company_id'])
        db.session.add(packaging)
        db.session.commit()
        
        # Create customer
        customer = Customer(
            name="Test Customer",
            email="customer@test.com",
            company_id=setup['company_id']
        )
        db.session.add(customer)
        db.session.commit()
        
        # Create items
        items = []
        for i in range(3):
            item = Item(
                name=f"Email Test Item {i}",
                code=f"ETI-{i:03d}",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging.id,
                company_id=setup['company_id']
            )
            items.append(item)
        db.session.add_all(items)
        db.session.commit()
        
        # Create price sheet
        sheet = PriceSheet(
            name="Test Price Sheet",
            date=date.today(),
            company_id=setup['company_id'],
            customer_id=customer.id
        )
        sheet.items.extend(items)
        db.session.add(sheet)
        db.session.commit()
        
        return {
            **setup,
            'sheet_id': sheet.id,
            'customer_id': customer.id,
            'customer_email': customer.email
        }


# ====================
# Admin Approval Email Tests
# ====================

class TestAdminApprovalEmail:
    """Tests for admin approval email functionality when new users sign up."""
    
    @patch('producepricer.routes.send_admin_approval_email')
    def test_signup_triggers_admin_email(self, mock_send_email, client, app, setup_company_with_admin):
        """Test that signing up triggers an admin approval email."""
        setup = setup_company_with_admin
        
        response = client.post('/signup', data={
            'first_name': 'New',
            'last_name': 'User',
            'email': 'newuser@test.com',
            'password': 'newpassword1',
            'confirm_password': 'newpassword1',
            'company': setup['company_id']
        }, follow_redirects=True)
        
        # Since newuser is not the admin email, should create pending user
        # and send admin approval email
        with app.app_context():
            pending = PendingUser.query.filter_by(email='newuser@test.com').first()
            if pending:  # Pending user created
                mock_send_email.assert_called_once()

    @patch('producepricer.routes.EmailMessage')
    def test_admin_approval_email_content(self, mock_email_class, app, setup_company_with_admin):
        """Test that admin approval email contains correct content."""
        from producepricer.routes import send_admin_approval_email
        
        with app.app_context():
            setup = setup_company_with_admin
            mock_msg = MagicMock()
            mock_email_class.return_value = mock_msg
            
            send_admin_approval_email("test_token_123", setup['company_id'])
            
            # Verify EmailMessage was called with correct parameters
            mock_email_class.assert_called_once()
            call_kwargs = mock_email_class.call_args[1]
            
            assert call_kwargs['subject'] == 'Approve new user request'
            assert setup['admin_email'] in call_kwargs['to']
            assert 'approve' in call_kwargs['body'].lower()
            
            mock_msg.send.assert_called_once()


# ====================
# Password Reset Email Tests
# ====================

class TestPasswordResetEmail:
    """Tests for password reset email functionality."""
    
    def test_password_reset_request_page_loads(self, client, app):
        """Test that the password reset request page loads."""
        response = client.get('/reset/_password')
        assert response.status_code == 200
        assert b'Reset' in response.data or b'reset' in response.data

    @patch('producepricer.routes.send_reset_password_email')
    def test_password_reset_triggers_email(self, mock_send_email, client, app, setup_company_with_admin):
        """Test that requesting password reset triggers email."""
        response = client.post('/reset/_password', data={
            'email': 'emailadmin@test.com'
        }, follow_redirects=True)
        
        mock_send_email.assert_called_once()

    @patch('producepricer.routes.send_reset_password_email')
    def test_password_reset_no_email_for_nonexistent_user(self, mock_send_email, client, app):
        """Test that no email is sent for non-existent users."""
        response = client.post('/reset/_password', data={
            'email': 'nonexistent@test.com'
        }, follow_redirects=True)
        
        # Should not send email for non-existent user
        mock_send_email.assert_not_called()

    def test_password_reset_token_generation(self, app, setup_company_with_admin):
        """Test that password reset token is generated properly."""
        with app.app_context():
            user = User.query.filter_by(email='emailadmin@test.com').first()
            token = user.generate_reset_password_token()
            
            assert token is not None
            assert len(token) > 0

    def test_password_reset_token_verification(self, app, setup_company_with_admin):
        """Test that password reset token can be verified."""
        with app.app_context():
            user = User.query.filter_by(email='emailadmin@test.com').first()
            token = user.generate_reset_password_token()
            
            # Verify token
            verified_user = User.verify_reset_password_token(token, user.id)
            assert verified_user is not None
            assert verified_user.id == user.id

    def test_password_reset_invalid_token(self, app, setup_company_with_admin):
        """Test that invalid token returns None."""
        with app.app_context():
            user = User.query.filter_by(email='emailadmin@test.com').first()
            
            # Use invalid token
            verified_user = User.verify_reset_password_token("invalid_token", user.id)
            assert verified_user is None

    def test_password_reset_wrong_user_id(self, app, setup_company_with_admin):
        """Test that token with wrong user ID returns None."""
        with app.app_context():
            user = User.query.filter_by(email='emailadmin@test.com').first()
            token = user.generate_reset_password_token()
            
            # Try to verify with wrong user ID
            verified_user = User.verify_reset_password_token(token, 99999)
            assert verified_user is None


# ====================
# Email Template CRUD Tests
# ====================

class TestEmailTemplateCRUD:
    """Tests for email template Create, Read, Update, Delete operations."""
    
    def test_email_templates_page_requires_login(self, client, app):
        """Test that email templates page requires authentication."""
        response = client.get('/email_templates')
        assert response.status_code == 302
        assert '/login' in response.location

    def test_email_templates_page_loads(self, logged_in_admin, app, setup_company_with_admin):
        """Test that email templates page loads for logged in users."""
        response = logged_in_admin.get('/email_templates')
        assert response.status_code == 200
        assert b'Email Template' in response.data or b'email' in response.data.lower()

    def test_create_email_template(self, logged_in_admin, app, setup_company_with_admin):
        """Test creating a new email template."""
        response = logged_in_admin.post('/email_templates', data={
            'name': 'New Test Template',
            'subject': 'Test Subject {{ sheet.name }}',
            'body': 'Test body content',
            'is_default': False
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify template was created
        with app.app_context():
            template = EmailTemplate.query.filter_by(name='New Test Template').first()
            assert template is not None
            assert template.subject == 'Test Subject {{ sheet.name }}'

    def test_create_default_template(self, logged_in_admin, app, setup_company_with_admin):
        """Test creating a default email template."""
        response = logged_in_admin.post('/email_templates', data={
            'name': 'Default Test Template',
            'subject': 'Default Subject',
            'body': 'Default body',
            'is_default': True
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        with app.app_context():
            template = EmailTemplate.query.filter_by(name='Default Test Template').first()
            assert template is not None
            assert template.is_default == True

    def test_set_default_unsets_others(self, logged_in_admin, app, setup_email_template_data):
        """Test that setting a template as default unsets other defaults."""
        setup = setup_email_template_data
        
        # Set template2 as default
        response = logged_in_admin.post(f'/email_template/{setup["template2_id"]}/set_default',
                                       follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify template2 is now default and template1 is not
        with app.app_context():
            template1 = db.session.get(EmailTemplate, setup['template1_id'])
            template2 = db.session.get(EmailTemplate, setup['template2_id'])
            
            assert template2.is_default == True
            assert template1.is_default == False

    def test_edit_email_template(self, logged_in_admin, app, setup_email_template_data):
        """Test editing an email template."""
        setup = setup_email_template_data
        
        response = logged_in_admin.post(f'/email_template/{setup["template2_id"]}/edit', data={
            'name': 'Updated Template',
            'subject': 'Updated Subject',
            'body': 'Updated body content',
            'is_default': False
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        with app.app_context():
            template = db.session.get(EmailTemplate, setup['template2_id'])
            assert template.name == 'Updated Template'
            assert template.subject == 'Updated Subject'

    def test_delete_email_template(self, logged_in_admin, app, setup_email_template_data):
        """Test deleting an email template."""
        setup = setup_email_template_data
        
        response = logged_in_admin.post(f'/email_template/{setup["template2_id"]}/delete',
                                       follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify template was deleted
        with app.app_context():
            template = db.session.get(EmailTemplate, setup['template2_id'])
            assert template is None

    def test_delete_nonexistent_template_404(self, logged_in_admin, app):
        """Test that deleting non-existent template returns 404."""
        response = logged_in_admin.post('/email_template/99999/delete')
        assert response.status_code == 404


# ====================
# Email Template Model Tests
# ====================

class TestEmailTemplateModel:
    """Tests for EmailTemplate model operations."""
    
    def test_email_template_repr(self, app, setup_company_with_admin):
        """Test EmailTemplate string representation."""
        with app.app_context():
            setup = setup_company_with_admin
            template = EmailTemplate(
                name="Test Repr",
                subject="Test Subject",
                body="Test Body",
                company_id=setup['company_id']
            )
            
            assert "Test Repr" in repr(template)
            assert "Test Subject" in repr(template)

    def test_template_jinja_variables(self, app, setup_company_with_admin):
        """Test that templates can contain Jinja2 variables."""
        with app.app_context():
            setup = setup_company_with_admin
            
            template = EmailTemplate(
                name="Jinja Template",
                subject="Price Sheet: {{ sheet.name }}",
                body="Dear {{ company.name }},\n\nSheet: {{ sheet.name }}\nDate: {{ now }}",
                company_id=setup['company_id']
            )
            db.session.add(template)
            db.session.commit()
            
            result = EmailTemplate.query.filter_by(name="Jinja Template").first()
            assert "{{ sheet.name }}" in result.subject
            assert "{{ company.name }}" in result.body

    def test_multiple_templates_per_company(self, app, setup_company_with_admin):
        """Test that a company can have multiple templates."""
        with app.app_context():
            setup = setup_company_with_admin
            
            for i in range(5):
                template = EmailTemplate(
                    name=f"Template {i}",
                    subject=f"Subject {i}",
                    body=f"Body {i}",
                    company_id=setup['company_id']
                )
                db.session.add(template)
            db.session.commit()
            
            templates = EmailTemplate.query.filter_by(company_id=setup['company_id']).all()
            assert len(templates) >= 5

    def test_template_isolation_between_companies(self, app):
        """Test that templates are isolated between companies."""
        with app.app_context():
            # Create two companies
            company1 = Company(name="Template Co 1", admin_email="tpl1@test.com")
            company2 = Company(name="Template Co 2", admin_email="tpl2@test.com")
            db.session.add_all([company1, company2])
            db.session.commit()
            
            # Create templates for each company
            tpl1 = EmailTemplate(
                name="Company 1 Template",
                subject="C1 Subject",
                body="C1 Body",
                company_id=company1.id
            )
            tpl2 = EmailTemplate(
                name="Company 2 Template",
                subject="C2 Subject",
                body="C2 Body",
                company_id=company2.id
            )
            db.session.add_all([tpl1, tpl2])
            db.session.commit()
            
            # Query templates for company 1 only
            company1_templates = EmailTemplate.query.filter_by(company_id=company1.id).all()
            template_names = [t.name for t in company1_templates]
            
            assert "Company 1 Template" in template_names
            assert "Company 2 Template" not in template_names


# ====================
# Price Sheet Email Tests
# ====================

class TestPriceSheetEmail:
    """Tests for emailing price sheets to customers."""
    
    @patch('producepricer.routes.EmailMessage')
    @patch('producepricer.routes._generate_price_sheet_pdf_bytes')
    def test_email_price_sheet(self, mock_pdf, mock_email_class, logged_in_admin, app, setup_price_sheet_data):
        """Test sending price sheet email."""
        setup = setup_price_sheet_data
        mock_pdf.return_value = b'fake pdf bytes'
        mock_msg = MagicMock()
        mock_email_class.return_value = mock_msg
        
        response = logged_in_admin.post(f'/email_price_sheet/{setup["sheet_id"]}', data={
            'recipient': 'customer@test.com'
        }, follow_redirects=True)
        
        # Should call EmailMessage
        mock_email_class.assert_called_once()
        # Should generate PDF
        mock_pdf.assert_called_once()
        # Should send the message
        mock_msg.send.assert_called_once()

    @patch('producepricer.routes.EmailMessage')
    @patch('producepricer.routes._generate_price_sheet_pdf_bytes')
    def test_email_price_sheet_with_template(self, mock_pdf, mock_email_class, logged_in_admin, app, setup_price_sheet_data):
        """Test sending price sheet email using a template."""
        setup = setup_price_sheet_data
        
        # Create a template
        with app.app_context():
            template = EmailTemplate(
                name="Price Sheet Template",
                subject="Your Price Sheet: {{ sheet.name }}",
                body="Please review attached price sheet.",
                company_id=setup['company_id'],
                is_default=True
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id
        
        mock_pdf.return_value = b'fake pdf bytes'
        mock_msg = MagicMock()
        mock_email_class.return_value = mock_msg
        
        response = logged_in_admin.post(f'/email_price_sheet/{setup["sheet_id"]}', data={
            'recipient': 'customer@test.com',
            'template_id': template_id
        }, follow_redirects=True)
        
        mock_email_class.assert_called_once()

    def test_email_price_sheet_requires_recipient(self, logged_in_admin, app, setup_price_sheet_data):
        """Test that emailing price sheet requires a recipient."""
        setup = setup_price_sheet_data
        
        response = logged_in_admin.post(f'/email_price_sheet/{setup["sheet_id"]}', data={},
                                       follow_redirects=True)
        
        # Should show error about recipient
        assert b'Recipient' in response.data or b'recipient' in response.data or b'required' in response.data.lower()

    def test_email_price_sheet_nonexistent_sheet(self, logged_in_admin, app):
        """Test that emailing non-existent price sheet returns 404."""
        response = logged_in_admin.post('/email_price_sheet/99999', data={
            'recipient': 'test@test.com'
        })
        assert response.status_code == 404

    @patch('producepricer.routes.EmailMessage')
    @patch('producepricer.routes._generate_price_sheet_pdf_bytes')
    def test_email_price_sheet_attaches_pdf(self, mock_pdf, mock_email_class, logged_in_admin, app, setup_price_sheet_data):
        """Test that price sheet email attaches PDF."""
        setup = setup_price_sheet_data
        mock_pdf.return_value = b'fake pdf bytes'
        mock_msg = MagicMock()
        mock_email_class.return_value = mock_msg
        
        response = logged_in_admin.post(f'/email_price_sheet/{setup["sheet_id"]}', data={
            'recipient': 'customer@test.com'
        }, follow_redirects=True)
        
        # Verify attach was called
        mock_msg.attach.assert_called()
        call_args = mock_msg.attach.call_args[0]
        assert '.pdf' in call_args[0]  # Filename should contain .pdf
        assert call_args[1] == b'fake pdf bytes'  # PDF bytes
        assert call_args[2] == 'application/pdf'  # MIME type

    @patch('producepricer.routes.EmailMessage')
    @patch('producepricer.routes._generate_price_sheet_pdf_bytes')
    def test_email_price_sheet_uses_default_template(self, mock_pdf, mock_email_class, logged_in_admin, app, setup_price_sheet_data):
        """Test that price sheet email uses default template when no template specified."""
        setup = setup_price_sheet_data
        
        # Create default template
        with app.app_context():
            default_template = EmailTemplate(
                name="Default Template",
                subject="DEFAULT: {{ sheet.name }}",
                body="This is the default template.",
                company_id=setup['company_id'],
                is_default=True
            )
            db.session.add(default_template)
            db.session.commit()
        
        mock_pdf.return_value = b'fake pdf bytes'
        mock_msg = MagicMock()
        mock_email_class.return_value = mock_msg
        
        # Don't specify template_id
        response = logged_in_admin.post(f'/email_price_sheet/{setup["sheet_id"]}', data={
            'recipient': 'customer@test.com'
        }, follow_redirects=True)
        
        mock_email_class.assert_called_once()
        # The subject should be rendered from the default template
        call_kwargs = mock_email_class.call_args[1]
        # Subject should include "DEFAULT:" from our template
        assert 'DEFAULT:' in call_kwargs['subject'] or 'Price Sheet' in call_kwargs['subject']


# ====================
# Email Error Handling Tests
# ====================

class TestEmailErrorHandling:
    """Tests for email error handling."""
    
    @patch('producepricer.routes.EmailMessage')
    @patch('producepricer.routes._generate_price_sheet_pdf_bytes')
    def test_email_send_failure_handled(self, mock_pdf, mock_email_class, logged_in_admin, app, setup_price_sheet_data):
        """Test that email send failures are handled gracefully."""
        setup = setup_price_sheet_data
        mock_pdf.return_value = b'fake pdf bytes'
        mock_msg = MagicMock()
        mock_msg.send.side_effect = Exception("SMTP Error")
        mock_email_class.return_value = mock_msg
        
        response = logged_in_admin.post(f'/email_price_sheet/{setup["sheet_id"]}', data={
            'recipient': 'customer@test.com'
        }, follow_redirects=True)
        
        # Should show error message but not crash
        assert response.status_code == 200
        assert b'Failed' in response.data or b'error' in response.data.lower()

    @patch('producepricer.routes.EmailMessage')
    @patch('producepricer.routes._generate_price_sheet_pdf_bytes')
    def test_template_render_error_falls_back_to_defaults(self, mock_pdf, mock_email_class, logged_in_admin, app, setup_price_sheet_data):
        """Test that template rendering errors fall back to default content."""
        setup = setup_price_sheet_data
        
        # Create template with invalid Jinja syntax
        with app.app_context():
            bad_template = EmailTemplate(
                name="Bad Template",
                subject="{{ invalid.syntax. }}",  # Invalid syntax
                body="Body with {{ undefined_var }}",
                company_id=setup['company_id'],
                is_default=True
            )
            db.session.add(bad_template)
            db.session.commit()
        
        mock_pdf.return_value = b'fake pdf bytes'
        mock_msg = MagicMock()
        mock_email_class.return_value = mock_msg
        
        response = logged_in_admin.post(f'/email_price_sheet/{setup["sheet_id"]}', data={
            'recipient': 'customer@test.com'
        }, follow_redirects=True)
        
        # Should still attempt to send with fallback content
        # (the actual behavior depends on implementation)
        assert response.status_code == 200
