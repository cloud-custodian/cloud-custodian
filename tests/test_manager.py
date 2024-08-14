# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from c7n.ctx import ExecutionContext
from c7n.filters import Filter
from c7n.filters.core import trim_runtime
from c7n.resources.ec2 import EC2
from c7n.tags import Tag
from .common import BaseTest, instance, Bag


class TestEC2Manager(BaseTest):

    def get_manager(self, data, config=None, session_factory=None):
        ctx = ExecutionContext(
            session_factory, Bag(
                {"name": "test-policy", 'provider_name': 'aws'}),
            config or {})
        return EC2(ctx, data)

    def test_manager_iter_filters(self):
        p = self.load_policy({
            'name': 'xyz',
            'resource': 'aws.app-elb',
            'filters': [
                {'and': [
                    {'type': 'listener',
                     'key': 'Protocol',
                     'value': 'HTTP'},
                    {'type': 'listener',
                     'key': 'DefaultActions[*].Type',
                     'op': 'ni',
                     'value_type': 'swap',
                     'value': 'redirect',
                     'matched': True}]}]})
        self.assertEqual(
            [f.type for f in p.resource_manager.iter_filters()],
            ['and', 'listener', 'listener'])

    def test_trim_runtime_filters(self):
        filter_data = [
            {'and': [
                {'not': [{
                    'type': 'event',
                    'key': 'xyz',
                    'value': 'bar'}]},
                {'key': 'value'}]}
        ]

        p = self.load_policy({
            'name': 'xyz',
            'resource': 'aws.ec2',
            'mode': {
                'type': 'config-rule',
                'role': 'xyz'},
            'filters': deepcopy(filter_data)})
        m = p.resource_manager
        trim_runtime(m.filters)
        self.assertEqual(
            [n is not None and n.type or n for n in m.iter_filters(
                block_end=True)],
            ['and', 'value', None])
        # we modify filters array in place on resource manager
        # but we don't touch the underlying policy data structure
        self.assertEqual(m.data['filters'], filter_data)

    def test_filter_get_block_op(self):
        class F(Filter):
            type = 'xyz'

        p = self.load_policy({
            'name': 'xyz',
            'resource': 'ec2',
            'filters': [
                {'and': [{'or': []}]},
                {'not': []},
                {'or': []}
            ]})

        m = p.resource_manager
        self.assertEqual(
            [n is not None and n.type or n for n in m.iter_filters(
                block_end=True)],
            ['and', 'or', None, None, 'not', None, 'or', None])

        f = F({}, m)
        m.filters.append(f)
        self.assertEqual(f.get_block_operator(), 'and')

        f = F({}, m)
        m.filters[0].filters[0].filters.append(f)
        self.assertEqual(f.get_block_operator(), 'or')

        f = F({}, m)
        m.filters[1].filters.append(f)
        self.assertEqual(f.get_block_operator(), 'not')

    def test_get_resource_manager(self):
        p = self.load_policy(
            {'resource': 'ec2',
             'name': 'instances'})
        self.assertEqual(p.resource_manager.get_resource_manager(
            'aws.lambda').type, 'lambda')
        self.assertEqual(p.resource_manager.source_type, 'describe')
#        self.assertRaises(
#            ValueError,
#            p.resource_manager.get_resource_manager,
#            'gcp.lambda')

    def test_source_propagate(self):
        p = self.load_policy(
            {'resource': 'ec2',
             'source': 'config',
             'name': 'instances'})
        manager = p.resource_manager.get_resource_manager('aws.security-group')
        self.assertEqual(manager.source_type, 'config')

    def test_manager(self):
        ec2_mgr = self.load_policy({
            'name': 'xyz',
            'resource': 'aws.ec2',
            "query": [
                {"instance-state-name": "stopped"},
                {"tag-key": "CMDBEnvironment"}, {"tag-key": "Owner"}],
            "filters": [{"tag:ASV": "absent"}]}
        ).resource_manager

        source = ec2_mgr.get_source(ec2_mgr.source_type)
        self.assertEqual(len(ec2_mgr.filters), 1)

        qf = source.get_query_params(None)
        self.assertEqual(
            qf,
            {'Filters': [
                {"Values": ["stopped"], "Name": "instance-state-name"},
                {"Values": ["CMDBEnvironment", "Owner"], "Name": "tag-key"},
            ]
        })

    def test_filters(self):
        ec2 = self.load_policy({
            'name': 'xyz', 'resource': 'aws.ec2',
            'filters': [{"tag:CMDBEnvironment": "absent"}]}).resource_manager
        self.assertEqual(
            len(
                ec2.filter_resources([instance(Tags=[{"Key": "ASV", "Value": "xyz"}])])
            ),
            1,
        )

        self.assertEqual(
            len(
                ec2.filter_resources(
                    [instance(Tags=[{"Key": "CMDBEnvironment", "Value": "xyz"}])]
                )
            ),
            0,
        )

    def test_actions(self):
        # a simple action by string
        ec2 = self.load_policy(
            {'name': 'xyz', 'resource': 'aws.ec2',
             'actions': ['mark']}).resource_manager
        self.assertEqual(len(ec2.actions), 1)
        self.assertTrue(isinstance(ec2.actions[0], Tag))

        # a configured action with dict
        ec2 = self.load_policy(
            {'name': 'xyz', 'resource': 'aws.ec2',
             "actions": [
                 {"type": "mark",
                  "value": "Missing proper tags"}]}).resource_manager

        self.assertEqual(len(ec2.actions), 1)
        self.assertTrue(isinstance(ec2.actions[0], Tag))
        self.assertEqual(
            ec2.actions[0].data, {"value": "Missing proper tags", "type": "mark"}
        )
