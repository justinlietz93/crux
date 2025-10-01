# Ollama Provider: Known Issues & Troubleshooting

**Version:** 1.0  
**Last Updated:** 2025-01-01  
**Status:** Active Investigation

---

## Overview

This document details known issues with the Ollama provider implementation and provides comprehensive troubleshooting guidance. The Ollama provider fetches locally installed models via the `ollama list` CLI command and interacts with the local Ollama HTTP API.

---

## Known Issue #1: Model Fetching Reliability

### Symptom

- `ollama list --json` may fail or return unexpected formats
- Model fetching returns empty list despite models being installed
- Inconsistent parsing results between JSON and table output modes

### Root Causes Identified

#### 1. JSON Output Format Variations

The `ollama list --json` command output format may vary between Ollama versions:

**Expected format (modern versions):**

```json
{
  "models": [
    {
      "name": "llama3.2:latest",
      "model": "llama3.2",
      "size": "4.1 GB",
      "digest": "sha256:abc123...",
      "modified_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

**Observed variations:**

- Array at root: `[{...}, {...}]` (missing `models` wrapper)
- Different key names: `model` vs `name` vs `id`
- Missing fields in some versions

#### 2. Table Output Parsing Complexity

The human-readable table format has spacing variations:

```
NAME              ID                           SIZE      MODIFIED     
llama3.2:latest   sha256:abc123               4.1 GB    2 weeks ago
```

Challenges:

- Variable column spacing (2+ spaces between columns)
- Column values may contain single spaces ("2 weeks ago")
- Header line may be missing in some versions
- Column order variations

#### 3. Executable Validation Issues

The security validation of the `ollama` executable may fail:

**Validation checks:**

1. Basename must be exactly "ollama"
2. Must be a regular file
3. Must be user-executable
4. Must NOT be group/other writable (security requirement)

**Failure modes:**

- Executable not in PATH
- Incorrect permissions (too permissive)
- Symlink resolution issues
- Windows vs Unix path differences

### Current Implementation

**File:** `crux_providers/ollama/get_ollama_models.py`

**Strategy:**

1. Try JSON output first (`ollama list --json`)
2. Parse JSON with flexible key extraction
3. On JSON failure, fall back to table parsing
4. On CLI failure, return cached models from SQLite

**Code flow:**

```python
def run() -> List[Dict[str, Any]]:
    try:
        if items := _fetch_via_cli():
            save_provider_models(PROVIDER, items, ...)
            return items
    except Exception as e:
        log error
    
    # Fallback to cached
    snap = load_cached_models(PROVIDER)
    return [m.to_dict() for m in snap.models]

def _fetch_via_cli() -> List[Dict[str, Any]]:
    try:
        return _fetch_ollama_models_json(timeout)
    except Exception:
        log warning
    
    # Fallback to table parsing
    output = _invoke_ollama_list(json_output=False, timeout)
    return _parse_ollama_list_table(output)
```

### Testing & Validation

**Unit Tests:**

- `crux_providers/tests/providers/test_ollama_parsing.py`
- Tests table parsing with/without headers
- Tests variable spacing handling

**Run tests:**

```bash
python -m pytest crux_providers/tests/providers/test_ollama_parsing.py -v
```

**Expected results:**

- `test_parse_with_header_multiple_spaces`: PASS
- `test_parse_without_header_assumes_first_column_name`: PASS

---

## Known Issue #2: Executable Not Found

### Symptom

```
FileNotFoundError: 'ollama' executable not found on PATH
```

### Diagnosis Steps

1. **Check if Ollama is installed:**

```bash
which ollama
# Should return: /usr/local/bin/ollama (or similar)
```

2. **Check Ollama version:**

```bash
ollama --version
# Should return version info
```

3. **Check PATH environment:**

```bash
echo $PATH
# Should include directory containing ollama
```

4. **Test direct execution:**

```bash
/usr/local/bin/ollama list
# Should work if ollama is properly installed
```

### Solutions

#### Solution 1: Install Ollama

Visit <https://ollama.com/download>

**Linux:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Mac:**

```bash
brew install ollama
```

**Windows:**
Download installer from <https://ollama.com/download>

#### Solution 2: Add to PATH

If installed but not in PATH:

**Linux/Mac:**

```bash
export PATH="/usr/local/bin:$PATH"
# Add to ~/.bashrc or ~/.zshrc for persistence
```

**Windows:**
Add Ollama installation directory to System PATH environment variable.

#### Solution 3: Verify Installation

```bash
# After installation/PATH fix
which ollama
ollama --version
ollama list
```

---

## Known Issue #3: Service Not Running

### Symptom

- `ollama list` returns connection errors
- HTTP requests to `http://127.0.0.1:11434` fail
- Models fetch successfully via CLI but HTTP API fails

