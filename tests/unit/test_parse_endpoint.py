# Copyright Cade Stocker 2026
import io
from unittest.mock import patch


def test_parse_price_pdf_filters_suggestions(client, logged_in_user, app):
    # Create a RawProduct in the DB that should be matched
    with app.app_context():
        from app import db
        from app.models import RawProduct

        rp = RawProduct(name="Peppers, Green", company_id=logged_in_user.company_id)
        db.session.add(rp)
        db.session.commit()
        rp_id = rp.id

    # Patch PDF extraction and parsing to return controlled parsed items
    with patch('app.blueprints.ai.extract_pdf_text', return_value="dummy text"), \
         patch('app.blueprints.ai.parse_price_list_with_openai') as mock_parse:

        mock_parse.return_value = {
            "vendor": "Test Vendor",
            "effective_date": "2026-01-01",
            "items": [
                {"name": "Peppers, Green", "price_usd": 1.0},
                {"name": "Green Peppers Fancy", "price_usd": 2.0}
            ]
        }

        data = {'file': (io.BytesIO(b'%PDF-1.4 dummy'), 'test.pdf')}
        rv = client.post('/api/parse_price_pdf', data=data, content_type='multipart/form-data')
        assert rv.status_code == 200

        j = rv.get_json()
        matched = j.get('matched_items', [])
        skipped = j.get('skipped_items', [])
        parsed = j.get('parsed_items', [])

        # Ensure matched item references the RawProduct we created
        assert any(mi.get('matched_product_id') == rp_id for mi in matched)

        # New API: suggestions are preserved but parsed_items include candidate
        # annotations. Ensure parsed_items contains the candidate with in_use_by
        # pointing to the matched parsed item id.
        # Find the parsed item that matched our raw product
        matched_parsed = next((p for p in parsed if p.get('matched_product_id') == rp_id), None)
        assert matched_parsed is not None

        # Now ensure any parsed item's candidates that reference rp_id include an in_use_by annotation
        found = False
        for p in parsed:
            for c in p.get('candidates', []):
                if c.get('id') == rp_id:
                    # in_use_by should be set to the parsed item id that uses it
                    assert c.get('in_use_by') is not None
                    found = True
        assert found
