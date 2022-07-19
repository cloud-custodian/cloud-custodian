# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from os import path
import tempfile
from textwrap import dedent

from c7n import loader
from .common import BaseTest


class TestSourceLocator(BaseTest):

    def test_yaml_file(self):

        with tempfile.TemporaryDirectory() as tmpdirname:
            filename = path.join(tmpdirname, "testfile.yaml")
            with open(filename, "w") as f:
                f.write(dedent("""\
                    policies:
                      - name: foo
                        resource: s3

                      # One where name isn't the first element.
                      - resource: ec2
                        name: bar
                    """))
            locator = loader.SourceLocator(filename)
            self.assertEqual(locator.find("foo"), "testfile.yaml:2")
            self.assertEqual(locator.find("bar"), "testfile.yaml:7")
            self.assertEqual(locator.find("non-existent"), "")
