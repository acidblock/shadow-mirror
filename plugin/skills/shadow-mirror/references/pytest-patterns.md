# pytest Patterns for Shadow Mirror

## Fixture Patterns

```python
# conftest.py - Shadow mirror instrumentation fixtures

import pytest
import json
from datetime import datetime
from pathlib import Path

@pytest.fixture(scope="session")
def shadow_session():
    """Session-wide evidence collection."""
    session = {
        "started": datetime.utcnow().isoformat(),
        "hypothesis": None,
        "assertions": [],
        "traces": [],
    }
    yield session
    session["completed"] = datetime.utcnow().isoformat()
    Path("shadow-report").mkdir(exist_ok=True)
    with open("shadow-report/assertions.json", "w") as f:
        json.dump(session, f, indent=2)

@pytest.fixture
def shadow_node(request, shadow_session):
    """Track which operation tree node this test covers."""
    node_path = request.node.get_closest_marker("node")
    level = request.node.get_closest_marker("shadow")
    
    record = {
        "test": request.node.name,
        "node": node_path.args[0] if node_path else "unspecified",
        "level": level.args[0] if level else "functional",
        "outcome": None,
        "timing": {"start": datetime.utcnow().isoformat()},
    }
    yield record
    record["timing"]["end"] = datetime.utcnow().isoformat()
    shadow_session["assertions"].append(record)

@pytest.fixture
def trace_collector():
    """Collect trace data during test execution."""
    traces = []
    def collect(name: str, data: dict):
        traces.append({"name": name, "data": data, "ts": datetime.utcnow().isoformat()})
    yield collect
    return traces
```

## Marker Patterns

```python
# Register custom markers in conftest.py
def pytest_configure(config):
    config.addinivalue_line("markers", "shadow(level): validation depth level")
    config.addinivalue_line("markers", "node(path): operation tree node path")
    config.addinivalue_line("markers", "hypothesis(claim): hypothesis being tested")

# Usage in tests
@pytest.mark.shadow("functional")
@pytest.mark.node("auth.login.validate_credentials")
@pytest.mark.hypothesis("Login fails due to credential validation timeout")
def test_credential_validation_returns_within_threshold(shadow_node):
    # Test implementation
    pass

@pytest.mark.shadow("resilient")
@pytest.mark.node("auth.login.session_create")
def test_session_creation_handles_concurrent_requests(shadow_node):
    # Chaos testing for race conditions
    pass
```

## Async Patterns

```python
import pytest
import asyncio

@pytest.mark.asyncio
@pytest.mark.shadow("behavioral")
@pytest.mark.node("api.endpoint.concurrent")
async def test_concurrent_request_ordering(shadow_node, trace_collector):
    """Validate behavioral correctness under concurrency."""
    results = []
    
    async def make_request(i):
        trace_collector(f"request.{i}.start", {"index": i})
        # actual request logic
        await asyncio.sleep(0.01)
        trace_collector(f"request.{i}.end", {"index": i})
        return i
    
    tasks = [make_request(i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    
    # Assertions accumulate evidence
    assert len(results) == 10
    shadow_node["outcome"] = "passed"

@pytest.fixture
async def async_shadow_context():
    """Async context manager for instrumented operations."""
    async with aiohttp.ClientSession() as session:
        yield session
```

## Parametrized Hypothesis Testing

```python
@pytest.mark.parametrize("boundary_input,expected_behavior", [
    ({"concurrent": 1}, "passes"),
    ({"concurrent": 5}, "passes"),
    ({"concurrent": 10}, "passes"),
    ({"concurrent": 11}, "fails"),  # Boundary condition
    ({"concurrent": 50}, "fails"),
])
@pytest.mark.shadow("functional")
@pytest.mark.node("pool.exhaustion")
def test_connection_pool_boundary(boundary_input, expected_behavior, shadow_node):
    """Parametrized boundary testing from hypothesis."""
    result = simulate_load(boundary_input["concurrent"])
    
    if expected_behavior == "passes":
        assert result.success
    else:
        assert not result.success or result.degraded
    
    shadow_node["boundary_input"] = boundary_input
    shadow_node["outcome"] = "passed"
```

## Evidence Collection Hook

```python
# conftest.py - Hook for collecting assertion outcomes
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    
    if report.when == "call":
        # Attach shadow metadata to report
        shadow_marker = item.get_closest_marker("shadow")
        node_marker = item.get_closest_marker("node")
        
        report.shadow_level = shadow_marker.args[0] if shadow_marker else None
        report.shadow_node = node_marker.args[0] if node_marker else None
```

## Required Plugins

```ini
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
addopts = """
    -v
    --tb=short
    --json-report
    --json-report-file=shadow.json
    --timeout=30
"""
markers = [
    "shadow(level): functional, behavioral, performant, or resilient",
    "node(path): operation tree path",
    "hypothesis(claim): hypothesis under test",
]

# Dependencies
# pytest
# pytest-asyncio
# pytest-json-report
# pytest-timeout
# pytest-xdist (for parallel execution)
```
