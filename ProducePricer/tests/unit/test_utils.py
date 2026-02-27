import pytest
from unittest.mock import patch, MagicMock
from producepricer.utils.matching import best_match
from producepricer.utils.ai_utils import get_ai_response
from producepricer.utils.parsing import parse_price_list_with_openai, coerce_iso_date
from datetime import date, datetime
import json

# ====================
# Tests for utils/matching.py
# ====================

class TestMatching:
    def test_best_match_exact(self):
        """Test exact match."""
        candidates = ["Apple", "Banana", "Orange"]
        match = best_match("Apple", candidates)
        assert match is not None
        assert match[0] == "Apple"
        assert match[1] == 100.0

    def test_best_match_fuzzy(self):
        """Test fuzzy match."""
        candidates = ["Apple Red", "Banana Yellow", "Orange Juice"]
        # "Red Apple" should match "Apple Red" with high score due to token sort
        match = best_match("Red Apple", candidates)
        assert match is not None
        assert match[0] == "Apple Red"
        assert match[1] > 80.0

    def test_best_match_no_match(self):
        """Test no match found above threshold."""
        candidates = ["Apple", "Banana", "Orange"]
        match = best_match("Zucchini", candidates, threshold=90)
        assert match is None

    def test_best_match_empty_candidates(self):
        """Test empty candidates list."""
        match = best_match("Apple", [])
        assert match is None

    def test_best_match_threshold(self):
        """Test threshold parameter."""
        candidates = ["Apple Pie"]
        # "Apple" is somewhat similar to "Apple Pie"
        # With low threshold it should match
        match_low = best_match("Apple", candidates, threshold=10)
        assert match_low is not None
        
        # With very high threshold it should not match
        match_high = best_match("Apple", candidates, threshold=99)
        assert match_high is None


# ====================
# Tests for utils/ai_utils.py
# ====================

class TestAIUtils:
    @patch('producepricer.utils.ai_utils.openai_client')
    def test_get_ai_response_success(self, mock_openai):
        """Test successful AI response."""
        # Mock the response structure
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response content"
        mock_openai.chat.completions.create.return_value = mock_response
        
        result = get_ai_response(prompt="Test prompt")
        
        assert result["success"] is True
        assert result["content"] == "Test response content"
        
        # Verify OpenAI was called with correct parameters
        mock_openai.chat.completions.create.assert_called_once()
        call_args = mock_openai.chat.completions.create.call_args[1]
        assert call_args["messages"][1]["content"] == "Test prompt"

    @patch('producepricer.utils.ai_utils.openai_client')
    def test_get_ai_response_json_format(self, mock_openai):
        """Test AI response with JSON format."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"key": "value"}'
        mock_openai.chat.completions.create.return_value = mock_response
        
        result = get_ai_response(
            prompt="Test JSON", 
            response_format={"type": "json_object"}
        )
        
        assert result["success"] is True
        assert result["content"] == '{"key": "value"}'
        assert "response_format" in mock_openai.chat.completions.create.call_args[1]

    @patch('producepricer.utils.ai_utils.openai_client')
    def test_get_ai_response_invalid_json(self, mock_openai):
        """Test AI response with invalid JSON when JSON is expected."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = 'Invalid JSON'
        mock_openai.chat.completions.create.return_value = mock_response
        
        result = get_ai_response(
            prompt="Test JSON", 
            response_format={"type": "json_object"}
        )
        
        assert result["success"] is False
        assert "OpenAI returned invalid JSON" in result["error"]

    @patch('producepricer.utils.ai_utils.openai_client')
    def test_get_ai_response_api_error(self, mock_openai):
        """Test handling of OpenAI API errors."""
        mock_openai.chat.completions.create.side_effect = Exception("API Error")
        
        result = get_ai_response(prompt="Test prompt")
        
        assert result["success"] is False
        assert "API Error" in result["error"]

    @patch('producepricer.utils.ai_utils.openai_client')
    def test_get_ai_response_truncation(self, mock_openai):
        """Test truncation of long messages."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"
        mock_openai.chat.completions.create.return_value = mock_response
        
        # Create a very long prompt
        long_prompt = "a" * 20000
        get_ai_response(prompt=long_prompt)
        
        call_args = mock_openai.chat.completions.create.call_args[1]
        sent_content = call_args["messages"][1]["content"]
        
        # Should be truncated (4000 * 4 = 16000 chars max)
        assert len(sent_content) < 20000
        assert "[Content truncated]" in sent_content


# ====================
# Tests for utils/parsing.py
# ====================

class TestParsing:
    @patch('producepricer.utils.parsing.get_ai_response')
    def test_parse_price_list_success(self, mock_get_ai):
        """Test successful parsing of price list."""
        mock_data = {
            "vendor": "Test Vendor",
            "effective_date": "2023-01-01",
            "items": [
                {"name": "Item 1", "price_usd": 10.0},
                {"name": "Item 2", "price_usd": 20.0}
            ]
        }
        mock_get_ai.return_value = {
            "success": True,
            "content": json.dumps(mock_data)
        }
        
        result = parse_price_list_with_openai("Some PDF text")
        
        assert result["vendor"] == "Test Vendor"
        assert len(result["items"]) == 2
        assert result["items"][0]["name"] == "Item 1"

    @patch('producepricer.utils.parsing.get_ai_response')
    def test_parse_price_list_truncation_retry(self, mock_get_ai):
        """Test retry logic when first attempt fails due to truncation."""
        # First call fails with truncation error
        # Second call succeeds
        mock_get_ai.side_effect = [
            {"success": False, "error": "Context length exceeded (truncated)"},
            {"success": True, "content": '{"items": []}'}
        ]
        
        parse_price_list_with_openai("Very long text " * 1000)
        
        assert mock_get_ai.call_count == 2

    @patch('producepricer.utils.parsing.get_ai_response')
    def test_parse_price_list_json_repair(self, mock_get_ai):
        """Test repairing of malformed/truncated JSON."""
        # JSON is cut off
        malformed_json = '{"items": [{"name": "Item 1", "price_usd": 10.0}, {"name": "Item 2", "pri'
        
        mock_get_ai.return_value = {
            "success": True,
            "content": malformed_json
        }
        
        # Capture stdout to verify repair message
        with patch('builtins.print') as mock_print:
            result = parse_price_list_with_openai("Some text")
            
            # Should recover at least the first item
            assert len(result.get("items", [])) == 1
            assert result["items"][0]["name"] == "Item 1"

    def test_coerce_iso_date(self):
        """Test date coercion."""
        # YYYY-MM-DD
        d1 = coerce_iso_date("2023-12-25")
        assert d1 == date(2023, 12, 25)
        
        # MM/DD/YYYY
        d2 = coerce_iso_date("12/25/2023")
        assert d2 == date(2023, 12, 25)
        
        # Invalid/None returns today
        d3 = coerce_iso_date(None)
        assert d3 == datetime.now().date()
        
        d4 = coerce_iso_date("Not a date")
        assert d4 == datetime.now().date()
