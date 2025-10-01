"""Legacy shim deprecation test (retired).

This file originally tested `call_with_retry` deprecation semantics. The shim
has been fully removed; keep this module as a no-op skip so historical
references don't break pre-push provider test gating.
"""

from __future__ import annotations

import pytest


pytest.skip("call_with_retry retired; test removed", allow_module_level=True)
