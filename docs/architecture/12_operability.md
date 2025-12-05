# Operability & Production Readiness

**Repository:** justinlietz93/crux  
**Commit:** 5f656cd2c1962d2bde2dcfa17252b1821885c998  
**Generated:** 2025-12-05

---

## Logging

### Configuration

```python
# Default: JSON formatter to stdout
import logging
from crux_providers.base.log_support.json_formatter import JSONFormatter

logger = logging.getLogger("crux_providers")
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

### Log Structure

```json
{
  "timestamp": "2025-12-05T17:12:30.486Z",
  "level": "INFO",
  "logger": "crux_providers.openai",
  "provider": "openai",
  "operation": "chat",
  "stage": "finalize",
  "model": "gpt-4",
  "latency_ms": 850,
  "tokens": {"prompt": 45, "completion": 120, "total": 165},
  "request_id": "req_abc123",
  "correlation_id": "corr_xyz789",
  "message": "Chat request completed successfully"
}
```

### Log Levels by Environment

| Environment | Level | Rationale |
|-------------|-------|-----------|
| **Development** | DEBUG | Full visibility |
| **Staging** | INFO | Request lifecycle + warnings |
| **Production** | INFO | Request lifecycle only |
| **Troubleshooting** | DEBUG | Temporary for debugging |

### Log Rotation

**Recommendation:** Use external log aggregation

- **Option 1:** Cloud logging (AWS CloudWatch, GCP Logging, Azure Monitor)
- **Option 2:** ELK Stack (Elasticsearch, Logstash, Kibana)
- **Option 3:** Splunk, Datadog, New Relic

**File Rotation (if needed):**
```python
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    "crux_providers.log",
    maxBytes=100 * 1024 * 1024,  # 100 MB
    backupCount=5
)
```

### Sensitive Data Handling

- **API Keys:** Automatically redacted in logs (replaced with `***`)
- **User Messages:** Logged in full (consider PII redaction filter)
- **Responses:** Logged in full (consider PII redaction filter)

**Recommendation:** Add opt-in PII redaction for GDPR compliance

---

## Metrics

### Metrics Capture

All metrics are captured internally via `StreamMetrics` and logged in structured format.

**Key Metrics:**
- `time_to_first_token_ms` - Streaming TTFT
- `total_duration_ms` - Full request latency
- `emitted_count` - Number of streaming deltas
- `prompt_tokens`, `completion_tokens`, `total_tokens`
- `retry_attempts` - Number of retries per request
- `fallback_used` - Boolean flag for cached model usage

### Metrics Export

**Status:** Feature-flagged (default: disabled)

**Activation:**
```bash
export PROVIDERS_METRICS_EXPORT=1
```

**Exporters (Pluggable):**
- Prometheus (recommended for production)
- StatsD (for existing infrastructure)
- OpenTelemetry (OTLP exporter)

**Implementation Needed:**
```python
# crux_providers/base/metrics/exporter.py
class PrometheusExporter(MetricsExporter):
    def export(self, metrics: StreamMetrics):
        # Emit to Prometheus push gateway or /metrics endpoint
        pass
```

### Recommended Dashboards

#### Provider Health Dashboard
- Request rate per provider
- Error rate per provider
- P50/P95/P99 latency per provider
- Retry rate per provider

#### Model Performance Dashboard
- TTFT distribution by model
- Token consumption by model
- Cost estimation (tokens * pricing)

#### System Health Dashboard
- SQLite write latency
- Cache hit rate
- Adapter creation time
- HTTP connection pool utilization

---

## Tracing

### Correlation IDs

**Usage:**
```python
from crux_providers import create
from crux_providers.base import ChatRequest

adapter = create("openai")
request = ChatRequest(
    messages=[...],
    extra={"correlation_id": "trace_abc123"}
)
response = adapter.chat(request)
```

**Propagation:**
- Correlation ID flows through all log statements
- Not currently propagated to provider APIs (future enhancement)

### Distributed Tracing (Future)

**Recommended:** OpenTelemetry integration

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Instrument crux_providers
tracer = trace.get_tracer("crux_providers")

with tracer.start_as_current_span("chat_request"):
    response = adapter.chat(request)
```

---

## Configuration Management

### Configuration Sources (Priority Order)

1. **Explicit Constructor Args** (highest priority)
2. **Environment Variables** (via `config.env`)
3. **Configuration Defaults** (via `config.defaults`)
4. **Key Vault Repository** (for API keys)

### Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-...` |
| `GEMINI_API_KEY` | Gemini API key | `AIza...` |
| `GOOGLE_API_KEY` | Alias for Gemini | `AIza...` |
| `OPENROUTER_API_KEY` | OpenRouter API key | `sk-or-...` |
| `DEEPSEEK_API_KEY` | Deepseek API key | `sk-...` |
| `XAI_API_KEY` | xAI API key | `xai-...` |
| `PROVIDERS_METRICS_EXPORT` | Enable metrics export | `1` or `true` |
| `SQLITE_DB_PATH` | SQLite database path | `/data/crux_providers.db` |

### Configuration Validation

- **On Startup:** Adapter validates API key format (basic check)
- **On First Request:** Provider validates key authenticity
- **Logging:** Invalid keys logged with `AUTH_ERROR` code

---

## Feature Flags

