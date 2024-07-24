# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import os
import sys
import argparse

from argparse import ArgumentTypeError
from datetime import datetime, timedelta

from c7n import cli, version, commands
from c7n.resolver import ValuesFrom
from c7n.resources import aws
from c7n.schema import ElementSchema, generate
from c7n.utils import yaml_dump, yaml_load
from c7n.commands import LoadSessionPolicyJson

import pytest
from .common import BaseTest, TextTestIO


class CliTest(BaseTest):
    """ A subclass of BaseTest with some handy functions for CLI related tests. """

    def patch_account_id(self):

        def test_account_id(options):
            options.account_id = self.account_id

        self.patch(aws, "_default_account_id", test_account_id)

    def get_output(self, argv):
        """ Run cli.main with the supplied argv and return the output. """
        out, _ = self.run_and_expect_success(argv)
        return out

    def capture_output(self):
        out = TextTestIO()
        err = TextTestIO()
        self.patch(sys, "stdout", out)
        self.patch(sys, "stderr", err)
        return out, err

    def run_and_expect_success(self, argv):
        """ Run cli.main() with supplied argv and expect normal execution. """
        self.patch_account_id()
        self.patch(sys, "argv", argv)
        out, err = self.capture_output()
        try:
            cli.main()
        except SystemExit as e:
            self.fail(
                "Expected sys.exit would not be called. Exit code was ({})".format(
                    e.code
                )
            )
        return out.getvalue(), err.getvalue()

    def run_and_expect_failure(self, argv, exit_code):
        """ Run cli.main() with supplied argv and expect exit_code. """
        self.patch_account_id()
        self.patch(sys, "argv", argv)
        out, err = self.capture_output()
        # clear_resources()
        with self.assertRaises(SystemExit) as cm:
            cli.main()
        self.assertEqual(cm.exception.code, exit_code)
        return out.getvalue(), err.getvalue()

    def run_and_expect_exception(self, argv, exception):
        """ Run cli.main() with supplied argv and expect supplied exception. """
        self.patch_account_id()
        self.patch(sys, "argv", argv)
        # clear_resources()
        try:
            cli.main()
        except exception:
            return
        self.fail("Error: did not raise {}.".format(exception))


class UtilsTest(BaseTest):

    def test_key_val_pair(self):
        self.assertRaises(ArgumentTypeError, cli._key_val_pair, "invalid option")
        param = "day=today"
        self.assertIs(cli._key_val_pair(param), param)


class VersionTest(CliTest):

    def test_version(self):
        output = self.get_output(["custodian", "version"])
        self.assertEqual(output.strip(), version.version)

    def test_debug_version(self):
        output = self.get_output(["custodian", "version", "--debug"])
        self.assertIn(version.version, output)
        self.assertIn('botocore==', output)
        self.assertIn('python-dateutil==', output)


def check_left():
    try:
        import c7n_left  # noqa: F401
    except ImportError:
        return {"condition": True, "reason": "c7n_left not installed"}
    return {"condition": False, "reason": "c7n_left installed"}


