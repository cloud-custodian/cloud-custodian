# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, DescribeSource, TypeInfo, RetryPageIterator
from c7n.utils import local_session, type_schema


@resources.register('artifact-domain')
class ArtifactDomain(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'codeartifact'
        enum_spec = ('list_domains', 'domains', None)
        detail_spec = ('describe_domain', 'domain', 'name', 'domain')
        cfn_type = 'AWS::CodeArtifact::Domain'
        id = name = 'name'
        arn = 'arn'


@ArtifactDomain.filter_registry.register('cross-account')
class CrossAccountDomain(CrossAccountAccessFilter):

    policy_attribute = 'c7n:Policy'
    permissions = ('codeartifact:GetDomainPermissionsPolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('codeartifact')
        for r in resources:
            result = self.manager.retry(
                client.get_domain_permissions_policy,
                domain=r['domainName'],
                ignore_err_codes=('ResourceNotFoundException',))
            r[self.policy_attribute] = result['policy']['document']
        return super().process(resources)


@ArtifactDomain.action_registry.register('delete')
class DeleteDomain(Action):
    """
    :example:

    Delete empty domains older than 30 days.

    .. code-block:: yaml

      policies:
        - name: empty-delete
          resource: artifact-domain
          filters:
             - type: value
               key: createdTime
               value_type: age
               op: greater-than
               value: 30
             - assetSizeBytes: 0
          actions:
             - delete
    """
    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = ('codeartifact:DeleteDomain',
                   'codeartifact:DeleteRepository',
                   'codeartifact:ListRepositoriesInDomain')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('codeartifact')
        force = self.data.get('force', False)
        for r in resources:
            if force:
                self._remove_repositories(client, r)
            client.delete_domain(domain=r['name'])

    def _remove_repositories(self, client, domain):
        repos = []
        paginator = client.get_paginator('list_repositories_in_domain')
        paginator.PAGE_ITERATOR_CLS = RetryPageIterator

        try:
            results = paginator.paginate(domain=domain['name'])
            repos.extend(results.build_full_result().get('repositories'))
        except client.exceptions.ResourceNotFoundException:
            return False

        for r in repos:
            self.manager.retry(
                client.delete_repository,
                domain=domain['name'],
                repository=r['name'],
                ignore_err_codes=('ResourceNotFoundException',))


class DescribeRepo(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client(
            self.manager.resource_type.service)
        results = []
        for r in resources:
            rdescribe = self.manager.retry(
                client.describe_repository,
                repository=r['name'],
                domain=r['domainName'],
                ignore_err_codes=('ResourceNotFoundException',))
            if rdescribe:
                results.append(rdescribe['repository'])
        return results


@resources.register('artifact-repo')
class ArtifactRepo(QueryResourceManager):

    source_mapping = {'describe': DescribeRepo}

    class resource_type(TypeInfo):
        service = 'codeartifact'
        enum_spec = ('list_repositories', 'repositories', None)
        config_type = cfn_type = 'AWS::CodeArtifact::Repository'
        id = name = 'name'
        arn = 'arn'


@ArtifactRepo.filter_registry.register('cross-account')
class CrossAccountRepo(CrossAccountAccessFilter):

    policy_attribute = 'c7n:Policy'
    permissions = ('codeartifact:GetRepositoryPermissionsPolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('codeartifact')

        for r in resources:
            try:
                result = client.get_repository_permissions_policy(
                    domain=r['domainName'], repository=r['name']
                )
                r[self.policy_attribute] = result['policy']['document']
            except client.exceptions.ResourceNotFoundException:
                pass

        return super().process(resources)


@ArtifactRepo.action_registry.register('delete')
class DeleteRepo(Action):
    """Delete a repository

    :example:

    .. code-block:: yaml

      policies:
        - name: no-pypi
          resource: artifact-repo
          filters:
             - type: value
               key: externalConnections[].externalConnectionName
               value: public:pypi
               op: contains
          actions:
             - delete
    """
    schema = type_schema('delete')
    permissions = ('codeartifact:DeleteRepository',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('codeartifact')
        for r in resources:
            self.manager.retry(
                client.delete_repository,
                domain=r['domainName'],
                repository=r['name'],
                ignore_err_codes=('ResourceNotFoundException',))
