# Security Test Suite

This directory contains comprehensive security tests for the application, covering both API endpoints and web routes.

## Test Files

### `test_api_security.py`
Comprehensive security tests for REST API endpoints.

**Test Classes:**

1. **TestAPIAuthentication** - Authentication and authorization
   - Rejects unauthenticated requests
   - Rejects invalid API keys
   - Accepts valid API keys
   - Rejects revoked API keys
   - Tests alternative authentication methods
   - Validates /api/test endpoint security

2. **TestAPICompanyIsolation** - Multi-tenant data isolation
   - GET endpoints return only own company data
   - Cannot create resources with other company's foreign keys
   - Verifies receiving logs, raw products, and other resources are isolated

3. **TestAPIInputValidation** - Input validation and sanitization
   - SQL injection prevention
   - XSS attack prevention
   - Negative value rejection
   - Missing field rejection
   - Invalid foreign key rejection
   - Extremely large value handling

4. **TestAPIRateLimiting** - DOS prevention
   - Multiple rapid requests handled gracefully
   - Rate limiting (if implemented)

5. **TestAPIContentTypeHandling** - Request format validation
   - Malformed JSON rejection
   - Wrong content-type handling
   - Empty request body handling

6. **TestAPIMethodSecurity** - HTTP method restrictions
   - DELETE not allowed on GET-only endpoints
   - PUT not allowed where not implemented
   - Method validation

### `test_web_security.py`
Security tests for web routes and browser-facing functionality.

**Test Classes:**

1. **TestWebAuthentication** - Login requirements
   - Home page requires login
   - Items page requires login
   - Raw products page requires login
   - Receiving logs page requires login
   - Company page requires login

2. **TestWebCompanyIsolation** - Multi-tenant web security
   - Cannot view other company's receiving logs (404)
   - Cannot edit other company's receiving logs
   - Cannot view other company's raw products
   - Cannot delete other company's resources

3. **TestWebInputValidation** - Form input security
   - XSS prevention in forms
   - SQL injection prevention in search
   - Input sanitization and escaping

4. **TestWebCSRFProtection** - CSRF attack prevention
   - DELETE operations require valid tokens
   - State-changing operations protected

5. **TestWebAdminAccess** - Role-based access control
   - Regular users cannot approve pending users
   - Admin-only functions properly restricted
   - Company management access control

6. **TestWebFileUploadSecurity** - File upload safety
   - Malicious filenames sanitized
   - Path traversal prevention
   - File type validation

7. **TestWebSessionSecurity** - Session management
   - Sessions invalidated after logout
   - Concurrent session handling
   - Session hijacking prevention

## Running the Security Tests

### Run All Security Tests
```bash
cd /Users/cadestocker/LocalProjects/SouthernProduce/ProducePricer
python -m pytest tests/security/ -v
```

### Run Only API Security Tests
```bash
python -m pytest tests/security/test_api_security.py -v
```

### Run Only Web Security Tests
```bash
python -m pytest tests/security/test_web_security.py -v
```

### Run Specific Test Class
```bash
python -m pytest tests/security/test_api_security.py::TestAPIAuthentication -v
```

### Run with Coverage
```bash
python -m pytest tests/security/ --cov=producepricer --cov-report=html
```

## Security Coverage

### ✅ What These Tests Cover

1. **Authentication & Authorization**
   - API key validation
   - Login requirements
   - Session management
   - Token validation

2. **Multi-Tenant Isolation**
   - Company data separation
   - Cross-company access prevention
   - Foreign key validation
   - Resource ownership verification

3. **Input Validation**
   - SQL injection prevention
   - XSS attack prevention
   - Type validation
   - Range validation
   - Required field validation

4. **Request Security**
   - HTTP method restrictions
   - Content-type validation
   - Malformed request handling
   - Rate limiting (basic)

5. **File Security**
   - Filename sanitization
   - Path traversal prevention
   - Upload validation

6. **Session Security**
   - Logout invalidation
   - Concurrent sessions
   - Session expiration

### ⚠️ Security Recommendations

Based on these tests, consider implementing:

1. **Rate Limiting**
   - Add Flask-Limiter for API endpoint rate limiting
   - Prevent DOS attacks with request throttling
   - Example: 100 requests per hour per API key

