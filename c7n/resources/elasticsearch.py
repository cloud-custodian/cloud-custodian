# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import jmespath

from c7n.actions import Action, ModifyVpcSecurityGroupsAction
from c7n.filters import MetricsFilter
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter, VpcFilter
from c7n.manager import resources
from c7n.query import ConfigSource, DescribeSource, QueryResourceManager, TypeInfo
from c7n.utils import chunks, local_session, type_schema
from c7n.tags import Tag, RemoveTag, TagActionFilter, TagDelayedAction
from c7n.filters.kms import KmsRelatedFilter

from .securityhub import PostFinding


class DescribeDomain(DescribeSource):

    def get_resources(self, resource_ids):
        # augment will turn these into resource dictionaries
        return resource_ids

    def augment(self, domains):
        client = local_session(self.manager.session_factory).client('es')
        model = self.manager.get_model()
        results = []

        def _augment(resource_set):
            resources = self.manager.retry(
                client.describe_elasticsearch_domains,
                DomainNames=resource_set)['DomainStatusList']
            for r in resources:
                rarn = self.manager.generate_arn(r[model.id])
                r['Tags'] = self.manager.retry(
                    client.list_tags, ARN=rarn).get('TagList', [])
            return resources

        for resource_set in chunks(domains, 5):
            results.extend(_augment(resource_set))

        return results


@resources.register('elasticsearch')
class ElasticSearchDomain(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'es'
        arn = 'ARN'
        arn_type = 'domain'
        enum_spec = (
            'list_domain_names', 'DomainNames[].DomainName', None)
        id = 'DomainName'
        name = 'Name'
        dimension = "DomainName"
        cfn_type = config_type = 'AWS::Elasticsearch::Domain'

    source_mapping = {
        'describe': DescribeDomain,
        'config': ConfigSource
    }


ElasticSearchDomain.filter_registry.register('marked-for-op', TagActionFilter)


@ElasticSearchDomain.filter_registry.register('subnet')
class Subnet(SubnetFilter):

    RelatedIdsExpression = "VPCOptions.SubnetIds[]"


@ElasticSearchDomain.filter_registry.register('security-group')
class SecurityGroup(SecurityGroupFilter):

    RelatedIdsExpression = "VPCOptions.SecurityGroupIds[]"


@ElasticSearchDomain.filter_registry.register('vpc')
class Vpc(VpcFilter):

    RelatedIdsExpression = "VPCOptions.VPCId"


@ElasticSearchDomain.filter_registry.register('metrics')
class Metrics(MetricsFilter):

    def get_dimensions(self, resource):
        return [{'Name': 'ClientId',
                 'Value': self.manager.account_id},
                {'Name': 'DomainName',
                 'Value': resource['DomainName']}]


@ElasticSearchDomain.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):
    """
    Filter a resource by its associcated kms key and optionally the aliasname
    of the kms key by using 'c7n:AliasName'

    :example:

    .. code-block:: yaml

        policies:
          - name: elasticsearch-kms-key
            resource: aws.elasticsearch
            filters:
              - type: kms-key
                key: c7n:AliasName
                value: "^(alias/aws/es)"
                op: regex
    """
    RelatedIdsExpression = 'EncryptionAtRestOptions.KmsKeyId'


