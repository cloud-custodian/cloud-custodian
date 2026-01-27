# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from collections import defaultdict
import json
import time
from typing import TypedDict, Dict, List, Tuple

from botocore.client import BaseClient

from c7n.actions import Action, BaseAction, ModifyVpcSecurityGroupsAction, RemovePolicyBase
from c7n.filters import MetricsFilter, CrossAccountAccessFilter, ValueFilter
from c7n.filters.core import ComparableVersion
from c7n.exceptions import PolicyValidationError
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter, VpcFilter, Filter
from c7n.manager import resources
from c7n.query import ConfigSource, DescribeSource, QueryResourceManager, TypeInfo
from c7n.utils import chunks, local_session, type_schema, merge_dict_list, jmespath_search
from c7n.tags import Tag, RemoveTag, TagActionFilter, TagDelayedAction
from c7n.filters.kms import KmsRelatedFilter
import c7n.filters.policystatement as polstmt_filter

from .securityhub import PostFinding


def parse_es_version(version: str) -> Tuple[str, str]:
    """
    Parses a ElasticSearch/OpenSearch version string into a
    `(engine_name, full_version_str)` tuple.

    Examples:
    - "Elasticsearch_7.4" -> ("Elasticsearch", "7.4")
    - "OpenSearch_1.3" -> ("OpenSearch", "1.3")
    """
    # If it's empty, return all `None`s.
    if not version:
        return None, None

    # If there's no `_` in the version string, check for a plain version.
    if '_' not in version:
        # If it doesn't start with a number, it's probably not a valid version
        # string.
        if not version[0].isnumeric():
            return None, None

        return "Elasticsearch", version

    engine_name, version_str = version.split('_', 1)
    return engine_name, version_str


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
        permissions_augment = ("es:ListTags",)

    def resources(self, query=None):
        if 'query' in self.data:
            query = merge_dict_list(self.data['query'])
        elif query is None:
            query = {}
        return super(ElasticSearchDomain, self).resources(query=query)

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

    RelatedIdsExpression = 'EncryptionAtRestOptions.KmsKeyId'


