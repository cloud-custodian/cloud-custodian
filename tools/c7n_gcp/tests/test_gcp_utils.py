# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_gcp.utils import parse_protobuf_duration_to_seconds
from gcp_common import BaseTest


class TestGcpUtils(BaseTest):

    def test_parse_protobuf_duration_to_seconds_valid(self):
        self.assertEqual(parse_protobuf_duration_to_seconds("2592000s"), 2592000)

    def test_parse_protobuf_duration_to_seconds_trims_whitespace(self):
        self.assertEqual(parse_protobuf_duration_to_seconds("  3600s  "), 3600)

    def test_parse_protobuf_duration_to_seconds_none(self):
        self.assertIsNone(parse_protobuf_duration_to_seconds(None))

    def test_parse_protobuf_duration_to_seconds_invalid_suffix(self):
        with self.assertRaisesRegex(ValueError, "Expected format <seconds>s"):
            parse_protobuf_duration_to_seconds("3600")

    def test_parse_protobuf_duration_to_seconds_invalid_numeric_value(self):
        with self.assertRaisesRegex(ValueError, "Expected format <seconds>s"):
            parse_protobuf_duration_to_seconds("not-a-numbers")

    def test_parse_protobuf_duration_to_seconds_invalid_type(self):
        with self.assertRaisesRegex(
            ValueError,
            "Expected protobuf duration as string",
        ):
            parse_protobuf_duration_to_seconds(3600)
