# Crux Providers: Beta Testing Checklist

**Version:** 1.0  
**Created:** 2025-01-01  
**Purpose:** Comprehensive testing guide for the Crux Providers agentic assistant system

---

## Executive Summary

This checklist provides a thorough, structured approach to beta testing the Crux Providers system. It covers installation, configuration, provider-specific testing, architecture compliance, and known issues.

### Known Issues to Verify
1. **Ollama Models Issue**: There is a confirmed issue with ollama model fetching that needs investigation
2. **Setup Confusion**: Clarification needed on proper repository setup and configuration

---

## Table of Contents

1. [Environment Setup](#1-environment-setup)
2. [Installation & Dependencies](#2-installation--dependencies)
3. [Configuration Validation](#3-configuration-validation)
4. [Provider Testing](#4-provider-testing)
5. [Ollama-Specific Testing](#5-ollama-specific-testing)
6. [Architecture Compliance](#6-architecture-compliance)
7. [Integration Testing](#7-integration-testing)
8. [Performance & Reliability](#8-performance--reliability)
9. [Security Validation](#9-security-validation)
10. [Documentation Review](#10-documentation-review)

---

## 1. Environment Setup

### 1.1 Python Environment
- [ ] Verify Python version >= 3.9
  ```bash
  python --version
  ```
- [ ] Create and activate virtual environment
  ```bash
  python -m venv .venv
  source .venv/bin/activate  # On Windows: .venv\Scripts\activate
  ```
- [ ] Verify virtual environment is active
  ```bash
  which python  # Should point to .venv/bin/python
  ```

### 1.2 System Requirements
- [ ] Check available disk space (>1GB recommended)
- [ ] Verify network connectivity for package installation
- [ ] Ensure write permissions in project directory

---

## 2. Installation & Dependencies

### 2.1 Core Installation
- [ ] Install core dependencies
  ```bash
  pip install -r requirements.txt
  ```
- [ ] Verify core imports
  ```bash
  python -c "from crux_providers.base import ProviderFactory; print('Core imports OK')"
  ```
- [ ] Check installed providers
  ```bash
  python -c "from crux_providers.base.factory import ProviderFactory; print('Supported:', ProviderFactory.supported())"
  ```
  Expected output: `('openai', 'anthropic', 'gemini', 'deepseek', 'openrouter', 'ollama', 'xai')`

### 2.2 Provider-Specific SDKs
- [ ] Install OpenAI SDK (if testing OpenAI)
  ```bash
  pip install openai
  ```
- [ ] Install Anthropic SDK (if testing Anthropic)
  ```bash
  pip install anthropic
  ```
- [ ] Install Google Generative AI SDK (if testing Gemini)
  ```bash
  pip install google-generativeai
  ```
- [ ] Install Ollama package (if testing Ollama)
  ```bash
  pip install ollama
  ```

### 2.3 Testing Dependencies
- [ ] Install pytest and coverage tools
  ```bash
  pip install pytest pytest-cov
  ```
- [ ] Install httpx for HTTP client support
  ```bash
  pip install httpx
  ```
- [ ] Install pydantic for data validation
  ```bash
  pip install "pydantic>=2.7,<3"
  ```

---

## 3. Configuration Validation

### 3.1 Environment Variables
- [ ] Copy example environment file
  ```bash
  cp .env.example .env
  ```
- [ ] Review environment variable mappings in `crux_providers/config/env.py`
  - Expected variables:
    - `OPENAI_API_KEY`
    - `ANTHROPIC_API_KEY`
    - `GEMINI_API_KEY` (or `GOOGLE_API_KEY`)
    - `DEEPSEEK_API_KEY`
    - `OPENROUTER_API_KEY`
    - `XAI_API_KEY`
    - `OLLAMA_HOST` (optional, defaults to `http://127.0.0.1:11434`)

### 3.2 Configuration Files
- [ ] Verify `crux_providers/config/defaults.py` exists
- [ ] Check default values:
  ```bash
  python -c "from crux_providers.config.defaults import OLLAMA_DEFAULT_HOST, OLLAMA_DEFAULT_MODEL; print(f'Host: {OLLAMA_DEFAULT_HOST}, Model: {OLLAMA_DEFAULT_MODEL}')"
  ```
- [ ] Validate centralized configuration loading
  ```bash
  python -c "from crux_providers.config.env import resolve_provider_key; print('Config module OK')"
  ```

### 3.3 API Key Resolution
- [ ] Test placeholder detection
  ```bash
  python -c "from crux_providers.config.env import is_placeholder; print('Placeholder check:', is_placeholder('PLACEHOLDER_KEY'))"
  ```
- [ ] Test provider key resolution (without real keys)
  ```bash
  python -c "from crux_providers.config.env import resolve_provider_key; key, var = resolve_provider_key('openai'); print(f'Resolved: {var}')"
  ```
- [ ] Test Gemini alias support (GEMINI_API_KEY vs GOOGLE_API_KEY)
  ```bash
  python -c "from crux_providers.config.env import get_env_var_candidates; print('Gemini vars:', list(get_env_var_candidates('gemini')))"
  ```

---

## 4. Provider Testing

### 4.1 Factory Pattern Testing
- [ ] Test provider creation for each supported provider
  ```bash
  python -c "from crux_providers.base.factory import ProviderFactory; p = ProviderFactory.create('ollama'); print(f'Created: {p.provider_name}')"
  ```
- [ ] Test unknown provider error handling
  ```bash
  python -c "from crux_providers.base.factory import ProviderFactory, UnknownProviderError; import sys; \
  try: ProviderFactory.create('invalid_provider'); sys.exit(1); \
  except UnknownProviderError: print('Error handling OK'); sys.exit(0)"
  ```
- [ ] Verify each provider implements required interfaces
  ```bash
  python -c "from crux_providers.base.factory import ProviderFactory; \
  from crux_providers.base.interfaces import LLMProvider; \
  p = ProviderFactory.create('openai'); \
  print('Interface check:', isinstance(p, LLMProvider))"
  ```

### 4.2 Model Registry Testing
- [ ] Test model listing for each provider (requires API keys or fallback)
  ```bash
  # OpenAI
  python -c "from crux_providers.openai.get_openai_models import run; models = run(); print(f'OpenAI: {len(models)} models')"
  
  # Anthropic
  python -c "from crux_providers.anthropic.get_anthropic_models import run; models = run(); print(f'Anthropic: {len(models)} models')"
  
  # Gemini
  python -c "from crux_providers.gemini.get_gemini_models import run; models = run(); print(f'Gemini: {len(models)} models')"
  ```

### 4.3 Provider Capabilities
- [ ] Test JSON output support detection
  ```bash
  python -c "from crux_providers.base.factory import ProviderFactory; \
  p = ProviderFactory.create('ollama'); \
  print('JSON support:', p.supports_json_output() if hasattr(p, 'supports_json_output') else 'N/A')"
  ```
- [ ] Test default model configuration
  ```bash
  python -c "from crux_providers.base.factory import ProviderFactory; \
  p = ProviderFactory.create('ollama', model='llama3.2'); \
  print('Default model:', p.default_model() if hasattr(p, 'default_model') else 'N/A')"
  ```

---

## 5. Ollama-Specific Testing

### 5.1 Ollama Installation Check
- [ ] Verify Ollama CLI is installed
  ```bash
  which ollama || echo "Ollama not installed - install from https://ollama.com"
  ```
- [ ] Check Ollama version
  ```bash
  ollama --version
  ```
- [ ] Verify Ollama service is running
  ```bash
  curl http://127.0.0.1:11434/api/tags || echo "Ollama service not running - run: ollama serve"
  ```

### 5.2 Ollama Model Listing (KNOWN ISSUE)
- [ ] **[CRITICAL]** Test JSON output mode
  ```bash
  ollama list --json
  ```
  - **Expected**: JSON array with model entries
  - **Issue**: May fail or produce incorrect format
  
- [ ] Test table output mode
  ```bash
  ollama list
  ```
  - **Expected**: Human-readable table with NAME, ID, SIZE, MODIFIED columns
  
- [ ] Test Python model fetching
  ```bash
  python -c "from crux_providers.ollama.get_ollama_models import run; models = run(); print(f'Fetched {len(models)} models'); print(models[:2] if models else 'No models')"
  ```
  - **Expected**: List of dicts with 'id' and 'name' keys
  - **Known Issue**: May fail with executable validation errors or parsing issues

### 5.3 Ollama Executable Validation
- [ ] Test executable resolution
  ```bash
  python -c "from crux_providers.ollama.get_ollama_models import _resolve_ollama_executable; path = _resolve_ollama_executable(); print(f'Resolved: {path}')"
  ```
- [ ] Test executable validation
  - Verifies basename is exactly 'ollama'
  - Checks file is regular and executable
  - Ensures not group/other writable (security check)
  
- [ ] **[ISSUE]** Test fallback behavior when ollama not installed
  ```bash
  python -c "import os; os.environ['PATH']=''; from crux_providers.ollama.get_ollama_models import run; models = run(); print(f'Fallback: {len(models)} cached models')"
  ```

### 5.4 Ollama Parsing Tests
- [ ] Run table parsing unit tests
  ```bash
  python -m pytest crux_providers/tests/providers/test_ollama_parsing.py -v
  ```
  - **Expected**: 2 tests pass
    - `test_parse_with_header_multiple_spaces`
    - `test_parse_without_header_assumes_first_column_name`

### 5.5 Ollama Provider Client
- [ ] Test provider instantiation
  ```bash
  python -c "from crux_providers.ollama.client import OllamaProvider; p = OllamaProvider(); print(f'Provider: {p.provider_name}, Host: {p._host}')"
  ```
- [ ] Test custom host configuration
  ```bash
  python -c "from crux_providers.ollama.client import OllamaProvider; p = OllamaProvider(host='http://localhost:11434'); print(f'Host: {p._host}')"
  ```
- [ ] Test OLLAMA_HOST environment variable
  ```bash
  OLLAMA_HOST=http://custom-host:8080 python -c "from crux_providers.ollama.client import OllamaProvider; p = OllamaProvider(); print(f'Host from env: {p._host}')"
  ```

### 5.6 Ollama HTTP API Testing
- [ ] Test /api/tags endpoint manually
  ```bash
  curl -s http://127.0.0.1:11434/api/tags | python -m json.tool
  ```
- [ ] Test /api/generate endpoint (if model available)
  ```bash
  curl -s http://127.0.0.1:11434/api/generate -d '{
    "model": "llama3.2",
    "prompt": "Hello",
    "stream": false
  }' | python -m json.tool
  ```

---

## 6. Architecture Compliance

### 6.1 File Size Limits
- [ ] Run file size policy test
  ```bash
  python -m pytest crux_providers/tests/test_policies_filesize.py -v
  ```
  - **Rule**: No source file should exceed 500 LOC
  - **Note**: Some files may have temporary allowlist with deviation markers

### 6.2 Dependency Flow Validation
- [ ] Verify no outer-to-inner dependencies
  - Presentation layer should only import from Business Logic interfaces
  - Business Logic should only import from Domain and Repository interfaces
  - Infrastructure/Persistence implements interfaces
  
- [ ] Check import statements in key files
  ```bash
  # Example: Check ollama client only imports from base
  grep -n "^from\|^import" crux_providers/ollama/client.py | grep -v "^from \.\." | grep -v "^from crux_providers\.base"
  ```

### 6.3 Interface-Based Design
- [ ] Verify repository interfaces exist
  ```bash
  ls -la crux_providers/base/repositories/
  ```
- [ ] Check model registry uses interfaces
  ```bash
  python -c "from crux_providers.base.repositories.model_registry import repository; print('Repository module OK')"
  ```

### 6.4 Timeout & Security Compliance
- [ ] Verify no hardcoded timeouts in provider code
  ```bash
  grep -r "timeout\s*=\s*[0-9]" crux_providers/ollama/*.py crux_providers/anthropic/*.py crux_providers/openai/*.py || echo "No hardcoded timeouts found"
  ```
- [ ] Check subprocess security (no shell=True)
  ```bash
  grep -r "shell\s*=\s*True" crux_providers/**/*.py && echo "WARNING: shell=True found" || echo "Security check passed"
  ```
- [ ] Verify executable validation in ollama
  ```bash
  grep -A 5 "_validate_executable" crux_providers/ollama/get_ollama_models.py
  ```

---

## 7. Integration Testing

### 7.1 Model Registry Integration
- [ ] Test save and load model snapshots
  ```bash
  python -c "
from crux_providers.base.get_models_base import save_provider_models, load_cached_models
test_models = [{'id': 'test-1', 'name': 'Test Model 1'}]
save_provider_models('test_provider', test_models, fetched_via='test', metadata={'source': 'test'})
snapshot = load_cached_models('test_provider')
print(f'Saved and loaded: {len(snapshot.models)} models')
"
  ```

### 7.2 End-to-End Provider Workflow
- [ ] Test complete flow: create provider -> fetch models -> use model
  ```bash
  python -c "
from crux_providers.base.factory import ProviderFactory
# Create provider
provider = ProviderFactory.create('ollama', model='llama3.2')
print(f'1. Created provider: {provider.provider_name}')
# Fetch models
from crux_providers.ollama.get_ollama_models import run
models = run()
print(f'2. Fetched {len(models)} models')
# Check capabilities
print(f'3. JSON support: {provider.supports_json_output()}')
print(f'4. Default model: {provider.default_model()}')
"
  ```

### 7.3 Streaming Architecture
- [ ] Verify BaseStreamingAdapter is used
  ```bash
  grep -r "BaseStreamingAdapter" crux_providers/ollama/helpers.py
  ```
- [ ] Test streaming capability detection
  ```bash
  python -c "from crux_providers.base.streaming import streaming_supported; print('Streaming module OK')"
  ```

---

## 8. Performance & Reliability

### 8.1 Timeout Configuration
- [ ] Test timeout configuration retrieval
  ```bash
  python -c "from crux_providers.base.timeouts import get_timeout_config; cfg = get_timeout_config(); print(f'Timeout config: start={cfg.start_timeout_seconds}s')"
  ```
- [ ] Verify operation_timeout context manager
  ```bash
  python -c "from crux_providers.base.timeouts import operation_timeout; print('Timeout utilities OK')"
  ```

### 8.2 Retry Mechanisms
- [ ] Check retry configuration exists
  ```bash
  python -c "from crux_providers.base.config import get_provider_config; print('Config module OK')"
  ```

### 8.3 Error Handling
- [ ] Test exception classification
  ```bash
  python -c "from crux_providers.base.errors import classify_exception, ErrorCode; print('Error classification OK')"
  ```
- [ ] Verify fallback behavior (returns cached data on failure)
  ```bash
  python -c "
from crux_providers.ollama.get_ollama_models import run
# This should fallback gracefully if ollama not available
models = run()
print(f'Fallback test: {len(models)} models (may be cached)')
"
  ```

---

## 9. Security Validation

### 9.1 Subprocess Security
- [ ] Verify shutil.which usage for executable resolution
  ```bash
  grep -n "shutil.which" crux_providers/ollama/get_ollama_models.py
  ```
- [ ] Check executable validation includes permission checks
  ```bash
  grep -A 10 "def _validate_executable" crux_providers/ollama/get_ollama_models.py
  ```
- [ ] Verify no shell=True in subprocess calls
  ```bash
  grep -n "subprocess.run" crux_providers/ollama/get_ollama_models.py
  grep -n "shell=False" crux_providers/ollama/get_ollama_models.py
  ```

### 9.2 API Key Handling
- [ ] Verify keys are not logged
  ```bash
  grep -r "log.*api_key\|print.*api_key" crux_providers/ && echo "WARNING: API key logging found" || echo "API key handling secure"
  ```
- [ ] Test placeholder detection
  ```bash
  python -c "from crux_providers.config.env import is_placeholder; assert is_placeholder('PLACEHOLDER_KEY'); assert not is_placeholder('real-key-123'); print('Placeholder detection OK')"
  ```

### 9.3 Input Validation
- [ ] Check size guards exist
  ```bash
  ls -la crux_providers/utils/input_size_guard.py
  ```

---

## 10. Documentation Review

### 10.1 README Files
- [ ] Review main README
  ```bash
  cat crux_providers/README.md | head -50
  ```
- [ ] Check provider-specific READMEs exist
  ```bash
  ls -la crux_providers/*/README.md
  ```

### 10.2 Architecture Documentation
- [ ] Review ARCHITECTURE_RULES.md
  ```bash
  head -100 ARCHITECTURE_RULES.md
  ```
- [ ] Check AGENTS.md for agent instructions
  ```bash
  head -50 AGENTS.md
  ```

### 10.3 Docstring Coverage
- [ ] Verify key functions have docstrings
  ```bash
  python -c "
from crux_providers.ollama.get_ollama_models import run, _fetch_via_cli, _validate_executable
print('run.__doc__:', bool(run.__doc__))
print('_fetch_via_cli.__doc__:', bool(_fetch_via_cli.__doc__))
print('_validate_executable.__doc__:', bool(_validate_executable.__doc__))
"
  ```

---

## Known Issues & Troubleshooting

### Issue 1: Ollama Model Fetching Failure

**Symptoms:**
- `ollama list --json` fails or returns unexpected format
- `FileNotFoundError: 'ollama' executable not found on PATH`
- Permission errors on executable validation

**Investigation Steps:**
1. Check if ollama is installed and in PATH
   ```bash
   which ollama
   ollama --version
   ```
2. Check if ollama service is running
   ```bash
   curl http://127.0.0.1:11434/api/tags
   ```
3. Check executable permissions
   ```bash
   ls -la $(which ollama)
   ```
4. Test direct CLI invocation
   ```bash
   ollama list --json
   ollama list
   ```

**Potential Fixes:**
- Install ollama: https://ollama.com/download
- Start ollama service: `ollama serve`
- Check PATH includes ollama location
- Verify executable permissions are correct

### Issue 2: Setup Confusion

**Symptoms:**
- Unclear where to start
- Missing dependencies
- Configuration not loading

**Investigation Steps:**
1. Verify virtual environment is activated
2. Check requirements.txt is complete
3. Ensure .env file exists with proper variables
4. Verify Python version >= 3.9

**Potential Fixes:**
1. Follow installation section above
2. Create .env from .env.example
3. Install all dependencies: `pip install -r requirements.txt`
4. Install provider-specific SDKs as needed

### Issue 3: Import Errors

**Symptoms:**
- `ModuleNotFoundError` for pydantic, httpx, or provider SDKs

**Investigation Steps:**
1. Check installed packages: `pip list`
2. Verify virtual environment is active
3. Check pyproject.toml dependencies

**Potential Fixes:**
```bash
pip install pydantic httpx pytest
pip install openai anthropic google-generativeai ollama
```

---

## Testing Summary Report Template

Use this template to document test results:

```markdown
## Beta Testing Report

**Tester:** [Name]
**Date:** [YYYY-MM-DD]
**Environment:** [OS, Python version]
**Ollama Version:** [Version or N/A]

### Test Results

#### Section 1: Environment Setup
- Python Environment: [PASS/FAIL]
- System Requirements: [PASS/FAIL]
- Issues: [Description]

#### Section 2: Installation
- Core Installation: [PASS/FAIL]
- Provider SDKs: [PASS/FAIL]
- Testing Dependencies: [PASS/FAIL]
- Issues: [Description]

#### Section 3: Configuration
- Environment Variables: [PASS/FAIL]
- Configuration Files: [PASS/FAIL]
- API Key Resolution: [PASS/FAIL]
- Issues: [Description]

#### Section 4: Provider Testing
- Factory Pattern: [PASS/FAIL]
- Model Registry: [PASS/FAIL]
- Provider Capabilities: [PASS/FAIL]
- Issues: [Description]

#### Section 5: Ollama-Specific
- Installation Check: [PASS/FAIL]
- Model Listing: [PASS/FAIL]
- Executable Validation: [PASS/FAIL]
- Parsing Tests: [PASS/FAIL]
- Provider Client: [PASS/FAIL]
- HTTP API: [PASS/FAIL]
- Issues: [Description]

#### Section 6: Architecture Compliance
- File Size Limits: [PASS/FAIL]
- Dependency Flow: [PASS/FAIL]
- Interface Design: [PASS/FAIL]
- Security Compliance: [PASS/FAIL]
- Issues: [Description]

#### Section 7: Integration Testing
- Model Registry: [PASS/FAIL]
- E2E Workflow: [PASS/FAIL]
- Streaming: [PASS/FAIL]
- Issues: [Description]

#### Section 8: Performance
- Timeout Configuration: [PASS/FAIL]
- Retry Mechanisms: [PASS/FAIL]
- Error Handling: [PASS/FAIL]
- Issues: [Description]

#### Section 9: Security
- Subprocess Security: [PASS/FAIL]
- API Key Handling: [PASS/FAIL]
- Input Validation: [PASS/FAIL]
- Issues: [Description]

#### Section 10: Documentation
- README Files: [PASS/FAIL]
- Architecture Docs: [PASS/FAIL]
- Docstring Coverage: [PASS/FAIL]
- Issues: [Description]

### Critical Issues Found
1. [Issue description]
2. [Issue description]

### Recommendations
1. [Recommendation]
2. [Recommendation]

### Overall Assessment
[READY FOR RELEASE / NEEDS FIXES / MAJOR ISSUES]
```

---

## Quick Start Guide for Beta Testers

For a quick validation of core functionality:

```bash
# 1. Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pydantic httpx pytest

# 2. Test imports
python -c "from crux_providers.base import ProviderFactory; print('OK')"

# 3. Test factory
python -c "from crux_providers.base.factory import ProviderFactory; print(ProviderFactory.supported())"

# 4. Run unit tests
python -m pytest crux_providers/tests/providers/test_ollama_parsing.py -v

# 5. Test ollama (if installed)
which ollama && python -c "from crux_providers.ollama.get_ollama_models import run; print(f'{len(run())} models')"

# 6. Check architecture compliance
python -m pytest crux_providers/tests/test_policies_filesize.py -v
```

---

## Contact & Support

For issues or questions during beta testing:
- Create an issue on GitHub with `[BETA-TEST]` prefix
- Include: OS, Python version, Ollama version (if applicable)
- Attach full error messages and stack traces
- Use the testing summary report template above

---

**End of Checklist**
