from __future__ import annotations

from crux_providers.base.openai_style_parts.structured import translate_openai_structured_chunk
from crux_providers.base.dto.structured_output import StructuredOutputDTO


class _Fn:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _Call:
    def __init__(self, function):
        self.function = function


class _Delta:
    def __init__(self, tool_calls=None):
        self.tool_calls = tool_calls or []


class _Choice:
    def __init__(self, delta):
        self.delta = delta


class _Chunk:
    def __init__(self, choices, chunk_id=None):
        self.choices = choices
        self.id = chunk_id


def test_translator_partial_args_without_name():
    chunk = _Chunk([_Choice(_Delta([_Call(_Fn(name=None, arguments='{"a": 1'))]))])
    dto = translate_openai_structured_chunk(chunk)
    assert isinstance(dto, StructuredOutputDTO)  # nosec B101 - test assertion
    assert dto.partial == '{"a": 1'  # nosec B101 - test assertion
    assert dto.metadata == {}  # nosec B101 - test assertion


def test_translator_name_only():
    chunk = _Chunk([_Choice(_Delta([_Call(_Fn(name='search', arguments=None))]))])
    dto = translate_openai_structured_chunk(chunk)
    assert dto is not None  # nosec B101 - test assertion
    assert dto.metadata.get('function_name') == 'search'  # nosec B101 - test assertion
    assert dto.partial is None  # nosec B101 - test assertion


def test_translator_parses_complete_json_args():
    chunk = _Chunk([_Choice(_Delta([_Call(_Fn(name='add', arguments='{"x":10}'))]))])
    dto = translate_openai_structured_chunk(chunk)
    assert dto is not None  # nosec B101 - test assertion
    assert dto.function_call is not None  # nosec B101 - test assertion
    assert dto.function_call.name == 'add'  # nosec B101 - test assertion
    assert dto.function_call.arguments == {"x": 10}  # nosec B101 - test assertion


def test_translator_accepts_mapping_arguments():
    chunk = _Chunk([_Choice(_Delta([_Call(_Fn(name='sum', arguments={"a": 1, "b": 2}))]))])
    dto = translate_openai_structured_chunk(chunk)
    assert dto is not None  # nosec B101 - test assertion
    assert dto.function_call is not None  # nosec B101 - test assertion
    assert dto.function_call.name == 'sum'  # nosec B101 - test assertion
    assert dto.function_call.arguments == {"a": 1, "b": 2}  # nosec B101 - test assertion
