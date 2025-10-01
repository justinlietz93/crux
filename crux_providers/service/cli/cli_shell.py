"""Interactive developer terminal (headless) for provider debugging.

Purpose
-------
Provide a dependency-free, headless terminal experience to explore providers,
switch models, toggle streaming, and run prompts repeatedly without restarting
or re-entering configuration. This is intended as an optional convenience layer
for developers to interact directly with the abstraction layer.

Design
------
- Presentation-only: interacts via stdin/stdout; no provider logic here.
- Uses helpers from ``cli_actions`` for adapter resolution and streaming checks.
- Persistent session state (provider, model, stream, live) with simple commands:
    - ``help``: Show available commands
    - ``status``: Print current settings
    - ``providers``: List known providers
    - ``use <provider>``: Switch provider and refresh adapter
    - ``model [<id>]``: Show or set model
    - ``stream [on|off] [live|nolive]``: Toggle streaming and live token print
    - ``ask <prompt>``: Send a one-line prompt
    - ``chat``: Enter multi-line prompt mode (end with an empty line)
    - ``quit``/``exit``: Leave the terminal

Notes
-----
- Keys auto-load via ``set_env_for_provider`` (dotenv/DB fallbacks are gated in
    tests per repository policy).
- No external dependencies; suitable for headless environments and CI.
"""


from __future__ import annotations

import argparse
import contextlib
from typing import Any, Dict, Optional, Tuple
import os
import readline  # type: ignore[attr-defined]

from .cli_actions import (
    ChatRequest,
    Message,
    instantiate_adapter,
    streaming_capable,
)
from ..helpers import set_env_for_provider
from .settings import (
    CLISettings,
    load_settings,
    save_settings,
    apply_logging,
    normalize_log_path,
)
from .cli_utils import parse_verbosity as _parse_verbosity, suppress_console_logs as _suppress_console_logs


## Verbosity parsing has been centralized in cli_utils.parse_verbosity.


def _print_header(title: str) -> None:
    """Print a section header in the terminal UI.

    Parameters
    ----------
    title: str
        Descriptive section title.
    """
    print("\n== " + title + " ==")


def _list_known_providers() -> Dict[str, str]:
    """Return a mapping of provider keys to human-friendly labels."""
    return {
        "openrouter": "OpenRouter (meta-router)",
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "xai": "xAI",
        "deepseek": "Deepseek",
        "gemini": "Google Gemini",
        "ollama": "Ollama (local)",
    }


def _readline(prompt: str) -> str:
    """Read a single line from stdin; return ``quit`` on EOF.

    This keeps the dev terminal resilient when input is piped or closed.
    """
    try:
        return input(prompt)
    except EOFError:
        return "quit"


def _live_stream(adapter: Any, req: ChatRequest) -> str:
    """Stream tokens live to stdout and return the accumulated text.

    During streaming, temporarily suppress console JSON logs from the
    shared ``providers`` logger so they don't interleave with token
    output. File logging remains unaffected.
    """
    parts: list[str] = []
    with _suppress_console_logs():
        for ev in adapter.stream_chat(req):
            if ev.delta:
                text = ev.delta
                parts.append(text)
                print(text, end="", flush=True)
    print()
    return "".join(parts)


# Note: Console log suppression is implemented in `cli_utils.suppress_console_logs`.


