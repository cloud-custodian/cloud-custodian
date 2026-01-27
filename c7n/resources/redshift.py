# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import itertools

from botocore.exceptions import ClientError
from concurrent.futures import as_completed

from c7n.actions import BaseAction, ModifyVpcSecurityGroupsAction
from c7n.exceptions import PolicyValidationError
from c7n.filters import (
    ValueFilter, AgeFilter, CrossAccountAccessFilter, Filter)
import c7n.filters.vpc as net_filters
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters.offhours import OffHour, OnHour
from c7n.manager import resources
from c7n.resolver import ValuesFrom
from c7n.query import QueryResourceManager, TypeInfo, RetryPageIterator
from c7n import tags
from c7n.utils import (
    type_schema, local_session, chunks, snapshot_identifier, jmespath_search)
from .aws import shape_validate
from datetime import datetime, timedelta
from c7n.filters.backup import ConsecutiveAwsBackupsFilter


@resources.register('redshift')
class Redshift(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'redshift'
        arn_type = 'cluster'
        arn_separator = ":"
        enum_spec = ('describe_clusters', 'Clusters', None)
        name = id = 'ClusterIdentifier'
        filter_name = 'ClusterIdentifier'
        filter_type = 'scalar'
        date = 'ClusterCreateTime'
        dimension = 'ClusterIdentifier'
        cfn_type = config_type = "AWS::Redshift::Cluster"


Redshift.filter_registry.register('marked-for-op', tags.TagActionFilter)
Redshift.filter_registry.register('network-location', net_filters.NetworkLocation)
Redshift.filter_registry.register('offhour', OffHour)
Redshift.filter_registry.register('onhour', OnHour)
Redshift.filter_registry.register('consecutive-aws-backups', ConsecutiveAwsBackupsFilter)


@Redshift.filter_registry.register('default-vpc')
class DefaultVpc(net_filters.DefaultVpcBase):
    """ Matches if an redshift database is in the default vpc

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-default-vpc
                resource: redshift
                filters:
                  - default-vpc
    """

    schema = type_schema('default-vpc')

    def __call__(self, redshift):
        return (redshift.get('VpcId') and
                self.match(redshift.get('VpcId')) or False)


@Redshift.filter_registry.register('logging')
class LoggingFilter(ValueFilter):
    """ Checks Redshift logging status and attributes.

    :example:

    .. code-block:: yaml


            policies:

                - name: redshift-logging-bucket-and-prefix-test
                  resource: redshift
                  filters:
                   - type: logging
                     key: LoggingEnabled
                     value: true
                   - type: logging
                     key: S3KeyPrefix
                     value: "accounts/{account_id}"
                   - type: logging
                     key: BucketName
                     value: "redshiftlogs"


    """
    permissions = ("redshift:DescribeLoggingStatus",)
    schema = type_schema('logging', rinherit=ValueFilter.schema)
    annotation_key = 'c7n:logging'

    def process(self, clusters, event=None):
        client = local_session(self.manager.session_factory).client('redshift')
        results = []
        for cluster in clusters:
            if self.annotation_key not in cluster:
                try:
                    result = client.describe_logging_status(
                        ClusterIdentifier=cluster['ClusterIdentifier'])
                    result.pop('ResponseMetadata')
                except client.exceptions.ClusterNotFound:
                    continue
                cluster[self.annotation_key] = result

            if self.match(cluster[self.annotation_key]):
                results.append(cluster)
        return results


@Redshift.action_registry.register('pause')
class Pause(BaseAction):

    schema = type_schema('pause')
    permissions = ('redshift:PauseCluster',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('redshift')
        for r in self.filter_resources(resources, 'ClusterStatus', ('available',)):
            try:
                client.pause_cluster(
                    ClusterIdentifier=r['ClusterIdentifier'])
            except (client.exceptions.ClusterNotFoundFault,
                    client.exceptions.InvalidClusterStateFault):
                raise


@Redshift.action_registry.register('resume')
class Resume(BaseAction):

    schema = type_schema('resume')
    permissions = ('redshift:ResumeCluster',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('redshift')
        for r in self.filter_resources(resources, 'ClusterStatus', ('paused',)):
            try:
                client.resume_cluster(
                    ClusterIdentifier=r['ClusterIdentifier'])
            except (client.exceptions.ClusterNotFoundFault,
                    client.exceptions.InvalidClusterStateFault):
                raise


@Redshift.action_registry.register('set-logging')
class SetRedshiftLogging(BaseAction):
    """Action to enable/disable Redshift logging for a Redshift Cluster.

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-test
                resource: redshift
                filters:
                  - type: logging
                    key: LoggingEnabled
                    value: false
                actions:
                  - type: set-logging
                    bucket: redshiftlogtest
                    prefix: redshiftlogs
                    state: enabled
    """
    schema = type_schema(
        'set-logging',
        state={'enum': ['enabled', 'disabled']},
        bucket={'type': 'string'},
        prefix={'type': 'string'},
        required=('state',))

    def get_permissions(self):
        perms = ('redshift:EnableLogging',)
        if self.data.get('state') == 'disabled':
            return ('redshift:DisableLogging',)
        return perms

    def validate(self):
        if self.data.get('state') == 'enabled':
            if 'bucket' not in self.data:
                raise PolicyValidationError((
                    "redshift logging enablement requires `bucket` "
                    "and `prefix` specification on %s" % (self.manager.data,)))
        return self

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('redshift')
        for redshift in resources:
            redshift_id = redshift['ClusterIdentifier']

            if self.data.get('state') == 'enabled':

                prefix = self.data.get('prefix')
                bucketname = self.data.get('bucket')

                self.manager.retry(
                    client.enable_logging,
                    ClusterIdentifier=redshift_id, BucketName=bucketname, S3KeyPrefix=prefix)

            elif self.data.get('state') == 'disabled':

                self.manager.retry(
                    client.disable_logging,
                    ClusterIdentifier=redshift_id)


@Redshift.filter_registry.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "VpcSecurityGroups[].VpcSecurityGroupId"


@Redshift.filter_registry.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = ""

    def get_permissions(self):
        return RedshiftSubnetGroup(self.manager.ctx, {}).get_permissions()

    def get_related_ids(self, resources):
        group_ids = set()
        for r in resources:
            group_ids.update(
                [s['SubnetIdentifier'] for s in
                 self.groups[r['ClusterSubnetGroupName']]['Subnets']])
        return group_ids

    def process(self, resources, event=None):
        self.groups = {r['ClusterSubnetGroupName']: r for r in
                       RedshiftSubnetGroup(self.manager.ctx, {}).resources()}
        return super(SubnetFilter, self).process(resources, event)


@Redshift.filter_registry.register('param')
class Parameter(ValueFilter):
    """Filter redshift clusters based on parameter values

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-param-ssl
                resource: redshift
                filters:
                  - type: param
                    key: require_ssl
                    value: false
                    op: eq
    """

    schema = type_schema('param', rinherit=ValueFilter.schema)
    schema_alias = False
    group_params = ()

    permissions = ("redshift:DescribeClusterParameters",)

    def process(self, clusters, event=None):
        groups = {}
        for r in clusters:
            for pg in r['ClusterParameterGroups']:
                groups.setdefault(pg['ParameterGroupName'], []).append(
                    r['ClusterIdentifier'])

        def get_params(group_name):
            c = local_session(self.manager.session_factory).client('redshift')
            paginator = c.get_paginator('describe_cluster_parameters')
            param_group = list(itertools.chain(*[p['Parameters']
                for p in paginator.paginate(ParameterGroupName=group_name)]))
            params = {}
            for p in param_group:
                v = p['ParameterValue']
                if v != 'default' and p['DataType'] in ('integer', 'boolean'):
                    # overkill..
                    v = json.loads(v)
                params[p['ParameterName']] = v
            return params

        with self.executor_factory(max_workers=3) as w:
            group_names = groups.keys()
            self.group_params = dict(
                zip(group_names, w.map(get_params, group_names)))
        return super(Parameter, self).process(clusters, event)

    def __call__(self, db):
        params = {}
        for pg in db['ClusterParameterGroups']:
            params.update(self.group_params[pg['ParameterGroupName']])
        return self.match(params)


@Redshift.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = 'KmsKeyId'


@Redshift.action_registry.register('delete')
class Delete(BaseAction):
    """Action to delete a redshift cluster

    To prevent unwanted deletion of redshift clusters, it is recommended to
    apply a filter to the rule

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-no-ssl
                resource: redshift
                filters:
                  - type: param
                    key: require_ssl
                    value: false
                    op: eq
                actions:
                  - type: delete
    """

    schema = type_schema(
        'delete', **{'skip-snapshot': {'type': 'boolean'}})

    permissions = ('redshift:DeleteCluster',)

    def process(self, clusters):
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for db_set in chunks(clusters, size=5):
                futures.append(
                    w.submit(self.process_db_set, db_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting redshift set \n %s",
                        f.exception())

    def process_db_set(self, db_set):
        skip = self.data.get('skip-snapshot', False)
        c = local_session(self.manager.session_factory).client('redshift')
        for db in db_set:
            params = {'ClusterIdentifier': db['ClusterIdentifier']}
            if skip:
                params['SkipFinalClusterSnapshot'] = True
            else:
                params['FinalClusterSnapshotIdentifier'] = snapshot_identifier(
                    'Final', db['ClusterIdentifier'])
            try:
                c.delete_cluster(**params)
            except ClientError as e:
                if e.response['Error']['Code'] == "InvalidClusterState":
                    self.log.warning(
                        "Cannot delete cluster when not 'Available' state: %s",
                        db['ClusterIdentifier'])
                    continue
                raise


@Redshift.action_registry.register('retention')
class RetentionWindow(BaseAction):
    """Action to set the snapshot retention period (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-snapshot-retention
                resource: redshift
                filters:
                  - type: value
                    key: AutomatedSnapshotRetentionPeriod
                    value: 21
                    op: ne
                actions:
                  - type: retention
                    days: 21
    """

    date_attribute = 'AutomatedSnapshotRetentionPeriod'
    schema = type_schema(
        'retention',
        **{'days': {'type': 'number'}})
    permissions = ('redshift:ModifyCluster',)

    def process(self, clusters):
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for cluster in clusters:
                futures.append(w.submit(
                    self.process_snapshot_retention,
                    cluster))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception setting Redshift retention  \n %s",
                        f.exception())

    def process_snapshot_retention(self, cluster):
        current_retention = int(cluster.get(self.date_attribute, 0))
        new_retention = self.data['days']

        if current_retention < new_retention:
            self.set_retention_window(
                cluster,
                max(current_retention, new_retention))
            return cluster

    def set_retention_window(self, cluster, retention):
        c = local_session(self.manager.session_factory).client('redshift')
        c.modify_cluster(
            ClusterIdentifier=cluster['ClusterIdentifier'],
            AutomatedSnapshotRetentionPeriod=retention)


@Redshift.action_registry.register('snapshot')
class Snapshot(BaseAction):
    """Action to take a snapshot of a redshift cluster

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-snapshot
                resource: redshift
                filters:
                  - type: value
                    key: ClusterStatus
                    value: available
                    op: eq
                actions:
                  - snapshot
    """

    schema = type_schema('snapshot')
    permissions = ('redshift:CreateClusterSnapshot',)

    def process(self, clusters):
        client = local_session(self.manager.session_factory).client('redshift')
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for cluster in clusters:
                futures.append(w.submit(
                    self.process_cluster_snapshot,
                    client, cluster))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception creating Redshift snapshot  \n %s",
                        f.exception())
        return clusters

    def process_cluster_snapshot(self, client, cluster):
        cluster_tags = cluster.get('Tags')
        client.create_cluster_snapshot(
            SnapshotIdentifier=snapshot_identifier(
                'Backup',
                cluster['ClusterIdentifier']),
            ClusterIdentifier=cluster['ClusterIdentifier'],
            Tags=cluster_tags)


@Redshift.action_registry.register('enable-vpc-routing')
class EnhancedVpcRoutine(BaseAction):
    """Action to enable enhanced vpc routing on a redshift cluster

    More: https://docs.aws.amazon.com/redshift/latest/mgmt/enhanced-vpc-routing.html

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-enable-enhanced-routing
                resource: redshift
                filters:
                  - type: value
                    key: EnhancedVpcRouting
                    value: false
                    op: eq
                actions:
                  - type: enable-vpc-routing
                    value: true
    """

    schema = type_schema(
        'enable-vpc-routing',
        value={'type': 'boolean'})
    permissions = ('redshift:ModifyCluster',)

    def process(self, clusters):
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for cluster in clusters:
                futures.append(w.submit(
                    self.process_vpc_routing,
                    cluster))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception changing Redshift VPC routing  \n %s",
                        f.exception())
        return clusters

    def process_vpc_routing(self, cluster):
        current_routing = bool(cluster.get('EnhancedVpcRouting', False))
        new_routing = self.data.get('value', True)

        if current_routing != new_routing:
            c = local_session(self.manager.session_factory).client('redshift')
            c.modify_cluster(
                ClusterIdentifier=cluster['ClusterIdentifier'],
                EnhancedVpcRouting=new_routing)


@Redshift.action_registry.register('set-public-access')
class RedshiftSetPublicAccess(BaseAction):
    """
    Action to set the 'PubliclyAccessible' setting on a redshift cluster

    :example:

    .. code-block:: yaml

            policies:
                - name: redshift-set-public-access
                  resource: redshift
                  filters:
                    - PubliclyAccessible: true
                  actions:
                    - type: set-public-access
                      state: false
    """

    schema = type_schema(
        'set-public-access',
        state={'type': 'boolean'})
    permissions = ('redshift:ModifyCluster',)

    def set_access(self, c):
        client = local_session(self.manager.session_factory).client('redshift')
        client.modify_cluster(
            ClusterIdentifier=c['ClusterIdentifier'],
            PubliclyAccessible=self.data.get('state', False))

    def process(self, clusters):
        with self.executor_factory(max_workers=2) as w:
            futures = {w.submit(self.set_access, c): c for c in clusters}
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception setting Redshift public access on %s  \n %s",
                        futures[f]['ClusterIdentifier'], f.exception())
        return clusters


