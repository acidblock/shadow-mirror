# Instrumentation Patterns for Shadow Mirror

## Instrumentation Philosophy

Every operation in a system casts a shadow—the observable trace of its execution. Instrumentation is the art of positioning lights to reveal these shadows at the right granularity. Too few lights and failures hide in darkness; too many and you burn energy illuminating the obvious.

## eBPF Probes

eBPF provides kernel-level observation without modifying application code—the deepest shadows.

### Syscall Tracing

```python
# bpftrace one-liner for connection tracking
# Tracks all connect() syscalls to observe connection pool behavior
bpftrace -e '
tracepoint:syscalls:sys_enter_connect {
    printf("%s pid=%d connecting\n", comm, pid);
}
tracepoint:syscalls:sys_exit_connect {
    printf("%s pid=%d connect returned %d\n", comm, pid, args->ret);
}
'
```

```python
# shadow_ebpf.py - Python wrapper for eBPF instrumentation
from bcc import BPF

PROBE_CODE = """
#include <uapi/linux/ptrace.h>
#include <net/sock.h>

BPF_HASH(connection_times, u32, u64);

int trace_connect_entry(struct pt_regs *ctx) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 ts = bpf_ktime_get_ns();
    connection_times.update(&pid, &ts);
    return 0;
}

int trace_connect_return(struct pt_regs *ctx) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 *start_ts = connection_times.lookup(&pid);
    if (start_ts) {
        u64 delta = bpf_ktime_get_ns() - *start_ts;
        bpf_trace_printk("connect_latency_ns=%llu pid=%u\\n", delta, pid);
        connection_times.delete(&pid);
    }
    return 0;
}
"""

def attach_connection_probes():
    """Attach eBPF probes for connection timing."""
    b = BPF(text=PROBE_CODE)
    b.attach_kprobe(event="tcp_v4_connect", fn_name="trace_connect_entry")
    b.attach_kretprobe(event="tcp_v4_connect", fn_name="trace_connect_return")
    return b
```

### File I/O Observation

```bash
# Track all file operations for a specific process
bpftrace -e '
tracepoint:syscalls:sys_enter_openat /pid == $1/ {
    printf("open: %s\n", str(args->filename));
}
tracepoint:syscalls:sys_enter_read /pid == $1/ {
    printf("read: fd=%d size=%d\n", args->fd, args->count);
}
tracepoint:syscalls:sys_enter_write /pid == $1/ {
    printf("write: fd=%d size=%d\n", args->fd, args->count);
}
' -p $(pgrep your-app)
```

## Cilium Observability

Cilium + Hubble provides network-layer visibility in Kubernetes—shadows cast by service mesh traffic.

### Hubble Flow Observation

```bash
# Observe all traffic to a specific service
hubble observe --to-service default/api-server --json > shadow-flows.json

# Filter by HTTP status for error investigation
hubble observe --http-status 500 --json

# Watch connection states for pool exhaustion hypothesis
hubble observe --protocol TCP --json | jq 'select(.flow.verdict == "DROPPED")'
```

### Hubble Metrics for Shadow Evidence

```yaml
# cilium-hubble-metrics.yaml
apiVersion: cilium.io/v2
kind: CiliumClusterwideNetworkPolicy
metadata:
  name: shadow-mirror-metrics
spec:
  hubbleMetrics:
    enabled:
      - dns
      - drop
      - tcp
      - flow
      - http
    portDistribution:
      enabled: true
```

```python
# Query Hubble metrics for shadow evidence
import requests

def collect_hubble_evidence(service: str, duration: str = "5m"):
    """Collect network evidence from Hubble metrics."""
    queries = {
        "request_rate": f'sum(rate(hubble_flows_processed_total{{destination="{service}"}}[{duration}]))',
        "error_rate": f'sum(rate(hubble_drop_total{{destination="{service}"}}[{duration}]))',
        "latency_p99": f'histogram_quantile(0.99, sum(rate(hubble_http_request_duration_seconds_bucket{{destination="{service}"}}[{duration}])) by (le))',
    }
    
    evidence = {}
    for name, query in queries.items():
        resp = requests.get(f"http://prometheus:9090/api/v1/query", params={"query": query})
        evidence[name] = resp.json()["data"]["result"]
    
    return evidence
```

### Network Policy Validation

```python
# Test that network policies are correctly enforced
def test_network_policy_enforcement(shadow_node):
    """Validate network policy blocks unauthorized traffic."""
    shadow_node["node"] = "security.network_policy.enforcement"
    shadow_node["level"] = "functional"
    
    # Attempt blocked connection
    result = kubectl_exec("curl -s -o /dev/null -w '%{http_code}' http://internal-service")
    
    # Should be blocked by policy
    assert result == "000" or "connection refused" in result.lower()
    
    # Verify in Hubble that drop was recorded
    drops = hubble_query("--to-service internal-service --verdict DROPPED --last 1m")
    assert len(drops) > 0
    
    shadow_node["evidence"] = {"drops_recorded": len(drops)}
```

## OpenTelemetry Integration

OTel provides application-level tracing—shadows cast by your code's execution path.

### Trace Context for Distributed Assertions

