# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from . import tools_tags as tools
from .azure_common import BaseTest, arm_template
from unittest.mock import Mock

from c7n.filters.core import ValueFilter


class TagsTest(BaseTest):

    def test_tag_schema_validate(self):
        self.assertTrue(
            self.load_policy(
                tools.get_policy(filters=[
                    {'tag:Test': 'value'},
                ]), validate=True))

    def _get_filter(self, data):
        return ValueFilter(data=data, manager=Mock)

    @arm_template('vm.json')
    def test_tag_filter(self):

        resources = [tools.get_resource({'Pythontest': 'ItWorks', 'Another-Tag-1': 'value1'})]

        config = [({'tag:Pythontest': 'present'}, 1),
                  ({'tag:Pythontest': 'absent'}, 0),
                  ({'tag:Pythontest': 'ItWorks'}, 1),
                  ({'tag:Pythontest': 'ItDoesntWork'}, 0)]

        for c in config:
            f = self._get_filter(c[0])
            result = f.process(resources)
            self.assertEqual(len(result), c[1])
