# Refactor Plan & Technical Debt Roadmap

**Repository:** justinlietz93/crux  
**Commit:** 5f656cd2c1962d2bde2dcfa17252b1821885c998  
**Generated:** 2025-12-05

---

## Executive Summary

The Crux Providers codebase demonstrates **exceptional architectural discipline** with a 4.4/5.0 quality score. This refactor plan addresses identified technical debt while preserving the strong architectural foundation.

**Overall Assessment:** System is **production-ready** with targeted improvements for scale and security.

---

## Quick Wins (1-2 Days)

### QW1: Pin Provider SDK Versions
**Priority:** CRITICAL  
**Effort:** 2 hours  
**Impact:** HIGH (prevents breaking changes)

**Current State:**
```txt
# requirements.txt
openai
anthropic
google-generativeai
```

**Target State:**
```txt
# requirements.txt
openai==1.40.0
anthropic==0.31.1
google-generativeai==0.7.2
ollama==0.3.1
```

**Steps:**
1. Document current versions: `pip freeze | grep -E 'openai|anthropic|google'`
2. Pin all provider SDKs with `==` operator
3. Add CI check to prevent unpinned dependencies
4. Document version update process in CONTRIBUTING.md

**Owner:** DevOps / Platform Team  
**Risk:** Low  
**Dependencies:** None

---

### QW2: Decompose Gemini Client (507 LOC → <500 LOC)
**Priority:** MEDIUM  
**Effort:** 6 hours  
**Impact:** MEDIUM (improves maintainability)

**Current State:**
- Single file: `crux_providers/gemini/client.py` (507 LOC)
- Contains: chat, streaming, model listing, helpers

**Target State:**
```
crux_providers/gemini/
  ├── client.py (200 LOC) - main adapter
  ├── chat_helpers.py (150 LOC) - request/response normalization
  ├── stream_helpers.py (100 LOC) - streaming logic
  └── model_helpers.py (60 LOC) - model listing
```

**Steps:**
1. Extract `_transform_request()` → `chat_helpers.py`
2. Extract `_handle_stream()` → `stream_helpers.py`
3. Extract `_fetch_models()` → `model_helpers.py`
4. Update imports in `client.py`
5. Run tests: `pytest tests/providers/test_gemini_adapter.py`
6. Update allowlist in `test_policies_filesize.py`

**Owner:** Backend Team  
**Risk:** Low (high test coverage)  
**Dependencies:** None

---

### QW3: Decompose CLI Shell (576 LOC → <500 LOC)
**Priority:** MEDIUM  
**Effort:** 6 hours  
**Impact:** MEDIUM (improves maintainability)

**Current State:**
- Single file: `crux_providers/service/cli/cli_shell.py` (576 LOC)
- Contains: shell, commands, UI, history

**Target State:**
```
crux_providers/service/cli/
  ├── cli_shell.py (200 LOC) - shell core
  ├── cli_shell_commands.py (200 LOC) - command handlers
  ├── cli_shell_ui.py (100 LOC) - UI formatting
  └── cli_shell_history.py (80 LOC) - history management
```

**Steps:**
1. Extract command handlers → `cli_shell_commands.py`
2. Extract UI helpers → `cli_shell_ui.py`
3. Extract history logic → `cli_shell_history.py`
4. Update imports
5. Run smoke tests: `pytest crux_providers/tests/test_cli_smoke.py`
6. Update allowlist in `test_policies_filesize.py`

**Owner:** CLI Team  
**Risk:** Low  
**Dependencies:** None

---

### QW4: Validate Model Defaults Against Registry
**Priority:** LOW  
**Effort:** 4 hours  
**Impact:** LOW (prevents misconfiguration)

**Goal:** Ensure default models in `config/defaults.py` exist in provider model lists.

**Implementation:**
```python
# crux_providers/utils/validate_defaults.py
def validate_model_defaults():
    """Cross-check config defaults against cached model registry."""
    from crux_providers.config.defaults import (
        OPENAI_DEFAULT_MODEL,
        ANTHROPIC_DEFAULT_MODEL,
        # ...
    )
    from crux_providers.base.get_models_base import load_cached_models
    
    issues = []
    for provider, default_model in [("openai", OPENAI_DEFAULT_MODEL), ...]:
        models = load_cached_models(provider)
        if default_model not in [m["id"] for m in models]:
            issues.append(f"{provider}: {default_model} not in registry")
    
    return issues
```

**Steps:**
1. Create validation script
2. Add to CI as non-blocking warning
3. Schedule monthly manual review

**Owner:** DevOps  
**Risk:** Low  
**Dependencies:** None