class ValidateTest(CliTest):

    def test_invalidate_structure_exit(self):
        invalid_policies = {"policies": [{"name": "foo"}]}
        yaml_file = self.write_policy_file(invalid_policies)
        self.run_and_expect_failure(["custodian", "validate", yaml_file], 1)

    @pytest.mark.skipif(**check_left())
    def test_validate_terraform(self):
        policies = {
            "policies": [
                {"name": "tfx",
                 "resource": "terraform.*",
                 "filters": ["taggable"]}
            ]
        }
        yaml_file = self.write_policy_file(policies)
        self.run_and_expect_success(["custodian", "validate", yaml_file])

    def test_validate(self):
        invalid_policies = {
            "policies": [
                {
                    "name": "foo",
                    "resource": "s3",
                    "filters": [{"tag:custodian_tagging": "not-null"}],
                    "actions": [
                        {"type": "untag", "tags": {"custodian_cleanup": "yes"}}
                    ],
                }
            ]
        }
        yaml_file = self.write_policy_file(invalid_policies)
        json_file = self.write_policy_file(invalid_policies, format="json")

        # YAML validation
        self.run_and_expect_exception(["custodian", "validate", yaml_file], SystemExit)

        # JSON validation
        self.run_and_expect_failure(["custodian", "validate", json_file], 1)

        # no config files given
        self.run_and_expect_failure(["custodian", "validate"], 1)

        # nonexistent file given
        self.run_and_expect_exception(
            ["custodian", "validate", "fake.yaml"], ValueError
        )

        valid_policies = {
            "policies": [
                {
                    "name": "foo",
                    "resource": "s3",
                    "filters": [{"tag:custodian_tagging": "not-null"}],
                    "actions": [{"type": "tag", "tags": {"custodian_cleanup": "yes"}}],
                }
            ]
        }
        yaml_file = self.write_policy_file(valid_policies)

        self.run_and_expect_success(["custodian", "validate", yaml_file])

        # legacy -c option
        self.run_and_expect_success(["custodian", "validate", "-c", yaml_file])

        # duplicate policy names
        self.run_and_expect_failure(["custodian", "validate", yaml_file, yaml_file], 1)

    def test_deprecated(self):

        deprecated = {
            "policies": [
                {
                    "name": "foo",
                    "resource": "ec2",
                    "filters": [{"tag:custodian_tagging": "not-null"}],
                    "actions": [{"type": "unmark", "tags": ["custodian_cleanup"]}],
                }
            ]
        }
        yaml_file = self.write_policy_file(deprecated)

        self.run_and_expect_success(["custodian", "validate", yaml_file])

        # strict checking should fail as unmark is deprecated
        self.run_and_expect_failure(["custodian", "validate", "--strict", yaml_file], 1)


class SchemaTest(CliTest):

    def test_schema_outline(self):
        stdout, _ = self.run_and_expect_success([
            "custodian", "schema", "--outline", "--json", "aws"])
        data = json.loads(stdout)
        self.assertEqual(list(data.keys()), ["aws"])
        self.assertTrue(len(data['aws']) > 100)
        self.assertEqual(
            sorted(data['aws']['aws.ec2'].keys()), ['actions', 'filters'])
        self.assertTrue(len(data['aws']['aws.ec2']['actions']) > 10)

    def test_schema_alias(self):
        stdout, _ = self.run_and_expect_success([
            "custodian", "schema", "aws.network-addr"])
        self.assertIn("aws.elastic-ip:", stdout)

    def test_schema_alias_unqualified(self):
        stdout, _ = self.run_and_expect_success([
            "custodian", "schema", "network-addr"])
        self.assertIn("aws.elastic-ip:", stdout)

    def test_schema(self):

        # no options
        stdout, _ = self.run_and_expect_success(["custodian", "schema"])
        data = yaml_load(stdout)
        assert data['resources']

        # summary option
        self.run_and_expect_success(["custodian", "schema", "--summary"])

        # json option
        self.run_and_expect_success(["custodian", "schema", "--json"])

        # with just a cloud
        self.run_and_expect_success(["custodian", "schema", "aws"])

        # with just a resource
        self.run_and_expect_success(["custodian", "schema", "ec2"])

        # with just a mode
        self.run_and_expect_success(["custodian", "schema", "mode"])

        # mode.type
        self.run_and_expect_success(["custodian", "schema", "mode.phd"])

        # resource.actions
        self.run_and_expect_success(["custodian", "schema", "ec2.actions"])

        # resource.filters
        self.run_and_expect_success(["custodian", "schema", "ec2.filters"])

        # specific item
        self.run_and_expect_success(["custodian", "schema", "ec2.filters.tag-count"])

    def test_invalid_options(self):

        # invalid resource
        self.run_and_expect_failure(["custodian", "schema", "fakeresource"], 1)

        # invalid category
        self.run_and_expect_failure(["custodian", "schema", "ec2.arglbargle"], 1)

        # invalid item
        self.run_and_expect_failure(
            ["custodian", "schema", "ec2.filters.nonexistent"], 1
        )

        # invalid number of selectors
        self.run_and_expect_failure(["custodian", "schema", "ec2.filters.and.foo"], 1)

    def test_schema_output(self):

        output = self.get_output(["custodian", "schema"])
        self.assertIn("aws.ec2", output)
        # self.assertIn("azure.vm", output)
        # self.assertIn("gcp.instance", output)

        output = self.get_output(["custodian", "schema", "aws"])
        self.assertIn("aws.ec2", output)
        self.assertNotIn("azure.vm", output)
        self.assertNotIn("gcp.instance", output)

        output = self.get_output(["custodian", "schema", "aws.ec2"])
        self.assertIn("actions:", output)
        self.assertIn("filters:", output)

        output = self.get_output(["custodian", "schema", "ec2"])
        self.assertIn("actions:", output)
        self.assertIn("filters:", output)

        output = self.get_output(["custodian", "schema", "ec2.filters"])
        self.assertNotIn("actions:", output)
        self.assertIn("filters:", output)

        output = self.get_output(["custodian", "schema", "ec2.filters.image"])
        self.assertIn("Help", output)

    def test_schema_expand(self):
        # refs should only ever exist in a dictionary by itself
        test_schema = {
            '$ref': '#/definitions/filters_common/value_from'
        }
        result = ElementSchema.schema(generate()['definitions'], test_schema)
        self.assertEqual(result, ValuesFrom.schema)

    def test_schema_multi_expand(self):
        test_schema = {
            'schema1': {
                '$ref': '#/definitions/filters_common/value_from'
            },
            'schema2': {
                '$ref': '#/definitions/filters_common/value_from'
            }
        }

        expected = yaml_dump({
            'schema1': {
                'type': 'object',
                'additionalProperties': 'False',
                'required': ['url'],
                'properties': {
                    'url': {'type': 'string'},
                    'query': {'type': 'string'},
                    'format': {'enum': ['csv', 'json', 'txt', 'csv2dict']},
                    'expr': {'oneOf': [
                        {'type': 'integer'},
                        {'type': 'string'}]},
                    'headers': {
                        'type': 'object',
                        'patternProperties': {
                            '': {'type': 'string'},
                        },
                    },
                }
            },
            'schema2': {
                'type': 'object',
                'additionalProperties': 'False',
                'required': ['url'],
                'properties': {
                    'url': {'type': 'string'},
                    'query': {'type': 'string'},
                    'format': {'enum': ['csv', 'json', 'txt', 'csv2dict']},
                    'expr': {'oneOf': [
                        {'type': 'integer'},
                        {'type': 'string'}]},
                    'headers': {
                        'type': 'object',
                        'patternProperties': {
                            '': {'type': 'string'},
                        },
                    },
                }
            }
        })

        result = yaml_dump(ElementSchema.schema(generate()['definitions'], test_schema))
        self.assertEqual(result, expected)

    def test_schema_expand_not_found(self):
        test_schema = {
            '$ref': '#/definitions/filters_common/invalid_schema'
        }
        result = ElementSchema.schema(generate()['definitions'], test_schema)
        self.assertEqual(result, None)


