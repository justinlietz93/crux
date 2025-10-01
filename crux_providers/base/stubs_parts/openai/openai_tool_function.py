"""OpenAI tool function protocol.

Defines the minimal structural contract for function-call style tool metadata
emitted by OpenAI streaming chunks.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class OpenAIToolFunction(Protocol):
    """Protocol for an OpenAI tool function descriptor.

    Attributes
    ----------
    name: Optional[str]
        The tool function name when known.
    arguments: Optional[str]
        The JSON fragment (as a string) representing partial or complete
        function arguments during streaming.
    """

    name: Optional[str]
    arguments: Optional[str]