---

## Medium-Term (1-2 Sprints)

### MT1: Encrypt API Key Vault
**Priority:** HIGH  
**Effort:** 2-3 days  
**Impact:** HIGH (security)

**Current State:**
- API keys stored in SQLite plaintext

**Target State:**
- Keys encrypted at rest using Fernet (cryptography library)

**Implementation:**
```python
from cryptography.fernet import Fernet
import os

class EncryptedKeyVault:
    def __init__(self):
        # Store encryption key in env (or external KMS)
        key = os.environ.get("KEY_VAULT_ENCRYPTION_KEY")
        if not key:
            key = Fernet.generate_key()
            print(f"Generated key: {key.decode()}")
        self.cipher = Fernet(key)
    
    def encrypt(self, value: str) -> bytes:
        return self.cipher.encrypt(value.encode())
    
    def decrypt(self, encrypted: bytes) -> str:
        return self.cipher.decrypt(encrypted).decode()
```

**Steps:**
1. Add `cryptography` dependency
2. Implement `EncryptedKeyVault` wrapper
3. Add migration to encrypt existing keys
4. Update `KeystoreRepository` to use encryption
5. Add tests for encryption/decryption
6. Document key management in SECURITY.md

**Owner:** Security Team  
**Risk:** Medium (requires migration)  
**Dependencies:** None

**Rollback Plan:**
- Decrypt all keys back to plaintext
- Remove encryption layer

---

### MT2: Add End-to-End Test Suite
**Priority:** MEDIUM  
**Effort:** 4-5 days  
**Impact:** HIGH (confidence in changes)

**Current State:**
- Unit tests: 90%+ coverage
- Integration tests: Streaming contracts
- E2E tests: <10% coverage

**Target State:**
- E2E coverage: 50%+ (critical flows)

**Test Scenarios:**
1. **Full Chat Flow**
   - Create adapter → chat → verify response → check log persistence
2. **Streaming Flow**
   - Create adapter → stream → iterate deltas → finalize → check metrics
3. **Error Recovery**
   - Invalid API key → verify error code
   - Timeout → verify retry → verify fallback
4. **Model Registry**
   - Refresh → verify cache invalidation → query → verify response
5. **Concurrent Access**
   - Parallel chat requests → verify SQLite WAL handling

**Implementation:**
```python
# tests/e2e/test_full_chat_flow.py
def test_full_chat_flow_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    
    adapter = create("openai")
    request = ChatRequest(messages=[Message(role=Role.USER, content="Hello")])
    response = adapter.chat(request)
    
    assert response.content
    assert response.metadata.provider == "openai"
    
    # Verify persistence
    logs = query_chat_logs(provider="openai")
    assert len(logs) >= 1
```

**Steps:**
1. Create `tests/e2e/` directory
2. Implement 5 core E2E scenarios
3. Add CI job for E2E tests (nightly or on-demand)
4. Mock external provider APIs (use VCR.py for recording)

**Owner:** QA / Test Engineering  
**Risk:** Low  
**Dependencies:** None

---

### MT3: Implement Async Write Queue for SQLite
**Priority:** MEDIUM  
**Effort:** 3-4 days  
**Impact:** MEDIUM (performance under load)

**Current State:**
- Synchronous writes to SQLite (blocks on lock)

**Target State:**
- Async write queue with background worker

**Implementation:**
```python
import asyncio
from queue import Queue
from threading import Thread

class AsyncWriteQueue:
    def __init__(self, db_path):
        self.queue = Queue()
        self.worker = Thread(target=self._process_queue, daemon=True)
        self.worker.start()
    
    def enqueue(self, sql, params):
        self.queue.put((sql, params))
    
    def _process_queue(self):
        while True:
            sql, params = self.queue.get()
            # Execute write in background
            execute_write(sql, params)
```

**Steps:**
1. Implement `AsyncWriteQueue` class
2. Update `ChatLogRepository` and `MetricsRepository` to use queue
3. Add graceful shutdown (drain queue on exit)
4. Add tests for queue behavior
5. Benchmark performance improvement

**Owner:** Backend Team  
**Risk:** Medium (requires testing under load)  
**Dependencies:** None

---

### MT4: Implement Concrete Metrics Exporters
**Priority:** MEDIUM  
**Effort:** 3 days  
**Impact:** MEDIUM (observability)

**Target Exporters:**
1. **Prometheus** (push gateway)
2. **StatsD** (for existing Datadog/Grafana)
3. **OpenTelemetry (OTLP)** (future-proof)

