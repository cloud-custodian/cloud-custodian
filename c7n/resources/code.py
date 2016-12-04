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

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, chunks


@resources.register('codecommit')
class CodeRepository(QueryResourceManager):

    class resource_type(object):
        service = 'codecommit'
        enum_spec = ('list_repositories', 'repositories', None)
        id = 'repositoryId'
        name = 'repositoryName'
        date = 'creationDate'
        dimension = None

    def augment(self, resources):
        def _augment(resource_set):
            client = local_session(
                self.session_factory).client('codecommit')
            repo_infos = client.batch_get_repositories(
                RepositoryNames=[r['repositoryName'] for r in resource_set]
            )['repositories']
            return repo_infos

        with self.executor_factory(max_workers=2) as w:
            return list(w.map(_augment, chunks(resources, 200)))


@resources.register('codebuild')
class CodeBuildProject(QueryResourceManager):

    class resource_type(object):
        service = 'codebuild'
        enum_spec = ('list_projects', 'projects', None)
        name = id = 'project'
        date = 'created'
        dimension = None

    def augment(self, resources):
        def _augment(resource_set):
            client = local_session(
                self.session_factory).client('codebuild')
            repo_infos = client.batch_get_projects(
                names=resource_set)['projects']
            return repo_infos

        with self.executor_factory(max_workers=2) as w:
            return list(w.map(_augment, chunks(resources, 200)))


@resources.register('codepipeline')
class CodeDeployPipeline(QueryResourceManager):

    class resource_type(object):
        service = 'codepipeline'
        enum_spec = ('list_pipelines', 'pipelines', None)
        name = id = 'name'
        date = 'created'
        dimension = None

    def augment(self, resources):

        def _augment(r):
            client = local_session(self.session_factory).client('codepipeline')
            attrs = client.get_pipeline(
                Name=r['name'])['pipeline']
            r.update(attrs)
            return r

        with self.executor_factory(max_workers=2) as w:
            return list(w.map(_augment, resources))


