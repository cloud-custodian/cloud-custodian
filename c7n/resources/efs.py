# Copyright 2016 Capital One Services, LLC
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
from c7n.actions import Action
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema


@resources.register('efs')
class ElasticFileSystem(QueryResourceManager):

    class resource_type(object):
        service = 'efs'
        enum_spec = ('describe_file_systems', 'FileSystems', None)
        id = 'FileSystemId'
        name = 'Name'
        date = 'CreationTime'
        dimension = None


@ElasticFileSystem.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('efs')
        mounted = []
        for r in resources:
            if r['NumberOfMountTargets']:
                mounted.append(r)
        self.unmount_filesystems(mounted)
        for r in resources:
            client.delete_file_system(FileSystemId=r['FileSystemId'])

    def unmount_filesystems(self, resources):
        client = local_session(self.manager.session_factory).client('efs')
        fs_ids = {r['FileSystmId'] for r in resources}
        targets = [t for t in client.describe_mount_targets()['MountTargets']
                   if t['FileSystemId'] in fs_ids]
        for t in targets:
            client.delete_mount_target(TargetId=t['MountTargetId'])
