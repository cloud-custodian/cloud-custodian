# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from io import BytesIO

import pytest
from botocore.response import StreamingBody

from tests.zpill import deserialize, serialize, utc


class TestSerialize:

    def test_serialize_datetime(self):
        dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=utc)
        result = serialize(dt)
        assert result == {
            "__class__": "datetime",
            "year": 2023,
            "month": 1,
            "day": 1,
            "hour": 12,
            "minute": 0,
            "second": 0,
            "microsecond": 0,
        }

    def test_serialize_bytes(self):
        result = serialize(b"hello")
        assert result == "aGVsbG8="

    def test_serialize_unknown_type(self):
        with pytest.raises(TypeError, match="not serializable"):
            serialize("hello")


class TestDeserialize:

    def test_deserialize_datetime(self):
        obj = {"__class__": "datetime", "year": 2023, "month": 1, "day": 1}
        result = deserialize(obj)
        assert isinstance(result, datetime)
        assert result == datetime(2023, 1, 1, tzinfo=utc)

    def test_deserialize_datetime_with_module_does_not_mutate_input(self):
        """Ensure deserialize pops __module__ from its working copy, not the original dict."""
        obj = {
            "__class__": "datetime",
            "__module__": "datetime",
            "year": 2023,
            "month": 1,
            "day": 1,
        }
        original = dict(obj)
        result = deserialize(obj)
        assert isinstance(result, datetime)
        assert obj == original

    def test_deserialize_streaming_body(self):
        obj = {"__class__": "StreamingBody", "body": b"dGVzdA=="}
        result = deserialize(obj)
        assert isinstance(result, StreamingBody)
        assert result.read() == b"test"

    def test_deserialize_unrecognized_returns_as_is(self):
        obj = {"foo": "bar"}
        result = deserialize(obj)
        assert result == {"foo": "bar"}
