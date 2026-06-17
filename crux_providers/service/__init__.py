from __future__ import annotations

# Provider service package init.
# The FastAPI streaming route lives in chat_stream and is registered when the
# app module (crux_providers.service.app) is imported, NOT here. Importing this
# package (e.g. for service.db) must not pull in FastAPI.