### Current Flags

| Flag | Environment Variable | Default | Purpose |
|------|---------------------|---------|---------|
| **Metrics Export** | `PROVIDERS_METRICS_EXPORT` | `0` | Enable external metrics emission |
| **Debug Logging** | `LOG_LEVEL` | `INFO` | Set log verbosity |

### Future Flags (Recommended)

- `ENABLE_PII_REDACTION` - Redact PII from logs
- `ENABLE_RESPONSE_CACHE` - Cache identical requests
- `ENABLE_CIRCUIT_BREAKER` - Enable circuit breaker pattern
- `ENABLE_RATE_LIMITING` - Enforce per-provider rate limits

---

## Health Checks

### API Health Endpoint (FastAPI)

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "0.1.0",
        "timestamp": datetime.now(UTC).isoformat()
    }
```

### Readiness Check

```python
@app.get("/ready")
async def readiness_check():
    # Check SQLite connectivity
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ready"}
    except Exception:
        return {"status": "not_ready"}, 503
```

### Liveness Check

```python
@app.get("/live")
async def liveness_check():
    return {"status": "alive"}
```

---

## Deployment

### Deployment Options

#### Option 1: Standalone Python Application
```bash
# Install package
pip install crux-providers[all]

# Run API server
python -m crux_providers.service.dev_server

# Run CLI
python -m crux_providers.service.cli
```

#### Option 2: Docker Container
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY crux_providers ./crux_providers
COPY pyproject.toml .

RUN pip install -e .

EXPOSE 8091
CMD ["python", "-m", "crux_providers.service.dev_server"]
```

#### Option 3: Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: crux-providers-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: crux-providers
  template:
    metadata:
      labels:
        app: crux-providers
    spec:
      containers:
      - name: api
        image: crux-providers:0.1.0
        ports:
        - containerPort: 8091
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: provider-keys
              key: openai
        livenessProbe:
          httpGet:
            path: /live
            port: 8091
        readinessProbe:
          httpGet:
            path: /ready
            port: 8091
```

### Persistence Considerations

- **SQLite:** Single-file database; suitable for single-instance deployments
- **Multi-Instance:** Migrate to PostgreSQL or shared database
- **Backups:** Implement hourly SQLite backups (e.g., `cp crux_providers.db backups/`)

---

## Monitoring & Alerting

### Recommended Alerts

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| **High Error Rate** | error_rate > 5% for 5m | HIGH | Page on-call |
| **Provider Timeout** | timeout_rate > 10% for 5m | MEDIUM | Check provider status |
| **SQLite Write Errors** | db_write_errors > 0 | CRITICAL | Check disk space |
| **Slow TTFT** | ttft_p95 > 2s for 10m | MEDIUM | Investigate provider perf |
| **Retry Storm** | retry_rate > 20% for 5m | HIGH | Check provider rate limits |
| **API Down** | health_check fails | CRITICAL | Restart service |

### Monitoring Stack Recommendations

#### Cloud-Native
- **AWS:** CloudWatch + X-Ray
- **GCP:** Cloud Logging + Cloud Trace
- **Azure:** Application Insights

#### Self-Hosted
- **Prometheus + Grafana** (metrics + dashboards)
- **ELK Stack** (logs + search)
- **Jaeger** (distributed tracing)

---

## Troubleshooting Guide

### Common Issues

#### Issue: Adapter initialization fails with "Invalid API key"

**Diagnosis:**
```bash
# Check environment variable
echo $OPENAI_API_KEY

# Verify key format
python -c "from crux_providers.config.env import is_placeholder; print(is_placeholder('$OPENAI_API_KEY'))"
```

**Resolution:**
- Ensure API key is set correctly in environment
- Check for typos or extra whitespace
- Verify key with provider's API dashboard

#### Issue: Timeouts on streaming requests

**Diagnosis:**
```bash
# Check timeout configuration
python -c "from crux_providers.base.timeouts import get_timeout_config; print(get_timeout_config())"

# Review logs for timeout stage
grep "stage.*timeout" /var/log/crux_providers.log
```

**Resolution:**
- Increase `start_timeout` (default: 30s)
- Check network connectivity to provider
- Verify provider status page

#### Issue: SQLite database locked

**Diagnosis:**
```bash
# Check for WAL mode
sqlite3 crux_providers.db "PRAGMA journal_mode;"

# Check for long-running transactions
lsof | grep crux_providers.db
```

**Resolution:**
- Ensure WAL mode is enabled (default)
- Close long-running connections
- Implement async write queue

---

## Runbooks

### Runbook: Provider API Key Rotation

1. Generate new API key from provider dashboard
2. Update environment variable or key vault
3. Restart service or reload config
4. Verify new key works with test request
5. Revoke old API key

### Runbook: Database Corruption Recovery

1. Stop all services writing to SQLite
2. Restore from latest backup
3. Verify database integrity: `sqlite3 crux_providers.db "PRAGMA integrity_check;"`
4. Re-run migrations if needed
5. Restart services

### Runbook: High Latency Investigation

1. Check provider status pages
2. Review logs for timeout patterns
3. Check network connectivity
4. Verify connection pool saturation
5. Increase timeout if needed

---

**Document Version:** 1.0  
**Last Updated:** 2025-12-05  
**Next Review:** 2026-03-01
