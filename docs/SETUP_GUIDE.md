# Crux Providers: Setup & Quick Start Guide

**Version:** 1.0  
**Last Updated:** 2025-01-01  
**Purpose:** Clear, step-by-step guide for setting up the Crux Providers system

---

## Overview

Crux Providers is a provider-agnostic LLM abstraction layer built with Hybrid Clean Architecture principles. This guide will help you set up the project correctly and understand its structure.

### What is Crux Providers?

- **Purpose**: Normalize interactions with multiple LLM providers (OpenAI, Anthropic, Gemini, Ollama, etc.) behind a single, typed interface
- **Architecture**: Modular monolith following Clean Architecture with strict layering
- **Key Features**: 
  - Provider-agnostic DTOs and interfaces
  - Central factory for adapter creation
  - Model registry with SQLite persistence
  - Unified streaming architecture
  - Comprehensive timeout and retry mechanisms

---

## Prerequisites

### Required
- Python 3.9 or higher
- pip (Python package manager)
- Git (for cloning the repository)
- 1GB+ free disk space

### Optional (Provider-Specific)
- **Ollama**: Local installation from https://ollama.com (for testing Ollama provider)
- **API Keys**: For testing cloud providers (OpenAI, Anthropic, Gemini, etc.)

---

## Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/justinlietz93/crux.git
cd crux
```

### Step 2: Create Virtual Environment

**IMPORTANT**: Always use a virtual environment to avoid dependency conflicts.

```bash
# Create virtual environment
python -m venv .venv

# Activate it
# On Linux/Mac:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

**Verification**: Your terminal prompt should show `(.venv)` prefix.

```bash
# Verify you're in the virtual environment
which python  # Should point to .venv/bin/python
```

### Step 3: Install Core Dependencies

```bash
# Install all core dependencies
pip install -r requirements.txt

# Additionally install commonly needed packages
pip install pydantic httpx pytest pytest-cov
```

**What gets installed:**
- Core provider adapters
- HTTP client (httpx)
- Data validation (pydantic)
- Testing tools (pytest)
- Various provider SDKs (openai, anthropic, etc.)

### Step 4: Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your preferred editor
nano .env  # or vim, code, etc.
```

**What to configure in .env:**

```bash
# API Keys (optional for testing, use placeholders if not testing specific providers)
OPENAI_API_KEY="your-openai-key-here"
ANTHROPIC_API_KEY="your-anthropic-key-here"
GEMINI_API_KEY="your-gemini-key-here"  # or GOOGLE_API_KEY
DEEPSEEK_API_KEY="your-deepseek-key-here"
OPENROUTER_API_KEY="your-openrouter-key-here"
XAI_API_KEY="your-xai-key-here"

# Ollama Configuration (optional, defaults shown)
OLLAMA_HOST="http://127.0.0.1:11434"  # Local ollama server
```

**Security Note**: Never commit real API keys to the repository!

### Step 5: Verify Installation

```bash
# Test core imports
python -c "from crux_providers.base import ProviderFactory; print('✓ Core imports OK')"

# List supported providers
python -c "from crux_providers.base.factory import ProviderFactory; print('Supported providers:', ProviderFactory.supported())"

# Expected output: ('openai', 'anthropic', 'gemini', 'deepseek', 'openrouter', 'ollama', 'xai')
```

---

## Project Structure Explained

Understanding the codebase structure will help you navigate and work with it effectively.

```
crux/
├── crux_providers/              # Main package
│   ├── base/                    # Core abstractions and interfaces
│   │   ├── factory.py           # Provider factory (entry point)
│   │   ├── interfaces.py        # LLMProvider interface
│   │   ├── models.py            # DTOs (ChatRequest, ChatResponse)
│   │   ├── streaming/           # Streaming architecture
│   │   ├── repositories/        # Data access layer
│   │   └── ...
│   ├── config/                  # Configuration management
│   │   ├── defaults.py          # Default values
│   │   └── env.py               # Environment variable handling
│   ├── ollama/                  # Ollama provider implementation
│   │   ├── client.py            # OllamaProvider adapter
│   │   ├── get_ollama_models.py # Model fetching
│   │   └── helpers.py           # Provider-specific utilities
│   ├── openai/                  # OpenAI provider
│   ├── anthropic/               # Anthropic provider
│   ├── gemini/                  # Gemini provider
│   ├── deepseek/                # Deepseek provider
│   ├── openrouter/              # OpenRouter provider
│   ├── xai/                     # xAI provider
│   ├── persistence/             # SQLite and data storage
│   ├── utils/                   # Shared utilities
│   └── tests/                   # Unit and integration tests
├── docs/                        # Documentation
├── tests/                       # Additional tests
├── pyproject.toml               # Project metadata
├── requirements.txt             # Python dependencies
├── .env.example                 # Example environment file
└── README.md                    # Main documentation
```

### Key Concepts

#### 1. **Provider Factory Pattern**
The `ProviderFactory` is your entry point for creating provider instances:

```python
from crux_providers.base.factory import ProviderFactory

