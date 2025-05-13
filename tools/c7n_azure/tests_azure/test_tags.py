# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .azure_common import BaseTest
from mock import patch, Mock

from c7n_azure.tags import TagHelper
from . import tools_tags as tools


class TagsTest(BaseTest):

    existing_tags = {'tag1': 'value1', 'tag2': 'value2'}

    def test_get_tag_value(self):
        resource = tools.get_resource(self.existing_tags)

        self.assertEqual(TagHelper.get_tag_value(resource, 'tag1'), 'value1')
        self.assertEqual(TagHelper.get_tag_value(resource, 'tag2'), 'value2')
        self.assertFalse(TagHelper.get_tag_value(resource, 'tag3'))

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_add_tags(self, update_resource_tags):
        resource = tools.get_resource(self.existing_tags)

        TagHelper.add_tags(None, resource, {})
        update_resource_tags.assert_not_called()

        TagHelper.add_tags(None, resource, {'tag3': 'value3'})
        expected_tags = self.existing_tags.copy()
        expected_tags.update({'tag3': 'value3'})
        self.assertEqual(tools.get_tags_parameter(update_resource_tags), expected_tags)

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_remove_tags(self, update_resource_tags):
        resource = tools.get_resource(self.existing_tags)

        TagHelper.remove_tags(None, resource, [])
        update_resource_tags.assert_not_called()

        TagHelper.remove_tags(None, resource, ['tag3'])
        update_resource_tags.assert_not_called()

        TagHelper.remove_tags(None, resource, ['tag2'])
        expected_tags = {'tag1': 'value1'}
        self.assertEqual(tools.get_tags_parameter(update_resource_tags), expected_tags)

    def test_update_tags(self):
        for resource_type, resource in {
            "vm": tools.get_resource({}),
            "resourcegroup": tools.get_resource_group_resource({})
        }.items():
            client_mock = Mock()
            action = Mock()
            action.manager.type = resource_type
            action.session.client.return_value = client_mock

            TagHelper.update_resource_tags(action, resource, self.existing_tags)
            client_mock.tags.begin_update_at_scope.assert_called_once()
            args = client_mock.tags.begin_update_at_scope.call_args[0]
            self.assertEqual(args[0], resource['id'])
            self.assertEqual(args[1].properties['tags'], self.existing_tags)
