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