# Create a provider instance
provider = ProviderFactory.create('ollama', model='llama3.2')
```

#### 2. **Clean Architecture Layers**

```
┌─────────────────────────────────────┐
│  Presentation Layer (Providers)     │  ← ollama/client.py, openai/client.py
│  - Provider adapters                │
│  - HTTP/CLI interaction             │
└─────────────────────────────────────┘
              ↓ uses
┌─────────────────────────────────────┐
│  Application Layer (Base)           │  ← base/interfaces.py
│  - LLMProvider interface            │
│  - Business logic abstractions      │
└─────────────────────────────────────┘
              ↓ uses
┌─────────────────────────────────────┐
│  Domain Layer                       │  ← base/models.py
│  - DTOs (ChatRequest, ChatResponse) │
│  - Pure data models                 │
└─────────────────────────────────────┘
              ↓ used by
┌─────────────────────────────────────┐
│  Infrastructure (Persistence)       │  ← repositories/, persistence/
│  - SQLite storage                   │
│  - Model registry                   │
└─────────────────────────────────────┘
```

**Key Rule**: Dependencies flow inward only. Outer layers depend on inner layers via interfaces.

#### 3. **Model Registry**
Each provider can fetch and cache its available models:

```python
from crux_providers.ollama.get_ollama_models import run

# Fetch models (tries live fetch, falls back to cache)
models = run()
print(f"Found {len(models)} models")
```

#### 4. **Configuration Centralization**
All configuration is centralized in `crux_providers/config/`:

- `defaults.py`: Default values (host URLs, model names, timeouts)
- `env.py`: Environment variable mappings and resolution

**Never hardcode values** in provider implementations!

---

## Usage Examples

### Basic Provider Usage

```python
from crux_providers.base.factory import ProviderFactory
from crux_providers.base.models import ChatRequest, Message

# 1. Create a provider
provider = ProviderFactory.create('ollama', model='llama3.2')

# 2. Prepare a request
request = ChatRequest(
    messages=[
        Message(role='user', content='Hello, how are you?')
    ],
    model='llama3.2'
)

# 3. Get a response
response = provider.chat(request)
print(f"Response: {response.text}")
```

### Listing Available Models

```python
from crux_providers.ollama.get_ollama_models import run as get_ollama_models
from crux_providers.openai.get_openai_models import run as get_openai_models

# Ollama models (local)
ollama_models = get_ollama_models()
print(f"Ollama: {len(ollama_models)} models")

# OpenAI models (requires API key)
openai_models = get_openai_models()
print(f"OpenAI: {len(openai_models)} models")
```

### Testing Provider Capabilities

```python
from crux_providers.base.factory import ProviderFactory

# Create provider
provider = ProviderFactory.create('ollama')

# Check capabilities
print(f"Provider: {provider.provider_name}")
print(f"Supports JSON output: {provider.supports_json_output()}")
print(f"Default model: {provider.default_model()}")
```

---

## Ollama-Specific Setup

Ollama is a local LLM runtime that doesn't require API keys. Here's how to set it up:

### Step 1: Install Ollama

Visit https://ollama.com/download and follow instructions for your OS:

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Mac
brew install ollama

# Windows
# Download installer from https://ollama.com/download
```

### Step 2: Start Ollama Service

```bash
# Start the ollama service
ollama serve

# In another terminal, verify it's running
curl http://127.0.0.1:11434/api/tags
```

