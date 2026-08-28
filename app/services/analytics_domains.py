# Copyright Cade Stocker 2026

"""Registry of the business domains the analytics layer covers.

This is the single place that knows what "the whole app" means to analytics.
The dashboard renders one section per domain, the anomaly detector tags every
anomaly it records with a domain key, and the data-health panel uses
``fact_types`` to report which domains actually have data flowing.

To add a domain later:

1. Append an entry here.
2. Write the AnalyticsFact writer(s) in ``analytics_facts`` (if the domain has
   its own fact type) and the read queries in ``analytics_reports``.
3. Add a detector class to ``scripts/anomaly_detector.py`` and register it in
   ``DETECTORS`` with ``domain`` set to the new key.
4. Add a panel to ``templates/dashboard.html`` keyed on the same string.

Nothing outside this file hardcodes the list, so steps 2-4 are independent and
a domain can ship read-only (reports, no detector) or detect-only (detector, no
panel) while it is being built out.
"""


DOMAINS = (
    {
        'key': 'sales',
        'label': 'Sales & Customers',
        'blurb': 'Revenue, volume, and customer concentration.',
        'icon': 'bi-cash-coin',
        'fact_types': ('item_sale', 'customer_order'),
    },
    {
        'key': 'pricing',
        'label': 'Pricing & Margin',
        'blurb': 'List prices vs. landed cost, margin erosion, price spread across customers.',
        'icon': 'bi-tags',
        'fact_types': ('cost_margin',),
    },
    {
        'key': 'efficiency',
        'label': 'Labor & Efficiency',
        'blurb': 'Man-hours per case, payroll per case, labor as a share of sales.',
        'icon': 'bi-speedometer2',
        'fact_types': ('labor',),
    },
    {
        'key': 'receiving',
        'label': 'Receiving & Suppliers',
        'blurb': 'Inbound spend, cost per unit by raw product, supplier concentration.',
        'icon': 'bi-truck',
        'fact_types': ('receiving',),
    },
    {
        'key': 'inventory',
        'label': 'Inventory',
        'blurb': 'On-hand levels, count-to-count movement, stale counts.',
        'icon': 'bi-box-seam',
        'fact_types': ('inventory_snapshot',),
    },
)

DOMAIN_KEYS = tuple(domain['key'] for domain in DOMAINS)

DOMAINS_BY_KEY = {domain['key']: domain for domain in DOMAINS}


def fact_types_for_domain(domain_key):
    """Fact types backing a domain, or an empty tuple for an unknown key."""
    domain = DOMAINS_BY_KEY.get(domain_key)
    return domain['fact_types'] if domain else ()


def domain_for_fact_type(fact_type):
    """Reverse lookup: which domain owns a given AnalyticsFact type."""
    for domain in DOMAINS:
        if fact_type in domain['fact_types']:
            return domain['key']
    return None


def label_for_domain(domain_key):
    """Human-readable label, falling back to the raw key for unknown domains."""
    domain = DOMAINS_BY_KEY.get(domain_key)
    return domain['label'] if domain else (domain_key or 'Other')
