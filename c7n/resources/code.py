# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.filters.vpc import SubnetFilter, SecurityGroupFilter, VpcFilter
from c7n.manager import resources
from c7n.query import (
    QueryResourceManager, DescribeSource, ConfigSource, TypeInfo, ChildResourceManager)
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema, jmespath_search
from c7n import query

from .securityhub import OtherResourcePostFinding


class DescribeRepo(DescribeSource):

    def augment(self, resources):
        return universal_augment(
            self.manager,
            super().augment(resources)
        )


@resources.register('codecommit')
class CodeRepository(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'codecommit'
        enum_spec = ('list_repositories', 'repositories', None)
        batch_detail_spec = (
            'batch_get_repositories', 'repositoryNames', 'repositoryName',
            'repositories', None)
        name = id = 'repositoryName'
        arn = "Arn"
        date = 'creationDate'
        cfn_type = 'AWS::CodeCommit::Repository'
        universal_taggable = object()
        permissions_augment = ("codecommit:ListTagsForResource",)

    source_mapping = {
        'describe': DescribeRepo,
        'config': ConfigSource
    }

    def get_resources(self, ids, cache=True, augment=True):
        return universal_augment(self, self.augment([{'repositoryName': i} for i in ids]))


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


class DescribeBuild(DescribeSource):

    def augment(self, resources):
        return universal_augment(
            self.manager,
            super(DescribeBuild, self).augment(resources))


class ConfigBuild(ConfigSource):

    def load_resource(self, item):
        item_config = item['configuration']
        item_config['Tags'] = [
            {'Key': t['key'], 'Value': t['value']} for t in item_config.get('tags')]

        # AWS Config garbage mangle undo.

        if 'queuedtimeoutInMinutes' in item_config:
            item_config['queuedTimeoutInMinutes'] = int(item_config.pop('queuedtimeoutInMinutes'))

        artifacts = item_config.pop('artifacts')
        item_config['artifacts'] = artifacts.pop(0)
        if artifacts:
            item_config['secondaryArtifacts'] = artifacts
        sources = item_config['source']
        item_config['source'] = sources.pop(0)
        if sources:
            item_config['secondarySources'] = sources

        if 'vpcConfig' in item_config and 'subnets' in item_config['vpcConfig']:
            item_config['vpcConfig']['subnets'] = [
                s['subnet'] for s in item_config['vpcConfig']['subnets']]

        item_config['arn'] = 'arn:aws:codebuild:{}:{}:project/{}'.format(
            self.manager.config.region, self.manager.config.account_id, item_config['name'])
        return item_config


@resources.register('codebuild')
class CodeBuildProject(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'codebuild'
        enum_spec = ('list_projects', 'projects', None)
        batch_detail_spec = (
            'batch_get_projects', 'names', None, 'projects', None)
        name = id = 'name'
        arn = 'arn'
        date = 'created'
        dimension = 'ProjectName'
        cfn_type = config_type = "AWS::CodeBuild::Project"
        arn_type = 'project'
        universal_taggable = object()

    source_mapping = {
        'describe': DescribeBuild,
        'config': ConfigBuild
    }


@resources.register('codebuild-credential')
class CodeBuildSourceCredentials(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'codebuild'
        enum_spec = ('list_source_credentials', 'sourceCredentialsInfos', None)
        name = id = 'arn'
        arn = 'arn'
        cfn_type = 'AWS::CodeBuild::SourceCredential'


@CodeBuildProject.filter_registry.register('subnet')
class BuildSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "vpcConfig.subnets[]"


@CodeBuildProject.filter_registry.register('security-group')
class BuildSecurityGroupFilter(SecurityGroupFilter):

    RelatedIdsExpression = "vpcConfig.securityGroupIds[]"


@CodeBuildProject.filter_registry.register('vpc')
class BuildVpcFilter(VpcFilter):

    RelatedIdsExpression = "vpcConfig.vpcId"


@CodeBuildProject.action_registry.register('post-finding')
class BuildPostFinding(OtherResourcePostFinding):

    resource_type = 'AwsCodeBuildProject'

    def format_resource(self, r):
        envelope, payload = self.format_envelope(r)
        payload.update(self.filter_empty({
            'Name': r['name'],
            'EncryptionKey': r['encryptionKey'],
            'Environment': self.filter_empty({
                'Type': r['environment']['type'],
                'Certificate': r['environment'].get('certificate'),
                'RegistryCredential': self.filter_empty({
                    'Credential': jmespath_search(
                        'environment.registryCredential.credential', r),
                    'CredentialProvider': jmespath_search(
                        'environment.registryCredential.credentialProvider', r)
                }),
                'ImagePullCredentialsType': r['environment'].get(
                    'imagePullCredentialsType')
            }),
            'ServiceRole': r['serviceRole'],
            'VpcConfig': self.filter_empty({
                'VpcId': jmespath_search('vpcConfig.vpcId', r),
                'Subnets': jmespath_search('vpcConfig.subnets', r),
                'SecurityGroupIds': jmespath_search('vpcConfig.securityGroupIds', r)
            }),
            'Source': self.filter_empty({
                'Type': jmespath_search('source.type', r),
                'Location': jmespath_search('source.location', r),
                'GitCloneDepth': jmespath_search('source.gitCloneDepth', r)
            }),
        }))
        return envelope


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


class ConfigPipeline(ConfigSource):

    def load_resource(self, item):
        item_config = self._load_item_config(item)
        resource = item_config.pop('pipeline')
        resource.update(item_config['metadata'])
        self._load_resource_tags(resource, item)
        return resource


class DescribePipeline(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        return universal_augment(self.manager, resources)


@resources.register('codepipeline')
class CodeDeployPipeline(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'codepipeline'
        enum_spec = ('list_pipelines', 'pipelines', None)
        detail_spec = ('get_pipeline', 'name', 'name', 'pipeline')
        name = id = 'name'
        date = 'created'
        # Note this is purposeful, codepipeline don't have a separate type specifier.
        arn_type = ""
        cfn_type = config_type = "AWS::CodePipeline::Pipeline"
        universal_taggable = object()

    source_mapping = {
        'describe': DescribePipeline,
        'config': ConfigPipeline
    }


@CodeDeployPipeline.action_registry.register('delete')
class DeletePipeline(BaseAction):

    schema = type_schema('delete')
    permissions = ('codepipeline:DeletePipeline',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('codepipeline')
        for r in resources:
            try:
                self.manager.retry(client.delete_pipeline, name=r['name'])
            except client.exceptions.PipelineNotFoundException:
                continue


class DescribeApplication(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        client = local_session(self.manager.session_factory).client('codedeploy')
        for r, arn in zip(resources, self.manager.get_arns(resources)):
            r['Tags'] = client.list_tags_for_resource(
                ResourceArn=arn).get('Tags', [])
        return resources


@resources.register('codedeploy-app')
class CodeDeployApplication(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'codedeploy'
        enum_spec = ('list_applications', 'applications', None)
        batch_detail_spec = (
            'batch_get_applications', 'applicationNames',
            None, 'applicationsInfo', None)
        id = name = 'applicationName'
        date = 'createTime'
        arn_type = "application"
        arn_separator = ":"
        config_type = cfn_type = "AWS::CodeDeploy::Application"
        universal_taggable = True

    source_mapping = {
        'describe': DescribeApplication,
        'config': ConfigSource
    }

    def get_arns(self, resources):
        return [self.generate_arn(r['applicationName']) for r in resources]


@CodeDeployApplication.action_registry.register('delete')
class DeleteApplication(BaseAction):

    schema = type_schema('delete')
    permissions = ('codedeploy:DeleteApplication',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('codedeploy')
        for r in resources:
            try:
                self.manager.retry(client.delete_application, applicationName=r['applicationName'])
            except (client.exceptions.InvalidApplicationNameException,
            client.exceptions.ApplicationDoesNotExistException):
                continue


@resources.register('codedeploy-deployment')
class CodeDeployDeployment(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'codedeploy'
        enum_spec = ('list_deployments', 'deployments', {'includeOnlyStatuses': [
            'Created', 'Queued', 'InProgress', 'Baking', 'Ready']})
        batch_detail_spec = (
            'batch_get_deployments', 'deploymentIds',
            None, 'deploymentsInfo', None)
        name = id = 'deploymentId'
        # couldn't find a real cloudformation type
        cfn_type = None
        arn_type = "deploymentgroup"
        date = 'createTime'
        permissions_augment = ("codedeploy:ListTagsForResource",)


class DescribeDeploymentGroup(query.ChildDescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('codedeploy')
        results = []
        for parent_id, group_name in resources:
            dg = self.manager.retry(
                client.get_deployment_group, applicationName=parent_id,
                deploymentGroupName=group_name).get('deploymentGroupInfo')
            results.append(dg)
        for r in results:
            rarn = self.manager.generate_arn(r['applicationName'] + '/' + r['deploymentGroupName'])
            r['Tags'] = self.manager.retry(
                client.list_tags_for_resource, ResourceArn=rarn).get('Tags')
        return results


@resources.register('codedeploy-group')
class CodeDeployDeploymentGroup(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'codedeploy'
        parent_spec = ('codedeploy-app', 'applicationName', None)
        enum_spec = ('list_deployment_groups', 'deploymentGroups', None)
        id = 'deploymentGroupId'
        name = 'deploymentGroupName'
        arn_type = "deploymentgroup"
        config_type = cfn_type = 'AWS::CodeDeploy::DeploymentGroup'
        arn_separator = ':'
        permission_prefix = 'codedeploy'
        universal_taggable = True

    source_mapping = {
        'describe-child': DescribeDeploymentGroup
    }

    def get_arns(self, resources):
        arns = []
        for r in resources:
            arns.append(self.generate_arn(r['applicationName'] + '/' + r['deploymentGroupName']))
        return arns


@CodeDeployDeploymentGroup.action_registry.register('delete')
class DeleteDeploymentGroup(BaseAction):
    """Delete a deployment group tied to an application.
    """

    schema = type_schema('delete')
    permissions = ('codedeploy:DeleteDeploymentGroup',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('codedeploy')
        for r in resources:
            try:
                self.manager.retry(client.delete_deployment_group,
                      applicationName=r['applicationName'],
                      deploymentGroupName=r['deploymentGroupName'])
            except client.exceptions.InvalidDeploymentGroupNameException:
                continue