### Diagnosis

1. **Check if service is running:**

```bash
curl http://127.0.0.1:11434/api/tags
```

Expected: JSON response with models list
If fails: Service is not running

2. **Check process:**

```bash
ps aux | grep ollama
```

### Solutions

#### Solution 1: Start Ollama Service

**Option A: Manual start**

```bash
ollama serve
```

Keep this terminal open, service runs in foreground.

**Option B: Background (Linux/Mac)**

```bash
nohup ollama serve > /dev/null 2>&1 &
```

**Option C: System service (recommended for production)**

**Linux (systemd):**

```bash
sudo systemctl start ollama
sudo systemctl enable ollama  # Auto-start on boot
```

**Mac (launchd):**

```bash
brew services start ollama
```

#### Solution 2: Change Port (if conflict)

If port 11434 is already in use:

```bash
export OLLAMA_HOST=http://127.0.0.1:8080
ollama serve --port 8080
```

Update environment in `.env`:

```bash
OLLAMA_HOST=http://127.0.0.1:8080
```

---

## Known Issue #4: Permission Errors

### Symptom

```
RuntimeError: ollama executable has insecure write permissions (group/other writable)
```

### Diagnosis

```bash
ls -la $(which ollama)
# Example output:
# -rwxrwxrwx 1 user group 12345 Jan 01 00:00 /usr/local/bin/ollama
#          ^ These bits should NOT be set
```

### Explanation

The security validation checks that the executable is NOT writable by group or others (the `0o022` bits). This prevents tampering by unprivileged users.

### Solution

Fix permissions:

```bash
chmod 755 $(which ollama)
# Results in: -rwxr-xr-x (owner: rwx, group: rx, other: rx)
```

Verify:

```bash
ls -la $(which ollama)
# Should show: -rwxr-xr-x
```

---

## Known Issue #5: No Models Available

### Symptom

- `ollama list` returns empty list
- Model fetching returns 0 models
- Service is running but no models installed

### Diagnosis

```bash
ollama list
# Output: empty or only headers
```

### Solution

Pull some models:

```bash
# Small model for testing (~4GB)
ollama pull llama3.2

# Medium models
ollama pull llama3.1:8b
ollama pull qwen2.5:7b

# Tiny model for quick testing (~1GB)
ollama pull tinyllama

# Verify
ollama list
```

Test with Crux Providers:

```bash
python -c "from crux_providers.ollama.get_ollama_models import run; models = run(); print(f'{len(models)} models found')"
```

---

## Diagnostic Commands

Use these commands to gather information when reporting issues:

```bash
# System info
echo "OS: $(uname -s)"
echo "Python: $(python --version)"

# Ollama installation
echo "Ollama path: $(which ollama)"
echo "Ollama version: $(ollama --version 2>&1)"
echo "Ollama permissions: $(ls -la $(which ollama) 2>&1)"

# Service status
echo "Service check: $(curl -s http://127.0.0.1:11434/api/tags | head -c 100)"

# Models available
echo "Models (CLI): $(ollama list 2>&1)"
echo "Models (JSON): $(ollama list --json 2>&1 | head -c 200)"

# Crux Providers test
python -c "
from crux_providers.ollama.get_ollama_models import run
try:
    models = run()
    print(f'Crux test: SUCCESS - {len(models)} models')
except Exception as e:
    print(f'Crux test: FAILED - {e}')
"
```

---

## Advanced Troubleshooting

### Debug Mode

Enable debug logging to see detailed execution:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from crux_providers.ollama.get_ollama_models import run
models = run()
```

### Manual Testing

Test each component individually:

```python
# 1. Test executable resolution
from crux_providers.ollama.get_ollama_models import _resolve_ollama_executable
try:
    path = _resolve_ollama_executable()
    print(f"✓ Executable found: {path}")
except Exception as e:
    print(f"✗ Resolution failed: {e}")

# 2. Test JSON fetching
from crux_providers.ollama.get_ollama_models import _fetch_ollama_models_json
from crux_providers.base.timeouts import get_timeout_config
try:
    cfg = get_timeout_config()
    models = _fetch_ollama_models_json(int(cfg.start_timeout_seconds))
    print(f"✓ JSON fetch: {len(models)} models")
except Exception as e:
    print(f"✗ JSON fetch failed: {e}")

# 3. Test table parsing
from crux_providers.ollama.get_ollama_models import _invoke_ollama_list, _parse_ollama_list_table
try:
    output = _invoke_ollama_list(json_output=False, timeout=30)
    models = _parse_ollama_list_table(output)
    print(f"✓ Table parse: {len(models)} models")
    print(f"Sample: {models[0] if models else 'none'}")
