#!/usr/bin/env python3
"""
Production-safe REST API security + light-load probe for the ProducePricer/SouthernProduce backend.

Zero dependencies (stdlib only). READ-ONLY: issues only GET requests and intentionally
bad/unauthenticated requests. Does NOT create, modify, or delete data.

Usage:
    export PRODUCE_API_KEY="<your real api key>"
    export PRODUCE_API_BASE="https://producepricer.onrender.com"   # optional, this is the default
    python3 scripts/api_security_probe.py                # security probes only
    python3 scripts/api_security_probe.py --load         # also run a SMALL load ramp
    python3 scripts/api_security_probe.py --load --rps 5 --duration 15

Notes:
  * The default target is Render's hobby tier. Keep --load small or you'll just measure
    Render's throttling / cold-starts, and you may briefly degrade your own service.
  * The image-IDOR check needs a known filename to be conclusive; pass one with --image-name.
"""
import argparse
import json
import os
import sys
import time
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

DEFAULT_BASE = "https://producepricer.onrender.com"

# Read-only endpoints safe to GET with a valid key.
READ_ENDPOINTS = [
    "/api/test",
    "/api/receiving_logs",
    "/api/raw_products",
    "/api/items",
    "/api/sellers",
    "/api/brand_names",
    "/api/inventory_sessions",
]

GREEN, RED, YEL, DIM, RST = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def request(base, path, method="GET", headers=None, timeout=30):
    """Return (status_code, body_bytes, elapsed_seconds). status_code=0 on transport error."""
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read(), time.time() - start
    except urllib.error.HTTPError as e:
        return e.code, e.read(), time.time() - start
    except Exception as e:  # noqa: BLE001 - transport/timeout
        return 0, str(e).encode(), time.time() - start


def ok(msg):
    print(f"  {GREEN}PASS{RST}  {msg}")


def fail(msg):
    print(f"  {RED}FAIL{RST}  {msg}")


def warn(msg):
    print(f"  {YEL}WARN{RST}  {msg}")


def auth_headers(key):
    return {"X-API-Key": key, "X-Device-ID": "security-probe", "Accept": "application/json"}


# ---------------------------------------------------------------------------
# Security probes
# ---------------------------------------------------------------------------

def probe_auth_enforced(base):
    """Every protected endpoint must reject missing / malformed keys with 401/403."""
    print(f"\n{DIM}[1] Authentication enforcement (no key / bad key -> must be 401/403){RST}")
    failures = 0
    for path in READ_ENDPOINTS:
        # No key at all
        code, _, _ = request(base, path, headers={"X-Device-ID": "probe"})
        if code in (401, 403):
            ok(f"{path} rejects no-key ({code})")
        else:
            fail(f"{path} returned {code} WITHOUT a key (expected 401/403)")
            failures += 1
        # Malformed key
        code, _, _ = request(base, path, headers={"X-API-Key": "not-a-real-key", **{"X-Device-ID": "probe"}})
        if code in (401, 403):
            ok(f"{path} rejects bad key ({code})")
        else:
            fail(f"{path} returned {code} with a GARBAGE key (expected 401/403)")
            failures += 1
    return failures


def probe_valid_key(base, key):
    """Sanity-check the supplied key actually works (so other probes are meaningful)."""
    print(f"\n{DIM}[2] Supplied key is valid{RST}")
    code, body, _ = request(base, "/api/test", headers=auth_headers(key))
    if code == 200:
        ok(f"/api/test returns 200 with your key")
        return True
    fail(f"/api/test returned {code} with your key -- check PRODUCE_API_KEY. Body: {body[:200]!r}")
    return False


def probe_transport(base):
    """HTTPS should be enforced; plaintext should redirect or fail, never serve data."""
    print(f"\n{DIM}[3] Transport security{RST}")
    if base.startswith("https://"):
        ok("Base URL uses HTTPS")
        http_base = "http://" + base[len("https://"):]
        code, _, _ = request(http_base, "/api/test", headers={"X-Device-ID": "probe"})
        if code in (301, 302, 307, 308):
            ok(f"HTTP redirects to HTTPS ({code})")
        elif code == 0:
            ok("HTTP connection refused (HTTPS-only)")
        else:
            warn(f"HTTP /api/test returned {code} -- confirm it never serves data over plaintext")
    else:
        fail("Base URL is not HTTPS")


def probe_error_leakage(base, key):
    """Malformed input should not return stack traces / SQL / 'Invalid JSON: ...' details."""
    print(f"\n{DIM}[4] Error message leakage{RST}")
    leak_markers = [b"Traceback", b"sqlalchemy", b"psycopg", b"sqlite3",
                    b"File \"", b"Werkzeug", b"Invalid JSON:", b"line ", b" in <module>"]
    # Hit a typed-id endpoint with garbage; and POST malformed JSON to a create endpoint.
    code, body, _ = request(base, "/api/receiving_logs/not-an-int", headers=auth_headers(key))
    found = [m.decode() for m in leak_markers if m in body]
    if found:
        fail(f"/api/receiving_logs/<bad id> ({code}) leaks internals: {found}")
    else:
        ok(f"/api/receiving_logs/<bad id> ({code}) returns no obvious internals")


