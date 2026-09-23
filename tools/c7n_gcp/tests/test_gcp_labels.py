# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest import mock

from gcp_common import BaseTest
from googleapiclient.errors import HttpError
from httplib2 import Response

from c7n.filters import FilterValidationError
from c7n.resources import load_resources
from c7n_gcp.actions.labels import has_update_mask
from c7n_gcp.provider import resources


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


# Minimal resources carrying enough identity for each type's get_label_params.
LABEL_REMOVAL_RESOURCES = {
    'gcp.bucket': {'name': 'bucket-1'},
    'gcp.bq-dataset': {
        'datasetReference': {'projectId': 'cloud-custodian', 'datasetId': 'dataset_1'}},
    'gcp.bq-table': {
        'tableReference': {
            'projectId': 'cloud-custodian', 'datasetId': 'dataset_1', 'tableId': 'table_1'}},
    'gcp.dns-managed-zone': {'project_id': 'cloud-custodian', 'name': 'zone-1'},
    'gcp.sql-instance': {
        'selfLink': 'https://sqladmin.googleapis.com/sql/v1beta4'
                    '/projects/cloud-custodian/instances/sql-1'},
    'gcp.instance': {
        'selfLink': 'https://www.googleapis.com/compute/v1'
                    '/projects/cloud-custodian/zones/us-central1-a/instances/instance-1',
        'labelFingerprint': 'abc='},
    'gcp.kms-cryptokey': {
        'name': 'projects/cloud-custodian/locations/global/keyRings/ring-1/cryptoKeys/key-1'},
}

# Label ops with merge-patch semantics: omitted keys are left in place, so
# removal must send the key with a null value.
MERGE_PATCH_TYPES = ('gcp.bucket', 'gcp.bq-dataset', 'gcp.bq-table', 'gcp.sql-instance')


def label_body(resource_type, params):
    if resource_type == 'gcp.sql-instance':
        return params['body']['settings']['userLabels']
    return params['body']['labels']


class SetLabelsRemoveTest(BaseTest):

    def get_params(self, resource_type, action, current_labels):
        policy = self.load_policy({
            'name': 'test-label-remove',
            'resource': resource_type,
            'actions': [action]})
        resource = dict(LABEL_REMOVAL_RESOURCES[resource_type], labels=current_labels)
        manager = policy.resource_manager
        return manager.actions[0].get_resource_params(manager.get_model(), resource)

    def test_merge_patch_remove_sends_null(self):
        for resource_type in MERGE_PATCH_TYPES:
            with self.subTest(resource_type=resource_type):
                params = self.get_params(
                    resource_type,
                    {'type': 'set-labels', 'remove': ['remove_a', 'remove_b']},
                    {'keep': 'yes', 'remove_a': 'a', 'remove_b': 'b'})
                self.assertEqual(
                    label_body(resource_type, params),
                    {'keep': 'yes', 'remove_a': None, 'remove_b': None})

    def test_merge_patch_remove_all_sends_null(self):
        for resource_type in MERGE_PATCH_TYPES:
            with self.subTest(resource_type=resource_type):
                params = self.get_params(
                    resource_type,
                    {'type': 'set-labels', 'remove': ['remove_a']},
                    {'remove_a': 'a'})
                self.assertEqual(label_body(resource_type, params), {'remove_a': None})

    def test_merge_patch_remove_absent_label_is_noop(self):
        for resource_type in MERGE_PATCH_TYPES:
            with self.subTest(resource_type=resource_type):
                params = self.get_params(
                    resource_type,
                    {'type': 'set-labels', 'remove': ['missing']},
                    {'keep': 'yes'})
                self.assertEqual(label_body(resource_type, params), {'keep': 'yes'})

    def test_merge_patch_add_and_remove(self):
        for resource_type in MERGE_PATCH_TYPES:
            with self.subTest(resource_type=resource_type):
                params = self.get_params(
                    resource_type,
                    {'type': 'set-labels', 'labels': {'added': 'new'}, 'remove': ['remove_a']},
                    {'keep': 'yes', 'remove_a': 'a'})
                self.assertEqual(
                    label_body(resource_type, params),
                    {'keep': 'yes', 'added': 'new', 'remove_a': None})

    def test_merge_patch_mark_for_op_sends_no_null(self):
        for resource_type in MERGE_PATCH_TYPES:
            with self.subTest(resource_type=resource_type):
                params = self.get_params(
                    resource_type,
                    {'type': 'mark-for-op', 'op': 'set-labels', 'label': 'marked'},
                    {'keep': 'yes'})
                labels = label_body(resource_type, params)
                self.assertEqual(labels['keep'], 'yes')
                self.assertNotIn(None, labels.values())

    def test_replace_and_masked_types_omit_removed_labels(self):
        # setLabels replaces the whole map, and masked patches replace the
        # masked field, so removed keys must be omitted rather than nulled.
        for resource_type in ('gcp.instance', 'gcp.kms-cryptokey'):
            with self.subTest(resource_type=resource_type):
                params = self.get_params(
                    resource_type,
                    {'type': 'set-labels', 'remove': ['remove_a']},
                    {'keep': 'yes', 'remove_a': 'a'})
                self.assertEqual(params['body']['labels'], {'keep': 'yes'})

    def test_merge_patch_override(self):
        policy = self.load_policy({'name': 'test', 'resource': 'gcp.bucket'})
        self.patch(policy.resource_manager.get_model(), 'labels_merge_patch', False)
        params = self.get_params(
            'gcp.bucket',
            {'type': 'set-labels', 'remove': ['remove_a']},
            {'keep': 'yes', 'remove_a': 'a'})
        self.assertEqual(params['body']['labels'], {'keep': 'yes'})


