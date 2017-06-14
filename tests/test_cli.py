# Copyright 2016 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import os
import sys

from argparse import ArgumentTypeError
from .common import BaseTest
from cStringIO import StringIO
from c7n import cli, version, commands, utils
from datetime import datetime, timedelta


class CliTest(BaseTest):
    """ A subclass of BaseTest with some handy functions for CLI related tests. """

    def patch_account_id(self):
        test_account_id = lambda x: self.account_id
        self.patch(cli, '_default_account_id', test_account_id)

    def get_output(self, argv):
        """ Run cli.main with the supplied argv and return the output. """
        out, err = self.run_and_expect_success(argv)
        return out

    def capture_output(self):
        out = StringIO()
        err = StringIO()
        self.patch(sys, 'stdout', out)
        self.patch(sys, 'stderr', err)
        return out, err

    def run_and_expect_success(self, argv):
        """ Run cli.main() with supplied argv and expect normal execution. """
        self.patch_account_id()
        self.patch(sys, 'argv', argv)
        out, err = self.capture_output()
        try:
            cli.main()
        except SystemExit as e:
            self.fail('Expected sys.exit would not be called. Exit code was ({})'.format(e.message))
        return out.getvalue(), err.getvalue()

    def run_and_expect_failure(self, argv, exit_code):
        """ Run cli.main() with supplied argv and expect exit_code. """
        self.patch_account_id()
        self.patch(sys, 'argv', argv)
        out, err = self.capture_output()
        #clear_resources()
        with self.assertRaises(SystemExit) as cm:
            cli.main()
        self.assertEqual(cm.exception.code, exit_code)
        return out.getvalue(), err.getvalue()

    def run_and_expect_exception(self, argv, exception):
        """ Run cli.main() with supplied argv and expect supplied exception. """
        self.patch_account_id()
        self.patch(sys, 'argv', argv)
        #clear_resources()
        try:
            cli.main()
        except exception:
            return
        self.fail('Error: did not raise {}.'.format(exception))


class UtilsTest(BaseTest):

    def test_key_val_pair(self):
        self.assertRaises(
            ArgumentTypeError,
            cli._key_val_pair,
            'invalid option',
        )
        param = 'day=today'
        self.assertIs(cli._key_val_pair(param), param)


class VersionTest(CliTest):

    def test_version(self):
        output = self.get_output(['custodian', 'version'])
        self.assertEqual(output.strip(), version.version)

    def test_debug_version(self):
        output = self.get_output(['custodian', 'version', '--debug'])
        # Among other things, this should print sys.path
        self.assertIn(version.version, output)
        self.assertIn(sys.path[0], output)


class ValidateTest(CliTest):

    def test_validate(self):
        invalid_policies = {
            'policies':
            [{
                'name': 'foo',
                'resource': 's3',
                'filters': [{"tag:custodian_tagging": "not-null"}],
                'actions': [{'type': 'untag',
                             'tags': {'custodian_cleanup': 'yes'}}],
            }]
        }
        yaml_file = self.write_policy_file(invalid_policies)
        json_file = self.write_policy_file(invalid_policies, format='json')

        # YAML validation
        self.run_and_expect_failure(['custodian', 'validate', yaml_file], 1)

        # JSON validation
        self.run_and_expect_failure(['custodian', 'validate', json_file], 1)

        # no config files given
        self.run_and_expect_failure(['custodian', 'validate'], 1)

        # nonexistent file given
        self.run_and_expect_exception(
            ['custodian', 'validate', 'fake.yaml'], ValueError)

        valid_policies = {
            'policies':
            [{
                'name': 'foo',
                'resource': 's3',
                'filters': [{"tag:custodian_tagging": "not-null"}],
                'actions': [{'type': 'tag',
                             'tags': {'custodian_cleanup': 'yes'}}],
            }]
        }
        yaml_file = self.write_policy_file(valid_policies)

        self.run_and_expect_success(['custodian', 'validate', yaml_file])

        # legacy -c option
        self.run_and_expect_success(['custodian', 'validate', '-c', yaml_file])

        # duplicate policy names
        self.run_and_expect_failure(
            ['custodian', 'validate', yaml_file, yaml_file], 1)