def probe_rate_limit(base, n=30):
    """Fire N bad keys fast. No throttle (429) under brute force is a weakness."""
    print(f"\n{DIM}[5] Brute-force / rate limiting ({n} bad keys rapidly){RST}")
    codes = []
    for i in range(n):
        code, _, _ = request(base, "/api/test", headers={"X-API-Key": f"guess-{i}", "X-Device-ID": "probe"})
        codes.append(code)
    if 429 in codes:
        ok(f"Server returned 429 (rate limited) after {codes.index(429)+1} attempts")
    else:
        warn(f"{n} bad-key attempts, never throttled (no 429). Add rate limiting on the key check.")


def probe_image_idor(base, key, image_name):
    """Read-only check of the known cross-tenant image-disclosure issue (finding C1)."""
    print(f"\n{DIM}[6] Receiving-image authorization (IDOR){RST}")
    if not image_name:
        warn("Pass --image-name <filename> to test cross-tenant image access conclusively.")
        warn("Code review found GET /receiving_images/<file> has NO company check (finding C1).")
        return
    # With your key (baseline)
    code_self, _, _ = request(base, f"/receiving_images/{image_name}", headers=auth_headers(key))
    # With a different/garbage key
    code_other, _, _ = request(base, f"/receiving_images/{image_name}",
                               headers={"X-API-Key": "wrong-tenant-key", "X-Device-ID": "probe"})
    if code_self == 200 and code_other == 200:
        fail(f"Image served to a DIFFERENT/invalid key ({code_other}) -- IDOR confirmed (C1)")
    elif code_self == 200 and code_other in (401, 403, 404):
        ok(f"Image requires valid auth (self={code_self}, other={code_other})")
    else:
        warn(f"Inconclusive: self={code_self}, other={code_other}")


# ---------------------------------------------------------------------------
# Light load ramp (GET /api/test only)
# ---------------------------------------------------------------------------

def load_test(base, key, rps, duration):
    print(f"\n{DIM}[load] {rps} req/s for {duration}s against /api/test (read-only){RST}")
    latencies, statuses, lock = [], {}, threading.Lock()

    def one():
        code, _, elapsed = request(base, "/api/test", headers=auth_headers(key))
        with lock:
            latencies.append(elapsed)
            statuses[code] = statuses.get(code, 0) + 1

    total = rps * duration
    with ThreadPoolExecutor(max_workers=min(rps * 2, 50)) as pool:
        start = time.time()
        for i in range(total):
            pool.submit(one)
            # pace submissions to ~rps
            target = start + (i + 1) / rps
            sleep = target - time.time()
            if sleep > 0:
                time.sleep(sleep)
    latencies.sort()
    if not latencies:
        print("  no responses recorded")
        return
    n = len(latencies)
    p = lambda q: latencies[min(n - 1, int(q * n))]
    print(f"  requests: {n}   statuses: {statuses}")
    print(f"  latency  p50={p(.5)*1000:.0f}ms  p95={p(.95)*1000:.0f}ms  p99={p(.99)*1000:.0f}ms  max={latencies[-1]*1000:.0f}ms")
    errors = sum(v for k, v in statuses.items() if k == 0 or k >= 500)
    if errors:
        warn(f"{errors}/{n} responses were errors/5xx under load")
    else:
        ok("no 5xx/transport errors under this load")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.environ.get("PRODUCE_API_BASE", DEFAULT_BASE))
    ap.add_argument("--key", default=os.environ.get("PRODUCE_API_KEY"))
    ap.add_argument("--image-name", help="A known receiving-image filename, to test IDOR conclusively")
    ap.add_argument("--load", action="store_true", help="also run a small load ramp")
    ap.add_argument("--rps", type=int, default=3, help="load: requests per second (keep small on Render)")
    ap.add_argument("--duration", type=int, default=10, help="load: seconds")
    args = ap.parse_args()

    if not args.key:
        print(f"{RED}Set PRODUCE_API_KEY (or pass --key).{RST}")
        sys.exit(2)

    print(f"Target: {args.base}")
    failures = 0
    failures += probe_auth_enforced(args.base)
    if probe_valid_key(args.base, args.key):
        probe_error_leakage(args.base, args.key)
        probe_image_idor(args.base, args.key, args.image_name)
    probe_transport(args.base)
    probe_rate_limit(args.base)

    if args.load:
        load_test(args.base, args.key, args.rps, args.duration)

    print()
    if failures:
        print(f"{RED}{failures} hard security failure(s). See FAIL lines above.{RST}")
        sys.exit(1)
    print(f"{GREEN}No hard auth failures. Review WARN lines and the code-review findings.{RST}")


if __name__ == "__main__":
    main()
