# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest import mock

from gcp_common import BaseTest
from googleapiclient.errors import HttpError
from httplib2 import Response

from c7n.filters import FilterValidationError
from c7n.resources import load_resources
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

    def test_unchanged_labels_skip_write(self):
        for resource_type in ('gcp.bucket', 'gcp.instance'):
            for action in (
                    {'type': 'set-labels', 'remove': ['missing']},
                    {'type': 'set-labels', 'labels': {'keep': 'yes'}}):
                with self.subTest(resource_type=resource_type, action=action):
                    policy = self.load_policy({
                        'name': 'test-label-noop',
                        'resource': resource_type,
                        'actions': [action]})
                    manager = policy.resource_manager
                    resource = dict(
                        LABEL_REMOVAL_RESOURCES[resource_type], labels={'keep': 'yes'})
                    client = mock.MagicMock()
                    manager.actions[0].process_resource_set(
                        client, manager.get_model(), [resource])
                    client.execute_command.assert_not_called()

    def test_merge_patch_types_flagged(self):
        for resource_type in LABEL_REMOVAL_RESOURCES:
            with self.subTest(resource_type=resource_type):
                policy = self.load_policy({'name': 'test', 'resource': resource_type})
                self.assertEqual(
                    policy.resource_manager.get_model().labels_merge_patch,
                    resource_type in MERGE_PATCH_TYPES)

    def test_merge_patch_ignores_mask_like_label_keys(self):
        params = self.get_params(
            'gcp.bucket',
            {'type': 'set-labels', 'remove': ['env']},
            {'update_mask': 'x', 'env': 'prod'})
        self.assertEqual(params['body']['labels'], {'update_mask': 'x', 'env': None})