except Exception as e:
    print(f"✗ Table parse failed: {e}")

# 4. Test HTTP API
import httpx
try:
    response = httpx.get("http://127.0.0.1:11434/api/tags", timeout=10)
    data = response.json()
    print(f"✓ HTTP API: {len(data.get('models', []))} models")
except Exception as e:
    print(f"✗ HTTP API failed: {e}")
```

### Fallback Behavior Testing

Test that cached fallback works:

```python
from crux_providers.ollama.get_ollama_models import run
from crux_providers.base.get_models_base import save_provider_models

# 1. Seed cache with test data
test_models = [
    {"id": "test-model-1", "name": "Test Model 1"},
    {"id": "test-model-2", "name": "Test Model 2"}
]
save_provider_models("ollama", test_models, fetched_via="test", metadata={"source": "manual"})

# 2. Test fallback (will use cache if live fetch fails)
models = run()
print(f"Fallback test: {len(models)} models")
print(f"First model: {models[0] if models else 'none'}")
```

---

## Workarounds

### Workaround 1: Use HTTP API Directly

If CLI is problematic, use the HTTP API:

```python
import httpx

# Fetch models via HTTP
response = httpx.get("http://127.0.0.1:11434/api/tags")
data = response.json()
models = data.get("models", [])

# Convert to Crux format
crux_models = [
    {"id": m["name"], "name": m["name"]}
    for m in models
]

# Save to cache
from crux_providers.base.get_models_base import save_provider_models
save_provider_models("ollama", crux_models, fetched_via="http_api", metadata={"source": "workaround"})
```

### Workaround 2: Manual Model Registration

If fetching is broken, manually register models:

```python
from crux_providers.base.get_models_base import save_provider_models

# Define your installed models
my_models = [
    {"id": "llama3.2", "name": "llama3.2"},
    {"id": "llama3.1:8b", "name": "llama3.1:8b"},
    {"id": "qwen2.5:7b", "name": "qwen2.5:7b"}
]

# Save to registry
save_provider_models(
    "ollama",
    my_models,
    fetched_via="manual",
    metadata={"source": "manual_registration"}
)

# Verify
from crux_providers.base.get_models_base import load_cached_models
snapshot = load_cached_models("ollama")
print(f"Registered {len(snapshot.models)} models")
```

---

## Reporting Issues

When reporting Ollama-related issues, please include:

### Required Information

1. **Environment:**
   - OS and version
   - Python version
   - Ollama version (`ollama --version`)

2. **Diagnostic output:**

   ```bash
   # Run and include output
   bash -c "$(curl -fsSL https://raw.githubusercontent.com/justinlietz93/crux/main/scripts/diagnose_ollama.sh)"
   ```

3. **Error messages:**
   - Full stack trace
   - Any warnings in logs

4. **What you tried:**
   - List troubleshooting steps attempted
   - Include any workarounds

### GitHub Issue Template

```markdown
**Title:** Ollama: [Brief description]

**Environment:**
- OS: [e.g., Ubuntu 22.04]
- Python: [e.g., 3.11.5]
- Ollama: [e.g., 0.1.17]

**Issue:**
[Describe what's not working]

**Steps to reproduce:**
1. 
2. 
3. 

**Diagnostic output:**
```

[Paste output from diagnostic commands]

```

**Attempts:**
- [ ] Verified ollama installed and in PATH
- [ ] Checked service is running
- [ ] Tested with curl
- [ ] Ran unit tests
- [ ] [Other steps]

**Additional context:**
[Any other relevant information]
```

---

## Future Improvements

Planned enhancements to address these issues:

1. **Improved version detection**: Detect Ollama version and adjust parsing strategy
2. **Better error messages**: More specific guidance based on failure mode
3. **Automatic service start**: Optionally start ollama service if not running
4. **HTTP API fallback**: Prefer HTTP API over CLI to avoid parsing issues
5. **Configuration validation**: Pre-flight checks before attempting fetch
6. **Retry logic**: Automatic retries with exponential backoff for transient failures

Track progress in GitHub issues with label `provider:ollama`.

---

## Quick Reference

```bash
# Install
curl -fsSL https://ollama.com/install.sh | sh

# Start service
ollama serve

# Pull model
ollama pull llama3.2

# Test CLI
ollama list
ollama list --json

# Test HTTP
curl http://127.0.0.1:11434/api/tags

# Test Crux
python -c "from crux_providers.ollama.get_ollama_models import run; print(len(run()), 'models')"

# Run tests
python -m pytest crux_providers/tests/providers/test_ollama_parsing.py -v

# Fix permissions
chmod 755 $(which ollama)
```

---

**End of Document**