**Implementation:**
```python
# crux_providers/base/metrics/exporters/prometheus.py
from prometheus_client import Counter, Histogram, push_to_gateway

class PrometheusExporter(MetricsExporter):
    def __init__(self, gateway_url):
        self.gateway = gateway_url
        self.request_latency = Histogram("crux_request_latency_ms", "Request latency")
        self.request_count = Counter("crux_request_total", "Total requests")
    
    def export(self, metrics: StreamMetrics):
        self.request_latency.observe(metrics.total_duration_ms)
        self.request_count.inc()
        push_to_gateway(self.gateway, job="crux_providers")
```

**Steps:**
1. Implement Prometheus exporter
2. Implement StatsD exporter
3. Add configuration for exporter selection
4. Document setup in `12_operability.md`
5. Add example Grafana dashboards

**Owner:** SRE Team  
**Risk:** Low  
**Dependencies:** None

---

## Strategic (6+ Months)

### ST1: Migrate to PostgreSQL for Multi-Instance Support
**Priority:** LOW (when scale requires)  
**Effort:** 2-3 weeks  
**Impact:** HIGH (enables horizontal scaling)

**Trigger:** More than 3 API instances needed

**Current State:**
- SQLite (single-file, single-instance)

**Target State:**
- PostgreSQL (multi-instance, replication)

**Steps:**
1. Define PostgreSQL schema (migrate from SQLite DDL)
2. Implement PostgreSQL repository implementations
3. Add connection pooling (pgbouncer or SQLAlchemy)
4. Migration script from SQLite → PostgreSQL
5. Update configuration to support both backends
6. Load testing with PostgreSQL

**Owner:** Backend + DBA Team  
**Risk:** High (requires careful migration)  
**Dependencies:** Scaling requirements

---

### ST2: Implement Circuit Breaker Pattern
**Priority:** LOW  
**Effort:** 1 week  
**Impact:** MEDIUM (resilience)

**Implementation:**
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.failures = 0
        self.threshold = failure_threshold
        self.timeout = timeout
        self.last_failure = None
        self.state = "closed"
    
    def call(self, func, *args, **kwargs):
        if self.state == "open":
            if time.time() - self.last_failure > self.timeout:
                self.state = "half_open"
            else:
                raise CircuitBreakerOpenError()
        
        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise
```

**Steps:**
1. Implement circuit breaker for each provider
2. Add configuration (threshold, timeout)
3. Add metrics for circuit breaker state
4. Document behavior

**Owner:** Backend Team  
**Risk:** Medium  
**Dependencies:** None

---

### ST3: Add PII Redaction Filter
**Priority:** LOW (unless GDPR required)  
**Effort:** 1 week  
**Impact:** MEDIUM (compliance)

**Implementation:**
```python
import re

PII_PATTERNS = [
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),
    (r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]'),
    (r'\b\d{16}\b', '[CARD]'),
]

def redact_pii(text: str) -> str:
    for pattern, replacement in PII_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text
```

**Steps:**
1. Define PII patterns (email, SSN, credit card, phone)
2. Implement redaction filter
3. Add opt-in via `ENABLE_PII_REDACTION` flag
4. Apply to chat logs and structured logs
5. Add tests for PII detection

**Owner:** Compliance Team  
**Risk:** Low  
**Dependencies:** None

---

## Summary Timeline

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| **Quick Wins** | 1-2 days | SDK pinning, file decomposition, validation script |
| **Medium-Term** | 1-2 sprints | Key encryption, E2E tests, async writes, metrics exporters |
| **Strategic** | 6+ months | PostgreSQL migration, circuit breaker, PII redaction |

---

## Risk Mitigation

### High-Risk Items
1. **Key Vault Encryption** - Requires migration; test thoroughly
2. **PostgreSQL Migration** - Major infrastructure change; phased rollout

### Rollback Plans
- **Encryption:** Decrypt keys, revert to plaintext
- **Async Writes:** Drain queue, fall back to sync writes
- **PostgreSQL:** Keep SQLite as fallback for single-instance

---

## Success Metrics

| Metric | Baseline | Target (6 months) |
|--------|----------|-------------------|
| **Architecture Score** | 4.4 / 5.0 | 4.7 / 5.0 |
| **File Size Compliance** | 99% (2 violations) | 100% |
| **Test Coverage** | 85% | 90% |
| **Security Score** | 3.5 / 5.0 | 4.5 / 5.0 |
| **Mean Time to Resolve Issues** | N/A | <4 hours |

---

**Document Version:** 1.0  
**Last Updated:** 2025-12-05  
**Next Review:** 2026-01-15