@Redshift.action_registry.register('set-attributes')
class RedshiftSetAttributes(BaseAction):
    """
    Action to modify Redshift clusters

    :example:

    .. code-block:: yaml

            policies:
                - name: redshift-modify-cluster
                  resource: redshift
                  filters:
                    - type: value
                      key: AllowVersionUpgrade
                      value: false
                  actions:
                    - type: set-attributes
                      attributes:
                        AllowVersionUpgrade: true
    """

    schema = type_schema('set-attributes',
                        attributes={"type": "object"},
                        required=('attributes',))

    permissions = ('redshift:ModifyCluster',)
    cluster_mapping = {
        'ElasticIp': 'ElasticIpStatus.ElasticIp',
        'ClusterSecurityGroups': 'ClusterSecurityGroups[].ClusterSecurityGroupName',
        'VpcSecurityGroupIds': 'VpcSecurityGroups[].ClusterSecurityGroupName',
        'HsmClientCertificateIdentifier': 'HsmStatus.HsmClientCertificateIdentifier',
        'HsmConfigurationIdentifier': 'HsmStatus.HsmConfigurationIdentifier'
    }

    shape = 'ModifyClusterMessage'

    def validate(self):
        attrs = dict(self.data.get('attributes'))
        if attrs.get('ClusterIdentifier'):
            raise PolicyValidationError('ClusterIdentifier field cannot be updated')
        attrs["ClusterIdentifier"] = ""
        return shape_validate(attrs, self.shape, 'redshift')

    def process(self, clusters):
        client = local_session(self.manager.session_factory).client(
            self.manager.get_model().service)
        for cluster in clusters:
            self.process_cluster(client, cluster)

    def process_cluster(self, client, cluster):
        try:
            config = dict(self.data.get('attributes'))
            modify = {}
            for k, v in config.items():
                if ((k in self.cluster_mapping and
                v != jmespath_search(self.cluster_mapping[k], cluster)) or
                v != cluster.get('PendingModifiedValues', {}).get(k, cluster.get(k))):
                    modify[k] = v
            if not modify:
                return

            modify['ClusterIdentifier'] = (cluster.get('PendingModifiedValues', {})
                                          .get('ClusterIdentifier')
                                          or cluster.get('ClusterIdentifier'))
            client.modify_cluster(**modify)
        except (client.exceptions.ClusterNotFoundFault):
            return
        except ClientError as e:
            self.log.warning(
                "Exception trying to modify cluster: %s error: %s",
                cluster['ClusterIdentifier'], e)
            raise