@ElasticSearchDomain.action_registry.register('post-finding')
class ElasticSearchPostFinding(PostFinding):

    resource_type = 'AwsElasticsearchDomain'

    def format_resource(self, r):
        envelope, payload = self.format_envelope(r)
        payload.update(self.filter_empty({
            'AccessPolicies': r.get('AccessPolicies'),
            'DomainId': r['DomainId'],
            'DomainName': r['DomainName'],
            'Endpoint': r.get('Endpoint'),
            'Endpoints': r.get('Endpoints'),
            'DomainEndpointOptions': self.filter_empty({
                'EnforceHTTPS': jmespath.search(
                    'DomainEndpointOptions.EnforceHTTPS', r),
                'TLSSecurityPolicy': jmespath.search(
                    'DomainEndpointOptions.TLSSecurityPolicy', r)
            }),
            'ElasticsearchVersion': r['ElasticsearchVersion'],
            'EncryptionAtRestOptions': self.filter_empty({
                'Enabled': jmespath.search(
                    'EncryptionAtRestOptions.Enabled', r),
                'KmsKeyId': jmespath.search(
                    'EncryptionAtRestOptions.KmsKeyId', r)
            }),
            'NodeToNodeEncryptionOptions': self.filter_empty({
                'Enabled': jmespath.search(
                    'NodeToNodeEncryptionOptions.Enabled', r)
            }),
            'VPCOptions': self.filter_empty({
                'AvailabilityZones': jmespath.search(
                    'VPCOptions.AvailabilityZones', r),
                'SecurityGroupIds': jmespath.search(
                    'VPCOptions.SecurityGroupIds', r),
                'SubnetIds': jmespath.search('VPCOptions.SubnetIds', r),
                'VPCId': jmespath.search('VPCOptions.VPCId', r)
            })
        }))
        return envelope


@ElasticSearchDomain.action_registry.register('modify-security-groups')
class ElasticSearchModifySG(ModifyVpcSecurityGroupsAction):
    """Modify security groups on an Elasticsearch domain"""

    permissions = ('es:UpdateElasticsearchDomainConfig',)

    def process(self, domains):
        groups = super(ElasticSearchModifySG, self).get_groups(domains)
        client = local_session(self.manager.session_factory).client('es')

        for dx, d in enumerate(domains):
            client.update_elasticsearch_domain_config(
                DomainName=d['DomainName'],
                VPCOptions={
                    'SecurityGroupIds': groups[dx]})


@ElasticSearchDomain.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')
    permissions = ('es:DeleteElasticsearchDomain',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('es')
        for r in resources:
            client.delete_elasticsearch_domain(DomainName=r['DomainName'])


@ElasticSearchDomain.action_registry.register('tag')
class ElasticSearchAddTag(Tag):
    """Action to create tag(s) on an existing elasticsearch domain

    :example:

    .. code-block:: yaml

                policies:
                  - name: es-add-tag
                    resource: elasticsearch
                    filters:
                      - "tag:DesiredTag": absent
                    actions:
                      - type: tag
                        key: DesiredTag
                        value: DesiredValue
    """
    permissions = ('es:AddTags',)

    def process_resource_set(self, client, domains, tags):
        for d in domains:
            try:
                client.add_tags(ARN=d['ARN'], TagList=tags)
            except client.exceptions.ResourceNotFoundExecption:
                continue


@ElasticSearchDomain.action_registry.register('remove-tag')
class ElasticSearchRemoveTag(RemoveTag):
    """Removes tag(s) on an existing elasticsearch domain

    :example:

    .. code-block:: yaml

        policies:
          - name: es-remove-tag
            resource: elasticsearch
            filters:
              - "tag:ExpiredTag": present
            actions:
              - type: remove-tag
                tags: ['ExpiredTag']
        """
    permissions = ('es:RemoveTags',)

    def process_resource_set(self, client, domains, tags):
        for d in domains:
            try:
                client.remove_tags(ARN=d['ARN'], TagKeys=tags)
            except client.exceptions.ResourceNotFoundExecption:
                continue


@ElasticSearchDomain.action_registry.register('mark-for-op')
class ElasticSearchMarkForOp(TagDelayedAction):
    """Tag an elasticsearch domain for action later

    :example:

    .. code-block:: yaml

                policies:
                  - name: es-delete-missing
                    resource: elasticsearch
                    filters:
                      - "tag:DesiredTag": absent
                    actions:
                      - type: mark-for-op
                        days: 7
                        op: delete
                        tag: c7n_es_delete
    """


@resources.register('elasticsearch-reserved')
class ReservedInstances(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'es'
        name = id = 'ReservedElasticsearchInstanceId'
        date = 'StartTime'
        enum_spec = (
            'describe_reserved_elasticsearch_instances', 'ReservedElasticsearchInstances', None)
        filter_name = 'ReservedElasticsearchInstances'
        filter_type = 'list'
        arn_type = "reserved-instances"
        permissions_enum = ('es:DescribeReservedElasticsearchInstances',)
