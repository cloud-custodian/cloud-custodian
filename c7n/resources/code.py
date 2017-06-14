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
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import get_retry


@resources.register('codecommit')
class CodeRepository(QueryResourceManager):

    retry = staticmethod(get_retry(('Throttling',)))

    class resource_type(object):
        service = 'codecommit'
        enum_spec = ('list_repositories', 'repositories', None)
        batch_detail_spec = (
            'batch_get_repositories', 'repositoryNames', 'repositoryName',
            'repositories')
        id = 'repositoryId'
        name = 'repositoryName'
        date = 'creationDate'
        dimension = None


@resources.register('codebuild')
class CodeBuildProject(QueryResourceManager):

    class resource_type(object):
        service = 'codebuild'
        enum_spec = ('list_projects', 'projects', None)
        batch_detail_spec = (
            'batch_get_projects', 'names', None, 'projects')
        name = id = 'project'
        date = 'created'
        dimension = None


@resources.register('codepipeline')
class CodeDeployPipeline(QueryResourceManager):

    retry = staticmethod(get_retry(('Throttling',)))

    class resource_type(object):
        service = 'codepipeline'
        enum_spec = ('list_pipelines', 'pipelines', None)
        detail_spec = ('get_pipeline', 'name', 'name', 'pipeline')
        dimension = filter_name = None
        name = id = 'name'
        date = 'created'
