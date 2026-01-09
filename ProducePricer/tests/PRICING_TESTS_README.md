# Receiving Log Pricing Tests

This directory contains comprehensive tests for the receiving log pricing comparison feature.

## Test Files

### Unit Tests
- `test_receiving_log_pricing.py` - Tests for the ReceivingLog model methods:
  - `get_master_customer_price()` - Finding market cost from CostHistory
  - `get_price_comparison()` - Calculating price comparison metrics
  - Tests for various scenarios (below/above/at market, no data, company isolation)

### Functional Tests
- `test_receiving_log_pricing_routes.py` - Tests for web routes:
  - Viewing receiving logs with price comparison
  - Editing prices through the web interface
  - Modal display of market cost reference
  - Debug route functionality
  - Company data isolation

## Running the Tests

### Run All Pricing Tests
```bash
cd /Users/cadestocker/LocalProjects/SouthernProduce/ProducePricer
python -m pytest tests/unit/test_receiving_log_pricing.py tests/functional/test_receiving_log_pricing_routes.py -v
```

### Run Only Unit Tests
```bash
python -m pytest tests/unit/test_receiving_log_pricing.py -v
```

### Run Only Functional Tests
```bash
python -m pytest tests/functional/test_receiving_log_pricing_routes.py -v
```

### Run a Specific Test
```bash
python -m pytest tests/unit/test_receiving_log_pricing.py::TestReceivingLogPricing::test_get_price_comparison_below_market -v
```

### Run Tests with Coverage
```bash
python -m pytest tests/unit/test_receiving_log_pricing.py tests/functional/test_receiving_log_pricing_routes.py --cov=producepricer.models --cov=producepricer.routes --cov-report=html
```

## Test Isolation Features

All tests include proper cleanup to prevent issues when running multiple tests:

1. **Database Cleanup**: Each test class has a `setup` fixture with `autouse=True` that:
   - Creates fresh test data before each test
   - Deletes all test data after each test in proper dependency order
   - Uses `db.session.rollback()` to ensure clean state

2. **In-Memory Database**: Tests use SQLite in-memory database (`sqlite:///:memory:`) for speed and isolation

3. **No Side Effects**: Tests don't modify global state or leave data behind

4. **Company Isolation**: Tests verify that data from one company cannot be accessed by another

## Test Coverage

### Model Methods (Unit Tests)
✅ get_master_customer_price with recent cost
✅ get_master_customer_price with no cost history
✅ get_master_customer_price ignores old costs (>30 days)
✅ get_master_customer_price selects most recent
✅ get_price_comparison for below market prices
✅ get_price_comparison for above market prices
✅ get_price_comparison for at market prices
✅ get_price_comparison with no price entered
✅ get_price_comparison with no market data
✅ Company isolation (doesn't use other company's data)

### Web Routes (Functional Tests)
✅ View receiving log with price comparison
✅ View receiving log without price
✅ Modal shows market cost reference
✅ Edit receiving log price
✅ Price validation (rejects negative prices)
✅ Remove price (empty string handling)
✅ Debug route shows cost history
✅ Receiving logs table shows comparison badges
✅ Company isolation in routes (404 for other company's data)

## Key Testing Patterns

### 1. Fixture with Cleanup
```python
@pytest.fixture(autouse=True)
def setup(self, app):
    with app.app_context():
        # Create test data
        ...
    yield
    with app.app_context():
        # Delete in reverse dependency order
        ReceivingLog.query.delete()
        CostHistory.query.delete()
        ...
        db.session.commit()
```

### 2. Storing IDs for Reuse
```python
self.company_id = self.company.id  # Store ID before session closes
```

### 3. Re-fetching Objects
```python
log = db.session.get(ReceivingLog, log.id)  # Re-fetch to attach to session
```

### 4. Testing Dates
```python
cost_date = date.today() - timedelta(days=2)  # Use relative dates
```

## Troubleshooting

### Tests Fail with "Object is not bound to a Session"
- Make sure to re-fetch objects after committing: `log = db.session.get(ReceivingLog, log.id)`
- Store IDs and use them to fetch fresh instances in new contexts

### Tests Leave Behind Data
- Check cleanup fixture is using `autouse=True`
- Ensure deletes are in reverse dependency order
- Use `db.session.rollback()` at start of cleanup

### Import Errors
- Make sure you're running pytest from the ProducePricer directory
- Check that `__init__.py` exists in test directories

### Random Failures
- Tests should be isolated and not depend on execution order
- Each test should create its own data
- Use in-memory database to avoid file locking issues

## Adding New Tests

When adding new tests:

1. Follow the existing pattern with `setup` fixture
2. Always include cleanup in the fixture
3. Store IDs, not object references
4. Re-fetch objects when needed
5. Test both success and failure cases
6. Include company isolation tests
7. Use descriptive test names that explain what's being tested