class ReportTest(CliTest):

    def test_report(self):
        policy_name = "ec2-running-instances"
        valid_policies = {
            "policies": [
                {
                    "name": policy_name,
                    "resource": "ec2",
                    "query": [{"instance-state-name": "running"}],
                }
            ]
        }
        yaml_file = self.write_policy_file(valid_policies)

        output = self.get_output(
            ["custodian", "report", "-s", self.output_dir, yaml_file]
        )
        self.assertIn("InstanceId", output)
        self.assertIn("i-014296505597bf519", output)

        # ASCII formatted test
        output = self.get_output(
            [
                "custodian",
                "report",
                "--format",
                "grid",
                "-s",
                self.output_dir,
                yaml_file,
            ]
        )
        self.assertIn("InstanceId", output)
        self.assertIn("i-014296505597bf519", output)

        # json format
        output = self.get_output(
            ["custodian", "report", "--format", "json", "-s", self.output_dir, yaml_file]
        )
        self.assertTrue("i-014296505597bf519", json.loads(output)[0]['InstanceId'])

        # empty file
        temp_dir = self.get_temp_dir()
        empty_policies = {"policies": []}
        yaml_file = self.write_policy_file(empty_policies)
        self.run_and_expect_failure(
            ["custodian", "report", "-s", temp_dir, yaml_file], 1
        )

        # more than 1 policy
        policies = {
            "policies": [
                {"name": "foo", "resource": "s3"}, {"name": "bar", "resource": "ec2"}
            ]
        }
        yaml_file = self.write_policy_file(policies)
        self.run_and_expect_failure(
            ["custodian", "report", "-s", temp_dir, yaml_file], 1
        )

    def test_warning_on_empty_policy_filter(self):
        # This test is to examine the warning output supplied when -p is used and
        # the resulting policy set is empty.  It is not specific to the `report`
        # subcommand - it is also used by `run` and a few other subcommands.

        policy_name = "test-policy"
        valid_policies = {
            "policies": [
                {
                    "name": policy_name,
                    "resource": "s3",
                    "filters": [{"tag:custodian_tagging": "not-null"}],
                }
            ]
        }
        yaml_file = self.write_policy_file(valid_policies)
        temp_dir = self.get_temp_dir()

        bad_policy_name = policy_name + "-nonexistent"
        log_output = self.capture_logging("custodian.commands")
        self.run_and_expect_failure(
            ["custodian", "report", "-s", temp_dir, "-p", bad_policy_name, yaml_file], 1
        )
        self.assertIn(policy_name, log_output.getvalue())

        bad_resource_name = "foo"
        self.run_and_expect_failure(
            ["custodian", "report", "-s", temp_dir, "-t", bad_resource_name, yaml_file],
            1,
        )


