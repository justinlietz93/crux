# CLI Issues TODO Checklist

Review the codebase to get familiar, then examine this TODO_CHECKLIST.md for your tasks.

This document tracks known issues in the Crux Providers CLI interactive shell (`python -m crux_providers.service.cli shell`). Issues are prioritized by impact on usability. Mark items as [DONE], [STARTED], [RETRYING], [DEBUGGGING], [NOT STARTED], as you go and document your work under each item as you work. 

You should not remain stagnant on an issue for too long, if you get stuck on an item and it's marked [RETRYING] or [DEBUGGING], put an x# next to it, where # is the number of times you've attempted resolving it, for example [DEBUGGING x2]. 

If you hit x3 then move on unless it's blocking anything else or if it would introduce significant technical debt if not addressed immediately. If it is a blocker like that, state this clearly in your response including "BLOCKER PREVENTING FURTHER DEVELOPMENT"

This work is closed-beta readiness finalizing, do not put anything "out of scope" if it is listed as required for production release.

If tests fail because of any missing packages or installations, you need to install those and try to run the tests again. Same thing if you run into errors for missing packages.

Mention which items you updated on the checklist in your response

## Critical Priority (Development Blockers)

- [DONE] **Providers Mock**
  - Designed `MockProvider` implementing `LLMProvider`/`SupportsStreaming` with fixture-backed responses and structured metadata.
  - Added JSON fixtures powering deterministic chat completions and streaming chunks for greetings and fallback prompts.
  - Streaming pipeline now delegates to `BaseStreamingAdapter`, attaching metadata to terminal events for aggregation.
  - `ProviderFactory` detects `CRUX_USE_MOCKS` and routes providers through mock adapters; explicit `mock` provider supported.
  - Introduced pytest fixtures enabling mock mode and direct `MockProvider` access for tests.
  - Added `CRUX_USE_MOCKS` toggle helper in `config/env.py` with truthy parsing utility.
  - Created unit and integration tests covering chat, streaming, factory routing, CLI usage, and event accumulation.
  - Documented activation steps and smoke tests for mock mode in `docs/SETUP_GUIDE.md`.
  - CLI shell regression test confirms mock responses render end-to-end via `DevSession`.
  

## High Priority (Usability Blockers)

- [DONE] **Backslashes in Log Keys/Values (Regression)**
  Logs show literal backslashes (`\`) escaping keys and values in JSON (e.g., `"provider\": \"ollama\"` becomes `"provider\": \"\\ollama\"`). This was fixed previously but regressed. Likely in JSON serialization in [base/log_support/json_formatter.py](crux_providers/base/log_support/json_formatter.py). Fix: Ensure proper escaping in logger or formatter. Test: Run `chat hello` and verify clean JSON.
  - Added regression coverage in `test_logging_unit` verifying `JsonFormatter` hoists JSON keys without double escaping.
  - Confirmed structured logging rewrite still emits clean payloads using the updated formatter helper.

- [DONE] **Duplicated Log Messages**
  Events like "chat.start", "retry.attempt", "chat.end" log twice (e.g., identical timestamps). Seen in Ollama provider. Possible double-logging in [ollama/client.py](crux_providers/ollama/client.py) or base logging. Fix: Audit log calls in provider invocation. Test: Enable INFO, run chat, confirm single logs.
  - Reworked `get_logger` so child loggers propagate to the shared console handler, preventing duplicate handler emissions.
  - Added unit coverage ensuring child logger writes exactly one line per event.

- [DONE] **INFO Logs Persist at WARNING Level**
  Even after `options verbosity WARNING`, INFO-level provider logs (e.g., "chat.start") appear. Expected: Suppress below WARNING. Issue in [service/helpers.py](crux_providers/service/helpers.py) or logging config application. Fix: Ensure `logging.basicConfig` or handler respects level. Test: Set WARNING, chat, no INFO visible.
  - Adjusted logger configuration to centralize level control and propagate child loggers, then verified with new warning-level unit test.

## Medium Priority (UX Improvements)

- [DONE] **No Synonyms for Verbosity Levels**
  Commands like `verbosity low` fail with "invalid verbosity value"; requires exact "INFO"/"WARNING". User-friendly aliases (low=WARNING, high=DEBUG) missing. Fix: Extend parser in [service/cli_utils.py](crux_providers/service/cli_utils.py) or **main**.py. Test: `verbosity low` sets WARNING.
  - Verified existing synonym mappings via a targeted unit test covering low/verbose/high/silent inputs.

- [DONE] **Single-Line Chat Input Not Supported**
  `chat hello` prompts for multi-line ("Enter message. End with empty line"), ignoring inline prompt. Users expect direct input like `ask hello`. Regression from prior terminal design. Fix: Add `ask <prompt>` subcommand or parse inline in `chat`. Test: `ask hello` chats immediately.
  - Extended `chat` command to accept inline prompts and documented the behavior in the help output.

- [DONE] **Unknown Command for Simple Inputs**
  Typing "hello" gives "unknown command — try 'help'". Should route to chat if not a command. Fix: Fallback in shell loop to treat non-commands as chat prompts. Test: Direct "hello" initiates chat.
  - Added command execution helper that falls back to `ask` when dispatching fails, plus unit coverage ensuring fallback occurs.

  - [DONE] **Meta-Data Display**
  Right now the meta-data displays only as JSON in the terminal. There should be an option to display this in a table view in the terminal, and optionally to log file
   so it's more human readable during debugging.
  - Added CLI metadata options for table or JSON rendering and optional file logging, with streamed responses honoring the selected mode.

## Low Priority (Polish)

- [DONE] **Streaming Logs Not Fully Suppressed**
  With `stream on live`, internal JSON should hide, but some leak. Enhance `_suppress_console_logs` in [service/cli_utils.py](crux_providers/service/cli/cli_utils.py). Test: Stream chat, clean output.
  - Updated console suppression to detach handlers entirely during streaming and added regression coverage to ensure logs stay silent.

- [DONE] **Help Command Enhancement**
  `help` lists commands but lacks examples (e.g., verbosity synonyms, chat usage). Add section in output. Fix: Update help text in **main**.py.
  - Expanded help output with practical examples highlighting verbosity synonyms, metadata options, and inline chat usage.

- [DONE] **CLI UX**
  The CLI pointer tag says `dev>`, when `debug>` is more clear that the CLI isn't meant for the optimal experience, it's meant for troubleshooting and diagnostics.
  - Updated shell prompt to `debug>` to emphasize diagnostic usage.

## Testing & Validation

- Run full smoke tests: `pytest crux_providers/tests/test_cli_* -v`.
- Manual: Launch shell, test each issue at INFO/WARNING levels with Ollama.
- After fixes: Update [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md) with examples.

Last Updated: 2025-10-02