### Step 3: Pull a Model

```bash
# Pull a small model for testing
ollama pull llama3.2

# List available models
ollama list
```

### Step 4: Test with Crux Providers

```bash
# Test model fetching
python -c "from crux_providers.ollama.get_ollama_models import run; models = run(); print(f'Found {len(models)} models')"

# Test provider
python -c "
from crux_providers.base.factory import ProviderFactory
provider = ProviderFactory.create('ollama', model='llama3.2')
print(f'Provider ready: {provider.provider_name}')
"
```

---

## Common Issues & Solutions

### Issue 1: Import Errors

**Symptom:**
```
ModuleNotFoundError: No module named 'pydantic'
```

**Solution:**
```bash
# Make sure virtual environment is activated
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate      # Windows

# Install missing dependencies
pip install pydantic httpx pytest
```

### Issue 2: Ollama Not Found

**Symptom:**
```
FileNotFoundError: 'ollama' executable not found on PATH
```

**Solution:**
1. Install ollama from https://ollama.com
2. Verify installation: `which ollama`
3. Add to PATH if needed
4. Start ollama service: `ollama serve`

### Issue 3: API Key Issues

**Symptom:**
```
WARNING: API key not found, using cached models
```

**Solution:**
1. Create `.env` file from `.env.example`
2. Add your API keys (without quotes if using direnv):
   ```bash
   OPENAI_API_KEY=sk-...
   ```
3. Or export in terminal:
   ```bash
   export OPENAI_API_KEY=sk-...
   ```

### Issue 4: SQLite Database Errors

**Symptom:**
```
sqlite3.OperationalError: database is locked
```

**Solution:**
- The system uses WAL mode and handles this automatically
- If persistent, check no other process is using the DB
- Delete `shell_prefs.db` to start fresh (loses cached data)

---

## Running Tests

### Run All Tests

```bash
# Run all tests
python -m pytest crux_providers/tests/ -v

# Run with coverage
python -m pytest crux_providers/tests/ --cov=crux_providers --cov-report=html
```

### Run Specific Test Suites

```bash
# Ollama parsing tests
python -m pytest crux_providers/tests/providers/test_ollama_parsing.py -v

# Architecture compliance
python -m pytest crux_providers/tests/test_policies_filesize.py -v

# Streaming tests
python -m pytest crux_providers/tests/streaming/ -v
```

---

## Development Workflow

### Adding a New Provider

1. Create provider directory: `crux_providers/my_provider/`
2. Implement adapter: `my_provider/client.py` (implements `LLMProvider`)
3. Optional model fetcher: `my_provider/get_my_provider_models.py`
4. Register in factory: `crux_providers/base/factory.py`
5. Add tests: `crux_providers/tests/providers/test_my_provider.py`

### Architecture Guidelines

**Critical Rules:**
- No source file > 500 lines
- Dependencies flow inward only
- Use interfaces for cross-layer communication
- No hardcoded timeouts (use `get_timeout_config()`)
- No `shell=True` in subprocess calls
- All streaming must use `BaseStreamingAdapter`

See `ARCHITECTURE_RULES.md` for complete guidelines.

---

## Next Steps

1. **For Beta Testers**: See `docs/BETA_TESTING_CHECKLIST.md`
2. **For Developers**: Review `ARCHITECTURE_RULES.md` and `AGENTS.md`
3. **For Contributors**: Check `crux_providers/README.md` for contribution guidelines

---

## Quick Reference Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Test installation
python -c "from crux_providers.base.factory import ProviderFactory; print(ProviderFactory.supported())"

# Run tests
python -m pytest crux_providers/tests/ -v

# Check ollama
which ollama && ollama list

# Fetch models
python -c "from crux_providers.ollama.get_ollama_models import run; print(len(run()), 'models')"

# Create provider
python -c "from crux_providers.base.factory import ProviderFactory; p = ProviderFactory.create('ollama'); print(p.provider_name)"
```

---

## Getting Help

- **Documentation**: See `docs/` directory
- **Architecture**: Read `ARCHITECTURE_RULES.md`
- **Beta Testing**: Follow `docs/BETA_TESTING_CHECKLIST.md`
- **Issues**: Create GitHub issue with detailed error messages

---

**End of Setup Guide**