class LogsTest(CliTest):

    def test_logs(self):
        temp_dir = self.get_temp_dir()

        # Test 1 - empty file
        empty_policies = {"policies": []}
        yaml_file = self.write_policy_file(empty_policies)
        self.run_and_expect_failure(["custodian", "logs", "-s", temp_dir, yaml_file], 1)

        # Test 2 - more than one policy
        policies = {
            "policies": [
                {"name": "foo", "resource": "s3"}, {"name": "bar", "resource": "ec2"}
            ]
        }
        yaml_file = self.write_policy_file(policies)
        self.run_and_expect_failure(["custodian", "logs", "-s", temp_dir, yaml_file], 1)

        # Test 3 - successful test
        p_data = {
            "name": "test-policy",
            "resource": "rds",
            "filters": [
                {"key": "GroupName", "type": "security-group", "value": "default"}
            ],
            "actions": [{"days": 10, "type": "retention"}],
        }
        yaml_file = self.write_policy_file({"policies": [p_data]})
        output_dir = os.path.join(os.path.dirname(__file__), "data", "logs")
        self.run_and_expect_failure(["custodian", "logs", "-s", output_dir, yaml_file], 1)


class RunTest(CliTest):

    def test_ec2(self):
        session_factory = self.replay_flight_data(
            "test_ec2_state_transition_age_filter"
        )

        from c7n.policy import PolicyCollection

        self.patch(
            PolicyCollection,
            "session_factory",
            staticmethod(lambda x=None: session_factory),
        )

        temp_dir = self.get_temp_dir()
        yaml_file = self.write_policy_file(
            {
                "policies": [
                    {
                        "name": "ec2-state-transition-age",
                        "resource": "ec2",
                        "filters": [
                            {"State.Name": "running"}, {"type": "state-age", "days": 30}
                        ],
                    }
                ]
            }
        )

        # TODO - capture logging and ensure the following
        # self.assertIn('Running policy ec2-state-transition-age', logs)
        # self.assertIn('metric:ResourceCount Count:1 policy:ec2-state-transition-age', logs)

        self.run_and_expect_success(
            [
                "custodian",
                "run",
                "--cache",
                temp_dir + "/cache",
                "-s",
                temp_dir,
                yaml_file,
            ]
        )

    def test_error(self):
        from c7n.policy import Policy

        self.patch(
            Policy, "__call__", lambda x: (_ for _ in ()).throw(Exception("foobar"))
        )

        #
        # Make sure that if the policy causes an exception we error out
        #

        temp_dir = self.get_temp_dir()
        yaml_file = self.write_policy_file(
            {
                "policies": [
                    {
                        "name": "error",
                        "resource": "ec2",
                        "filters": [
                            {"State.Name": "running"}, {"type": "state-age", "days": 30}
                        ],
                    }
                ]
            }
        )

        self.run_and_expect_failure(
            [
                "custodian",
                "run",
                "--cache",
                temp_dir + "/cache",
                "-s",
                temp_dir,
                yaml_file,
            ],
            2,
        )

        #
        # Test --debug
        #
        class CustomError(Exception):
            pass

        import pdb

        self.patch(pdb, "post_mortem", lambda x: (_ for _ in ()).throw(CustomError))

        self.run_and_expect_exception(
            ["custodian", "run", "-s", temp_dir, "--debug", yaml_file], CustomError
        )

    def test_session_policy(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('--session-policy', action=LoadSessionPolicyJson)
        bad_session_policy = "bad_policy"
        sample_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Sid": "Statement1",
                "Effect": "Allow",
                "Action": ["lambda:ListFunctions", "tag:*", "ebs:Delete*"],
                "Resource": "*"
                }]
            }
        session_policy = self.write_policy_file(sample_policy, format="json")
        arguments = parser.parse_args(["--session-policy", session_policy])
        self.assertEqual(vars(arguments).get('session_policy'), sample_policy)
        self.assertEqual(LoadSessionPolicyJson(dest=session_policy,
            option_strings=None).load_session_policy_from_file(session_policy), sample_policy)
        with self.assertRaises(FileNotFoundError) as e:
            LoadSessionPolicyJson(dest=session_policy,
                option_strings=None).load_session_policy_from_file(bad_session_policy)
        self.assertIn("No such file or directory", str(e.exception))


