# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from mock import Mock, patch

from .common import BaseTest

from c7n.config import Config
from c7n.provider import get_resource_class, import_resource_classes
from c7n.resources import aws, load_resources
from c7n.resources.resource_map import ResourceMap


class ProviderTest(BaseTest):

    def test_import_resource_classes(self):
        rtypes, missing = import_resource_classes(
            ResourceMap, ('aws.ec2', 'aws.app-elb', 'aws.foobar'))
        self.assertEqual(len(rtypes), 2)
        self.assertEqual([r.type for r in rtypes], ['ec2', 'app-elb'])
        self.assertEqual(missing, ['aws.foobar'])

#    def test_import_resource_classes_wildcard(self):
#        rtypes = import_resource_classes(ResourceMap, ('*',))

    def test_get_resource_class(self):
        with self.assertRaises(KeyError) as ectx:
            get_resource_class('aws.xyz')
        self.assertIn("resource: xyz", str(ectx.exception))

        with self.assertRaises(KeyError) as ectx:
            get_resource_class('xyz.foo')
        self.assertIn("provider: xyz", str(ectx.exception))

        load_resources(('aws.ec2',))
        ec2 = get_resource_class('aws.ec2')
        self.assertEqual(ec2.type, 'ec2')

    def _mock_initialize_resource(self, resource_class):
        resource_class.filter_registry.register('mock_filter', Mock)
        resource_class.action_registry.register('mock_action', Mock)

    def test_provider_specific_registry(self):
        with patch.object(aws.AWS, 'initialize_resource') as mock_aws:
            mock_aws.side_effect = self._mock_initialize_resource
            p = self.load_policy({
                'name': 'foo',
                'resource': 's3',
            }, config=Config.empty(regions=['us-east-1']))
            self.assertIn('mock_filter', p.resource_manager.filter_registry.keys())
            self.assertIn('mock_action', p.resource_manager.action_registry.keys())
            mock_aws.reset_mock(side_effect=True)