class DevSession:
    """Holds interactive terminal state and executes commands.

    Parameters
    ----------
    provider: str
        Initial provider key (e.g., ``openrouter``).
    model: Optional[str]
        Initial model override or ``None`` for adapter default.
    stream: bool
        Whether to use streaming by default.
    live: bool
        Whether to print tokens live when streaming.
    """

    def __init__(self, provider: Optional[str], model: Optional[str], stream: Optional[bool], live: Optional[bool]) -> None:
        """Initialize a development session.

        Prefers CLI arguments when provided, otherwise falls back to last
        persisted values from settings. Logging is configured immediately.
        """
        # Load and apply persistent CLI settings (verbosity, log file)
        self.settings: CLISettings = load_settings()
        apply_logging(self.settings)

        # Resolve initial state with persistence fallbacks
        chosen_provider = (provider or self.settings.last_provider or "openrouter")
        self.provider = chosen_provider.lower().strip()
        self.model_override = model if model is not None else self.settings.last_model
        # For flags, treat CLI arg as override when truthy; otherwise use last saved values
        self.stream = bool(stream) if stream is not None else bool(self.settings.last_stream)
        self.live = bool(live) if live is not None else bool(self.settings.last_live)

        # Persist the resolved initial state for next session
        self.settings.last_provider = self.provider
        self.settings.last_model = self.model_override
        self.settings.last_stream = bool(self.stream)
        self.settings.last_live = bool(self.live)
        with contextlib.suppress(Exception):
            save_settings(self.settings)

        self.adapter: Optional[Any] = None
        self._ensure_adapter()
        # Initialize UI conveniences (readline history, tab completion)
        self._init_ui()

    def _color(self, text: str, color: str) -> str:
        """Return ANSI-colored text if colors are enabled.

        Parameters
        ----------
        text: str
            The text to wrap with color sequences.
        color: str
            One of 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan'.
        """
        if not getattr(self.settings, "ui_colors", True):
            return text
        colors = {
            "red": "\033[31m",
            "green": "\033[32m",
            "yellow": "\033[33m",
            "blue": "\033[34m",
            "magenta": "\033[35m",
            "cyan": "\033[36m",
        }
        reset = "\033[0m"
        return f"{colors.get(color, '')}{text}{reset}"

    def _init_ui(self) -> None:
        """Initialize readline history and tab-completion according to settings."""
        try:
            # Base command list for completion and suggestions
            self._commands = [
                "help", "status", "providers", "use", "model", "stream",
                "options", "verbosity", "logfile", "colors", "readline", "complete",
                "ask", "chat", "quit", "exit",
            ]
            if getattr(self.settings, "ui_readline", True):
                hist_path = os.path.expanduser(self.settings.history_file_path)
                os.makedirs(os.path.dirname(hist_path), exist_ok=True)
                # Load history
                with contextlib.suppress(FileNotFoundError):
                    readline.read_history_file(hist_path)
                # Enable basic tab completion of known commands
                if getattr(self.settings, "ui_completions", True):
                    def completer(text: str, state: int) -> Optional[str]:
                        matches = [c for c in self._commands if c.startswith(text)]
                        return matches[state] if state < len(matches) else None
                    readline.set_completer(completer)
                    readline.parse_and_bind("tab: complete")
                # Save history on exit
                self._history_path = hist_path
            else:
                self._history_path = None  # type: ignore[assignment]
        except Exception:
            self._history_path = None  # type: ignore[assignment]

    def _ensure_adapter(self) -> None:
        """Ensure the adapter is instantiated for the current provider."""
        set_env_for_provider(self.provider)
        self.adapter = instantiate_adapter(self.provider)

    def _effective_model(self) -> str:
        """Compute the effective model using override or adapter default."""
        with contextlib.suppress(Exception):
            if self.model_override:
                return self.model_override
            if self.adapter:
                return self.adapter.default_model() or "auto"  # type: ignore[return-value]
        return "auto"

    def status(self) -> None:
        """Print current session settings."""
        _print_header(self._color("status", "cyan"))
        print(f"provider : {self.provider}")
        print(
            f"model    : {self._effective_model()}"
            + (" (override)" if self.model_override else "")
        )
        print(self._color(f"stream   : {'on' if self.stream else 'off'}", "yellow"))
        print(self._color(f"live     : {'on' if (self.stream and self.live) else 'off'}", "yellow"))
        print(f"verbosity: {self.settings.verbosity}")
        print(f"log file : {self.settings.log_file_path if self.settings.log_to_file else 'disabled'}")
        print(f"colors   : {'on' if getattr(self.settings, 'ui_colors', True) else 'off'}")
        print(f"readline : {'on' if getattr(self.settings, 'ui_readline', True) else 'off'}")
        print(f"complete : {'on' if getattr(self.settings, 'ui_completions', True) else 'off'}")

    def list_providers(self) -> None:
        """Print known providers."""
        _print_header(self._color("providers", "cyan"))
        for key, label in _list_known_providers().items():
            print(f"- {key:10s} : {label}")

    def use(self, provider: str) -> None:
        """Switch to a different provider and refresh adapter."""
        if not provider:
            print("usage: use <provider>")
            return
        self.provider = provider.lower().strip()
        self._ensure_adapter()
        if not self.adapter:
            print(f"error: unknown or unavailable provider '{provider}'")
        else:
            # Persist provider change
            self.settings.last_provider = self.provider
            with contextlib.suppress(Exception):
                save_settings(self.settings)
            print(self._color(f"using provider '{self.provider}'", "green"))

    def set_model(self, model: Optional[str]) -> None:
        """Set or show the current model override."""
        if not model:
            print(self._effective_model())
            return
        self.model_override = model
        # Persist model override (None indicates adapter default)
        self.settings.last_model = self.model_override
        with contextlib.suppress(Exception):
            save_settings(self.settings)
        print(f"model set to '{self.model_override}'")

    def set_stream(self, stream: Optional[str], live: Optional[str]) -> None:
        """Configure stream and live flags.

        Parameters accept simple tokens:
        - stream: on|off (optional)
        - live: live|nolive (optional)
        """
        if stream:
            self.stream = stream.lower() in {"on", "1", "true", "yes", "y"}
        if live:
            self.live = live.lower() in {"live", "on", "1", "true", "yes", "y"}
        # Persist stream/live toggles
        self.settings.last_stream = bool(self.stream)
        self.settings.last_live = bool(self.live)
        with contextlib.suppress(Exception):
            save_settings(self.settings)
        print(self._color(f"stream={'on' if self.stream else 'off'}, live={'on' if self.live else 'off'}", "yellow"))

    def options(self, tokens: list[str]) -> None:
        """Configure persistent CLI options and apply immediately.

        This is a thin dispatcher; individual sub-commands are handled by
        dedicated helpers to keep complexity low.
        """
        if not tokens:
            self._opt_show()
            return
        cmd = tokens[0].lower()
        if cmd == "verbosity":
            self._opt_set_verbosity(tokens)
        elif cmd == "logfile":
            self._opt_logfile(tokens)
        elif cmd in {"colors", "readline", "complete"}:
            self._opt_toggle(cmd, tokens)
        else:
            print("unknown options command — see 'options' for help")

    def _opt_show(self) -> None:
        """Print current options and usage help."""
        _print_header(self._color("options", "cyan"))
        print(f"verbosity : {self.settings.verbosity}")
        print(f"log file  : {self.settings.log_file_path if self.settings.log_to_file else 'disabled'}")
        print(f"colors    : {'on' if getattr(self.settings, 'ui_colors', True) else 'off'}")
        print(f"readline  : {'on' if getattr(self.settings, 'ui_readline', True) else 'off'}")
        print(f"complete  : {'on' if getattr(self.settings, 'ui_completions', True) else 'off'}")
        print("\nCommands:")
        print("  options verbosity <LEVEL>")
        print("      LEVEL: DEBUG|INFO|WARNING|ERROR|CRITICAL (synonyms: verbose, low, med/medium, warn, high, err, crit, quiet, silent)")
        print("  options logfile on [<path>]")
        print("  options logfile off")
        print("  options colors on|off")
        print("  options readline on|off")
        print("  options complete on|off")
        print("\nAliases:")
        print("  verbosity <LEVEL>")
        print("  logfile on|off [<path>]")
        print("  colors on|off  |  readline on|off  |  complete on|off")

    def _opt_set_verbosity(self, tokens: list[str]) -> None:
        """Set verbosity from tokens; validates synonyms and applies logging."""
        if len(tokens) < 2 or tokens[1].lower() in {"help", "?"}:
            print("usage: options verbosity <DEBUG|INFO|WARNING|ERROR|CRITICAL>")
            print("       synonyms: verbose, low, med/medium, warn, high, err, crit, quiet, silent")
            return
        level = _parse_verbosity(tokens[1])
        if not level:
            print("error: invalid verbosity value; use one of DEBUG|INFO|WARNING|ERROR|CRITICAL (or synonyms)")
            return
        self.settings.verbosity = level
        ok, err = save_settings(self.settings)
        if not ok:
            print(f"warning: failed to save settings: {err}")
        apply_logging(self.settings)
        print(f"verbosity set to {self.settings.verbosity}")

    def _opt_logfile(self, tokens: list[str]) -> None:
        """Enable/disable logfile and normalize an optional path."""
        if len(tokens) < 2:
            print("usage: options logfile on [<path>] | options logfile off")
            return
        onoff = tokens[1].lower()
        if onoff == "on":
            self.settings.log_to_file = True
            if len(tokens) >= 3:
                raw_path = " ".join(tokens[2:])
                self.settings.log_file_path = normalize_log_path(raw_path)
            ok, err = save_settings(self.settings)
            if not ok:
                print(f"warning: failed to save settings: {err}")
            apply_logging(self.settings)
            print(f"file logging enabled → {self.settings.log_file_path}")
            return
        if onoff == "off":
            self.settings.log_to_file = False
            ok, err = save_settings(self.settings)
            if not ok:
                print(f"warning: failed to save settings: {err}")
            apply_logging(self.settings)
            print("file logging disabled")
            return
        print("usage: options logfile on [<path>] | options logfile off")

    def _opt_toggle(self, field: str, tokens: list[str]) -> None:
        """Toggle simple boolean UI flags: colors, readline, complete."""
        if len(tokens) < 2:
            print(f"usage: options {field} on|off")
            return
        new_val = tokens[1].lower() in {"on", "1", "true", "yes", "y"}
        if field == "colors":
            self.settings.ui_colors = new_val
        elif field == "readline":
            self.settings.ui_readline = new_val
        elif field == "complete":
            self.settings.ui_completions = new_val
        ok, err = save_settings(self.settings)
        if not ok:
            print(f"warning: failed to save settings: {err}")
        # Reinitialize UI when readline or completions change
        if field in {"readline", "complete"}:
            self._init_ui()
        label = {
            "colors": "colors",
            "readline": "readline",
            "complete": "completions",
        }[field]
        print(f"{label} {'enabled' if new_val else 'disabled'}")

    def _run(self, prompt: str) -> None:
        """Execute a single prompt with current settings and print output."""
        if not prompt:
            print("enter a prompt or use: ask <text>")
            return
        if not self.adapter:
            print("error: no adapter for provider")
            return
        req = ChatRequest(model=self._effective_model(), messages=[Message(role="user", content=prompt)])
        try:
            if self.stream and streaming_capable(self.adapter):
                if self.live:
                    self._run_stream_live(req)
                else:
                    self._run_stream_buffered(req)
            else:
                resp = self.adapter.chat(req)
                print(resp.text or "")
        except Exception as e:
            print(self._color(f"error: {e}", "red"))

    def _run_stream_live(self, req: ChatRequest) -> None:
        """Stream tokens live, suppressing console logs during stream."""
        _ = _live_stream(self.adapter, req)  # type: ignore[arg-type]

    def _run_stream_buffered(self, req: ChatRequest) -> None:
        """Buffer streamed tokens then print once; suppress console logs while buffering."""
        parts: list[str] = []
        with _suppress_console_logs():
            # type: ignore[arg-type]
            parts.extend(ev.delta for ev in self.adapter.stream_chat(req) if ev.delta)  # noqa: E501
        print("".join(parts))

    def chat(self) -> None:
        """Enter multi-line prompt mode; finish with an empty line."""
        print("Enter message. End with an empty line:")
        lines: list[str] = []
        while True:
            line = _readline("")
            if line.lower() in {"quit", "exit"}:
                return
            if line == "":
                break
            lines.append(line)
        self._run("\n".join(lines))

    def ask(self, text: str) -> None:
        """Send a one-line prompt using current settings."""
        self._run(text)

    @staticmethod
    def help() -> None:
        """Print available commands and usage."""
        _print_header("help")
        print("status                         Show current settings")
        print("providers                      List known providers")
        print("use <provider>                Switch provider")
        print("model [<id>]                  Show or set model")
        print("stream [on|off] [live|nolive] Toggle streaming and live printing")
        print("options [..]                  Configure persistent options (verbosity, log file)")
        print("ask <prompt>                  Send a one-line prompt")
        print("chat                           Enter multi-line prompt mode")
        print("help                           Show this help")
        print("quit | exit                    Leave the terminal")