class SetLabelsClearToRemoveTest(BaseTest):
    """gcp.dns-managed-zone patches drop null label values, so removing a
    subset of labels clears them all and then sets the survivors.
    """

    def run_action(self, action, current_labels, client=None):
        policy = self.load_policy({
            'name': 'test-label-clear-to-remove',
            'resource': 'gcp.dns-managed-zone',
            'actions': [action]})
        manager = policy.resource_manager
        resource = dict(LABEL_REMOVAL_RESOURCES['gcp.dns-managed-zone'], labels=current_labels)
        client = client or mock.MagicMock()
        manager.actions[0].process_resource_set(client, manager.get_model(), [resource])
        return [
            (op, params['body']['labels'])
            for (op, params), _ in client.execute_command.call_args_list
        ]

    def test_partial_remove_clears_then_sets(self):
        calls = self.run_action(
            {'type': 'set-labels', 'remove': ['remove_a', 'remove_b']},
            {'keep': 'yes', 'remove_a': 'a', 'remove_b': 'b'})
        self.assertEqual(calls, [
            ('patch', {'keep': None, 'remove_a': None, 'remove_b': None}),
            ('patch', {'keep': 'yes'}),
        ])

    def test_partial_remove_with_add(self):
        calls = self.run_action(
            {'type': 'set-labels', 'labels': {'added': 'new'}, 'remove': ['remove_a']},
            {'keep': 'yes', 'remove_a': 'a'})
        self.assertEqual(calls, [
            ('patch', {'keep': None, 'remove_a': None}),
            ('patch', {'keep': 'yes', 'added': 'new'}),
        ])

    def test_replace_all_with_add_clears_then_sets(self):
        # Every existing label goes, but one is added, so a single patch
        # would leave the removed labels in place.
        calls = self.run_action(
            {'type': 'set-labels', 'labels': {'added': 'new'}, 'remove': ['remove_a']},
            {'remove_a': 'a'})
        self.assertEqual(calls, [
            ('patch', {'remove_a': None}),
            ('patch', {'added': 'new'}),
        ])

    def test_full_remove_only_clears(self):
        calls = self.run_action(
            {'type': 'set-labels', 'remove': ['remove_a', 'remove_b']},
            {'remove_a': 'a', 'remove_b': 'b'})
        self.assertEqual(calls, [('patch', {'remove_a': None, 'remove_b': None})])

    def test_remove_absent_label_is_single_patch(self):
        calls = self.run_action(
            {'type': 'set-labels', 'remove': ['missing']}, {'keep': 'yes'})
        self.assertEqual(calls, [('patch', {'keep': 'yes'})])

    def test_add_is_single_patch(self):
        calls = self.run_action(
            {'type': 'set-labels', 'labels': {'added': 'new'}}, {'keep': 'yes'})
        self.assertEqual(calls, [('patch', {'keep': 'yes', 'added': 'new'})])

    def test_set_failure_after_clear_logs_labels(self):
        client = mock.MagicMock()
        client.execute_command.side_effect = [
            {}, HttpError(Response({'status': '500'}), b'')]
        log_output = self.capture_logging('custodian.actions')
        with self.assertRaises(HttpError):
            self.run_action(
                {'type': 'set-labels', 'remove': ['remove_a']},
                {'keep': 'yes', 'remove_a': 'a'},
                client=client)
        self.assertIn(
            "cleared labels on zone-1 but failed to set {'keep': 'yes'}",
            log_output.getvalue())


def test_has_update_mask():
    assert has_update_mask({'name': 'x', 'updateMask': 'labels'})
    assert has_update_mask({'body': {'instance': {}, 'field_mask': 'labels'}})
    assert not has_update_mask({'body': {'labels': {}, 'netmask': '255.255.255.0'}})
    assert not has_update_mask({'bucket': 'x', 'body': {'labels': {}}})


# Superset of the identity fields read by patch-op get_label_params
# implementations. Extend it if a new type needs another field.
PATCH_LABEL_RESOURCE = {
    'name': 'projects/cloud-custodian/locations/us-central1/things/thing-1',
    'selfLink': 'https://example.googleapis.com/v1/projects/cloud-custodian/instances/thing-1',
    'project_id': 'cloud-custodian',
    'datasetReference': {'projectId': 'cloud-custodian', 'datasetId': 'dataset_1'},
    'tableReference': {
        'projectId': 'cloud-custodian', 'datasetId': 'dataset_1', 'tableId': 'table_1'},
}


def test_inferred_merge_patch_types():
    """Snapshot of the types whose label removal sends nulls, so a change to
    the inferred set shows up in review.
    """
    load_resources(('gcp.*',))
    inferred = set()
    for name, resource in resources.items():
        model = resource.resource_type
        if not model.labels or model.labels_op != 'patch':
            continue
        action = resource.action_registry['set-labels']({'remove': ['env']})
        params = model.get_label_params(PATCH_LABEL_RESOURCE, {'env': 'test'})
        if action.is_merge_patch(model, params):
            inferred.add(name)
    assert inferred == set(MERGE_PATCH_TYPES)