@Redshift.action_registry.register('mark-for-op')
class TagDelayedAction(tags.TagDelayedAction):
    """Action to create an action to be performed at a later time

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-terminate-unencrypted
                resource: redshift
                filters:
                  - "tag:custodian_cleanup": absent
                  - type: value
                    key: Encrypted
                    value: false
                    op: eq
                actions:
                  - type: mark-for-op
                    tag: custodian_cleanup
                    op: delete
                    days: 5
                    msg: "Unencrypted Redshift cluster: {op}@{action_date}"
    """


@Redshift.action_registry.register('tag')
class Tag(tags.Tag):
    """Action to add tag/tags to a redshift cluster

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-tag
                resource: redshift
                filters:
                  - "tag:RedshiftTag": absent
                actions:
                  - type: tag
                    key: RedshiftTag
                    value: "Redshift Tag Value"
    """

    concurrency = 2
    batch_size = 5
    permissions = ('redshift:CreateTags',)

    def process_resource_set(self, client, resources, tags):
        for rarn, r in zip(self.manager.get_arns(resources), resources):
            client.create_tags(ResourceName=rarn, Tags=tags)


@Redshift.action_registry.register('unmark')
@Redshift.action_registry.register('remove-tag')
class RemoveTag(tags.RemoveTag):
    """Action to remove tag/tags from a redshift cluster

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-remove-tag
                resource: redshift
                filters:
                  - "tag:RedshiftTag": present
                actions:
                  - type: remove-tag
                    tags: ["RedshiftTags"]
    """

    concurrency = 2
    batch_size = 5
    permissions = ('redshift:DeleteTags',)

    def process_resource_set(self, client, resources, tag_keys):
        for rarn, r in zip(self.manager.get_arns(resources), resources):
            client.delete_tags(ResourceName=rarn, TagKeys=tag_keys)


