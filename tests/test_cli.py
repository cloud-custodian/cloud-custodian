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
        t = tempfile.NamedTemporaryFile(suffix=".yml")
        t.write(yaml.dump({'policies': [
            {'name': 'foo',
             'resource': 's3',
             'filters': [
                 {"tag:custodian_tagging": "not-null"}],
             'actions': [{
                 'type': 'untag',
                 'tags': ['custodian_cleanup']}]}]},
                Dumper=yaml.SafeDumper))
        t.flush()
        self.addCleanup(t.close)
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir)

        exit_code = []

        def exit(code):
            exit_code.append(code)

        self.patch(sys, 'exit', exit)
        self.patch(sys, 'argv', [
            'custodian', 'validate', '-c', t.name])

        cli.main()
        self.assertEqual(exit_code, [1])


class RunTest(BaseTest):

    def test_run(self):
        t = tempfile.NamedTemporaryFile(suffix=".yml")
        t.write(yaml.dump({'policies': []}, Dumper=yaml.SafeDumper))
        t.flush()
        self.addCleanup(t.close)

        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir)

        exit_code = []

        def exit(code):
            exit_code.append(code)

        self.patch(sys, 'exit', exit)
        self.patch(sys, 'argv', [
            'custodian', 'run', '-c', t.name, "-s", temp_dir])

        cli.main()
        self.assertEqual(exit_code, [0])