def _parse_stream_args(tokens: list[str]) -> Tuple[Optional[str], Optional[str]]:
    """Extract optional stream and live tokens from a token list."""
    st = lv = None
    for t in tokens:
        tl = t.lower()
        if tl in {"on", "off", "true", "false", "live", "nolive", "y", "n", "1", "0"}:
            if tl in {"live", "nolive"}:
                lv = tl
            else:
                st = tl
    return st, lv


def handle_shell(args: argparse.Namespace) -> int:
    """Run the interactive developer terminal.

    Parameters
    ----------
    args: argparse.Namespace
        Parsed CLI args with ``provider``, ``model``, ``stream`` and ``live`` flags.

    Returns
    -------
    int
        Exit code (``0`` on normal exit).
    """
    session = DevSession(
        provider=(args.provider or "openrouter").lower().strip(),
        model=args.model,
        stream=getattr(args, "stream", None),
        live=getattr(args, "live", None),
    )
    print("Developer Terminal — type 'help' for commands.\n")
    session.status()

    while True:
        raw = _readline("dev> ").strip()
        if raw.lower() in {"quit", "exit"}:
            try:
                if getattr(session, "_history_path", None):
                    readline.write_history_file(session._history_path)  # type: ignore[arg-type]
            except Exception as _exc:  # pragma: no cover - best-effort history persistence
                _ = _exc
            return 0
        if not raw:
            continue

        parts = raw.split()
        cmd, args_list = parts[0].lower(), parts[1:]
        if not session_dispatch(session, cmd, args_list):
            _handle_unknown_command(session, cmd)

