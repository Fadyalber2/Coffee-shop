# Sentinel's Journal

## 2025-05-15 - Initial Security Scan
**Vulnerability:** Hardcoded `SECRET_KEY` and Open Redirect in `login` route.
**Learning:** The application uses a hardcoded secret key for session management and does not validate the `next` parameter in the login redirect, making it vulnerable to session hijacking if the key is exposed and phishing via open redirects.
**Prevention:** Always use environment variables for secrets and validate redirect targets to be within the same domain.