class MetricsTest(CliTest):

    def test_metrics(self):
        session_factory = self.replay_flight_data("test_lambda_policy_metrics")
        from c7n.policy import PolicyCollection

        self.patch(
            PolicyCollection,
            "session_factory",
            staticmethod(lambda x=None: session_factory),
        )

        yaml_file = self.write_policy_file(
            {
                "policies": [
                    {
                        "name": "ec2-tag-compliance-v6",
                        "resource": "ec2",
                        "mode": {"type": "ec2-instance-state", "events": ["running"]},
                        "filters": [
                            {"tag:custodian_status": "absent"},
                            {
                                "or": [
                                    {"tag:App": "absent"},
                                    {"tag:Env": "absent"},
                                    {"tag:Owner": "absent"},
                                ]
                            },
                        ],
                    }
                ]
            }
        )

        end = datetime.utcnow()
        start = end - timedelta(14)
        period = 24 * 60 * 60 * 14
        self.run_and_expect_failure(
            [
                "custodian",
                "metrics",
                "--start",
                str(start),
                "--end",
                str(end),
                "--period",
                str(period),
                yaml_file,
            ],
            1
        )

    def test_metrics_get_endpoints(self):

        #
        # Test for defaults when --start is not supplied
        #
        class FakeOptions:
            start = end = None
            days = 5

        options = FakeOptions()
        start, end = commands._metrics_get_endpoints(options)
        self.assertEqual((end - start).days, options.days)

        #
        # Test that --start and --end have to be passed together
        #
        policy = {
            "policies": [
                {
                    "name": "metrics-test",
                    "resource": "ec2",
                    "query": [{"instance-state-name": "running"}],
                }
            ]
        }
        yaml_file = self.write_policy_file(policy)

        self.run_and_expect_failure(
            ["custodian", "metrics", "--start", "1", yaml_file], 1
        )


class MiscTest(CliTest):

    def test_no_args(self):
        _, stderr = self.run_and_expect_failure(["custodian"], 2)
        self.assertIn("metrics", stderr)
        self.assertIn("logs", stderr)

    def test_empty_policy_file(self):
        # Doesn't do anything, but should exit 0
        temp_dir = self.get_temp_dir()
        yaml_file = self.write_policy_file({})
        self.run_and_expect_failure(
            ["custodian", "run", "-s", temp_dir, yaml_file], 1)

    def test_nonexistent_policy_file(self):
        temp_dir = self.get_temp_dir()
        yaml_file = self.write_policy_file({})
        nonexistent = yaml_file + ".bad"
        self.run_and_expect_failure(
            ["custodian", "run", "-s", temp_dir, yaml_file, nonexistent], 1
        )

    def test_duplicate_policy(self):
        policy = {
            "policies": [
                {
                    "name": "metrics-test",
                    "resource": "ec2",
                    "query": [{"instance-state-name": "running"}],
                }
            ]
        }
        temp_dir = self.get_temp_dir()
        yaml_file = self.write_policy_file(policy)
        self.run_and_expect_failure(
            ["custodian", "run", "-s", temp_dir, yaml_file, yaml_file], 1
        )

    def test_failure_with_no_default_region(self):
        policy = {"policies": [{"name": "will-never-run", "resource": "ec2"}]}
        temp_dir = self.get_temp_dir()
        yaml_file = self.write_policy_file(policy)
        self.patch(aws, "get_profile_session", lambda x: None)
        self.run_and_expect_failure(["custodian", "run", "-s", temp_dir, yaml_file], 1)
