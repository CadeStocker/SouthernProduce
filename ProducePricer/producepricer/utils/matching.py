from typing import Optional, Tuple
from rapidfuzz import process, fuzz

def best_match(product_name: str, candidates: list[str], threshold: int = 55) -> Optional[Tuple[str, float]]:
    """
    Returns (best_name, score) if above threshold else None.
    Using token_sort_ratio to be resilient to commas/order.
    """
    if not candidates:
        return None
    
    # Use process.extractOne to find the best match
    hit = process.extractOne(
        product_name,
        candidates,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=threshold
    )
    
    if hit:
        # hit is a tuple of (string, score, index)
        return (hit[0], hit[1])
        
    return None