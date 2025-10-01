from __future__ import annotations

import json

from crux_providers.base.dto.function_call import FunctionCallDTO
from crux_providers.base.dto.structured_output import StructuredOutputDTO


def test_function_call_dto_round_trip():
    payload = {"x": 1, "y": [1, 2, 3], "flag": True}
    fc = FunctionCallDTO(name="add", arguments=payload)
    serialized = fc.model_dump()
    # Ensure keys and values persist round-trip
    assert serialized["name"] == "add"  # nosec B101 - test assertion
    assert serialized["arguments"] == payload  # nosec B101 - test assertion


def test_structured_output_dto_shapes():
    # function_call only
    fc = FunctionCallDTO(name="search", arguments={"q": "hello"})
    so = StructuredOutputDTO(function_call=fc)
    assert so.function_call is not None  # nosec B101 - test assertion
    assert so.partial is None  # nosec B101 - test assertion
    # partial only
    so2 = StructuredOutputDTO(partial="part-1")
    assert so2.partial == "part-1"  # nosec B101 - test assertion
    assert so2.function_call is None  # nosec B101 - test assertion
    # metadata present
    so3 = StructuredOutputDTO(metadata={"provider": "unit"})
    assert so3.metadata.get("provider") == "unit"  # nosec B101 - test assertion


def test_structured_output_dto_json_serializable():
    fc = FunctionCallDTO(name="toolx", arguments={"a": 10})
    so = StructuredOutputDTO(function_call=fc, metadata={"id": "123"})
    # pydantic model_dump_json returns JSON string; also ensure standard json works
    dumped = so.model_dump()
    json.dumps(dumped)  # Should not raise