def session_dispatch(session: DevSession, cmd: str, args_list: list[str]) -> bool:
    """Dispatch a single command to the appropriate `DevSession` method.

    Returns True if handled, False if unknown.
    """
    if cmd == "help":
        session.help()
        return True
    if cmd == "status":
        session.status()
        return True
    if cmd == "providers":
        session.list_providers()
        return True
    if cmd == "use":
        session.use(args_list[0] if args_list else "")
        return True
    if cmd == "model":
        session.set_model(args_list[0] if args_list else None)
        return True
    if cmd == "stream":
        st, lv = _parse_stream_args(args_list)
        session.set_stream(st, lv)
        return True
    if cmd == "options":
        session.options(args_list)
        return True
    if cmd in {"logfile", "verbosity", "colors", "readline", "complete"}:
        session.options([cmd, *args_list])
        return True
    if cmd == "ask":
        text = " ".join(args_list)
        session.ask(text)
        return True
    if cmd == "chat":
        session.chat()
        return True
    return False

def _handle_unknown_command(session: DevSession, cmd: str) -> None:
    """Print a helpful message for unknown commands with suggestions."""
    suggestions = []
    try:
        suggestions = [c for c in getattr(session, "_commands", []) if c.startswith(cmd)]
    except Exception:
        suggestions = []
    msg = "unknown command — try 'help'"
    if suggestions:
        msg += "; did you mean: " + ", ".join(suggestions[:3])
    try:
        print(session._color(msg, "red"))
    except Exception:
        print(msg)