class SchemaTest(CliTest):

    def test_schema(self):

        # no options
        self.run_and_expect_success(['custodian', 'schema'])

        # summary option
        self.run_and_expect_success(['custodian', 'schema', '--summary'])

        # json option
        self.run_and_expect_success(['custodian', 'schema', '--json'])

        # with just a resource
        self.run_and_expect_success(['custodian', 'schema', 'ec2'])

        # resource.actions
        self.run_and_expect_success(['custodian', 'schema', 'ec2.actions'])

        # resource.filters
        self.run_and_expect_success(['custodian', 'schema', 'ec2.filters'])

        # specific item
        self.run_and_expect_success(
            ['custodian', 'schema', 'ec2.filters.tag-count'])

    def test_invalid_options(self):

        # invalid resource
        self.run_and_expect_failure(['custodian', 'schema', 'fakeresource'], 1)

        # invalid category
        self.run_and_expect_failure(
            ['custodian', 'schema', 'ec2.arglbargle'], 1)

        # invalid item
        self.run_and_expect_failure(
            ['custodian', 'schema', 'ec2.filters.nonexistent'], 1)

        # invalid number of selectors
        self.run_and_expect_failure(
            ['custodian', 'schema', 'ec2.filters.and.foo'], 1)

    def test_schema_output(self):

        output = self.get_output(['custodian', 'schema'])
        self.assertIn('ec2', output)

        output = self.get_output(['custodian', 'schema', 'ec2'])
        self.assertIn('actions:', output)
        self.assertIn('filters:', output)

        output = self.get_output(['custodian', 'schema', 'ec2.filters'])
        self.assertNotIn('actions:', output)
        self.assertIn('filters:', output)

        output = self.get_output(['custodian', 'schema', 'ec2.filters.image'])
        self.assertIn('Help', output)


class ReportTest(CliTest):

    def test_report(self):
        policy_name = 'ec2-running-instances'
        valid_policies = {
            'policies':
            [{
                'name': policy_name,
                'resource': 'ec2',
                'query': [{"instance-state-name": "running"}],
            }]
        }
        yaml_file = self.write_policy_file(valid_policies)

        output = self.get_output(
            ['custodian', 'report', '-s', self.output_dir, yaml_file])
        self.assertIn('InstanceId', output)
        self.assertIn('i-014296505597bf519', output)

        # ASCII formatted test
        output = self.get_output(
            ['custodian', 'report', '--format', 'grid', '-s', self.output_dir, yaml_file])
        self.assertIn('InstanceId', output)
        self.assertIn('i-014296505597bf519', output)

        # empty file
        temp_dir = self.get_temp_dir()
        empty_policies = {'policies': []}
        yaml_file = self.write_policy_file(empty_policies)
        self.run_and_expect_failure(
            ['custodian', 'report', '-s', temp_dir, yaml_file],
            1)

        # more than 1 policy
        policies = {
            'policies': [
                {'name': 'foo', 'resource': 's3'},
                {'name': 'bar', 'resource': 'ec2'},
            ]
        }
        yaml_file = self.write_policy_file(policies)
        self.run_and_expect_failure(
            ['custodian', 'report', '-s', temp_dir, yaml_file],
            1)

    def test_warning_on_empty_policy_filter(self):
        # This test is to examine the warning output supplied when -p is used and
        # the resulting policy set is empty.  It is not specific to the `report`
        # subcommand - it is also used by `run` and a few other subcommands.
        policy_name = 'test-policy'
        valid_policies = {
            'policies':
            [{
                'name': policy_name,
                'resource': 's3',
                'filters': [{"tag:custodian_tagging": "not-null"}],
            }]
        }
        yaml_file = self.write_policy_file(valid_policies)
        temp_dir = self.get_temp_dir()

        bad_policy_name = policy_name + '-nonexistent'
        log_output = self.capture_logging('custodian.commands')
        self.run_and_expect_failure(
            ['custodian', 'report', '-s', temp_dir, '-p', bad_policy_name, yaml_file], 
            1)
        self.assertIn(policy_name, log_output.getvalue())

        bad_resource_name = 'foo'
        self.run_and_expect_failure(
            ['custodian', 'report', '-s', temp_dir, '-t', bad_resource_name, yaml_file],
            1)


