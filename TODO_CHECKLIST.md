# CLI Issues TODO Checklist

This document tracks known issues in the Crux Providers CLI interactive shell (`python -m crux_providers.service.cli shell`). Issues are prioritized by impact on usability. Status: [ ] Open, [-] In Progress, [x] Resolved.

## Critical Priority (Development Blockers)

- [ ] **Providers Mock**
  - [ ] Design MockProvider class implementing LLMProvider interface from crux_providers/base/interfaces_parts/llm_provider.py
  - [ ] Implement basic mock responses for chat completions using predefined JSON fixtures
  - [ ] Add support for streaming simulation in mocks, leveraging BaseStreamingAdapter
  - [ ] Integrate mock factory into crux_providers/base/factory.py with mock mode detection
  - [ ] Create pytest fixtures for mock usage in tests/conftest.py to enable isolated testing
  - [ ] Add configuration toggle (e.g., CRUX_USE_MOCKS env var) in crux_providers/config/env.py
  - [ ] Write unit tests for mock integration, targeting 95% coverage
  - [ ] Document mock usage and activation in docs/SETUP_GUIDE.md
  - [ ] Validate with end-to-end test against CLI shell (python -m crux_providers.service.cli shell)
  

## High Priority (Usability Blockers)

- [ ] **Backslashes in Log Keys/Values (Regression)**  
  Logs show literal backslashes (`\`) escaping keys and values in JSON (e.g., `"provider\": \"ollama\"` becomes `"provider\": \"\\ollama\"`). This was fixed previously but regressed. Likely in JSON serialization in [base/log_support/json_formatter.py](crux_providers/base/log_support/json_formatter.py). Fix: Ensure proper escaping in logger or formatter. Test: Run `chat hello` and verify clean JSON.

- [ ] **Duplicated Log Messages**  
  Events like "chat.start", "retry.attempt", "chat.end" log twice (e.g., identical timestamps). Seen in Ollama provider. Possible double-logging in [ollama/client.py](crux_providers/ollama/client.py) or base logging. Fix: Audit log calls in provider invocation. Test: Enable INFO, run chat, confirm single logs.

- [ ] **INFO Logs Persist at WARNING Level**  
  Even after `options verbosity WARNING`, INFO-level provider logs (e.g., "chat.start") appear. Expected: Suppress below WARNING. Issue in [service/helpers.py](crux_providers/service/helpers.py) or logging config application. Fix: Ensure `logging.basicConfig` or handler respects level. Test: Set WARNING, chat, no INFO visible.

## Medium Priority (UX Improvements)

- [ ] **No Synonyms for Verbosity Levels**  
  Commands like `verbosity low` fail with "invalid verbosity value"; requires exact "INFO"/"WARNING". User-friendly aliases (low=WARNING, high=DEBUG) missing. Fix: Extend parser in [service/cli_utils.py](crux_providers/service/cli_utils.py) or **main**.py. Test: `verbosity low` sets WARNING.

- [ ] **Single-Line Chat Input Not Supported**  
  `chat hello` prompts for multi-line ("Enter message. End with empty line"), ignoring inline prompt. Users expect direct input like `ask hello`. Regression from prior terminal design. Fix: Add `ask <prompt>` subcommand or parse inline in `chat`. Test: `ask hello` chats immediately.

- [ ] **Unknown Command for Simple Inputs**  
  Typing "hello" gives "unknown command — try 'help'". Should route to chat if not a command. Fix: Fallback in shell loop to treat non-commands as chat prompts. Test: Direct "hello" initiates chat.

  - [ ] **Meta-Data Display**  
  Right now the meta-data displays only as JSON in the terminal. There should be an option to display this in a table view in the terminal, and optionally to log file
   so it's more human readable during debugging.

## Low Priority (Polish)

- [ ] **Streaming Logs Not Fully Suppressed**  
  With `stream on live`, internal JSON should hide, but some leak. Enhance `_suppress_console_logs` in [service/cli_utils.py](crux_providers/service/cli_utils.py). Test: Stream chat, clean output.

- [ ] **Help Command Enhancement**  
  `help` lists commands but lacks examples (e.g., verbosity synonyms, chat usage). Add section in output. Fix: Update help text in **main**.py.

- [ ] **CLI UX**  
  The CLI pointer tag says `dev>`, when `debug>` is more clear that the CLI isn't meant for the optimal experience, it's meant for troubleshooting and diagnostics.

## Testing & Validation

- Run full smoke tests: `pytest crux_providers/tests/test_cli_* -v`.
- Manual: Launch shell, test each issue at INFO/WARNING levels with Ollama.
- After fixes: Update [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md) with examples.

Last Updated: 2025-10-02
