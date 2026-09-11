# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from gcp_common import BaseTest

from c7n.filters import FilterValidationError


def get_policy(actions=None, filters=None):
    policy = {'name': 'test-label',
              'resource': 'gcp.instance'}
    if filters:
        policy['filters'] = filters
    if actions:
        policy['actions'] = actions
    return policy


class SetLabelsActionTest(BaseTest):

    def test_schema_validate(self):
        self.assertTrue(
            self.load_policy(
                get_policy([
                    {'type': 'set-labels',
                     'labels': {'value': 'test_value'}}
                ])))

        self.assertTrue(
            self.load_policy(
                get_policy([
                    {'type': 'set-labels',
                     'remove': ['test']}
                ])))

        self.assertTrue(
            self.load_policy(
                get_policy([
                    {'type': 'set-labels',
                     'labels': {'value': 'test_value'},
                     'remove': ['test']}
                ])))

        with self.assertRaises(FilterValidationError):
            # Must specify labels to add or remove
            self.load_policy(get_policy([
                {'type': 'set-labels'}
            ]))


class SetLabelsLookupTest(BaseTest):
    """Resource lookups used as values inside the ``labels`` mapping."""

    def _get_action(self, labels):
        policy = self.load_policy(
            get_policy([{'type': 'set-labels', 'labels': labels}]))
        return policy.resource_manager.actions[0]

    def test_lookup_by_key_resolves(self):
        action = self._get_action({'env': {'type': 'resource', 'key': 'name'}})
        self.assertEqual(
            action.get_labels_to_add({'name': 'instance-1', 'labels': {}}),
            {'env': 'instance-1'})

    def test_lookup_miss_uses_default_value(self):
        action = self._get_action(
            {'env': {'type': 'resource',
                     'key': 'doesnotexist',
                     'default-value': 'production'}})
        self.assertEqual(
            action.get_labels_to_add({'name': 'instance-1', 'labels': {}}),
            {'env': 'production'})

    def test_static_value_passthrough(self):
        action = self._get_action({'env': 'test'})
        self.assertEqual(
            action.get_labels_to_add({'name': 'instance-1', 'labels': {}}),
            {'env': 'test'})

    def test_conditional_default_writes_when_label_absent(self):
        action = self._get_action(
            {'owner': {'type': 'resource', 'default-value': 'platform'}})
        self.assertEqual(
            action.get_labels_to_add({'name': 'instance-1', 'labels': {}}),
            {'owner': 'platform'})

    def test_conditional_default_skipped_when_label_present(self):
        action = self._get_action(
            {'owner': {'type': 'resource', 'default-value': 'platform'}})
        self.assertEqual(
            action.get_labels_to_add(
                {'name': 'instance-1', 'labels': {'owner': 'keep-me'}}),
            {})

    def test_conditional_default_leaves_existing_label_intact(self):
        """The skipped label must survive the merge with current labels."""
        action = self._get_action(
            {'owner': {'type': 'resource', 'default-value': 'platform'},
             'env': 'test'})
        resource = {'name': 'instance-1', 'labels': {'owner': 'keep-me'}}
        merged = action._merge_labels(
            action._get_current_labels(resource),
            action.get_labels_to_add(resource),
            action.get_labels_to_delete(resource))
        self.assertEqual(merged, {'owner': 'keep-me', 'env': 'test'})

    def test_schema_accepts_conditional_default(self):
        self.assertTrue(self.load_policy(get_policy([
            {'type': 'set-labels',
             'labels': {'owner': {'type': 'resource', 'default-value': 'x'}}}
        ])))

    def test_schema_rejects_malformed_label_values(self):
        for bad in ({'type': 'resource'},
                    {'type': 'resource', 'ky': 'name'},
                    {'foo': 'bar'}):
            with self.assertRaises(Exception):
                self.load_policy(
                    get_policy([{'type': 'set-labels', 'labels': {'x': bad}}]),
                    validate=True)


class LabelDelayedActionTest(BaseTest):

    def test_schema_validate(self):
        self.assertTrue(
            self.load_policy(
                get_policy([
                    {'type': 'mark-for-op',
                     'op': 'stop'}
                ])))

        with self.assertRaises(FilterValidationError):
            # Must specify op
            self.load_policy(get_policy([
                {'type': 'mark-for-op'}
            ]))

        with self.assertRaises(FilterValidationError):
            # Must specify right op
            self.load_policy(get_policy([
                {'type': 'mark-for-op',
                 'op': 'no-such-op'}
            ]))


class LabelActionFilterTest(BaseTest):

    def test_schema_validate(self):
        self.assertTrue(
            self.load_policy(
                get_policy(None, [
                    {'type': 'marked-for-op',
                     'op': 'stop'}
                ])))

        with self.assertRaises(FilterValidationError):
            # Must specify op
            self.load_policy(get_policy(None, [
                {'type': 'marked-for-op'}
            ]))

        with self.assertRaises(FilterValidationError):
            # Must specify right op
            self.load_policy(get_policy(None, [
                {'type': 'marked-for-op',
                 'op': 'no-such-op'}
            ]))

    def test_parse(self):
        p = self.load_policy(get_policy(None, [{"type": "marked-for-op", "op": "detach-disks"}]))
        marked_for = p.resource_manager.filters[0]
        assert marked_for.parse("resource_policy-detach-disks-2022_10_23_12_10") == (
            'resource_policy', 'detach-disks', '2022_10_23_12_10')

        assert marked_for.parse("resource_policy-create-machine-image-2022_10_23_12_10") == (
            'resource_policy', 'create-machine-image', '2022_10_23_12_10')

        assert marked_for.parse("resource_policy-delete-2022_10_23_12_10") == (
            'resource_policy', 'delete', '2022_10_23_12_10')

        assert marked_for.parse("custom-message-delete-2022_10_23_12_10") == (
            'custom-message', 'delete', '2022_10_23_12_10')
