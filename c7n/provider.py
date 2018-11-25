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

import abc
import six


from c7n.registry import PluginRegistry


clouds = PluginRegistry('c7n.providers')


@six.add_metaclass(abc.ABCMeta)
class Provider(object):
    """Provider Base Class"""

    @abc.abstractproperty
    def resources(self):
        """resources registry for this cloud provider"""

    @abc.abstractproperty
    def resource_prefix(self):
        """resource prefix for this cloud provider in policy files."""

    @abc.abstractmethod
    def initialize(self, options):
        """Perform any provider specific initialization
        """

    @abc.abstractmethod
    def initialize_policies(self, policy_collection, options):
        """Perform any initialization of policies.

        Common usage is expanding policy collection for per
        region execution and filtering policies for applicable regions.
        """

    @abc.abstractmethod
    def get_session_factory(self, options):
        """Get a credential/session factory for api usage."""


def resources(cloud_provider=None):
    results = {}
    for cname, ctype in clouds.items():
        if cloud_provider and cname != cloud_provider:
            continue
        for rname, rtype in ctype.resources.items():
            results['%s.%s' % (cname, rname)] = rtype
    return results
