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

from c7n.registry import PluginRegistry


clouds = PluginRegistry('c7n.providers')


@clouds.register('aws')
class AWS(object):

    resource_prefix = 'aws'
    # legacy path for older plugins
    resources = PluginRegistry('resources')


@clouds.register('gcp')
class GoogleCloud(object):

    resource_prefix = 'gcp'
    resources = PluginRegistry('%s.resources' % resource_prefix)


@clouds.register('azure')
class Azure(object):

    resource_prefix = 'azure'
    resources = PluginRegistry('%s.resources' % resource_prefix)


def resources(cloud_provider=None):
    results = {}
    for cname, ctype in clouds.items():
        if cloud_provider and cname != cloud_provider:
            continue
        for rname, rtype in ctype.resources.items():
            results['%s.%s' % (cname, rname)] = rtype
    return results
