# Copyright 2015-2017 Capital One Services, LLC
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


class PluginRegistry(object):
    """A plugin registry

    Custodian is intended to be innately pluggable both internally and
    externally, for resource types and their filters and actions.

    This plugin registry abstraction provides the core mechanism for
    that. Its a simple string to class map, with python package
    entry_point loading for external plugins.

    As an example of defining an external plugin using a python package

    .. code-block:: python

       setup(
           name="custodian_cmdb",
           description="Custodian filters for interacting with internal CMDB"
           version='1.0',
           packages=find_packages(),
           entry_points={
                'console_scripts': [
                     'custodian.ec2.filters = custodian_cmdb:filter_ec2']},
           )

    For loading the plugins we can simply invoke method:load_plugins like
    so::

      PluginRegistry('ec2.filters').load_plugins()

    """

    EVENT_REGISTER = 0
    EVENT_FINAL = 1
    EVENTS = (EVENT_REGISTER, EVENT_FINAL)

    def __init__(self, plugin_type):
        self.plugin_type = plugin_type
        self._factories = {}
        self._subscribers = {x: [] for x in self.EVENTS}

    def subscribe(self, event, func):
        if event not in self.EVENTS:
            raise ValueError('Invalid event')
        self._subscribers[event].append(func)

    def register(self, name, klass=None):
        # invoked as function
        if klass:
            klass.type = name
            self._factories[name] = klass
            self.notify(self.EVENT_REGISTER, klass)
            return klass

        # invoked as class decorator
        def _register_class(klass):
            self._factories[name] = klass
            klass.type = name
            self.notify(self.EVENT_REGISTER, klass)
            return klass
        return _register_class

    def unregister(self, name):
        if name in self._factories:
            del self._factories[name]

    def notify(self, event, key=None):
        for subscriber in self._subscribers[event]:
            subscriber(self, key)

    def __getitem__(self, name):
        return self.get(name)

    def get(self, name):
        return self._factories.get(name)

    def keys(self):
        return self._factories.keys()

    def items(self):
        return self._factories.items()

    def load_plugins(self):
        """ Load external plugins.

        Custodian is intended to interact with internal and external systems
        that are not suitable for embedding into the custodian code base.
        """
        try:
            from pkg_resources import iter_entry_points
        except ImportError:
            return
        for ep in iter_entry_points(group="custodian.%s" % self.plugin_type):
            f = ep.load()
            f()
