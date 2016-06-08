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
