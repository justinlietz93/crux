"""GeminiProvider adapter.

Uses google-generativeai (google-generativeai>=0.8.0) GenerativeModel API.
Supports simple text chat and heuristic JSON output capture.
"""

from __future__ import annotations

import time
from typing import Optional

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # type: ignore

from ..base.constants import MISSING_API_KEY_ERROR, STRUCTURED_STREAMING_UNSUPPORTED
from ..base.streaming import streaming_supported
from ..base.errors import ErrorCode, ProviderError, classify_exception
from ..base.interfaces import (
    HasDefaultModel,
    LLMProvider,
    ModelListingProvider,
    SupportsJSONOutput,
)
from ..base.logging import LogContext, get_logger, normalized_log_event
from ..base.models import (
    ChatRequest,
    ChatResponse,
    ContentPart,
    ProviderMetadata,
)
from ..base.repositories.model_registry.repository import ModelRegistryRepository
from ..base.resilience.retry import RetryConfig, retry
from ..base.streaming import ChatStreamEvent
from ..base.streaming import BaseStreamingAdapter
from ..base.capabilities import record_observation
from ..base.utils.messages import extract_system_and_user
from ..config.defaults import GEMINI_DEFAULT_MODEL


def _default_model() -> str:
    """Return the centralized default model for Gemini.

    Provides the default model identifier for the Gemini provider, ensuring a single source of truth for defaults.

    Returns:
        str: The default Gemini model name.
    """
    return GEMINI_DEFAULT_MODEL


