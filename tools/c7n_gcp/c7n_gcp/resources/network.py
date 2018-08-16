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
from c7n_gcp.query import QueryResourceManager, TypeInfo

from c7n_gcp.provider import resources


@resources.register('vpc')
class Network(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'networks'
        scope_template = "projects/{}/global/networks"


@resources.register('subnet')
class Subnet(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'networks'
        enum_spec = ('aggregatedList', 'items.*.subnetworks[]', None)
        scope_template = "projects/{}/aggregated/subnetworks"


@resources.register('firewall')
class Firewall(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'firewall'
        scope_template = "projects/{}/global/firewalls"


@resources.register('router')
class Router(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'routers'
        enum_spec = ('aggregatedList', 'items.*.routers[]', None)
        scope_template = "projects/{}/aggregated/routers"


@resources.register('route')
class Route(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'routes'
        scope_template = "projects/{}/global/routes"