@Redshift.action_registry.register('tag-trim')
class TagTrim(tags.TagTrim):
    """Action to remove tags from a redshift cluster

    This can be used to prevent reaching the ceiling limit of tags on a
    resource

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-tag-trim
                resource: redshift
                filters:
                  - type: value
                    key: "length(Tags)"
                    op: ge
                    value: 10
                actions:
                  - type: tag-trim
                    space: 1
                    preserve:
                      - RequiredTag1
                      - RequiredTag2
    """

    max_tag_count = 10
    permissions = ('redshift:DeleteTags',)

    def process_tag_removal(self, client, resource, candidates):
        arn = self.manager.generate_arn(resource['DBInstanceIdentifier'])
        client.delete_tags(ResourceName=arn, TagKeys=candidates)


@Redshift.action_registry.register('modify-security-groups')
class RedshiftModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):
    """Modify security groups on a Redshift cluster"""

    permissions = ('redshift:ModifyCluster',)

    def process(self, clusters):
        client = local_session(self.manager.session_factory).client('redshift')
        groups = super(
            RedshiftModifyVpcSecurityGroups, self).get_groups(clusters)

        for idx, c in enumerate(clusters):
            client.modify_cluster(
                ClusterIdentifier=c['ClusterIdentifier'],
                VpcSecurityGroupIds=groups[idx])