class SetLabelsClearToRemoveTest(BaseTest):
    """gcp.dns-managed-zone patches drop null label values, so removing a
    subset of labels clears them all and then sets the survivors.
    """

    def run_action(self, action, current_labels, client=None, fresh_labels=None):
        """Run the action against a zone listed with current_labels, whose
        labels are fresh_labels (default: unchanged) when refreshed.
        """
        policy = self.load_policy({
            'name': 'test-label-clear-to-remove',
            'resource': 'gcp.dns-managed-zone',
            'actions': [action]})
        manager = policy.resource_manager
        resource = dict(LABEL_REMOVAL_RESOURCES['gcp.dns-managed-zone'], labels=current_labels)
        self.client = client = client or mock.MagicMock()
        client.execute_query.return_value = {
            'labels': current_labels if fresh_labels is None else fresh_labels}
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
        self.client.execute_query.assert_called_once_with(
            'get', {'project': 'cloud-custodian', 'managedZone': 'zone-1'})

    def test_partial_remove_keeps_labels_added_since_listing(self):
        calls = self.run_action(
            {'type': 'set-labels', 'remove': ['remove_a']},
            {'keep': 'yes', 'remove_a': 'a'},
            fresh_labels={'keep': 'yes', 'remove_a': 'a', 'added_later': 'x'})
        self.assertEqual(calls, [
            ('patch', {'keep': None, 'remove_a': None, 'added_later': None}),
            ('patch', {'keep': 'yes', 'added_later': 'x'}),
        ])

    def test_remove_already_gone_since_listing_is_noop(self):
        calls = self.run_action(
            {'type': 'set-labels', 'remove': ['remove_a']},
            {'keep': 'yes', 'remove_a': 'a'},
            fresh_labels={'keep': 'yes'})
        self.assertEqual(calls, [])

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

    def test_remove_absent_label_is_noop(self):
        calls = self.run_action(
            {'type': 'set-labels', 'remove': ['missing']}, {'keep': 'yes'})
        self.assertEqual(calls, [])
        self.client.execute_query.assert_not_called()

    def test_add_is_single_patch(self):
        calls = self.run_action(
            {'type': 'set-labels', 'labels': {'added': 'new'}}, {'keep': 'yes'})
        self.assertEqual(calls, [('patch', {'keep': 'yes', 'added': 'new'})])
        self.client.execute_query.assert_not_called()

    def test_set_failure_restores_cleared_labels(self):
        client = mock.MagicMock()
        client.execute_command.side_effect = [
            {}, HttpError(Response({'status': '500'}), b''), {}]
        log_output = self.capture_logging('custodian.actions')
        with self.assertRaises(HttpError):
            self.run_action(
                {'type': 'set-labels', 'remove': ['remove_a']},
                {'keep': 'yes', 'remove_a': 'a'},
                client=client)
        calls = [params['body']['labels']
                 for (_, params), _ in client.execute_command.call_args_list]
        self.assertEqual(calls, [
            {'keep': None, 'remove_a': None},
            {'keep': 'yes'},
            {'keep': 'yes', 'remove_a': 'a'},
        ])
        self.assertIn(
            "failed to set labels on zone-1, restored {'keep': 'yes', 'remove_a': 'a'}",
            log_output.getvalue())

    def test_set_and_restore_failure_logs_labels(self):
        client = mock.MagicMock()
        error = HttpError(Response({'status': '500'}), b'')
        client.execute_command.side_effect = [{}, error, error]
        log_output = self.capture_logging('custodian.actions')
        with self.assertRaises(HttpError):
            self.run_action(
                {'type': 'set-labels', 'remove': ['remove_a']},
                {'keep': 'yes', 'remove_a': 'a'},
                client=client)
        self.assertIn(
            "cleared labels on zone-1 and failed to restore {'keep': 'yes', 'remove_a': 'a'}",
            log_output.getvalue())

    def test_set_waits_for_clear(self):
        client = mock.MagicMock()
        pending = {'id': 'op-1', 'status': 'pending'}
        client.execute_command.side_effect = [pending, {}]
        model = self.load_policy(
            {'name': 'test', 'resource': 'gcp.dns-managed-zone'}).resource_manager.get_model()
        sent_before_wait = []
        wait = mock.MagicMock(side_effect=lambda *args: sent_before_wait.append(
            client.execute_command.call_count))
        with mock.patch.object(model, 'wait_for_label_op', wait):
            self.run_action(
                {'type': 'set-labels', 'remove': ['remove_a']},
                {'keep': 'yes', 'remove_a': 'a'},
                client=client)
        self.assertEqual(wait.call_args[0][2], pending)
        self.assertEqual(sent_before_wait, [1])
        self.assertEqual(client.execute_command.call_count, 2)

    def test_wait_timeout_restores_cleared_labels(self):
        client = mock.MagicMock()
        client.execute_command.side_effect = [{'id': 'op-1', 'status': 'pending'}, {}]
        model = self.load_policy(
            {'name': 'test', 'resource': 'gcp.dns-managed-zone'}).resource_manager.get_model()
        with mock.patch.object(
                model, 'wait_for_label_op', mock.MagicMock(side_effect=TimeoutError)), \
                self.assertRaises(TimeoutError):
            self.run_action(
                {'type': 'set-labels', 'remove': ['remove_a']},
                {'keep': 'yes', 'remove_a': 'a'},
                client=client)
        self.assertEqual(
            client.execute_command.call_args[0][1]['body']['labels'],
            {'keep': 'yes', 'remove_a': 'a'})

    def test_failure_does_not_block_other_zones(self):
        policy = self.load_policy({
            'name': 'test-label-clear-to-remove',
            'resource': 'gcp.dns-managed-zone',
            'actions': [{'type': 'set-labels', 'remove': ['remove_a']}]})
        manager = policy.resource_manager
        model = manager.get_model()
        zones = [
            dict(LABEL_REMOVAL_RESOURCES['gcp.dns-managed-zone'], name=name,
                 labels={'keep': 'yes', 'remove_a': 'a'})
            for name in ('zone-1', 'zone-2')]
        client = mock.MagicMock()
        client.execute_query.return_value = {'labels': {'keep': 'yes', 'remove_a': 'a'}}
        client.execute_command.return_value = {'id': 'op-1', 'status': 'pending'}
        wait = mock.MagicMock(side_effect=[TimeoutError, None])
        with mock.patch.object(model, 'wait_for_label_op', wait), \
                self.assertRaises(TimeoutError):
            manager.actions[0].process_resource_set(client, model, zones)
        zone_2_labels = [
            params['body']['labels']
            for (_, params), _ in client.execute_command.call_args_list
            if params['managedZone'] == 'zone-2']
        self.assertEqual(zone_2_labels, [{'keep': None, 'remove_a': None}, {'keep': 'yes'}])

    def test_permissions_include_operation_poll(self):
        policy = self.load_policy({
            'name': 'test-label-perms',
            'resource': 'gcp.dns-managed-zone',
            'actions': [{'type': 'set-labels', 'labels': {'env': 'prod'}}]})
        self.assertEqual(
            set(policy.resource_manager.actions[0].get_permissions()),
            {'dns.managedZones.update', 'dns.managedZones.get', 'dns.managedZoneOperations.get'})


