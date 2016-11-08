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


class VersionTest(BaseTest):

    def test_version(self):
        self.patch(sys, "argv", ['custodian', 'version'])
        out = StringIO()
        self.patch(sys, "stdout", out)
        cli.main()
        self.assertEqual(out.getvalue().strip(), version.version)


class ValidateTest(BaseTest):

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
        t = tempfile.NamedTemporaryFile(suffix=".yml")
        t.write(yaml.dump(invalid_policies, Dumper=yaml.SafeDumper))
        t.flush()
        self.addCleanup(t.close)
        j = tempfile.NamedTemporaryFile(suffix=".json")
        json.dump(invalid_policies, j)
        j.flush()
        self.addCleanup(j.close)
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir)

        exit_code = []

        def exit(code):
            exit_code.append(code)

        self.patch(sys, 'exit', exit)
        # YAML validation
        self.patch(sys, 'argv', [
            'custodian', 'validate', t.name])
        cli.main()
        # JSON validation
        self.patch(sys, 'argv', [
            'custodian', 'validate', j.name])
        cli.main()
        # no config files given
        self.patch(sys, 'argv', [
            'custodian', 'validate'])
        cli.main()
        self.assertEqual(exit_code, [1, 1, 2])

        # nonexistent file given
        self.patch(sys, 'argv', [
            'custodian', 'validate', 'fake.yaml'])
        self.assertRaises(ValueError, cli.main)

        valid_policies = {
            'policies':
            [{
                'name': 'foo',
                'resource': 's3',
                'filters': [{"tag:custodian_tagging": "not-null"}],
                'actions': [{'type': 'tag', 'tags': ['custodian_cleanup']}],
            }]
        }
        v = tempfile.NamedTemporaryFile(suffix=".yml")
        v.write(yaml.dump(valid_policies, Dumper=yaml.SafeDumper))
        v.flush()
        self.addCleanup(v.close)
        self.patch(sys, 'argv', [
            'custodian', 'validate', v.name])
        cli.main()
        self.assertEqual(exit_code, [1, 1, 2])
        # legacy -c option
        self.patch(sys, 'argv', [
            'custodian', 'validate', '-c', v.name])
        cli.main()
        self.assertEqual(exit_code, [1, 1, 2])
        # duplicate policy names
        self.patch(sys, 'argv', [
            'custodian', 'validate', v.name, v.name])
        cli.main()
        self.assertEqual(exit_code, [1, 1, 2, 1])


class SchemaTest(BaseTest):

    def test_schema(self):
        exit_code = []

        def exit(code):
            exit_code.append(code)

        self.patch(sys, 'exit', exit)
        # no options
        self.patch(sys, 'argv', ['custodian', 'schema'])

        cli.main()
        self.assertEqual(exit_code, [])
        # summary option
        self.patch(sys, 'argv', ['custodian', 'schema', '--summary'])

        cli.main()
        self.assertEqual(exit_code, [])
        # json option
        self.patch(sys, 'argv', ['custodian', 'schema', '--json'])

        cli.main()
        self.assertEqual(exit_code, [])
        # json option
        self.patch(sys, 'argv', ['custodian', 'schema', 'ec2'])

        cli.main()
        self.assertEqual(exit_code, [])
        # json option
        self.patch(sys, 'argv', ['custodian', 'schema', 'ec2.actions'])

        cli.main()
        self.assertEqual(exit_code, [])
        # json option
        self.patch(sys, 'argv', ['custodian', 'schema', 'ec2.filters'])

        cli.main()
        self.assertEqual(exit_code, [])
        # json option
        self.patch(sys, 'argv', ['custodian', 'schema', 'ec2.filters.tag-count'])

        cli.main()
        self.assertEqual(exit_code, [])


class ReportTest(BaseTest):

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
        v = tempfile.NamedTemporaryFile(suffix=".yml")
        v.write(yaml.dump(valid_policies, Dumper=yaml.SafeDumper))
        v.flush()
        self.addCleanup(v.close)

        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir)
        exit_code = []

        def exit(code):
            exit_code.append(code)

        self.patch(sys, 'exit', exit)
        self.patch(
            sys,
            'argv',
            ['custodian', 'report', '-c', v.name, '-s', temp_dir]
        )
        cli.main()
        self.assertEqual(exit_code, [])

        # empty file
        e = tempfile.NamedTemporaryFile(suffix=".yml")
        e.write(yaml.dump({'policies': []}, Dumper=yaml.SafeDumper))
        e.flush()
        self.addCleanup(e.close)
        self.patch(
            sys,
            'argv',
            ['custodian', 'logs', '-c', e.name, '-s', temp_dir]
        )
        self.assertRaises(AssertionError, cli.main)
