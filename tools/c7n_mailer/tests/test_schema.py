# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import unittest

import c7n_mailer.cli as cli
import jsonschema
import jsonschema.exceptions as exceptions


class MailerSchemaTest(unittest.TestCase):
    def test_validate_secured_string(self):
        property_schema = {"type": "object", "properties": {"test": cli.SECURED_STRING_SCHEMA}}
        jsonschema.validate({"test": "raw_string"}, property_schema)
        jsonschema.validate(
            {"test": {"type": "azure.keyvault", "secret": "https://secret_uri"}}, property_schema
        )

        with self.assertRaises(exceptions.ValidationError):
            jsonschema.validate({"test": {"wrong": "value"}}, property_schema)
            jsonschema.validate({"test": {"secret": "https://secret_uri"}}, property_schema)
            jsonschema.validate(
                {"test": {"type": "azure.keyvault", "secret": "https://secret_uri", "extra": "e"}},
                property_schema,
            )