class LogsTest(CliTest):

    def test_logs(self):
        temp_dir = self.get_temp_dir()

        # Test 1 - empty file
        empty_policies = {'policies': []}
        yaml_file = self.write_policy_file(empty_policies)
        self.run_and_expect_failure(
            ['custodian', 'logs', '-s', temp_dir, yaml_file],
            1)

        # Test 2 - more than one policy
        policies = {
            'policies': [
                {'name': 'foo', 'resource': 's3'},
                { 'name': 'bar', 'resource': 'ec2'},
            ]
        }
        yaml_file = self.write_policy_file(policies)
        self.run_and_expect_failure(
            ['custodian', 'logs', '-s', temp_dir, yaml_file],
            1)

        # Test 3 - successful test
        p_data = {
            'name': 'test-policy',
            'resource': 'rds',
            'filters': [
                {
                    'key': 'GroupName',
                    'type': 'security-group',
                    'value': 'default',
                },
            ],
            'actions': [{'days': 10, 'type': 'retention'}],
        }
        yaml_file = self.write_policy_file({'policies': [p_data]})
        output_dir = os.path.join(
            os.path.dirname(__file__),
            'data',
            'logs',
        )
        self.run_and_expect_success(
            ['custodian', 'logs', '-s', output_dir, yaml_file],
        )


class TabCompletionTest(CliTest):
    """ Tests for argcomplete tab completion. """

    def test_schema_completer(self):
        self.assertIn('rds', cli.schema_completer('rd'))
        self.assertIn('s3.', cli.schema_completer('s3'))
        self.assertListEqual([], cli.schema_completer('invalidResource.'))
        self.assertIn('rds.actions', cli.schema_completer('rds.'))
        self.assertIn('s3.filters.', cli.schema_completer('s3.filters'))
        self.assertIn('s3.filters.event', cli.schema_completer('s3.filters.eve'))
        self.assertListEqual([], cli.schema_completer('rds.actions.foo.bar'))

    def test_schema_completer_wrapper(self):
        class MockArgs(object):
            summary = False

        args = MockArgs()
        self.assertIn('rds', cli._schema_tab_completer('rd', args))

        args.summary = True
        self.assertListEqual([], cli._schema_tab_completer('rd', args))


class RunTest(CliTest):

    def test_ec2(self):
        session_factory = self.replay_flight_data(
            'test_ec2_state_transition_age_filter'
        )

        from c7n.policy import PolicyCollection
        self.patch(PolicyCollection, 'test_session_factory',
                   staticmethod(lambda x=None: session_factory))

        temp_dir = self.get_temp_dir()
        yaml_file = self.write_policy_file({
            'policies': [{
                'name': 'ec2-state-transition-age',
                'resource': 'ec2',
                'filters': [
                    {'State.Name': 'running'},
                    {'type': 'state-age', 'days': 30},
                ]
            }]
        })

        # TODO - capture logging and ensure the following
        #self.assertIn('Running policy ec2-state-transition-age', logs)
        #self.assertIn('metric:ResourceCount Count:1 policy:ec2-state-transition-age', logs)

        self.run_and_expect_success(
            ['custodian', 'run', '-s', temp_dir, yaml_file],
        )

    def test_error(self):
        from c7n.policy import Policy
        self.patch(Policy, '__call__', lambda x: (_ for _ in ()).throw(Exception('foobar')))

        #
        # Make sure that if the policy causes an exception we error out
        #

        temp_dir = self.get_temp_dir()
        yaml_file = self.write_policy_file({
            'policies': [{
                'name': 'error',
                'resource': 'ec2',
                'filters': [
                    {'State.Name': 'running'},
                    {'type': 'state-age', 'days': 30},
                ],
            }]
        })

        self.run_and_expect_failure(
            ['custodian', 'run', '-s', temp_dir, yaml_file],
            2
        )

        #
        # Test --debug
        #
        class CustomError(Exception):
            pass

        import pdb
        self.patch(pdb, 'post_mortem', lambda x: (_ for _ in ()).throw(CustomError))

        self.run_and_expect_exception(
            ['custodian', 'run', '-s', temp_dir, '--debug', yaml_file],
            CustomError
        )


