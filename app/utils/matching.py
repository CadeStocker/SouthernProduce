# Copyright Cade Stocker 2026
from typing import Optional, Tuple, List, Dict
from rapidfuzz import process, fuzz


def _combined_score(a: str, b: str, *args, **kwargs) -> float:
    """Compute a combined similarity score (0-100) using several fuzzy scorers.

    We weight token_set_ratio more heavily to tolerate reordering and
    tokenization differences, but include token_sort_ratio and partial_ratio
    for robustness.
    """
    s1 = fuzz.token_set_ratio(a, b)
    s2 = fuzz.token_sort_ratio(a, b)
    s3 = fuzz.partial_ratio(a, b)
    # Weighted average
    return (0.6 * s1) + (0.3 * s2) + (0.1 * s3)


GENERIC_TOKENS = set([
    'green', 'red', 'yellow', 'white', 'black', 'small', 'large', 'fresh',
    'lb', 'lbs', 'pound', 'pounds', 'case', 'bulk', 'bag', 'box', 'tray',
    'ct', 'count', 'each', 'package', 'pkg', 'sweet', 'select', 'jumbo', 'medium'
])


def normalize_name(s: str) -> str:
    """Lowercase and remove common punctuation for token comparisons."""
    if not s:
        return ''
    import re
    s = s.lower()
    s = s.replace('–', '-').replace('—', '-')
    s = re.sub(r'[\(\)\[\]\"]', '', s)
    s = re.sub(r'[^a-z0-9\-\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def token_set(s: str) -> List[str]:
    return [t for t in normalize_name(s).split() if t]


def _adjust_score_for_tokens(parsed: str, candidate: str, score: float) -> float:
    """Adjust raw fuzzy score based on token overlap and presence of specific tokens.

    Heuristics:
    - If parsed contains a specific token (not generic) that candidate lacks, penalize heavily.
    - If token overlap ratio is low, penalize.
    - If there's exact token match, give a small boost.
    """
    p_tokens = token_set(parsed)
    c_tokens = token_set(candidate)
    if not p_tokens or not c_tokens:
        return score

    p_set = set(p_tokens)
    c_set = set(c_tokens)

    # Count informative tokens (exclude generic tokens)
    p_informative = [t for t in p_tokens if t not in GENERIC_TOKENS]
    c_informative = [t for t in c_tokens if t not in GENERIC_TOKENS]

    # If parsed has an informative token the candidate doesn't, penalize
    for tok in p_informative:
        if tok not in c_set:
            # Penalize more for longer informative tokens
            score -= 25

    # Compute overlap ratio relative to parsed tokens
    overlap = len(p_set & c_set)
    overlap_ratio = overlap / max(1, len(p_set))
    if len(p_set) >= 2 and overlap_ratio < 0.4:
        # not enough token overlap
        score -= 20

    # Small boost for exact whole-token matches
    if any(tok in c_set for tok in p_informative):
        score += 5

    # Clamp
    if score < 0:
        score = 0
    if score > 100:
        score = 100

    return float(score)


def best_match(product_name: str, candidates: List[str], threshold: int = 55) -> Optional[Tuple[str, float]]:
    """
    Returns (best_name, score) if above threshold else None.

    Uses a combined scorer (token_set + token_sort + partial) to improve
    real-world matching for vendor price lists. Keeps the original
    function signature for backward compatibility.
    """
    if not candidates:
        return None

    # Use process.extractOne with our combined scorer
    hit = process.extractOne(
        product_name,
        candidates,
        scorer=_combined_score,
        score_cutoff=threshold
    )

    if hit:
        # hit is a tuple of (string, score, index)
        return (hit[0], float(hit[1]))

    return None


def top_n_matches(product_name: str, candidates: List[str], n: int = 5, min_score: int = 30) -> List[Tuple[str, float]]:
    """Return the top N candidate matches as (name, score), filtered by min_score."""
    if not candidates:
        return []
    # Get raw hits (allow more than n so adjustments can reorder)
    hits = process.extract(
        product_name,
        candidates,
        scorer=_combined_score,
        limit=min(len(candidates), max(n, 10))
    )

    adjusted = []
    for h in hits:
        name, raw_score = h[0], float(h[1])
        adj = _adjust_score_for_tokens(product_name, name, raw_score)
        adjusted.append((name, adj))

    # Sort by adjusted score desc and return top n above min_score
    adjusted.sort(key=lambda x: x[1], reverse=True)
    return [(name, score) for (name, score) in adjusted[:n] if score >= min_score]


def match_parsed_items(parsed_items: List[Dict], candidates: List[str], threshold: int = 60, suggestion_count: int = 3) -> Dict[str, List]:
    """
    Given parsed items from a PDF (list of dicts with keys 'name' and 'price_usd'),
    return a dict with:
      - matched: items with a confident match (>= threshold)
      - ambiguous: items with several candidates near threshold
      - unmatched: items with no good match and suggestions for quick entry

    This helps the frontend present both confident matches and a compact
    quick-entry list for manual price application.
    """
    matched = []
    ambiguous = []
    unmatched = []

    for it in parsed_items:
        name = (it.get("name") or "").strip()
        price = it.get("price_usd")
        if not name or price is None:
            unmatched.append({"name_from_pdf": name, "price_from_pdf": price, "reason": "missing_name_or_price"})
            continue

        top = top_n_matches(name, candidates, n=suggestion_count, min_score=0)
        if not top:
            unmatched.append({"name_from_pdf": name, "price_from_pdf": price, "suggestions": []})
            continue

        best_name, best_score = top[0]

        if best_score >= threshold:
            matched.append({
                "name_from_pdf": name,
                "price_from_pdf": price,
                "matched_product_name": best_name,
                "match_score": best_score
            })
            # Also include near-ties as ambiguous if second-best is close
            if len(top) > 1 and top[1][1] >= (threshold - 5):
                ambiguous.append({
                    "name_from_pdf": name,
                    "price_from_pdf": price,
                    "suggestions": top
                })
        else:
            # No confident match — return suggestions for manual entry UI
            unmatched.append({
                "name_from_pdf": name,
                "price_from_pdf": price,
                "suggestions": top
            })

    return {"matched": matched, "ambiguous": ambiguous, "unmatched": unmatched}


def build_quick_entry_list(unmatched: List[Dict]) -> List[Dict]:
    """
    Convert unmatched items to a compact quick-entry list suitable for
    pasting into a simple UI or CSV; each entry contains the parsed name
    and the price so the user can rapidly confirm or edit values.
    """
    quick = []
    for u in unmatched:
        quick.append({
            "name_from_pdf": u.get("name_from_pdf") or u.get("name") or "",
            "price_from_pdf": u.get("price_from_pdf")
        })
    return quick
