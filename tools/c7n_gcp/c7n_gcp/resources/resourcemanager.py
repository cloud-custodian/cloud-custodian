# Copyright 2017-2018 Capital One Services, LLC
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


@resources.register('organization')
class Organization(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudresourcemanager'
        version = 'v1'
        component = 'organizations'
        scope = 'global'


@resources.register('folder')
class Folder(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudresourcemanager'
        version = 'v2'
        component = 'folders'
        scope = 'global'


@resources.register('project')
class Project(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudresourcemanager'
        version = 'v1'
        component = 'projects'
        scope = 'global'
        enum_spec = ('list', 'projects', None)