@resources.register('redshift-subnet-group')
class RedshiftSubnetGroup(QueryResourceManager):
    """Redshift subnet group."""

    class resource_type(TypeInfo):
        service = 'redshift'
        arn_type = 'subnetgroup'
        arn_separator = ':'
        id = name = 'ClusterSubnetGroupName'
        enum_spec = (
            'describe_cluster_subnet_groups', 'ClusterSubnetGroups', None)
        filter_name = 'ClusterSubnetGroupName'
        filter_type = 'scalar'
        cfn_type = config_type = "AWS::Redshift::ClusterSubnetGroup"
        universal_taggable = object()


@resources.register('redshift-snapshot')
class RedshiftSnapshot(QueryResourceManager):
    """Resource manager for Redshift snapshots.
    """

    class resource_type(TypeInfo):
        service = 'redshift'
        arn_type = 'snapshot'
        arn_separator = ':'
        enum_spec = ('describe_cluster_snapshots', 'Snapshots', None)
        name = id = 'SnapshotIdentifier'
        date = 'SnapshotCreateTime'
        config_type = "AWS::Redshift::ClusterSnapshot"
        universal_taggable = True

    def get_arns(self, resources):
        arns = []
        for r in resources:
            arns.append(self.generate_arn(r['ClusterIdentifier'] + '/' + r[self.get_model().id]))
        return arns


