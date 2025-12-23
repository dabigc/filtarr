---
applyTo: "**/*.py"
---

# Security Review Guidelines for Python

Review all Python code for security vulnerabilities. Flag HIGH severity issues that should block merge.

## Secrets & Credentials (HIGH)

- Flag hardcoded API keys, passwords, tokens, or secrets
- Ensure credentials come from environment variables or secure config
- Check for accidental logging of sensitive data

```python
# BAD - hardcoded secret
api_key = "sk-1234567890abcdef"

# GOOD - from environment
api_key = os.environ.get("API_KEY")
```

## Input Validation (HIGH)

- Validate all external input (API responses, user input, file contents)
- Use Pydantic models for API response validation
- Never trust data from external sources without validation

```python
# BAD - trusting external data
data = response.json()
movie_id = data["id"]  # Could be anything

# GOOD - validated with Pydantic
movie = Movie.model_validate(response.json())
movie_id = movie.id  # Guaranteed to be int
```

## Command Injection (HIGH)

- Never use `shell=True` with subprocess
- Never interpolate user input into shell commands
- Use parameterized commands

```python
# BAD - command injection risk
subprocess.run(f"curl {user_url}", shell=True)

# GOOD - parameterized
subprocess.run(["curl", user_url], shell=False)
```

## URL/Path Injection (MEDIUM)

- Validate URLs before making requests
- Prevent path traversal in file operations
- Use allowlists for external hosts when possible

## HTTP Security (MEDIUM)

- Verify SSL certificates (don't disable verification)
- Set appropriate timeouts on all HTTP requests
- Handle redirects carefully

```python
# BAD - disabled SSL verification
httpx.get(url, verify=False)

# GOOD - SSL verified (default)
httpx.get(url, timeout=30.0)
```

## Error Handling (LOW)

- Don't expose internal details in error messages
- Log errors appropriately without leaking secrets
- Use specific exception types

## Dependencies

- Flag use of deprecated or known-vulnerable patterns
- Ensure async code doesn't block event loop with sync calls