class GeminiProvider(
    LLMProvider, SupportsJSONOutput, ModelListingProvider, HasDefaultModel
):
    """Gemini provider for chat and model listing using the Google Generative AI API.

    This class implements synchronous and streaming chat, model listing, and JSON output support for the Gemini provider.
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        registry: Optional[ModelRegistryRepository] = None,
    ) -> None:
        """Initialize the GeminiProvider with API key, model, and registry.

        Sets up the provider with the specified API key, model, and model registry. Configures the Gemini SDK if available.

        Args:
            api_key: The API key for authenticating with Gemini.
            model: The default model to use for requests.
            registry: Optional model registry for provider integration.
        """
        self._api_key = api_key
        self._model = model or _default_model()
        self._registry = registry or ModelRegistryRepository()
        if genai and api_key:
            genai.configure(api_key=api_key)
        self._logger = get_logger("providers.gemini")

    @property
    def provider_name(self) -> str:
        """Return the name of the provider.

        This property identifies the provider as 'gemini'.

        Returns:
            str: The provider name.
        """
        return "gemini"

    def default_model(self) -> Optional[str]:
        """Return the default model name for the Gemini provider.

        Provides the model identifier used by default for chat requests.

        Returns:
            Optional[str]: The default model name.
        """
        return self._model

    def supports_json_output(self) -> bool:
        """Return True if the Gemini provider supports JSON output.

        Indicates that this provider can generate structured JSON responses.

        Returns:
            bool: True if JSON output is supported.
        """
        return True

    def list_models(self, refresh: bool = False):
        """List available Gemini models from the model registry.

        Retrieves the list of models for the Gemini provider, optionally refreshing the cache.

        Args:
            refresh: If True, refresh the model list from the source.

        Returns:
            List of available models for the Gemini provider.
        """
        return self._registry.list_models("gemini", refresh=refresh)

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Generate a synchronous chat response using the Gemini model.

        Handles chat requests with retry logic and optional JSON schema support. Returns a ChatResponse containing the generated text and metadata.

        Args:
            request: The chat request containing messages and parameters.

        Returns:
            ChatResponse: The response object with generated text and metadata.
        """
        model = request.model or self._model
        ctx = LogContext(provider=self.provider_name, model=model)
        if genai is None:
            meta = ProviderMetadata(
                provider_name=self.provider_name,
                model_name=model,
                extra={"error": "google-generativeai SDK not installed"},
            )
            return ChatResponse(text=None, parts=None, raw=None, meta=meta)
        _system_message, user_content = extract_system_and_user(request.messages)
        if not self._api_key:  # Early credential check
            meta = ProviderMetadata(
                provider_name=self.provider_name,
                model_name=model,
                extra={"error": MISSING_API_KEY_ERROR},
            )
            return ChatResponse(text=None, parts=None, raw=None, meta=meta)
        is_structured = request.response_format == "json_object"

        gen_model = self._build_model(model, request)
        normalized_log_event(
            self._logger,
            "chat.start",
            ctx,
            phase="start",
            has_tools=bool(request.tools),
            has_schema=bool(request.json_schema),
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            tokens=None,
            emitted=None,
            attempt=None,
            error_code=None,
        )
        t0 = time.perf_counter()
        retry_config = self._build_retry_config(ctx)
        try:
            resp = retry(retry_config)(
                lambda: self._start_generation(
                    gen_model, user_content, request.tools, stream=False
                )
            )()
            latency_ms = (time.perf_counter() - t0) * 1000.0
            normalized_log_event(
                self._logger,
                "chat.end",
                ctx,
                phase="finalize",
                latency_ms=latency_ms,
                tokens=None,
                emitted=None,
                attempt=None,
                error_code=None,
            )
        except ProviderError as e:  # pragma: no cover
            normalized_log_event(
                self._logger,
                "chat.error",
                ctx,
                phase="finalize",
                error=str(e),
                error_code=e.code.value,
                tokens=None,
                emitted=None,
                attempt=None,
            )
            meta = ProviderMetadata(
                provider_name=self.provider_name,
                model_name=model,
                latency_ms=None,
                extra={"error": e.message, "code": e.code.value},
            )
            return ChatResponse(text=None, parts=None, raw=None, meta=meta)
        except Exception as e:  # pragma: no cover
            code = classify_exception(e)
            normalized_log_event(
                self._logger,
                "chat.error",
                ctx,
                phase="finalize",
                error=str(e),
                error_code=code.value,
                tokens=None,
                emitted=None,
                attempt=None,
            )
            meta = ProviderMetadata(
                provider_name=self.provider_name,
                model_name=model,
                latency_ms=None,
                extra={"error": str(e), "code": code.value},
            )
            return ChatResponse(text=None, parts=None, raw=None, meta=meta)

        text = self._extract_text_from_response(resp)
        # 'max_output_tokens' is a public API parameter name, not a credential/secret.
        # Record json_output capability when structured response requested and succeeded
        try:
            if is_structured:
                record_observation(self.provider_name, model, "json_output", True)
        except Exception:
            ...

        meta = ProviderMetadata(
            provider_name=self.provider_name,
            model_name=model,
            latency_ms=latency_ms,
            token_param_used="max_output_tokens",  # nosec B106
            extra={"is_structured": is_structured},
        )
        parts = [ContentPart(type="text", text=text)] if text else None
        return ChatResponse(text=text or None, parts=parts, raw=None, meta=meta)

    # ---- Streaming ----
    def supports_streaming(self) -> bool:  # runtime-checkable capability
        """Return True if google-generativeai SDK installed and API key set."""
        return streaming_supported(
            genai,
            require_api_key=True,
            api_key_getter=lambda: self._api_key,  # type: ignore[attr-defined]
        )

    def stream_chat(self, request: ChatRequest):
        """Stream chat responses using the unified BaseStreamingAdapter.

        This replaces the bespoke loop with a centralized adapter that:
        - Starts the native SDK stream under a start-phase retry/timeout policy
        - Translates google-generativeai chunks into text deltas
        - Emits exactly one terminal event with metrics

        Notes:
        - Gemini SDK does not support structured streaming (tools/JSON) here;
          such requests are short-circuited with a terminal error event.
        """
        model = request.model or self._model
        ctx = LogContext(provider=self.provider_name, model=model)
        normalized_log_event(
            self._logger,
            "stream.start",
            ctx,
            phase="start",
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tokens=None,
            emitted=None,
            attempt=None,
            error_code=None,
        )
        # Capability and credential checks
        if genai is None:
            normalized_log_event(
                self._logger,
                "stream.error",
                ctx,
                phase="start",
                error="google-generativeai SDK not installed",
            )
            yield ChatStreamEvent(
                provider=self.provider_name,
                model=model,
                delta=None,
                finish=True,
                error="google-generativeai SDK not installed",
            )
            return
        _system_message, user_content = extract_system_and_user(request.messages)
        if not self._api_key:
            normalized_log_event(
                self._logger,
                "stream.error",
                ctx,
                phase="start",
                error=MISSING_API_KEY_ERROR,
            )
            yield ChatStreamEvent(
                provider=self.provider_name,
                model=model,
                delta=None,
                finish=True,
                error=MISSING_API_KEY_ERROR,
            )
            return
        if (
            request.response_format == "json_object"
            or request.json_schema
            or request.tools
        ):
            yield ChatStreamEvent(
                provider=self.provider_name,
                model=model,
                delta=None,
                finish=True,
                error=STRUCTURED_STREAMING_UNSUPPORTED,
            )
            # Persist that structured streaming is not supported when explicitly requested
            try:
                record_observation(self.provider_name, model, "structured_streaming", False)
            except Exception:
                ...
            return

        gen_model = self._build_model(model, request)

        def _starter():
            retry_cfg = self._build_retry_config(ctx, phase="stream.start")
            return retry(retry_cfg)(
                lambda: self._start_generation(
                    gen_model, user_content, request.tools, stream=True
                )
            )()

        def _translator(chunk) -> Optional[str]:  # noqa: ANN001 - external object
            return self._extract_text_from_chunk(chunk)

        adapter = BaseStreamingAdapter(
            ctx=ctx,
            provider_name=self.provider_name,
            model=model,
            starter=_starter,
            translator=_translator,
            retry_config_factory=lambda phase: self._build_retry_config(ctx, phase=phase),
            logger=self._logger,
        )
        emitted_any = False
        for ev in adapter.run():
            if ev is not None and ev.delta and not emitted_any:
                emitted_any = True
                try:
                    record_observation(self.provider_name, model, "streaming", True)
                except Exception:
                    ...
            yield ev

    # -------------------- internal helpers --------------------
    def _build_model(self, model_name: str, request: ChatRequest):
        """Create and configure the Gemini GenerativeModel instance.

        Parameters:
            model_name: The Gemini model identifier to use.
            request: The `ChatRequest` carrying generation parameters.

        Returns:
            A configured `genai.GenerativeModel` instance.
        """
        if genai is None:  # defensive guard
            raise ProviderError(
                code=ErrorCode.INTERNAL,
                message="google-generativeai SDK not available",
                provider=self.provider_name,
                model=model_name,
            )
        generation_config = {}
        if request.temperature is not None:
            generation_config["temperature"] = request.temperature
        if request.max_tokens is not None:
            generation_config["max_output_tokens"] = request.max_tokens  # nosec B106
        return genai.GenerativeModel(
            model_name=model_name,
            generation_config=generation_config or None,
        )

    def _start_generation(self, gen_model, user_content, tools, *, stream: bool):
        """Start a content generation call against the Gemini SDK.

        Parameters:
            gen_model: The configured `GenerativeModel` instance.
            user_content: The textual content extracted from request messages.
            tools: Not supported for streaming here; accepted for signature parity.
            stream: Whether to request a streaming response from the SDK.

        Returns:
            The SDK response object or an iterable stream of chunks.
        """
        # Tools/JSON not supported in streaming path per provider policy.
        if stream:
            return gen_model.generate_content(user_content, stream=True)
        return gen_model.generate_content(user_content)

    def _extract_text_from_chunk(self, chunk) -> Optional[str]:
        """Translate a Gemini streaming chunk to a plain text delta.

        Attempts `chunk.text` first. If not present, inspects the first
        candidate's first content part for a `.text` field. Uses narrow
        attribute access under try/except to avoid brittle getattr chains.

        Parameters
        ----------
        chunk: Any
            Streaming chunk object from google-generativeai.

        Returns
        -------
        Optional[str]
            The text delta when available, otherwise None.
        """
        try:
            txt_attr = chunk.text  # type: ignore[attr-defined]
            if txt_attr:
                return txt_attr
        except AttributeError:
            # chunk has no `.text`; fall through to candidates path
            ...
        except Exception:
            return None
        try:
            candidates = chunk.candidates  # type: ignore[attr-defined]
            if candidates and isinstance(candidates, list):
                parts = candidates[0].content.parts  # type: ignore[attr-defined]
                if parts:
                    txt = parts[0].text  # type: ignore[attr-defined]
                    return txt or None
        except Exception:
            return None
        return None

    def _extract_text_from_response(self, resp) -> str:
        """Extract final text from a non-stream Gemini response.

        Uses narrow attribute access with try/except to read `.text`. Returns
        an empty string when not present.

        Parameters
        ----------
        resp: Any
            The result object from `GenerativeModel.generate_content`.

        Returns
        -------
        str
            The response text or empty string if absent.
        """
        try:
            return resp.text or ""  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            return ""

    def _build_retry_config(self, ctx: LogContext, phase: str = "chat.start") -> RetryConfig:
        """Construct a retry configuration with standardized attempt logging.

        Parameters:
            ctx: Structured logging context for the provider/model.
            phase: The operation phase label (e.g., "stream.start").

        Returns:
            A `RetryConfig` instance with attempt logging wired to normalized events.
        """
        def _attempt_logger(*, attempt: int, max_attempts: int, delay: float | None, error: ProviderError | None) -> None:
            normalized_log_event(
                self._logger,
                "retry",
                ctx,
                stage="retry",
                phase=phase,
                attempt=attempt,
                max_attempts=max_attempts,
                delay=delay,
                failure_class=error.code.value if error else None,
                fallback_used=False,
            )

        return RetryConfig(attempt_logger=_attempt_logger)