@RedshiftSnapshot.filter_registry.register('age')
class RedshiftSnapshotAge(AgeFilter):
    """Filters redshift snapshots based on age (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-old-snapshots
                resource: redshift-snapshot
                filters:
                  - type: age
                    days: 21
                    op: gt
    """

    schema = type_schema(
        'age', days={'type': 'number'},
        op={'$ref': '#/definitions/filters_common/comparison_operators'})

    date_attribute = 'SnapshotCreateTime'


@RedshiftSnapshot.filter_registry.register('cross-account')
class RedshiftSnapshotCrossAccount(CrossAccountAccessFilter):
    """Filter all accounts that allow access to non-whitelisted accounts
    """
    permissions = ('redshift:DescribeClusterSnapshots',)
    schema = type_schema(
        'cross-account',
        whitelist={'type': 'array', 'items': {'type': 'string'}},
        whitelist_from=ValuesFrom.schema)

    def process(self, snapshots, event=None):
        accounts = self.get_accounts()
        snapshots = [s for s in snapshots if s.get('AccountsWithRestoreAccess')]
        results = []
        for s in snapshots:
            s_accounts = {a.get('AccountId') for a in s[
                'AccountsWithRestoreAccess']}
            delta_accounts = s_accounts.difference(accounts)
            if delta_accounts:
                s['c7n:CrossAccountViolations'] = list(delta_accounts)
                results.append(s)
        return results


