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
# limitations under the License.from c7n_azure.provider import resources

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager, ChildArmResourceManager


@resources.register('sqldatabase')
class SqlDatabase(ChildArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.sql'
        client = 'SqlManagementClient'
        enum_spec = ('databases', 'list_by_server', {
            'resource_group_name': 'resourceGroup',
            'server_name': 'name'
        })
        parent_spec = ChildArmResourceManager.ParentSpec(
            manager_name='sqlserver',
            annotate_parent=True
        )
