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
#
# AWS resources to manage
#
from __future__ import absolute_import, division, print_function, unicode_literals

import time
import os

LOADED = False

from c7n.provider import clouds


def load_resources(resource_types=('*',)):
    print('loaded')
    load_providers(resource_types)
    for p in clouds.values():
        p.get_resource_types(resource_types)


def load_providers(resource_types):
    global LOADED
    if LOADED:
        return

    # Even though we're lazy loading resources we still need to import
    # those that are making available generic filters/actions
    if '*' in resource_types or any([r.startswith('aws.') for r in resource_types]):
        import c7n.resources.securityhub
        import c7n.resources.sfn # NOQA

    # Conditionally import known resource providers.
    if '*' in resource_types or any([r.startswith('azure.') for r in resource_types]):
        from c7n_azure.entry import initialize_azure
        initialize_azure()

    if '*' in resource_types or any([r.startswith('gcp.') for r in resource_types]):
        from c7n_gcp.entry import initialize_gcp
        initialize_gcp()

    if '*' in resource_types or any([r.startswith('k8s.') for r in resource_types]):
        from c7n_kube.entry import initialize_kube
        initialize_kube()

    # Load external plugins (private sdks etc)
    #
    # We default to loading known cloud providers
    # to avoid the runtime costs in serverless
    # environments of scanning the entire python
    # path for entry points.
    #
    # **Note** this is unsupported and may go away in future.
    from c7n.manager import resources as resource_registry
    if 'C7N_EXTPLUGINS' in os.environ:
        resource_registry.load_plugins()

    resource_registry.notify(resource_registry.EVENT_FINAL)
    LOADED = True

