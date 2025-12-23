---
applyTo: "**/*.py"
---

# Performance Review Guidelines for Python

Review Python code for performance issues. Flag HIGH severity issues that should block merge.

## Async Anti-Patterns (HIGH)

- Never call blocking I/O in async functions
- Use `asyncio.to_thread()` for unavoidable blocking calls
- Prefer async libraries (httpx async, not requests)

```python
# BAD - blocking call in async context
async def fetch():
    response = requests.get(url)  # BLOCKS event loop!
    return response.json()

# GOOD - async HTTP client
async def fetch():
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

## N+1 Request Patterns (HIGH)

- Batch API requests where possible
- Use `asyncio.gather()` for concurrent requests
- Avoid loops that make sequential HTTP calls

```python
# BAD - N+1 requests
for movie_id in movie_ids:
    result = await client.get(f"/movie/{movie_id}")
    results.append(result)

# GOOD - concurrent requests
tasks = [client.get(f"/movie/{id}") for id in movie_ids]
results = await asyncio.gather(*tasks)
```

## HTTP Client Management (MEDIUM)

- Reuse httpx clients for connection pooling
- Don't create new clients per request
- Use context managers for proper cleanup

```python
# BAD - new client per request
async def fetch(url):
    async with httpx.AsyncClient() as client:
        return await client.get(url)

# GOOD - reused client
class APIClient:
    def __init__(self):
        self._client = httpx.AsyncClient()

    async def fetch(self, url):
        return await self._client.get(url)
```

## Memory Efficiency (MEDIUM)

- Stream large responses instead of loading into memory
- Use generators for large data processing
- Avoid unnecessary data copies

```python
# BAD - loads entire response into memory
data = response.json()  # Could be huge

# GOOD - stream processing for large responses
async for chunk in response.aiter_bytes():
    process(chunk)
```

## Algorithm Efficiency (MEDIUM)

- Use appropriate data structures (set for lookups, dict for key access)
- Avoid O(n^2) patterns in loops
- Use list comprehensions over explicit loops when clearer

```python
# BAD - O(n) lookup in list
if item in large_list:  # Linear scan

# GOOD - O(1) lookup in set
if item in large_set:  # Constant time
```

## Pydantic Efficiency (LOW)

- Use `model_validate()` not deprecated `parse_obj()`
- Consider `model_construct()` for trusted internal data
- Avoid repeated validation of the same data