@RedshiftSnapshot.action_registry.register('delete')
class RedshiftSnapshotDelete(BaseAction):
    """Filters redshift snapshots based on age (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-delete-old-snapshots
                resource: redshift-snapshot
                filters:
                  - type: age
                    days: 21
                    op: gt
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('redshift:DeleteClusterSnapshot',)

    def process(self, snapshots):
        self.log.info("Deleting %d Redshift snapshots", len(snapshots))
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for snapshot_set in chunks(reversed(snapshots), size=50):
                futures.append(
                    w.submit(self.process_snapshot_set, snapshot_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting snapshot set \n %s",
                        f.exception())
        return snapshots

    def process_snapshot_set(self, snapshots_set):
        c = local_session(self.manager.session_factory).client('redshift')
        for s in snapshots_set:
            c.delete_cluster_snapshot(
                SnapshotIdentifier=s['SnapshotIdentifier'],
                SnapshotClusterIdentifier=s['ClusterIdentifier'])


@RedshiftSnapshot.action_registry.register('revoke-access')
class RedshiftSnapshotRevokeAccess(BaseAction):
    """Revokes ability of accounts to restore a snapshot

    :example:

        .. code-block:: yaml

            policies:
              - name: redshift-snapshot-revoke-access
                resource: redshift-snapshot
                filters:
                  - type: cross-account
                    whitelist:
                      - 012345678910
                actions:
                  - type: revoke-access
    """
    permissions = ('redshift:RevokeSnapshotAccess',)
    schema = type_schema('revoke-access')

    def validate(self):
        for f in self.manager.iter_filters():
            if isinstance(f, RedshiftSnapshotCrossAccount):
                return self
        raise PolicyValidationError(
            '`revoke-access` may only be used in '
            'conjunction with `cross-account` filter on %s' % (self.manager.data,))

    def process_snapshot_set(self, client, snapshot_set):
        for s in snapshot_set:
            for a in s.get('c7n:CrossAccountViolations', []):
                try:
                    self.manager.retry(
                        client.revoke_snapshot_access,
                        SnapshotIdentifier=s['SnapshotIdentifier'],
                        AccountWithRestoreAccess=a)
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ClusterSnapshotNotFound':
                        continue
                    raise

    def process(self, snapshots):
        client = local_session(self.manager.session_factory).client('redshift')
        with self.executor_factory(max_workers=2) as w:
            futures = {}
            for snapshot_set in chunks(snapshots, 25):
                futures[w.submit(
                    self.process_snapshot_set, client, snapshot_set)
                ] = snapshot_set
            for f in as_completed(futures):
                if f.exception():
                    self.log.exception(
                        'Exception while revoking access on %s: %s' % (
                            ', '.join(
                                [s['SnapshotIdentifier'] for s in futures[f]]),
                            f.exception()))


@resources.register('redshift-reserved')
class ReservedNode(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'redshift'
        name = id = 'ReservedNodeId'
        date = 'StartTime'
        enum_spec = (
            'describe_reserved_nodes', 'ReservedNodes', None)
        filter_name = 'ReservedNodes'
        filter_type = 'list'
        arn_type = "reserved-nodes"
        permissions_enum = ('redshift:DescribeReservedNodes',)


@Redshift.filter_registry.register('consecutive-snapshots')
class ClusterConsecutiveSnapshots(Filter):
    """Returns Clusters where number of consective daily backups is
    equal to/or greater than n days.

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-daily-snapshot-count
                resource: redshift
                filters:
                  - type: consecutive-snapshots
                    count: 7
                    period: days
                    status: available
    """
    schema = type_schema('consecutive-snapshots', count={'type': 'number', 'minimum': 1},
        period={'enum': ['hours', 'days', 'weeks']},
        status={'enum': ['available', 'creating', 'final snapshot', 'failed']},
        required=['count', 'period', 'status'])
    permissions = ('redshift:DescribeClusterSnapshots', 'redshift:DescribeClusters', )
    annotation = 'c7n:RedshiftSnapshots'

    def process_resource_set(self, client, resources, lbdate):
        paginator = client.get_paginator('describe_cluster_snapshots')
        paginator.PAGE_ITERATOR_CLS = RetryPageIterator
        rs_snapshots = paginator.paginate(StartTime=lbdate).build_full_result().get(
            'Snapshots', [])

        cluster_map = {}
        for snap in rs_snapshots:
            cluster_map.setdefault(snap['ClusterIdentifier'], []).append(snap)
        for r in resources:
            r[self.annotation] = cluster_map.get(r['ClusterIdentifier'], [])

    def get_date(self, time):
        period = self.data.get('period')
        if period == 'weeks':
            date = (datetime.utcnow() - timedelta(weeks=time)).strftime('%Y-%m-%d')
        elif period == 'hours':
            date = (datetime.utcnow() - timedelta(hours=time)).strftime('%Y-%m-%d-%H')
        else:
            date = (datetime.utcnow() - timedelta(days=time)).strftime('%Y-%m-%d')
        return date

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('redshift')
        results = []
        retention = self.data.get('count')
        lbdate = self.get_date(retention)
        expected_dates = set()
        for time in range(1, retention + 1):
            expected_dates.add(self.get_date(time))

        for resource_set in chunks(
                [r for r in resources if self.annotation not in r], 50):
            self.process_resource_set(client, resource_set, lbdate)

        for r in resources:
            snapshot_dates = set()
            for snapshot in r[self.annotation]:
                if snapshot['Status'] == self.data.get('status'):
                    if self.data.get('period') == 'hours':
                        snapshot_dates.add(snapshot['SnapshotCreateTime'].strftime('%Y-%m-%d-%H'))
                    else:
                        snapshot_dates.add(snapshot['SnapshotCreateTime'].strftime('%Y-%m-%d'))
            if expected_dates.issubset(snapshot_dates):
                results.append(r)
        return results