class MetricsTest(CliTest):

    def test_metrics(self):
        session_factory = self.replay_flight_data('test_lambda_policy_metrics')

        from c7n.policy import PolicyCollection
        self.patch(PolicyCollection, 'test_session_factory',
                   staticmethod(lambda x=None: session_factory))

        yaml_file = self.write_policy_file({
            'policies': [{
                'name': 'ec2-tag-compliance-v6',
                'resource': 'ec2',
                'mode': {
                    'type': 'ec2-instance-state',
                    'events': ['running']},
                'filters': [
                    {"tag:custodian_status": 'absent'},
                    {'or': [
                        {"tag:App": 'absent'},
                        {"tag:Env": 'absent'},
                        {"tag:Owner": 'absent'}]}]
            }]
        })

        end = datetime.utcnow()
        start = end - timedelta(14)
        period = 24 * 60 * 60 * 14

        out = self.get_output(
            ['custodian', 'metrics', '--start', str(start), '--end', str(end), '--period', str(period), yaml_file])

        self.assertEqual(
            json.loads(out),
            {'ec2-tag-compliance-v6':
             {u'Durations': [],
              u'Errors': [{u'Sum': 0.0,
                           u'Timestamp': u'2016-05-30T10:50:00',
                           u'Unit': u'Count'}],
              u'Invocations': [{u'Sum': 4.0,
                                u'Timestamp': u'2016-05-30T10:50:00',
                                u'Unit': u'Count'}],
              u'ResourceCount': [{u'Average': 1.0,
                                  u'Sum': 2.0,
                                  u'Timestamp': u'2016-05-30T10:50:00',
                                  u'Unit': u'Count'}],
              u'Throttles': [{u'Sum': 0.0,
                              u'Timestamp': u'2016-05-30T10:50:00',
                              u'Unit': u'Count'}]}})

    def test_metrics_get_endpoints(self):

        #
        # Test for defaults when --start is not supplied
        #
        class FakeOptions(object):
            start = end = None
            days = 5
        options = FakeOptions()
        start, end = commands._metrics_get_endpoints(options)
        self.assertEqual((end - start).days, options.days)

        #
        # Test that --start and --end have to be passed together
        #
        policy = {
            'policies':
            [{
                'name': 'metrics-test',
                'resource': 'ec2',
                'query': [{"instance-state-name": "running"}],
            }]
        }
        yaml_file = self.write_policy_file(policy)

        self.run_and_expect_failure(
            ['custodian', 'metrics', '--start', '1', yaml_file],
            1
        )


class MiscTest(CliTest):

    def test_empty_policy_file(self):
        # Doesn't do anything, but should exit 0
        temp_dir = self.get_temp_dir()
        yaml_file = self.write_policy_file({})
        self.run_and_expect_success(
            ['custodian', 'run', '-s', temp_dir, yaml_file]
        )

    def test_nonexistent_policy_file(self):
        temp_dir = self.get_temp_dir()
        yaml_file = self.write_policy_file({})
        nonexistent = yaml_file + '.bad'
        self.run_and_expect_failure(
            ['custodian', 'run', '-s', temp_dir, yaml_file, nonexistent],
            1)

    def test_duplicate_policy(self):
        policy = {
            'policies':
            [{
                'name': 'metrics-test',
                'resource': 'ec2',
                'query': [{"instance-state-name": "running"}],
            }]
        }
        temp_dir = self.get_temp_dir()
        yaml_file = self.write_policy_file(policy)
        self.run_and_expect_failure(
            ['custodian', 'run', '-s', temp_dir, yaml_file, yaml_file],
            1)

    def test_failure_with_no_default_region(self):
        policy = {
            'policies':
            [{
                'name': 'will-never-run',
                'resource': 'ec2',
            }]
        }
        temp_dir = self.get_temp_dir()
        yaml_file = self.write_policy_file(policy)
        self.patch(utils, 'get_profile_session', lambda x: None)
        self.run_and_expect_failure(
            ['custodian', 'run', '-s', temp_dir, yaml_file],
            1)