```python
# shadow_otel.py - OpenTelemetry instrumentation for shadow mirror
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from functools import wraps

# Setup
provider = TracerProvider()
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://otel-collector:4317"))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("shadow-mirror")

def shadow_span(node: str, level: str = "functional"):
    """Decorator to create shadow-instrumented spans."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(func.__name__) as span:
                span.set_attribute("shadow.node", node)
                span.set_attribute("shadow.level", level)
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("shadow.outcome", "passed")
                    return result
                except Exception as e:
                    span.set_attribute("shadow.outcome", "failed")
                    span.set_attribute("shadow.error", str(e))
                    raise
        return wrapper
    return decorator

# Usage
@shadow_span("auth.login.validate", level="functional")
def validate_credentials(username: str, password: str) -> bool:
    # Implementation
    pass
```

### Collecting Trace Evidence

```python
# Query traces for shadow evidence
from opentelemetry.sdk.trace.export import SpanExportResult
import json

class ShadowExporter:
    """Export spans to shadow evidence files."""
    
    def __init__(self, output_dir: str = "shadow-report/traces"):
        self.output_dir = output_dir
        self.spans = []
    
    def export(self, spans):
        for span in spans:
            self.spans.append({
                "name": span.name,
                "node": span.attributes.get("shadow.node"),
                "level": span.attributes.get("shadow.level"),
                "outcome": span.attributes.get("shadow.outcome"),
                "duration_ns": span.end_time - span.start_time,
                "trace_id": format(span.context.trace_id, "032x"),
                "span_id": format(span.context.span_id, "016x"),
            })
        return SpanExportResult.SUCCESS
    
    def to_evidence(self):
        with open(f"{self.output_dir}/spans.json", "w") as f:
            json.dump(self.spans, f, indent=2)
```

### Cross-Service Hypothesis Testing

```python
# Test distributed behavior across services
@pytest.mark.shadow("behavioral")
@pytest.mark.node("distributed.order_flow")
async def test_order_creates_invoice(shadow_node, otel_collector):
    """Validate order service triggers invoice creation."""
    
    # Create order
    order_resp = await client.post("/orders", json={"items": [...]})
    order_id = order_resp.json()["id"]
    
    # Wait for async processing
    await asyncio.sleep(2)
    
    # Query traces for the full flow
    traces = otel_collector.query_traces(
        service="order-service",
        operation="create_order",
        tags={"order_id": order_id},
    )
    
    # Assert the expected span sequence
    span_names = [s["name"] for s in traces[0]["spans"]]
    assert "create_order" in span_names
    assert "publish_order_created" in span_names
    assert "create_invoice" in span_names  # From invoice-service
    
    shadow_node["evidence"] = {
        "trace_id": traces[0]["trace_id"],
        "span_count": len(traces[0]["spans"]),
        "services_touched": list(set(s["service"] for s in traces[0]["spans"])),
    }
```

## Sidecar Patterns

### Telemetry Sidecar Deployment

```yaml
# shadow-sidecar.yaml - Inject telemetry collection sidecar
apiVersion: v1
kind: Pod
metadata:
  name: app-with-shadow
  annotations:
    shadow-mirror/inject: "true"
spec:
  containers:
  - name: app
    image: your-app:latest
  - name: shadow-collector
    image: shadow-mirror/collector:latest
    env:
    - name: SHADOW_NODE_PREFIX
      value: "app.operations"
    - name: SHADOW_OUTPUT
      value: "/shadows"
    volumeMounts:
    - name: shadow-volume
      mountPath: /shadows
  volumes:
  - name: shadow-volume
    emptyDir: {}
```

### Envoy Sidecar for HTTP Observation

```yaml
# envoy-shadow-config.yaml
static_resources:
  listeners:
  - name: shadow_listener
    address:
      socket_address:
        address: 0.0.0.0
        port_value: 8080
    filter_chains:
    - filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: shadow_http
          access_log:
          - name: envoy.access_loggers.file
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.access_loggers.file.v3.FileAccessLog
              path: "/shadows/access.log"
              log_format:
                json_format:
                  timestamp: "%START_TIME%"
                  method: "%REQ(:METHOD)%"
                  path: "%REQ(:PATH)%"
                  status: "%RESPONSE_CODE%"
                  duration_ms: "%DURATION%"
                  upstream_time_ms: "%RESP(X-ENVOY-UPSTREAM-SERVICE-TIME)%"
```

## Resource Instrumentation

### Connection Pool Monitoring

```python
# Monitor connection pool for exhaustion hypothesis
import psycopg2.pool
from prometheus_client import Gauge, Histogram

pool_size = Gauge('db_pool_size', 'Current pool size')
pool_available = Gauge('db_pool_available', 'Available connections')
connection_wait = Histogram('db_connection_wait_seconds', 'Time waiting for connection')

class InstrumentedPool(psycopg2.pool.ThreadedConnectionPool):
    """Connection pool with shadow instrumentation."""
    
    def getconn(self, key=None):
        with connection_wait.time():
            conn = super().getconn(key)
        pool_available.set(len(self._pool))
        return conn
    
    def putconn(self, conn, key=None, close=False):
        super().putconn(conn, key, close)
        pool_available.set(len(self._pool))
```

### Memory/CPU at Operation Nodes

```python
import resource
import time
from contextlib import contextmanager

@contextmanager
def resource_shadow(node: str, collector: list):
    """Collect resource usage for a code block."""
    start_time = time.perf_counter()
    start_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    
    yield
    
    end_time = time.perf_counter()
    end_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    
    collector.append({
        "node": node,
        "duration_s": end_time - start_time,
        "memory_delta_kb": end_mem - start_mem,
        "timestamp": time.time(),
    })

# Usage
evidence = []
with resource_shadow("heavy.computation", evidence):
    result = expensive_operation()
```
