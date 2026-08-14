# Copyright Cade Stocker 2026
from app.utils.matching import match_parsed_items, build_quick_entry_list


def test_match_parsed_items_and_quick_entry():
    candidates = ["Peppers, Green", "Jalepeno"]

    parsed_items = [
        {"name": "Peppers, Green", "price_usd": 1.0},
        {"name": "Green Peppers Fancy", "price_usd": 2.0},
        {"name": "Unknown Item", "price_usd": 3.0},
    ]

    res = match_parsed_items(parsed_items, candidates, threshold=60, suggestion_count=3)

    # First item should be a confident match
    assert any(m.get("matched_product_name") == "Peppers, Green" for m in res.get("matched", []))

    # The 'Green Peppers Fancy' entry should appear in unmatched with suggestions
    unmatched_entry = next((u for u in res.get("unmatched", []) if u.get("name_from_pdf") == "Green Peppers Fancy"), None)
    assert unmatched_entry is not None
    # One of the suggestions should be 'Peppers, Green'
    assert any(s[0] == "Peppers, Green" for s in unmatched_entry.get("suggestions", []))

    # Quick entry list should include the unmatched entries
    quick = build_quick_entry_list(res.get("unmatched", []))
    assert any(q.get("name_from_pdf") == "Green Peppers Fancy" for q in quick)
