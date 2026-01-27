# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import argparse
import yaml

from .common import BaseTest
from c7n.commands import validate as validate_yaml_policies


class CommandsValidateTest(BaseTest):

    def test_duplicate_key(self):
        # try dupes with top level keys
        yaml_validate_options = argparse.Namespace(
            command="c7n.commands.validate",
            config=None,
            configs=[
                "tests/data/test_policies/dup-policies.yml"],
            debug=False,
            subparser="validate",
            verbose=False,
            check_deprecations="yes",
        )

        with self.assertRaises(yaml.YAMLError) as err:
            validate_yaml_policies(yaml_validate_options)
        self.assertTrue('found duplicate key' in str(err.exception))

        # try dupes with policy attributes
        yaml_validate_options = argparse.Namespace(
            command="c7n.commands.validate",
            config=None,
            configs=[
                "tests/data/test_policies/dup-policy-keys.yml"],
            debug=False,
            subparser="validate",
            verbose=False,
            check_deprecations="yes",
        )

        with self.assertRaises(yaml.YAMLError) as err:
            validate_yaml_policies(yaml_validate_options)
        self.assertTrue('found duplicate key' in str(err.exception))

    def test_failed_validation(self):
        yaml_validate_options = argparse.Namespace(
            command="c7n.commands.validate",
            config=None,
            configs=[
                "tests/data/test_policies/ebs-BADVALIDATION.yml",
                "tests/data/test_policies/ami-GOODVALIDATION.yml",
            ],
            debug=False,
            subparser="validate",
            verbose=False,
            check_deprecations="yes",
        )
        log_output = self.capture_logging("custodian.commands")
        with self.assertRaises((SystemExit, ValueError)) as exit:
            validate_yaml_policies(yaml_validate_options)
        # if there is a bad policy in the batch being validated, there should be an exit 1
        self.assertEqual(exit.exception.code, 1)

        # ...and it should report accurate per-file validation status individually
        validation_output = log_output.getvalue()
        self.assertIn(
            "Configuration invalid: tests/data/test_policies/ebs-BADVALIDATION.yml",
            validation_output
        )
        self.assertIn(
            "Configuration valid: tests/data/test_policies/ami-GOODVALIDATION.yml",
            validation_output
        )

        yaml_validate_options.configs.remove(
            "tests/data/test_policies/ebs-BADVALIDATION.yml"
        )
        # if there are only good policy, it should exit none
        self.assertIsNone(validate_yaml_policies(yaml_validate_options))