class DnsManagedZoneLabelOpsTest(BaseTest):

    def get_model(self):
        return self.load_policy(
            {'name': 'test', 'resource': 'gcp.dns-managed-zone'}).resource_manager.get_model()

    def test_get_sets_project_id(self):
        client = mock.MagicMock()
        client.execute_query.return_value = {'name': 'zone-1'}
        zone = self.get_model().get(
            client, {'project_id': 'cloud-custodian', 'zone_name': 'zone-1'})
        self.assertEqual(zone['project_id'], 'cloud-custodian')

    def test_wait_for_label_op_polls_pending(self):
        client = mock.MagicMock()
        client.execute_query.side_effect = [
            {'id': 'op-1', 'status': 'pending'}, {'id': 'op-1', 'status': 'done'}]
        session = mock.MagicMock()
        session.client.return_value = client
        with mock.patch('c7n_gcp.resources.dns.local_session', return_value=session), \
                mock.patch('c7n_gcp.resources.dns.time.sleep'):
            op = self.get_model().wait_for_label_op(
                None, LABEL_REMOVAL_RESOURCES['gcp.dns-managed-zone'],
                {'id': 'op-1', 'status': 'pending'})
        self.assertEqual(op['status'], 'done')
        client.execute_query.assert_called_with('get', {
            'project': 'cloud-custodian', 'managedZone': 'zone-1', 'operation': 'op-1'})

    def test_wait_for_label_op_skips_done(self):
        with mock.patch('c7n_gcp.resources.dns.local_session') as local_session:
            self.get_model().wait_for_label_op(
                None, LABEL_REMOVAL_RESOURCES['gcp.dns-managed-zone'], {'status': 'done'})
        local_session.assert_not_called()

    def test_wait_for_label_op_times_out(self):
        client = mock.MagicMock()
        client.execute_query.return_value = {'id': 'op-1', 'status': 'pending'}
        session = mock.MagicMock()
        session.client.return_value = client
        with mock.patch('c7n_gcp.resources.dns.local_session', return_value=session), \
                mock.patch('c7n_gcp.resources.dns.time.sleep'), \
                self.assertRaises(TimeoutError):
            self.get_model().wait_for_label_op(
                None, LABEL_REMOVAL_RESOURCES['gcp.dns-managed-zone'],
                {'id': 'op-1', 'status': 'pending'}, timeout=0)


# Update mask spellings used across apis, in query parameters or the body.
UPDATE_MASK_KEYS = frozenset(('updateMask', 'update_mask', 'fieldMask', 'field_mask'))


def has_update_mask(params):
    if not isinstance(params, dict):
        return False
    return any(k in UPDATE_MASK_KEYS or has_update_mask(v) for k, v in params.items())


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


def test_patch_label_ops_declare_merge_semantics():
    """A labels patch without an update mask merges into the existing labels,
    so removal only works if the type declares how (labels_merge_patch or
    labels_clear_to_remove), and a masked patch must declare neither.
    """
    load_resources(('gcp.*',))
    mismatched = []
    for name, resource in resources.items():
        model = resource.resource_type
        if not model.labels or model.labels_op != 'patch':
            continue
        # No labels, so label keys can't be mistaken for a mask.
        params = model.get_label_params(PATCH_LABEL_RESOURCE, {})
        merges = model.labels_merge_patch or model.labels_clear_to_remove
        if has_update_mask(params) == merges:
            mismatched.append(name)
    assert not mismatched, (
        "labels patch without an update mask should set labels_merge_patch or "
        "labels_clear_to_remove, and a masked one neither: %s" % ", ".join(sorted(mismatched)))
