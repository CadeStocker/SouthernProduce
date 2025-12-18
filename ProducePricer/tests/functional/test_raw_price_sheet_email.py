import pytest
from unittest.mock import patch, MagicMock
from flask import url_for
from producepricer import db
from producepricer.models import RawProduct, CostHistory, User, Company
from datetime import date

@pytest.fixture
def logged_in_user(client, app):
    """Fixture to create and log in a test user."""
    with app.app_context():
        # Create a test company
        company = Company(name="Test Company", admin_email="test@example.com")
        db.session.add(company)
        db.session.commit()
        
        # Create a test user
        user = User(
            first_name="Test",
            last_name="User",
            email="user@test.com",
            password="password",
            company_id=company.id
        )
        db.session.add(user)
        db.session.commit()
        
        # Store the user ID for later retrieval
        user_id = user.id
    
    # Log in the user
    client.post(
        url_for('main.login'),
        data={'email': 'user@test.com', 'password': 'password'},
        follow_redirects=True
    )
    
    with app.app_context():
        return db.session.get(User, user_id)

@pytest.fixture
def setup_raw_products(app, logged_in_user):
    with app.app_context():
        # Create raw products
        rp1 = RawProduct(name="Carrots", company_id=logged_in_user.company_id)
        rp2 = RawProduct(name="Potatoes", company_id=logged_in_user.company_id)
        db.session.add_all([rp1, rp2])
        db.session.commit()

        # Add cost history for Carrots
        ch1_prev = CostHistory(
            cost=6.00,
            date=date(2023, 2, 1),
            raw_product_id=rp1.id,
            company_id=logged_in_user.company_id
        )
        ch1_latest = CostHistory(
            cost=7.50,
            date=date(2023, 3, 1),
            raw_product_id=rp1.id,
            company_id=logged_in_user.company_id
        )
        
        db.session.add_all([ch1_prev, ch1_latest])
        db.session.commit()

def test_email_raw_price_sheet_single_recipient(client, app, logged_in_user, setup_raw_products):
    """Test emailing the raw price sheet to a single recipient."""
    with patch('producepricer.routes.EmailMessage') as MockEmailMessage, \
         patch('producepricer.routes._generate_raw_price_sheet_pdf_bytes') as mock_gen_pdf:
        
        mock_msg = MockEmailMessage.return_value
        mock_msg.send.return_value = None
        mock_gen_pdf.return_value = b'fake pdf content'
        
        response = client.post(
            url_for('main.email_raw_price_sheet'),
            data={
                'recipient': 'recipient@example.com',
                'recipients': [] 
            },
            follow_redirects=True
        )
        
        assert response.status_code == 200
        assert b'Raw Price Sheet emailed to recipient@example.com.' in response.data
        
        # Verify EmailMessage was initialized correctly
        MockEmailMessage.assert_called_once()
        call_args = MockEmailMessage.call_args
        assert call_args.kwargs['to'] == ['recipient@example.com']
        assert call_args.kwargs['subject'] == "Raw Product Price Sheet"
        
        # Verify attachment
        mock_msg.attach.assert_called_with('raw_price_sheet.pdf', b'fake pdf content', 'application/pdf')
        
        # Verify send was called
        mock_msg.send.assert_called_once()

def test_email_raw_price_sheet_multiple_recipients(client, app, logged_in_user, setup_raw_products):
    """Test emailing the raw price sheet to multiple recipients."""
    with patch('producepricer.routes.EmailMessage') as MockEmailMessage, \
         patch('producepricer.routes._generate_raw_price_sheet_pdf_bytes') as mock_gen_pdf:
        
        mock_msg = MockEmailMessage.return_value
        mock_gen_pdf.return_value = b'fake pdf content'
        
        response = client.post(
            url_for('main.email_raw_price_sheet'),
            data={
                'recipients': ['r1@example.com', 'r2@example.com'],
                'recipient': 'r3@example.com'
            },
            follow_redirects=True
        )
        
        assert response.status_code == 200
        # The flash message joins recipients with ", "
        # The order might vary depending on how form data is processed, but usually list + single
        # In routes.py: recipients = request.form.getlist('recipients'); single = ...; if single... append
        # So order should be r1, r2, r3
        assert b'Raw Price Sheet emailed to r1@example.com, r2@example.com, r3@example.com.' in response.data
        
        MockEmailMessage.assert_called_once()
        call_args = MockEmailMessage.call_args
        assert set(call_args.kwargs['to']) == {'r1@example.com', 'r2@example.com', 'r3@example.com'}

def test_email_raw_price_sheet_no_recipient(client, app, logged_in_user, setup_raw_products):
    """Test error when no recipient is provided."""
    response = client.post(
        url_for('main.email_raw_price_sheet'),
        data={
            'recipients': [],
            'recipient': ''
        },
        follow_redirects=True
    )
    
    assert response.status_code == 200
    assert b'At least one recipient email is required.' in response.data

def test_email_raw_price_sheet_hide_previous(client, app, logged_in_user, setup_raw_products):
    """Test emailing with hide_previous option."""
    with patch('producepricer.routes.EmailMessage') as MockEmailMessage, \
         patch('producepricer.routes._generate_raw_price_sheet_pdf_bytes') as mock_gen_pdf:
        
        mock_msg = MockEmailMessage.return_value
        mock_gen_pdf.return_value = b'fake pdf content'
        
        response = client.post(
            url_for('main.email_raw_price_sheet'),
            data={
                'recipient': 'test@example.com',
                'hide_previous': 'on'
            },
            follow_redirects=True
        )
        
        assert response.status_code == 200
        
        # Verify generate_pdf was called with hide_previous=True
        mock_gen_pdf.assert_called_once()
        call_args = mock_gen_pdf.call_args
        assert call_args.kwargs['hide_previous'] is True

def test_email_raw_price_sheet_send_failure(client, app, logged_in_user, setup_raw_products):
    """Test handling of email send failure."""
    with patch('producepricer.routes.EmailMessage') as MockEmailMessage, \
         patch('producepricer.routes._generate_raw_price_sheet_pdf_bytes') as mock_gen_pdf:
        
        mock_msg = MockEmailMessage.return_value
        mock_msg.send.side_effect = Exception("SMTP Error")
        mock_gen_pdf.return_value = b'fake pdf content'
        
        response = client.post(
            url_for('main.email_raw_price_sheet'),
            data={'recipient': 'test@example.com'},
            follow_redirects=True
        )
        
        assert response.status_code == 200
        assert b'Failed to send email: SMTP Error' in response.data
