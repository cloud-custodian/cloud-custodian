# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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

        @registry.register('hot')
        class _plugin_impl1:
            pass

        registry.subscribe(observer)

        @registry.register('water')
        class _plugin_impl2:
            pass

        self.assertEqual(observed, [])

        registry.notify(_plugin_impl1)
        registry.notify(_plugin_impl2)

        self.assertEqual(observed[1], (registry, _plugin_impl2))
        self.assertEqual(list(sorted(registry.keys())), ['hot', 'water'])

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
