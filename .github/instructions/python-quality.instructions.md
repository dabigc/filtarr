---
applyTo: "**/*.py"
---

# Code Quality Review Guidelines for Python

Review Python code for code smells and quality issues. Flag HIGH severity issues that should block merge.

## Type Annotations (HIGH)

- All public functions must have complete type annotations
- Use modern syntax: `list[str]` not `List[str]`
- Use `X | None` not `Optional[X]`

```python
# BAD - missing or outdated types
def process(items):
    return [x for x in items]

# GOOD - complete modern annotations
def process(items: list[str]) -> list[str]:
    return [x for x in items]
```

## Exception Handling (HIGH)

- Never use bare `except:` clauses
- Catch specific exceptions
- Include context in raised exceptions

```python
# BAD - catches everything including KeyboardInterrupt
try:
    do_something()
except:
    pass

# GOOD - specific exception
try:
    do_something()
except ValueError as e:
    logger.error("Invalid value: %s", e)
    raise
```

## Dead Code (MEDIUM)

- Flag unused imports
- Flag unused variables (especially `_` prefixed that are used)
- Flag unreachable code after return/raise
- Flag commented-out code blocks

## Code Duplication (MEDIUM)

- Flag repeated code blocks that should be extracted
- Suggest helper functions for common patterns
- Identify copy-paste code with minor variations

## Pydantic Patterns (MEDIUM)

- Use Pydantic v2 API, not v1 deprecated methods
- `model_validate()` not `parse_obj()`
- `model_dump()` not `dict()`
- Use `ConfigDict` not inner `Config` class

```python
# BAD - Pydantic v1 patterns
class Movie(BaseModel):
    class Config:
        orm_mode = True

movie = Movie.parse_obj(data)
d = movie.dict()

# GOOD - Pydantic v2 patterns
class Movie(BaseModel):
    model_config = ConfigDict(from_attributes=True)

movie = Movie.model_validate(data)
d = movie.model_dump()
```

## Naming Conventions (LOW)

- `snake_case` for functions, methods, variables
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- Descriptive names over abbreviations

## Complexity (LOW)

- Flag functions longer than 50 lines
- Flag deeply nested code (>4 levels)
- Suggest extraction of complex conditionals

## Testing Patterns (LOW)

- Test functions should be named `test_*`
- Use descriptive test names explaining the scenario
- Avoid test interdependence
- Mock external dependencies appropriately

## httpx Patterns

- Use async client for async code
- Always set timeouts
- Use `raise_for_status()` for error handling

## Project-Specific: filtarr

- 4K detection should check both quality name AND title
- API responses must be validated with Pydantic models
- All clients should support configurable timeouts
- Use `respx` for HTTP mocking in tests, not `responses`
