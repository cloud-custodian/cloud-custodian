# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from . import tools_tags as tools
from .azure_common import BaseTest
from c7n_azure.actions.tagging import Tag
from unittest.mock import patch, Mock

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

        self.assertTrue(self.load_policy({
            'name': 'test-tag-schema-validate',
            'resource': 'azure.vm',
            'actions': [
                {'type': 'tag',
                 'tags': {
                     'tag1': 'value1',
                     'tag2': {
                         'type': 'resource',
                         'key': 'name'
                     }
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


class ActionsTagMappingLookupTest(BaseTest):
    """Resource lookups used as values inside the ``tags`` mapping."""

    existing_tags = {'pre-existing-1': 'unmodified', 'pre-existing-2': 'unmodified'}

    def _get_action(self, data):
        # build through a real policy so the action is registry-registered and
        # the mapping is run through schema validation on the way in
        policy = self.load_policy(
            tools.get_policy([dict(data, type='tag')]), validate=True)
        return policy.resource_manager.actions[0]

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_mapping_lookup_by_key_resolves(self, update_resource_tags):
        action = self._get_action({
            'tags': {'from_name': {'type': 'resource', 'key': 'name'}}})
        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        expected_tags = self.existing_tags.copy()
        expected_tags.update({'from_name': resource['name']})
        self.assertEqual(tools.get_tags_parameter(update_resource_tags), expected_tags)

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_mapping_lookup_miss_uses_default_value(self, update_resource_tags):
        action = self._get_action({
            'tags': {'env': {'type': 'resource',
                             'key': 'doesnotexist',
                             'default-value': 'production'}}})
        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        expected_tags = self.existing_tags.copy()
        expected_tags.update({'env': 'production'})
        self.assertEqual(tools.get_tags_parameter(update_resource_tags), expected_tags)

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_mapping_lookup_preserves_existing_tag_value(self, update_resource_tags):
        """key pointing at an existing tag keeps that tag's current value.

        A second, changing tag forces the write so the preserved value is
        visible in the payload.
        """
        action = self._get_action({
            'tags': {'pre-existing-1': {'type': 'resource',
                                        'key': 'tags."pre-existing-1"',
                                        'default-value': 'fallback'},
                     'new': 'added'}})
        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        expected_tags = self.existing_tags.copy()
        expected_tags.update({'new': 'added'})
        self.assertEqual(
            tools.get_tags_parameter(update_resource_tags), expected_tags)

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_no_write_when_lookup_resolves_to_current_value(self, update_resource_tags):
        """Resolving a tag to the value it already has is a no-op."""
        action = self._get_action({
            'tags': {'pre-existing-1': {'type': 'resource',
                                        'key': 'tags."pre-existing-1"',
                                        'default-value': 'fallback'}}})
        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        update_resource_tags.assert_not_called()

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_mapping_mixes_static_and_lookup_values(self, update_resource_tags):
        action = self._get_action({
            'tags': {'static': 'plain',
                     'dynamic': {'type': 'resource', 'key': 'name'}}})
        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        expected_tags = self.existing_tags.copy()
        expected_tags.update({'static': 'plain', 'dynamic': resource['name']})
        self.assertEqual(tools.get_tags_parameter(update_resource_tags), expected_tags)

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_conditional_default_writes_when_tag_absent(self, update_resource_tags):
        action = self._get_action({
            'tags': {'owner': {'type': 'resource', 'default-value': 'platform'}}})
        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        expected_tags = self.existing_tags.copy()
        expected_tags.update({'owner': 'platform'})
        self.assertEqual(tools.get_tags_parameter(update_resource_tags), expected_tags)

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_conditional_default_skipped_when_tag_present(self, update_resource_tags):
        action = self._get_action({
            'tags': {'pre-existing-1': {'type': 'resource',
                                        'default-value': 'should-not-be-written'}}})
        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        # nothing left to write, so no update call is made at all
        update_resource_tags.assert_not_called()

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_conditional_default_partial_skip(self, update_resource_tags):
        action = self._get_action({
            'tags': {'pre-existing-1': {'type': 'resource', 'default-value': 'skipped'},
                     'owner': {'type': 'resource', 'default-value': 'platform'}}})
        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        expected_tags = self.existing_tags.copy()
        expected_tags.update({'owner': 'platform'})
        self.assertEqual(tools.get_tags_parameter(update_resource_tags), expected_tags)

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_lookup_resolved_per_resource(self, update_resource_tags):
        """Two resources with different values each get their own tag value."""
        action = self._get_action({
            'tags': {'from_name': {'type': 'resource', 'key': 'name'}}})
        first = tools.get_resource({})
        second = tools.get_resource({})
        second['name'] = 'other-vm'

        action.process([first, second])

        written = [c[0][2]['from_name'] for c in update_resource_tags.call_args_list]
        self.assertEqual(written, ['cctestvm', 'other-vm'])

    def test_schema_accepts_lookup_forms_in_mapping(self):
        self.assertTrue(self.load_policy(
            tools.get_policy([
                {'type': 'tag',
                 'tags': {
                     'by_key': {'type': 'resource', 'key': 'name'},
                     'by_key_default': {'type': 'resource',
                                        'key': 'name',
                                        'default-value': 'dv'},
                     'conditional': {'type': 'resource', 'default-value': 'dv'},
                     'static': 'plain'}}
            ]), validate=True))

    def test_schema_rejects_malformed_mapping_values(self):
        for bad in ({'type': 'resource'},
                    {'type': 'resource', 'ky': 'name'},
                    {'foo': 'bar'},
                    ['a']):
            with self.assertRaises(Exception):
                self.load_policy(
                    tools.get_policy([{'type': 'tag', 'tags': {'X': bad}}]),
                    validate=True)
