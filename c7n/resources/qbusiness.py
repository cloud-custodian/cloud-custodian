# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import (
    ChildDescribeSource,
    ChildResourceManager,
    DescribeWithResourceTags,
    QueryResourceManager,
    RetryPageIterator,
    TypeInfo,
)
from c7n.tags import universal_augment
from c7n.utils import local_session


@resources.register('qbusiness-application')
class QBusinessApplication(QueryResourceManager):
    """Amazon Q Business Application"""

    class resource_type(TypeInfo):
        service = 'qbusiness'
        enum_spec = ('list_applications', 'applications', None)
        detail_spec = ('get_application', 'applicationId', 'applicationId', None)
        id = 'applicationId'
        arn = 'applicationArn'
        name = 'displayName'
        date = 'updatedAt'
        cfn_type = 'AWS::QBusiness::Application'
        universal_taggable = object()

    source_mapping = {'describe': DescribeWithResourceTags}


@QBusinessApplication.filter_registry.register('cross-account')
class QBusinessApplicationCrossAccount(CrossAccountAccessFilter):
    """Filter Q Business applications whose resource-based permission policy
    grants cross-account access.

    :example:

    .. code-block:: yaml

        policies:
          - name: qbusiness-app-cross-account
            resource: aws.qbusiness-application
            filters:
              - type: cross-account
    """

    policy_attribute = 'c7n:Policy'
    permissions = ('qbusiness:GetPolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('qbusiness')
        for r in resources:
            if self.policy_attribute in r:
                continue
            try:
                r[self.policy_attribute] = self.manager.retry(
                    client.get_policy, applicationId=r['applicationId']).get('policy')
            except client.exceptions.ResourceNotFoundException:
                r[self.policy_attribute] = None
        return super().process(resources, event)


class QBusinessChildDescribe(ChildDescribeSource):

    def get_query(self):
        return super().get_query(capture_parent_id=True)

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('qbusiness')
        rtype = self.manager.resource_type
        op = getattr(client, rtype.detail_op)
        results = []
        for app_id, r in resources:
            detail = self.manager.retry(
                op, applicationId=app_id, **{rtype.id: r[rtype.id]})
            detail.pop('ResponseMetadata', None)
            results.append(detail)
        return universal_augment(self.manager, results)


@resources.register('qbusiness-index')
class QBusinessIndex(ChildResourceManager):
    """Amazon Q Business Index"""

    class resource_type(TypeInfo):
        service = 'qbusiness'
        enum_spec = ('list_indices', 'indices', None)
        detail_op = 'get_index'
        parent_spec = ('qbusiness-application', 'applicationId', None)
        id = 'indexId'
        arn = 'indexArn'
        name = 'displayName'
        date = 'updatedAt'
        cfn_type = 'AWS::QBusiness::Index'
        permissions_augment = ('qbusiness:GetIndex',)
        supports_trailevents = True
        universal_taggable = object()

    source_mapping = {'describe-child': QBusinessChildDescribe}


@resources.register('qbusiness-plugin')
class QBusinessPlugin(ChildResourceManager):
    """Amazon Q Business Plugin"""

    class resource_type(TypeInfo):
        service = 'qbusiness'
        enum_spec = ('list_plugins', 'plugins', None)
        detail_op = 'get_plugin'
        parent_spec = ('qbusiness-application', 'applicationId', None)
        id = 'pluginId'
        arn = 'pluginArn'
        name = 'displayName'
        date = 'updatedAt'
        cfn_type = 'AWS::QBusiness::Plugin'
        permissions_augment = ('qbusiness:GetPlugin',)
        supports_trailevents = True
        universal_taggable = object()

    source_mapping = {'describe-child': QBusinessChildDescribe}


class DescribeQDataAccessor(ChildDescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, resources)


@resources.register('qbusiness-data-accessor')
class QBusinessDataAccessor(ChildResourceManager):
    """Amazon Q Business Data Accessor"""

    class resource_type(TypeInfo):
        service = 'qbusiness'
        enum_spec = ('list_data_accessors', 'dataAccessors', None)
        parent_spec = ('qbusiness-application', 'applicationId', None)
        id = 'dataAccessorId'
        arn = 'dataAccessorArn'
        name = 'displayName'
        date = 'updatedAt'
        supports_trailevents = True
        universal_taggable = object()

    source_mapping = {'describe-child': DescribeQDataAccessor}


class DescribeQDataSource(ChildDescribeSource):

    def resources(self, query):
        client = local_session(self.manager.session_factory).client('qbusiness')
        paginator = client.get_paginator('list_data_sources')
        paginator.PAGE_ITERATOR_CLS = RetryPageIterator
        indices = self.manager.get_resource_manager('qbusiness-index').resources()
        results = []
        for idx in indices:
            app_id = idx['applicationId']
            index_id = idx['indexId']
            for page in paginator.paginate(applicationId=app_id, indexId=index_id):
                for ds in page.get('dataSources', []):
                    ds['applicationId'] = app_id
                    ds['indexId'] = index_id
                    results.append(ds)
        return results

    def get_resources(self, ids):
        # event mode: ids may be raw dataSourceId values or full arns
        wanted = {i.rsplit('/', 1)[-1] for i in ids}
        return [r for r in self.resources({}) if r['dataSourceId'] in wanted]

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('qbusiness')
        for r in resources:
            detail = self.manager.retry(
                client.get_data_source,
                applicationId=r['applicationId'],
                indexId=r['indexId'],
                dataSourceId=r['dataSourceId'])
            detail.pop('ResponseMetadata', None)
            r.update(detail)
        return universal_augment(self.manager, resources)


@resources.register('qbusiness-data-source')
class QBusinessDataSource(ChildResourceManager):
    """Amazon Q Business Data Source"""

    class resource_type(TypeInfo):
        service = 'qbusiness'
        enum_spec = ('list_data_sources', 'dataSources', None)
        parent_spec = ('qbusiness-index', 'indexId', None)
        id = 'dataSourceId'
        arn = 'dataSourceArn'
        name = 'displayName'
        date = 'updatedAt'
        cfn_type = 'AWS::QBusiness::DataSource'
        permissions_augment = ('qbusiness:GetDataSource',)
        supports_trailevents = True
        universal_taggable = object()

    source_mapping = {'describe-child': DescribeQDataSource}
