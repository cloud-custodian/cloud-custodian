# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from . import tools_tags as tools
from .azure_common import BaseTest
from c7n_azure.actions.tagging import Tag
from mock import patch, Mock

from c7n.filters import FilterValidationError


class ActionsTagTest(BaseTest):

    existing_tags = {'pre-existing-1': 'unmodified', 'pre-existing-2': 'unmodified'}

    def _get_action(self, data):
        return Tag(data=data, manager=Mock())

    def test_schema_validate(self):
        self.assertTrue(
            self.load_policy(
                tools.get_policy([
                    {'type': 'tag',
                     'tag': 'test',
                     'value': 'test_value'}
                ]),
                validate=True))

        self.assertTrue(
            self.load_policy(
                tools.get_policy([
                    {'type': 'tag',
                     'tags': {'tag1': 'test'}}
                ]),
                validate=True))

        self.assertTrue(self.load_policy({
            'name': 'test-tag-schema-validate',
            'resource': 'azure.vm',
            'actions': [
                {'type': 'tag',
                 'tag': {
                     'type': 'resource',
                     'key': 'name'
                 },
                 'value': {
                     'type': 'resource',
                     'key': 'name'
                 }},
            ]
        }, validate=True))

        with self.assertRaises(FilterValidationError):
            # Can't have both tags and tag/value
            self.load_policy(tools.get_policy([
                {'type': 'tag',
                 'tags': {'tag2': 'value2'},
                 'tag': 'tag1',
                 'value': 'value1'}
            ]), validate=True)

        with self.assertRaises(FilterValidationError):
            # Required tags or tag/value
            self.load_policy(tools.get_policy([
                {'type': 'tag'}
            ]), validate=True)

        with self.assertRaises(FilterValidationError):
            # Empty tags
            self.load_policy(tools.get_policy([
                {'type': 'tag',
                 'tags': {}}
            ]), validate=True)

        with self.assertRaises(FilterValidationError):
            # Missing value
            self.load_policy(tools.get_policy([
                {'type': 'tag',
                 'tag': 'myTag'}
            ]), validate=True)

        with self.assertRaises(FilterValidationError):
            # Missing tag
            self.load_policy(tools.get_policy([
                {'type': 'tag',
                 'value': 'myValue'}
            ]), validate=True)

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_add_or_update_single_tag(self, update_resource_tags):
        """Verifies we can add a new tag to a VM and not modify
        an existing tag on that resource
        """

        action = self._get_action({'tag': 'tag1', 'value': 'value1'})
        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        tags = tools.get_tags_parameter(update_resource_tags)

        expected_tags = self.existing_tags.copy()
        expected_tags.update({'tag1': 'value1'})

        self.assertEqual(tags, expected_tags)

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_add_or_update_single_tag_from_resource(self, update_resource_tags):
        """Verifies we can add a new tag to a VM from values on the VM
        """

        action = self._get_action(
            {
                'tag': {
                    'type': 'resource',
                    'key': 'name'
                },
                'value': {
                    'type': 'resource',
                    'key': 'type'
                }
            })

        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        tags = tools.get_tags_parameter(update_resource_tags)

        expected_tags = self.existing_tags.copy()
        expected_tags.update({resource['name']: resource['type']})

        self.assertEqual(tags, expected_tags)

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_add_or_update_single_tag_from_resource_default(self, update_resource_tags):
        """Verifies we can add a new tag to a VM from values on the VM
        when values do not exist with default-value
        """

        action = self._get_action(
            {
                'tag': {
                    'type': 'resource',
                    'key': 'doesnotexist',
                    'default-value': 'default_tag'
                },
                'value': {
                    'type': 'resource',
                    'key': 'doesnotexist',
                    'default-value': 'default_value'
                }
            })

        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        tags = tools.get_tags_parameter(update_resource_tags)

        expected_tags = self.existing_tags.copy()
        expected_tags.update({'default_tag': 'default_value'})

        self.assertEqual(tags, expected_tags)

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_add_or_update_tags(self, update_resource_tags):
        """Adds tags to an empty resource group, then updates one
        tag and adds a new tag
        """

        action = self._get_action({'tags': {'tag1': 'value1', 'pre-existing-1': 'modified'}})
        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        tags = tools.get_tags_parameter(update_resource_tags)

        expected_tags = self.existing_tags.copy()
        expected_tags.update({'tag1': 'value1', 'pre-existing-1': 'modified'})

        self.assertEqual(tags, expected_tags)
