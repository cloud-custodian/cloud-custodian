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
        resource = tools.get_resource({})
        resource_group = tools.get_resource_group_resource({})

        client_mock = Mock()

        action = Mock()
        action.manager.type = 'resourcegroup'
        action.session.client.return_value = client_mock

        TagHelper.update_resource_tags(action, resource_group, self.existing_tags)
        client_mock.resource_groups.update.assert_called_once()
        args = client_mock.resource_groups.update.call_args[0]
        self.assertEqual(args[0], resource_group['name'])
        self.assertEqual(args[1].tags, self.existing_tags)
        # Only PATCH tags
        self.assertListEqual(['tags'], [x for x in args[1].as_dict() if x is not None])

        action.manager.type = 'vm'
        TagHelper.update_resource_tags(action, resource, self.existing_tags)
        client_mock.resources.begin_update_by_id.assert_called_once()
        args = client_mock.resources.begin_update_by_id.call_args[0]
        self.assertEqual(args[0], resource['id'])
        self.assertEqual(args[2].tags, self.existing_tags)
        # Only PATCH tags
        self.assertListEqual(['tags'], [x for x in args[2].as_dict() if x is not None])