@ElasticSearchDomain.filter_registry.register('cross-account')
class ElasticSearchCrossAccountAccessFilter(CrossAccountAccessFilter):
    """
    Filter to return all elasticsearch domains with cross account access permissions

    :example:

    .. code-block:: yaml

        policies:
          - name: check-elasticsearch-cross-account
            resource: aws.elasticsearch
            filters:
              - type: cross-account
    """
    policy_attribute = 'c7n:Policy'
    permissions = ('es:DescribeElasticsearchDomainConfig',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('es')
        for r in resources:
            if self.policy_attribute not in r:
                result = self.manager.retry(
                    client.describe_elasticsearch_domain_config,
                    DomainName=r['DomainName'],
                    ignore_err_codes=('ResourceNotFoundException',))
                if result:
                    options = result.get('DomainConfig').get('AccessPolicies').get('Options')
                    r[self.policy_attribute] = options and json.loads(options) or None
        return super().process(resources)


@ElasticSearchDomain.filter_registry.register('cross-cluster')
class ElasticSearchCrossClusterFilter(Filter):
    """
    Filter to return all elasticsearch domains with inbound cross-cluster with the given info

    :example:

    .. code-block:: yaml

        policies:
          - name: check-elasticsearch-cross-cluster
            resource: aws.elasticsearch
            filters:
              - type: cross-cluster
                inbound:
                    key: SourceDomainInfo.OwnerId
                    op: eq
                    value: '123456789'
                outbound:
                    key: SourceDomainInfo.OwnerId
                    op: eq
                    value: '123456789'
    """
    schema = type_schema(type_name="cross-cluster",
                         inbound=type_schema(type_name='inbound',
                                             required=('key', 'value'),
                                             rinherit=ValueFilter.schema),
                         outbound=type_schema(type_name='outbound',
                                              required=('key', 'value'),
                                              rinherit=ValueFilter.schema),)
    schema_alias = False
    annotation_key = "c7n:SearchConnections"
    matched_key = "c7n:MatchedConnections"
    annotate = False
    permissions = ('es:ESCrossClusterGet',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('es')
        results = []
        for r in resources:
            if self.annotation_key not in r:
                r[self.annotation_key] = {}
                if "inbound" in self.data:
                    inbound = self.manager.retry(
                        client.describe_inbound_cross_cluster_search_connections,
                        Filters=[{'Name': 'destination-domain-info.domain-name',
                                'Values': [r['DomainName']]}])
                    inbound.pop('ResponseMetadata')
                    r[self.annotation_key]["inbound"] = inbound
                if "outbound" in self.data:
                    outbound = self.manager.retry(
                        client.describe_outbound_cross_cluster_search_connections,
                        Filters=[{'Name': 'source-domain-info.domain-name',
                                'Values': [r['DomainName']]}])
                    outbound.pop('ResponseMetadata')
                    r[self.annotation_key]["outbound"] = outbound
            matchFound = False
            r[self.matched_key] = {}
            for direction in r[self.annotation_key]:
                matcher = self.data.get(direction)
                valueFilter = ValueFilter(matcher)
                valueFilter.annotate = False
                matched = []
                for conn in r[self.annotation_key][direction]['CrossClusterSearchConnections']:
                    if valueFilter(conn):
                        matched.append(conn)
                        matchFound = True
                r[self.matched_key][direction] = matched
            if matchFound:
                results.append(r)
        return results


@ElasticSearchDomain.filter_registry.register('has-statement')
class HasStatementFilter(polstmt_filter.HasStatementFilter):
    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.policy_attribute = 'AccessPolicies'

    def get_std_format_args(self, domain):
        return {
            'domain_arn': domain['ARN'],
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region
        }


@ElasticSearchDomain.filter_registry.register('source-ip')
class SourceIP(Filter):
    """ValueFilter-based filter for verifying allowed source ips in
    an ElasticSearch domain's access policy. Useful for checking to see if
    an ElasticSearch domain allows traffic from non approved IP addresses/CIDRs.

    :example:

    Find ElasticSearch domains that allow traffic from IP addresses
    not in the approved list (string matching)

    .. code-block: yaml

      - type: source-ip
        op: not-in
        value: ["103.15.250.0/24", "173.240.160.0/21", "206.108.40.0/21"]

    Same  as above but using cidr matching instead of string matching

    .. code-block: yaml

      - type: source-ip
        op: not-in
        value_type: cidr
        value: ["103.15.250.0/24", "173.240.160.0/21", "206.108.40.0/21"]

    """
    schema = type_schema('source-ip', rinherit=ValueFilter.schema)
    permissions = ("es:DescribeElasticsearchDomainConfig",)
    annotation = 'c7n:MatchedSourceIps'

    def __call__(self, resource):
        es_access_policy = resource.get('AccessPolicies')
        matched = []
        source_ips = self.get_source_ip_perms(json.loads(es_access_policy))
        if not self.data.get('key'):
            self.data['key'] = 'SourceIp'
        vf = ValueFilter(self.data, self.manager)
        vf.annotate = False
        for source_ip in source_ips:
            found = vf(source_ip)
            if found:
                matched.append(source_ip)

        if matched:
            resource[self.annotation] = matched
            return True
        return False

    def get_source_ip_perms(self, es_access_policy):
        """Get SourceIps from the original access policy
        """
        ip_perms = []
        stmts = es_access_policy.get('Statement', [])
        for stmt in stmts:
            source_ips = self.source_ips_from_stmt(stmt)
            if not source_ips:
                continue
            ip_perms.extend([{'SourceIp': ip} for ip in source_ips])
        return ip_perms

    @classmethod
    def source_ips_from_stmt(cls, stmt):
        source_ips = []
        if stmt.get('Effect', '') == 'Allow':
            ips = stmt.get('Condition', {}).get('IpAddress', {}).get('aws:SourceIp', [])
            if len(ips) > 0:
                if isinstance(ips, list):
                    source_ips.extend(ips)
                else:
                    source_ips.append(ips)
        return source_ips


EngineUpgradesDict = Dict[
    # Version string from the API as the key.
    str, List[
        # Each of the available upgrades.
        TypedDict("TargetUpgradeOptions", {
            "engine": str,
            "version": str,
            "original": str,
        })
    ]
]
# A type to make clear the expected structure for upgrade options.
ESUpgradeOptionsDict = TypedDict("ESUpgradeOptionsDict", {
    "elasticsearch": EngineUpgradesDict,
    "opensearch": EngineUpgradesDict,
})


@ElasticSearchDomain.filter_registry.register('upgrade-available')
class UpgradeAvailable(Filter):
    """Scans for available upgrade-compatible ES versions

    This will check all the ElasticSearch domains on the resources, and return
    a list of viable upgrade options.

    :example:

    .. code-block:: yaml

            policies:
              - name: elasticsearch-upgrade-available
                resource: elasticsearch
                filters:
                  - type: upgrade-available
                    major: False

    """

    schema = type_schema(
        'upgrade-available',
        major={'type': 'boolean'},
        value={'type': 'boolean'},
    )
    permissions = ('es:GetCompatibleVersions',)
    annotation_key = "c7n:AvailableUpgrades"

    def collect_available_upgrades(self, client: BaseClient) -> ESUpgradeOptionsDict:
        """
        Fetch all upgrades for all engines/versions.

        We want a structure that will let us efficiently look up those values
        per-resource, and return all the upgrade options in a single O(1)-ish
        lookup.
        """
        all_upgrades = {
            "elasticsearch": {},
            "opensearch": {},
        }

        # We fetch them all at once & restructure.
        response = self.manager.retry(
            client.get_compatible_elasticsearch_versions,
            ignore_err_codes=('ResourceNotFoundException',)
        )
        compatible_versions = response.get('CompatibleElasticsearchVersions', [])

        for upgrade_options in compatible_versions:
            source_version = upgrade_options.get('SourceVersion')
            target_versions = upgrade_options.get('TargetVersions', [])

            source_engine, sversion_str = parse_es_version(source_version)
            source_engine = source_engine.lower()
            all_upgrades.setdefault(source_engine, {})
            all_upgrades[source_engine].setdefault(sversion_str, [])

            for target_version in target_versions:
                target_engine, tversion_str = parse_es_version(target_version)
                all_upgrades[source_engine][sversion_str].append({
                    "engine": target_engine,
                    "version": tversion_str,
                    "original": target_version,
                })

        return all_upgrades

    def get_matches_for(
        self,
        current_engine: str,
        cversion: ComparableVersion,
        per_engine_options: EngineUpgradesDict,
        check_major=False
    ) -> List[str]:
        matches = []

        for sversion_str, targets in per_engine_options.items():
            sversion = ComparableVersion(sversion_str)

            # Compare major versions first, ...
            if sversion.version[0] != cversion.version[0]:
                continue

            # ...then minor, to find a match.
            if (
                len(sversion.version) < 2
                or len(cversion.version) < 2
                or sversion.version[1] != cversion.version[1]
            ):
                continue

            # If we're here, we have a "good-enough" engine/version match.
            # Next, we'll build the list of matching upgrades.
            for target_data in targets:
                target_engine = target_data["engine"]
                tversion = ComparableVersion(target_data["version"])

                # If the engines don't match, it'd be considered a "major"
                # upgrade.
                if (
                    target_engine.lower() != current_engine.lower()
                    and not check_major
                ):
                    continue

                # Only if the engines are the same, should we check the
                # major versions.
                if (
                    target_engine.lower() == current_engine.lower()
                    and tversion.version[0] > sversion.version[0]
                    and not check_major
                ):
                    continue

                matches.append(target_data["original"])

        return matches

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('es')
        check_major = self.data.get('major', False)
        check_upgrade_extant = self.data.get('value', True)
        results = []

        all_available_upgrades = self.collect_available_upgrades(client)

        for r in resources:
            current_raw_version = r.get('ElasticsearchVersion', '')
            current_engine, cversion_str = parse_es_version(current_raw_version)
            cversion = ComparableVersion(cversion_str)
            per_engine_options = all_available_upgrades.get(current_engine.lower())
            matches = self.get_matches_for(
                current_engine,
                cversion,
                per_engine_options,
                check_major=check_major
            )

            # Annotate on all the upgrades (in a stable ordering).
            r[self.annotation_key] = list(sorted(matches))

            # Lastly, depending on `value` (filter if upgrades exist or not):
            if check_upgrade_extant:
                if matches:
                    # We want to filter to include only resources that have
                    # upgrades.
                    results.append(r)
            else:
                if not matches:
                    # We want to filter to include only resources **without**
                    # upgrades,
                    results.append(r)

        return results


@ElasticSearchDomain.action_registry.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """
    Action to remove policy statements from elasticsearch

    :example:

    .. code-block:: yaml

        policies:
          - name: elasticsearch-cross-account
            resource: aws.elasticsearch
            filters:
              - type: cross-account
            actions:
              - type: remove-statements
                statement_ids: matched
    """

    permissions = ('es:DescribeElasticsearchDomainConfig', 'es:UpdateElasticsearchDomainConfig',)

    def validate(self):
        for f in self.manager.iter_filters():
            if isinstance(f, ElasticSearchCrossAccountAccessFilter):
                return self
        raise PolicyValidationError(
            '`remove-statements` may only be used in '
            'conjunction with `cross-account` filter on %s' % (self.manager.data,))

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('es')
        for r in resources:
            try:
                self.process_resource(client, r)
            except Exception:
                self.log.exception("Error processing es:%s", r['ARN'])

    def process_resource(self, client, resource):
        p = resource.get('c7n:Policy')

        if p is None:
            return

        _, found = self.process_policy(
            p, resource, CrossAccountAccessFilter.annotation_key)

        if found:
            client.update_elasticsearch_domain_config(
                DomainName=resource['DomainName'],
                AccessPolicies=json.dumps(p)
            )

        return


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
                'EnforceHTTPS': jmespath_search(
                    'DomainEndpointOptions.EnforceHTTPS', r),
                'TLSSecurityPolicy': jmespath_search(
                    'DomainEndpointOptions.TLSSecurityPolicy', r)
            }),
            'ElasticsearchVersion': r['ElasticsearchVersion'],
            'EncryptionAtRestOptions': self.filter_empty({
                'Enabled': jmespath_search(
                    'EncryptionAtRestOptions.Enabled', r),
                'KmsKeyId': jmespath_search(
                    'EncryptionAtRestOptions.KmsKeyId', r)
            }),
            'NodeToNodeEncryptionOptions': self.filter_empty({
                'Enabled': jmespath_search(
                    'NodeToNodeEncryptionOptions.Enabled', r)
            }),
            'VPCOptions': self.filter_empty({
                'AvailabilityZones': jmespath_search(
                    'VPCOptions.AvailabilityZones', r),
                'SecurityGroupIds': jmespath_search(
                    'VPCOptions.SecurityGroupIds', r),
                'SubnetIds': jmespath_search('VPCOptions.SubnetIds', r),
                'VPCId': jmespath_search('VPCOptions.VPCId', r)
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
            except client.exceptions.ValidationException:
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
            except client.exceptions.ValidationException:
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


@ElasticSearchDomain.action_registry.register('remove-matched-source-ips')
class RemoveMatchedSourceIps(BaseAction):
    """Action to remove matched source ips from a Access Policy. This action
    needs to be used in conjunction with the source-ip filter. It can be used
    for removing non-approved IP addresses from the the access policy of a
    ElasticSearch domain.

    :example:

    .. code-block:: yaml

            policies:
              - name: es-access-revoke
                resource: elasticsearch
                filters:
                  - type: source-ip
                    value_type: cidr
                    op: not-in
                    value_from:
                       url: s3://my-bucket/allowed_cidrs.csv
                actions:
                  - type: remove-matched-source-ips
    """

    schema = type_schema('remove-matched-source-ips')
    permissions = ('es:UpdateElasticsearchDomainConfig',)

    def validate(self):
        for f in self.manager.iter_filters():
            if isinstance(f, SourceIP):
                return self

        raise PolicyValidationError(
            '`remove-matched-source-ips` can only be used in conjunction with '
            '`source-ip` filter on %s' % (self.manager.data,))

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('es')

        for r in resources:
            domain_name = r.get('DomainName', '')
            # ES Access policy is defined as json string
            accpol = json.loads(r.get('AccessPolicies', ''))
            good_cidrs = []
            bad_ips = []

            matched_key = SourceIP.annotation
            for matched_perm in r.get(matched_key, []):
                bad_ips.append(matched_perm.get('SourceIp'))

            if not bad_ips:
                self.log.info('no matched IPs, no update needed')
                return

            update_needed = False
            for stmt in accpol.get('Statement', []):
                source_ips = SourceIP.source_ips_from_stmt(stmt)
                if not source_ips:
                    continue

                update_needed = True
                good_ips = list(set(source_ips) - set(bad_ips))
                stmt['Condition']['IpAddress']['aws:SourceIp'] = good_ips

            if update_needed:
                ap = self.update_accpol(client, domain_name, accpol, good_cidrs)
                self.log.info('updated AccessPolicy: {}'.format(json.dumps(ap)))

    def update_accpol(self, client, domain_name, accpol, good_cidrs):
        """Update access policy to only have good ip addresses
        """
        for i, cidr in enumerate(good_cidrs):
            if 'Condition' not in accpol.get('Statement', [])[i] or \
                    accpol.get('Statement', [])[i].get('Effect', '') != 'Allow':
                continue
            accpol['Statement'][i]['Condition']['IpAddress']['aws:SourceIp'] = cidr
        resp = client.update_elasticsearch_domain_config(
            DomainName=domain_name,
            AccessPolicies=json.dumps(accpol))
        return json.loads(resp.get('DomainConfig', {}).get('AccessPolicies', {}).get('Options', ''))


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


@ElasticSearchDomain.action_registry.register('update-tls-config')
class UpdateTlsConfig(Action):

    """Action to update tls-config on a domain endpoint

    :example:

    .. code-block:: yaml

            policies:
              - name: update-tls-config
                resource: elasticsearch
                filters:
                  - type: value
                    key: 'DomainEndpointOptions.TLSSecurityPolicy'
                    op: eq
                    value: "Policy-Min-TLS-1-0-2019-07"
                actions:
                  - type: update-tls-config
                    value: "Policy-Min-TLS-1-2-2019-07"
    """

    schema = type_schema('update-tls-config', value={'type': 'string',
        'enum': ['Policy-Min-TLS-1-0-2019-07', 'Policy-Min-TLS-1-2-2019-07',
                 'Policy-Min-TLS-1-2-PFS-2023-10']}, required=['value'])
    permissions = ('es:UpdateElasticsearchDomainConfig', 'es:ListDomainNames')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('es')
        tls_value = self.data.get('value')
        for r in resources:
            client.update_elasticsearch_domain_config(DomainName=r['DomainName'],
                DomainEndpointOptions={'EnforceHTTPS': True, 'TLSSecurityPolicy': tls_value})


@ElasticSearchDomain.action_registry.register('enable-auditlog')
class EnableAuditLog(Action):

    """Action to enable audit logs on a domain endpoint

    :example:

    .. code-block:: yaml

            policies:
              - name: enable-auditlog
                resource: elasticsearch
                filters:
                  - type: value
                    key: 'LogPublishingOptions.AUDIT_LOGS.Enabled'
                    op: eq
                    value: false
                actions:
                  - type: enable-auditlog
                    state: True
                    loggroup_prefix: "/aws/es/domains"

    """

    schema = type_schema(
        'enable-auditlog',
        state={'type': 'boolean'},
        loggroup_prefix={'type': 'string'},
        delay={'type': 'number'},
        required=['state'])

    statement = {
        "Sid": "OpenSearchCloudWatchLogs",
        "Effect": "Allow",
        "Principal": {"Service": ["es.amazonaws.com"]},
        "Action": ["logs:PutLogEvents", "logs:CreateLogStream"],
        "Resource": None}

    permissions = (
        'es:UpdateElasticsearchDomainConfig',
        'es:ListDomainNames',
        'logs:DescribeLogGroups',
        'logs:CreateLogGroup',
        'logs:PutResourcePolicy')

    def get_loggroup_arn(self, domain, log_prefix=None):
        if log_prefix:
            log_group_name = "%s/%s/audit-logs" % (log_prefix, domain)
        else:
            log_group_name = "/aws/OpenSearchService/domains/%s/audit-logs" % (domain)
        log_group_arn = "arn:aws:logs:{}:{}:log-group:{}:*".format(
            self.manager.region, self.manager.account_id, log_group_name)
        return log_group_arn

    def merge_dict(self, d1, d2):
        merged_dict = defaultdict(list)

        for d in (d1, d2):
            for key, value in d.items():
                if key == 'Resource':
                    if isinstance(value, list):
                        merged_dict[key].extend(value)
                    else:
                        merged_dict[key].append(value)
                else:
                    merged_dict[key] = value

        return dict(merged_dict)

    def set_permissions(self, log_group_arn):
        statement = dict(self.statement)
        statement['Resource'] = [log_group_arn]
        client = local_session(
            self.manager.session_factory).client('logs')

        try:
            client.create_log_group(logGroupName=log_group_arn.split(":")[-2])
        except client.exceptions.ResourceAlreadyExistsException:
            pass

        for policy in client.describe_resource_policies().get('resourcePolicies'):
            if policy['policyName'] == "OpenSearchCloudwatchLogPermissions":
                policy_doc = json.loads(policy['policyDocument'])
                if log_group_arn not in policy_doc['Statement'][0]['Resource']:
                    merged_statement = self.merge_dict(statement, policy_doc['Statement'][0])
                    statement = merged_statement
                continue

        response = client.put_resource_policy(
            policyName='OpenSearchCloudwatchLogPermissions',
            policyDocument=json.dumps(
                {"Version": "2012-10-17", "Statement": statement}))

        return response

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('es')
        state = self.data.get('state')
        log_prefix = self.data.get('loggroup_prefix')
        log_group_arns = {
            r['DomainName']: self.get_loggroup_arn(r["DomainName"], log_prefix) for r in resources}

        for r in resources:
            if state:
                self.set_permissions(log_group_arns[r["DomainName"]])
                time.sleep(self.data.get('delay', 15))
            client.update_elasticsearch_domain_config(DomainName=r['DomainName'],
                LogPublishingOptions={"AUDIT_LOGS":
                {'CloudWatchLogsLogGroupArn': log_group_arns[r["DomainName"]], 'Enabled': state}})
