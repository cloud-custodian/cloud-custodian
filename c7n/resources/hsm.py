# Copyright 2017 Capital One Services, LLC
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

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('hsm')
class CloudHSM(QueryResourceManager):

    class resource_type(object):
        service = 'cloudhsm'
        enum_spec = ('list_hsms', 'HsmList', None)
        id = 'HsmArn'
        name = 'Name'
        date = dimension = None
        detail_spec = (
            "describe_hsm", "HsmArn", None, None)
        filter_name = None


@resources.register('hsm-hapg')
class PartitionGroup(QueryResourceManager):

    class resource_type(object):
        service = 'cloudhsm'
        enum_spec = ('list_hapgs', 'HapgList', None)
        detail_spec = ('describe_hapg', 'HapgArn', None, None)
        id = 'HapgArn'
        name = 'HapgSerial'
        date = 'LastModifiedTimestamp'
        dimension = None
        filter_name = None


@resources.register('hsm-client')
class HSMClient(QueryResourceManager):

    class resource_type(object):
        service = 'cloudhsm'
        enum_spec = ('list_luna_clients', 'ClientList', None)
        detail_spec = ('describe_luna_client', 'ClientArn', None, None)
        id = 'ClientArn'
        name = 'Label'
        date = dimension = None
        filter_name = None
