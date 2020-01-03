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
from __future__ import absolute_import, division, print_function, unicode_literals

import unittest

from c7n.registry import PluginRegistry


class RegistryTest(unittest.TestCase):

    def test_unregister(self):

        registry = PluginRegistry('dummy')
        klass = lambda: 1  # NOQA
        registry.register('dust', klass)
        self.assertEqual(list(registry.keys()), ['dust'])
        self.assertEqual(list(registry.values()), [klass])
        registry.unregister('dust')

    def test_registry_getitem_keyerror(self):
        registry = PluginRegistry('dummy')
        try:
            registry['xyz']
        except KeyError:
            pass
        else:
            self.fail('should have raised keyerror')

    def test_event_subscriber(self):

        observed = []

        def observer(*args):
            observed.append(args)

        registry = PluginRegistry('dummy')
        registry.subscribe(PluginRegistry.EVENT_REGISTER, observer)

        @registry.register('water')
        class _plugin_impl:
            pass

        self.assertEqual(observed[0], (registry, _plugin_impl))
        self.assertEqual(list(registry.keys()), ['water'])
        self.assertRaises(ValueError, registry.subscribe, 'foo', observer)

    def test_condition(self):

        registry = PluginRegistry('dummy')

        @registry.register('mud', condition=False)
        class _plugin_impl:
            pass

        self.assertEqual(list(registry.keys()), [])

        def _plugin_impl_func():
            pass

        registry.register('concrete', _plugin_impl_func, condition=False)
        self.assertEqual(list(registry.keys()), [])
