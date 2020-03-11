# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from .common import BaseTest

from c7n.provider import get_resource_class, import_resource_classes
from c7n.resources import load_resources
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