2. **CSRF Protection**
   - Enable Flask-WTF CSRF protection on all forms
   - Validate CSRF tokens on state-changing operations
   - Already partially implemented via Flask-WTF

3. **Content Security Policy (CSP)**
   - Add CSP headers to prevent XSS
   - Use Flask-Talisman for security headers
   - Restrict inline scripts

4. **HTTPS Enforcement**
   - Redirect all HTTP to HTTPS in production
   - Set secure cookie flags
   - Use HSTS headers

5. **API Key Security**
   - Rotate API keys periodically
   - Store API keys hashed (like passwords)
   - Add key expiration dates
   - Log API key usage for audit trails

6. **Password Policy**
   - Enforce minimum password length (8+ chars)
   - Require complexity (uppercase, lowercase, numbers, symbols)
   - Implement password change policies
   - Add password strength meter

7. **Audit Logging**
   - Log all authentication attempts
   - Log all data modifications
   - Log access to sensitive data
   - Track API key usage

8. **Additional Input Validation**
   - Validate file uploads more strictly
   - Add file size limits
   - Scan uploads for malware
   - Validate image formats

## Common Vulnerabilities Tested

### OWASP Top 10 Coverage

1. **A01:2021 - Broken Access Control** ✅
   - Multi-tenant isolation tests
   - Authorization checks
   - Direct object reference prevention

2. **A02:2021 - Cryptographic Failures** ⚠️
   - API key validation (partial)
   - Recommend: Hash API keys, enforce HTTPS

3. **A03:2021 - Injection** ✅
   - SQL injection prevention tests
   - XSS prevention tests
   - Input validation

4. **A04:2021 - Insecure Design** ⚠️
   - Authentication architecture tested
   - Recommend: Add threat modeling

5. **A05:2021 - Security Misconfiguration** ⚠️
   - Basic configuration tested
   - Recommend: Security headers, CSP

6. **A06:2021 - Vulnerable Components** ⚠️
   - Recommend: Regular dependency updates
   - Use `pip-audit` to scan for vulnerabilities

7. **A07:2021 - Authentication Failures** ✅
   - Login requirements tested
   - Session management tested
   - API key authentication tested

8. **A08:2021 - Software and Data Integrity** ⚠️
   - Recommend: Add integrity checks for uploads

9. **A09:2021 - Logging Failures** ⚠️
   - Recommend: Implement comprehensive logging

10. **A10:2021 - Server-Side Request Forgery** ✅
    - Not applicable to current architecture

## Test Isolation

All tests use fixtures with `autouse=True` to ensure:
- Clean database state before each test
- Proper cleanup after each test
- No interference between tests
- Tests can run in parallel

## Continuous Security Testing

### Pre-Commit Checks
```bash
# Run security tests before committing
python -m pytest tests/security/ --tb=short
```

### CI/CD Integration
Add to your CI/CD pipeline:
```yaml
# Example GitHub Actions
- name: Run Security Tests
  run: |
    pytest tests/security/ -v --tb=short
    pytest tests/security/ --cov=producepricer --cov-fail-under=80
```

### Security Scanning Tools

Complement these tests with:

1. **Bandit** - Python code security scanner
   ```bash
   pip install bandit
   bandit -r producepricer/
   ```

2. **Safety** - Check dependencies for vulnerabilities
   ```bash
   pip install safety
   safety check
   ```

3. **pip-audit** - Audit Python dependencies
   ```bash
   pip install pip-audit
   pip-audit
   ```

## Reporting Security Issues

If you discover a security vulnerability:

1. **DO NOT** open a public GitHub issue
2. Email security concerns to: [admin email]
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Security Checklist for New Features

When adding new features, verify:

- [ ] Requires authentication (login or API key)
- [ ] Validates company_id for multi-tenant isolation
- [ ] Validates all user inputs
- [ ] Escapes output to prevent XSS
- [ ] Uses parameterized queries (no SQL injection)
- [ ] Validates file uploads
- [ ] Has appropriate error handling
- [ ] Logs security-relevant events
- [ ] Has security tests
- [ ] Follows principle of least privilege

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Flask Security Best Practices](https://flask.palletsprojects.com/en/2.3.x/security/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)
- [API Security Checklist](https://github.com/shieldfy/API-Security-Checklist)
