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
import json
import shutil
import sys
import tempfile
import yaml


from common import BaseTest
from cStringIO import StringIO
from c7n import cli, version


class CliTest(BaseTest):
    """ A subclass of BaseTest with some handy functions for CLI related tests. """

    def write_policy_file(self, policy, format='yaml'):
        """ Write a policy file to disk in the specified format.
        
        Input a dictionary and a format. Valid formats are `yaml` and `json`
        Returns the file path.
        """
        suffix = "." + format
        file = tempfile.NamedTemporaryFile(suffix=suffix)
        if format == 'json':
            json.dump(policy, file)
        else:
            file.write(yaml.dump(policy, Dumper=yaml.SafeDumper))

        file.flush()
        self.addCleanup(file.close)
        return file.name

    def get_temp_dir(self):
        """ Return a temporary directory that will get cleaned up. """
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir)
        return temp_dir

    def get_output(self, argv):
        """ Run cli.main with the supplied argv and return the output. """
        
        # Cache the original sys.stdout so we can restore it later.
        # This is useful for using pdb when debugging tests.
        orig_stdout = sys.stdout

        out = StringIO()
        self.patch(sys, "stdout", out)
        self.run_and_expect_success(argv)
        self.patch(sys, "stdout", orig_stdout)

        return out.getvalue()

    def run_and_expect_success(self, argv):
        """ Run cli.main() with supplied argv and expect normal execution. """
        self.patch(sys, 'argv', argv)
        try:
            cli.main()
        except SystemExit as e:
            self.fail('Expected sys.exit would not be called. Exit code was ({})'.format(e.message))

    def run_and_expect_failure(self, argv, exit_code):
        """ Run cli.main() with supplied argv and expect exit_code. """
        self.patch(sys, 'argv', argv)
        with self.assertRaises(SystemExit) as cm:
            cli.main()
        self.assertEqual(cm.exception.code, exit_code)
        
    def run_and_expect_exception(self, argv, exception):
        """ Run cli.main() with supplied argv and expect supplied exception. """
        self.patch(sys, 'argv', argv)
        try:
            cli.main()
        except exception:
            return
        
        self.fail('Error: did not raise {}.'.format(exception))


class VersionTest(CliTest):

    def test_version(self):
        output = self.get_output(['custodian', 'version'])
        self.assertEqual(output.strip(), version.version)


class ValidateTest(CliTest):

    def test_validate(self):
        invalid_policies = {
            'policies':
            [{
                'name': 'foo',
                'resource': 's3',
                'filters': [{"tag:custodian_tagging": "not-null"}],
                'actions': [{'type': 'untag', 'tags': ['custodian_cleanup']}],
            }]
        }
        yaml_file = self.write_policy_file(invalid_policies)
        json_file = self.write_policy_file(invalid_policies, format='json')

        # YAML validation
        self.run_and_expect_failure(['custodian', 'validate', yaml_file], 1)

        # JSON validation
        self.run_and_expect_failure(['custodian', 'validate', json_file], 1)

        # no config files given
        self.run_and_expect_failure(['custodian', 'validate'], 2)

        # nonexistent file given
        self.run_and_expect_exception(['custodian', 'validate', 'fake.yaml'], ValueError)

        valid_policies = {
            'policies':
            [{
                'name': 'foo',
                'resource': 's3',
                'filters': [{"tag:custodian_tagging": "not-null"}],
                'actions': [{'type': 'tag', 'tags': ['custodian_cleanup']}],
            }]
        }
        yaml_file = self.write_policy_file(valid_policies)

        self.run_and_expect_success(['custodian', 'validate', yaml_file])

        # legacy -c option
        self.run_and_expect_success(['custodian', 'validate', '-c', yaml_file])

        # duplicate policy names
        self.run_and_expect_failure(['custodian', 'validate', yaml_file, yaml_file], 1)


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
        self.run_and_expect_success(['custodian', 'schema', 'ec2.filters.tag-count'])

    def test_invalid_options(self):

        # invalid resource
        self.run_and_expect_failure(['custodian', 'schema', 'fakeresource'], 2)
        
        # invalid category
        self.run_and_expect_failure(['custodian', 'schema', 'ec2.arglbargle'], 2)
        
        # invalid item
        self.run_and_expect_failure(['custodian', 'schema', 'ec2.filters.nonexistent'], 2)

        # invalid number of selectors
        self.run_and_expect_failure(['custodian', 'schema', 'ec2.filters.and.foo'], 2)

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
        self.assertIn('Help:', output)
        

class ReportTest(CliTest):

    def test_report(self):
        valid_policies = {
            'policies':
            [{
                'name': 'foo',
                'resource': 's3',
                'filters': [{"tag:custodian_tagging": "not-null"}],
                'actions': [{'type': 'tag', 'tags': ['custodian_cleanup']}],
            }]
        }
        yaml_file = self.write_policy_file(valid_policies)
        temp_dir = self.get_temp_dir()

        self.run_and_expect_success(['custodian', 'report', '-c', yaml_file, '-s', temp_dir])

        # empty file
        empty_policies = {'policies': []}
        yaml_file = self.write_policy_file(empty_policies)
        self.run_and_expect_exception([
                'custodian', 'report', '-c', yaml_file, '-s', temp_dir], AssertionError)


class LogsTest(CliTest):

    def test_logs(self):

        temp_dir = self.get_temp_dir()

        # empty file
        empty_policies = {'policies': []}
        yaml_file = self.write_policy_file(empty_policies)
        self.run_and_expect_exception([
                'custodian', 'report', '-c', yaml_file, '-s', temp_dir], AssertionError)
