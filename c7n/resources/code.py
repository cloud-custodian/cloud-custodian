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

from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.filters.vpc import SubnetFilter, SecurityGroupFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, get_retry, type_schema


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
        filter_name = None


@CodeRepository.action_registry.register('delete')
class DeleteRepository(BaseAction):
    """Action to delete code commit

    It is recommended to use a filter to avoid unwanted deletion of repos

    :example:

    .. code-block:: yaml

            policies:
              - name: codecommit-delete
                resource: codecommit
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("codecommit:DeleteRepository",)

    def process(self, repositories):
        client = local_session(
            self.manager.session_factory).client('codecommit')
        for r in repositories:
            self.process_repository(client, r)

    def process_repository(self, client, repository):
        try:
            client.delete_repository(repositoryName=repository['repositoryName'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting repo:\n %s" % e)


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
        filter_name = None
        config_type = "AWS::CodeBuild::Project"


class BuildSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "vpcConfig.subnets[]"


class BuildSecurityGroupFilter(SecurityGroupFilter):

    RelatedIdsExpression = "vpcConfig.securityGroupIds[]"


@CodeBuildProject.action_registry.register('delete')
class DeleteProject(BaseAction):
    """Action to delete code build

    It is recommended to use a filter to avoid unwanted deletion of builds

    :example:

    .. code-block:: yaml

            policies:
              - name: codebuild-delete
                resource: codebuild
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("codebuild:DeleteProject",)

    def process(self, projects):
        client = local_session(self.manager.session_factory).client('codebuild')
        for p in projects:
            self.process_project(client, p)

    def process_project(self, client, project):

        try:
            client.delete_project(name=project['name'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting project:\n %s" % e)


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
        filter_name = None
