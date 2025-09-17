# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""S3 Resource Manager

Filters:

The generic Values filters (jmespath) expression and Or filter are
available with all resources, including buckets, we include several
additonal bucket data (Tags, Replication, Acl, Policy) as keys within
a bucket representation.

Actions:

 encrypt-keys

   Scan all keys in a bucket and optionally encrypt them in place.

 global-grants

   Check bucket acls for global grants

 encryption-policy

   Attach an encryption required policy to a bucket, this will break
   applications that are not using encryption, including aws log
   delivery.

"""
import copy
import functools
import json
import logging
import math
import os
import time
import threading
import ssl

from botocore.client import Config
from botocore.exceptions import ClientError

from collections import defaultdict
from concurrent.futures import as_completed

try:
    from urllib3.exceptions import SSLError
except ImportError:
    from botocore.vendored.requests.packages.urllib3.exceptions import SSLError


from c7n.actions import (
    ActionRegistry, BaseAction, PutMetric, RemovePolicyBase)
from c7n.exceptions import PolicyValidationError, PolicyExecutionError
from c7n.filters import (
    FilterRegistry, Filter, CrossAccountAccessFilter, MetricsFilter,
    ValueFilter, ListItemFilter)
from .aws import shape_validate
from c7n.filters.policystatement import HasStatementFilter
from c7n.manager import resources
from c7n.output import NullBlobOutput
from c7n import query
from c7n.resources.securityhub import PostFinding
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import (
    chunks, local_session, set_annotation, type_schema, filter_empty,
    dumps, format_string_values, get_account_alias_from_sts)
from c7n.resources.aws import inspect_bucket_region


log = logging.getLogger('custodian.s3')

filters = FilterRegistry('s3.filters')
actions = ActionRegistry('s3.actions')
filters.register('marked-for-op', TagActionFilter)
actions.register('put-metric', PutMetric)

MAX_COPY_SIZE = 1024 * 1024 * 1024 * 2


class DescribeS3(query.DescribeSource):

    def augment(self, buckets):
        assembler = BucketAssembly(self.manager)
        assembler.initialize()

        with self.manager.executor_factory(
                max_workers=min((10, len(buckets) + 1))) as w:
            results = w.map(assembler.assemble, buckets)
            results = list(filter(None, results))
            return results


class ConfigS3(query.ConfigSource):

    # normalize config's janky idiosyncratic bespoke formating to the
    # standard describe api responses.

    def get_query_params(self, query):
        q = super(ConfigS3, self).get_query_params(query)
        if 'expr' in q:
            q['expr'] = q['expr'].replace('select ', 'select awsRegion, ')
        return q

    def load_resource(self, item):
        resource = super(ConfigS3, self).load_resource(item)
        cfg = item['supplementaryConfiguration']
        # aka standard
        if 'awsRegion' in item and item['awsRegion'] != 'us-east-1':
            resource['Location'] = {'LocationConstraint': item['awsRegion']}
        else:
            resource['Location'] = {}

        # owner is under acl per describe
        resource.pop('Owner', None)

        for k, null_value in S3_CONFIG_SUPPLEMENT_NULL_MAP.items():
            if k not in cfg:
                continue
            if cfg.get(k) == null_value:
                continue
            method = getattr(self, "handle_%s" % k, None)
            if method is None:
                raise ValueError("unhandled supplementary config %s", k)
                continue
            v = cfg[k]
            if isinstance(cfg[k], str):
                v = json.loads(cfg[k])
            method(resource, v)

        for el in S3_AUGMENT_TABLE:
            if el[1] not in resource:
                resource[el[1]] = el[2]
        return resource

    PERMISSION_MAP = {
        'FullControl': 'FULL_CONTROL',
        'Write': 'WRITE',
        'WriteAcp': 'WRITE_ACP',
        'Read': 'READ',
        'ReadAcp': 'READ_ACP'}

    GRANTEE_MAP = {
        'AllUsers': "http://acs.amazonaws.com/groups/global/AllUsers",
        'AuthenticatedUsers': "http://acs.amazonaws.com/groups/global/AuthenticatedUsers",
        'LogDelivery': 'http://acs.amazonaws.com/groups/s3/LogDelivery'}

    def handle_AccessControlList(self, resource, item_value):
        # double serialized in config for some reason
        if isinstance(item_value, str):
            item_value = json.loads(item_value)

        resource['Acl'] = {}
        resource['Acl']['Owner'] = {'ID': item_value['owner']['id']}
        if item_value['owner']['displayName']:
            resource['Acl']['Owner']['DisplayName'] = item_value[
                'owner']['displayName']
        resource['Acl']['Grants'] = grants = []

        for g in (item_value.get('grantList') or ()):
            if 'id' not in g['grantee']:
                assert g['grantee'] in self.GRANTEE_MAP, "unknown grantee %s" % g
                rg = {'Type': 'Group', 'URI': self.GRANTEE_MAP[g['grantee']]}
            else:
                rg = {'ID': g['grantee']['id'], 'Type': 'CanonicalUser'}

            if 'displayName' in g:
                rg['DisplayName'] = g['displayName']

            grants.append({
                'Permission': self.PERMISSION_MAP[g['permission']],
                'Grantee': rg,
            })

    def handle_BucketAccelerateConfiguration(self, resource, item_value):
        # not currently auto-augmented by custodian
        return

    def handle_BucketLoggingConfiguration(self, resource, item_value):
        if ('destinationBucketName' not in item_value or
                item_value['destinationBucketName'] is None):
            resource[u'Logging'] = {}
            return
        resource[u'Logging'] = {
            'TargetBucket': item_value['destinationBucketName'],
            'TargetPrefix': item_value['logFilePrefix']}

    def handle_BucketLifecycleConfiguration(self, resource, item_value):
        rules = []
        for r in item_value.get('rules'):
            rr = {}
            rules.append(rr)
            expiry = {}
            for ek, ck in (
                    ('Date', 'expirationDate'),
                    ('ExpiredObjectDeleteMarker', 'expiredObjectDeleteMarker'),
                    ('Days', 'expirationInDays')):
                if ck in r and r[ck] and r[ck] != -1:
                    expiry[ek] = r[ck]
            if expiry:
                rr['Expiration'] = expiry

            transitions = []
            for t in (r.get('transitions') or ()):
                tr = {}
                for k in ('date', 'days', 'storageClass'):
                    if t.get(k):
                        tr["%s%s" % (k[0].upper(), k[1:])] = t[k]
                transitions.append(tr)
            if transitions:
                rr['Transitions'] = transitions

            if r.get('abortIncompleteMultipartUpload'):
                rr['AbortIncompleteMultipartUpload'] = {
                    'DaysAfterInitiation': r[
                        'abortIncompleteMultipartUpload']['daysAfterInitiation']}
            if r.get('noncurrentVersionExpirationInDays'):
                rr['NoncurrentVersionExpiration'] = {
                    'NoncurrentDays': r['noncurrentVersionExpirationInDays']}

            nonc_transitions = []
            for t in (r.get('noncurrentVersionTransitions') or ()):
                nonc_transitions.append({
                    'NoncurrentDays': t['days'],
                    'StorageClass': t['storageClass']})
            if nonc_transitions:
                rr['NoncurrentVersionTransitions'] = nonc_transitions

            rr['Status'] = r['status']
            rr['ID'] = r['id']
            if r.get('prefix'):
                rr['Prefix'] = r['prefix']
            if 'filter' not in r or not r['filter']:
                continue

            if r['filter']['predicate']:
                rr['Filter'] = self.convertLifePredicate(r['filter']['predicate'])

        resource['Lifecycle'] = {'Rules': rules}

    def convertLifePredicate(self, p):
        if p['type'] == 'LifecyclePrefixPredicate':
            return {'Prefix': p['prefix']}
        if p['type'] == 'LifecycleTagPredicate':
            return {'Tags': [{'Key': p['tag']['key'], 'Value': p['tag']['value']}]}
        if p['type'] == 'LifecycleAndOperator':
            n = {}
            for o in p['operands']:
                ot = self.convertLifePredicate(o)
                if 'Tags' in n and 'Tags' in ot:
                    n['Tags'].extend(ot['Tags'])
                else:
                    n.update(ot)
            return {'And': n}

        raise ValueError("unknown predicate: %s" % p)

    NotifyTypeMap = {
        'QueueConfiguration': 'QueueConfigurations',
        'LambdaConfiguration': 'LambdaFunctionConfigurations',
        'CloudFunctionConfiguration': 'LambdaFunctionConfigurations',
        'TopicConfiguration': 'TopicConfigurations'}

    def handle_BucketNotificationConfiguration(self, resource, item_value):
        d = {}
        for nid, n in item_value['configurations'].items():
            ninfo = {}
            d.setdefault(self.NotifyTypeMap[n['type']], []).append(ninfo)
            if n['type'] == 'QueueConfiguration':
                ninfo['QueueArn'] = n['queueARN']
            elif n['type'] == 'TopicConfiguration':
                ninfo['TopicArn'] = n['topicARN']
            elif n['type'] == 'LambdaConfiguration':
                ninfo['LambdaFunctionArn'] = n['functionARN']
            ninfo['Id'] = nid
            ninfo['Events'] = n['events']
            rules = []
            if n['filter']:
                for r in n['filter'].get('s3KeyFilter', {}).get('filterRules', []):
                    rules.append({'Name': r['name'], 'Value': r['value']})
            if rules:
                ninfo['Filter'] = {'Key': {'FilterRules': rules}}
        resource['Notification'] = d

    def handle_BucketReplicationConfiguration(self, resource, item_value):
        d = {'Role': item_value['roleARN'], 'Rules': []}
        for rid, r in item_value['rules'].items():
            rule = {
                'ID': rid,
                'Status': r.get('status', ''),
                'Prefix': r.get('prefix', ''),
                'Destination': {
                    'Bucket': r['destinationConfig']['bucketARN']}
            }
            if 'Account' in r['destinationConfig']:
                rule['Destination']['Account'] = r['destinationConfig']['Account']
            if r['destinationConfig'].get('storageClass'):
                rule['Destination']['StorageClass'] = r['destinationConfig']['storageClass']
            d['Rules'].append(rule)
        resource['Replication'] = {'ReplicationConfiguration': d}

    def handle_BucketPolicy(self, resource, item_value):
        resource['Policy'] = item_value.get('policyText')

    def handle_BucketTaggingConfiguration(self, resource, item_value):
        resource['Tags'] = [
            {"Key": k, "Value": v} for k, v in item_value['tagSets'][0]['tags'].items()]

    def handle_BucketVersioningConfiguration(self, resource, item_value):
        # Config defaults versioning to 'Off' for a null value
        if item_value['status'] not in ('Enabled', 'Suspended'):
            resource['Versioning'] = {}
            return
        resource['Versioning'] = {'Status': item_value['status']}
        # `isMfaDeleteEnabled` is an optional boolean property - the key may be absent,
        # present with a null value, or present with a boolean value.
        # Mirror the describe source by populating Versioning.MFADelete only in the
        # boolean case.
        mfa_delete = item_value.get('isMfaDeleteEnabled')
        if mfa_delete is None:
            return
        resource['Versioning']['MFADelete'] = (
            'Enabled' if mfa_delete else 'Disabled'
        )

    def handle_BucketWebsiteConfiguration(self, resource, item_value):
        website = {}
        if item_value['indexDocumentSuffix']:
            website['IndexDocument'] = {
                'Suffix': item_value['indexDocumentSuffix']}
        if item_value['errorDocument']:
            website['ErrorDocument'] = {
                'Key': item_value['errorDocument']}
        if item_value['redirectAllRequestsTo']:
            website['RedirectAllRequestsTo'] = {
                'HostName': item_value['redirectAllRequestsTo']['hostName'],
                'Protocol': item_value['redirectAllRequestsTo']['protocol']}
        for r in item_value['routingRules']:
            redirect = {}
            rule = {'Redirect': redirect}
            website.setdefault('RoutingRules', []).append(rule)
            if 'condition' in r:
                cond = {}
                for ck, rk in (
                    ('keyPrefixEquals', 'KeyPrefixEquals'),
                    ('httpErrorCodeReturnedEquals',
                     'HttpErrorCodeReturnedEquals')):
                    if r['condition'][ck]:
                        cond[rk] = r['condition'][ck]
                rule['Condition'] = cond
            for ck, rk in (
                    ('protocol', 'Protocol'),
                    ('hostName', 'HostName'),
                    ('replaceKeyPrefixWith', 'ReplaceKeyPrefixWith'),
                    ('replaceKeyWith', 'ReplaceKeyWith'),
                    ('httpRedirectCode', 'HttpRedirectCode')):
                if r['redirect'][ck]:
                    redirect[rk] = r['redirect'][ck]
        resource['Website'] = website


@resources.register('s3')
class S3(query.QueryResourceManager):
    """Amazon's Simple Storage Service Buckets.


    By default and due to historical compatiblity cloud custodian will
    fetch a number of subdocuments (Acl, Policy, Tagging, Versioning,
    Website, Notification, Lifecycle, and Replication) for each bucket
    to allow policies authors's to target common bucket
    configurations.

    This behavior can be customized to avoid extraneous api calls if a
    particular sub document is not needed for a policy, by setting the
    `augment-keys` parameter in a query block of the policy.

    ie if we only care about bucket website and replication configuration, we can
    minimize the api calls needed to fetch a bucket by setting up augment-keys as follows.

    :example:

    .. code-block:: yaml

       policies:
         - name: check-website-replication
           resource: s3
           query:
             - augment-keys: ['Website', 'Replication']
           filters:
             - Website.ErrorDocument: not-null
             - Replication.ReplicationConfiguration.Rules: not-null

    It also supports an automatic detection mode where the use of a subdocument
    in a filter is automically with the augment-keys value of 'detect'.

    :example:

    .. code-block:: yaml

       policies:
         - name: check-website-replication
           resource: s3
           query:
             - augment-keys: 'detect'
           filters:
             - Website.ErrorDocument: not-null
             - Replication.ReplicationConfiguration.Rules: not-null

    The default value for augment-keys is `all` to preserve historical compatiblity. It also supports
    the value of 'none' to disable all subdocument fetching except Location and Tags.

    Note certain actions may implicitly depend on the corresponding subdocument being present.
    """

    class resource_type(query.TypeInfo):
        service = 's3'
        arn_type = ''
        enum_spec = ('list_buckets', 'Buckets[]', None)
        # not used but we want some consistency on the metadata
        detail_spec = ('get_bucket_location', 'Bucket', 'Name', 'LocationConstraint')
        permissions_augment = (
            "s3:GetBucketAcl",
            "s3:GetBucketLocation",
            "s3:GetBucketPolicy",
            "s3:GetBucketTagging",
            "s3:GetBucketVersioning",
            "s3:GetBucketLogging",
            "s3:GetBucketNotification",
            "s3:GetBucketWebsite",
            "s3:GetLifecycleConfiguration",
            "s3:GetReplicationConfiguration"
        )
        name = id = 'Name'
        date = 'CreationDate'
        dimension = 'BucketName'
        cfn_type = config_type = 'AWS::S3::Bucket'

    filter_registry = filters
    action_registry = actions
    source_mapping = {
        'describe': DescribeS3,
        'config': ConfigS3
    }

    def validate(self):
        super().validate()
        BucketAssembly(self).validate()

    def get_arns(self, resources):
        return ["arn:aws:s3:::{}".format(r["Name"]) for r in resources]

    @classmethod
    def get_permissions(cls):
        perms = ["s3:ListAllMyBuckets"]
        perms.extend([n[-1] for n in S3_AUGMENT_TABLE])
        return perms


S3_CONFIG_SUPPLEMENT_NULL_MAP = {
    'BucketLoggingConfiguration': u'{"destinationBucketName":null,"logFilePrefix":null}',
    'BucketPolicy': u'{"policyText":null}',
    'BucketVersioningConfiguration': u'{"status":"Off","isMfaDeleteEnabled":null}',
    'BucketAccelerateConfiguration': u'{"status":null}',
    'BucketNotificationConfiguration': u'{"configurations":{}}',
    'BucketLifecycleConfiguration': None,
    'AccessControlList': None,
    'BucketTaggingConfiguration': None,
    'BucketWebsiteConfiguration': None,
    'BucketReplicationConfiguration': None
}

S3_AUGMENT_TABLE = (
    ('get_bucket_location', 'Location', {}, None, 's3:GetBucketLocation'),
    ('get_bucket_tagging', 'Tags', [], 'TagSet', 's3:GetBucketTagging'),
    ('get_bucket_policy', 'Policy', None, 'Policy', 's3:GetBucketPolicy'),
    ('get_bucket_acl', 'Acl', None, None, 's3:GetBucketAcl'),
    ('get_bucket_replication',
     'Replication', None, None, 's3:GetReplicationConfiguration'),
    ('get_bucket_versioning', 'Versioning', None, None, 's3:GetBucketVersioning'),
    ('get_bucket_website', 'Website', None, None, 's3:GetBucketWebsite'),
    ('get_bucket_logging', 'Logging', None, 'LoggingEnabled', 's3:GetBucketLogging'),
    ('get_bucket_notification_configuration',
     'Notification', None, None, 's3:GetBucketNotification'),
    ('get_bucket_lifecycle_configuration',
     'Lifecycle', None, None, 's3:GetLifecycleConfiguration'),
    #        ('get_bucket_cors', 'Cors'),
)


class BucketAssembly:

    def __init__(self, manager):
        self.manager = manager
        self.default_region = None
        self.region_clients = {}
        self.session = None
        self.session_lock = None
        self.augment_fields = []

    def initialize(self):
        # construct a default boto3 client, using the current session region.
        self.session = local_session(self.manager.session_factory)
        self.session_lock = threading.Lock()
        self.default_region = self.manager.config.region
        self.region_clients[self.default_region] = self.session.client('s3')
        self.augment_fields = set(self.detect_augment_fields())
        # location is required for client construction
        self.augment_fields.add('Location')
        # custodian always returns tags
        self.augment_fields.add('Tags')

    def validate(self):
        config = self.get_augment_config()
        if isinstance(config, str) and config not in ('all', 'detect', 'none'):
            raise PolicyValidationError(
                "augment-keys supports 'all', 'detect', 'none' or list of keys found: %s" % config)
        elif isinstance(config, list):
            delta = set(config).difference([row[1] for row in S3_AUGMENT_TABLE])
            if delta:
                raise PolicyValidationError("augment-keys - found invalid keys: %s" % (list(delta)))
        if not isinstance(config, (list, str)):
            raise PolicyValidationError(
                "augment-keys supports 'all', 'detect', 'none' or list of keys found: %s" % config)

    def get_augment_config(self):
        augment_config = None
        for option in self.manager.data.get('query', []):
            if option and option.get('augment-keys') is not None:
                augment_config = option['augment-keys']
        if augment_config is None:
            augment_config = 'all'
        return augment_config

    def detect_augment_fields(self):
        # try to detect augment fields required for the policy execution
        # we want to avoid extraneous api calls unless they are being used by the policy.

        detected_keys = []
        augment_keys = [row[1] for row in S3_AUGMENT_TABLE]
        augment_config = self.get_augment_config()

        if augment_config == 'all':
            return augment_keys
        elif augment_config == 'none':
            return []
        elif isinstance(augment_config, list):
            return augment_config

        for f in self.manager.iter_filters():
            fkey = None
            if not isinstance(f, ValueFilter):
                continue

            f = f.data
            # type: value
            if f.get('type', '') == 'value':
                fkey = f.get('key')
            # k: v dict
            elif len(f) == 1:
                fkey = list(f.keys())[0]
            if fkey is None:
                continue

            # remove any jmespath expressions
            fkey = fkey.split('.', 1)[0]

            # tags have explicit handling in value filters.
            if fkey.startswith('tag:'):
                fkey = 'Tags'

            # denied methods checks get all keys
            if fkey.startswith('c7n:DeniedMethods'):
                return augment_keys

            if fkey in augment_keys:
                detected_keys.append(fkey)

        return detected_keys

    def get_client(self, region):
        if region in self.region_clients:
            return self.region_clients[region]
        with self.session_lock:
            self.region_clients[region] = self.session.client('s3', region=region)
            return self.region_clients[region]

    def normalize_region(self, location):
        # for historical reason we normalize EU to eu-west-1
        b_location = location.get('LocationConstraint')
        # Location == region for all cases but EU
        # https://docs.aws.amazon.com/AmazonS3/latest/API/RESTBucketGETlocation.html
        if b_location is None:
            b_location = "us-east-1"
        elif b_location == 'EU':
            b_location = "eu-west-1"
            location['LocationConstraint'] = 'eu-west-1'

    def assemble(self, bucket):

        client = self.get_client(self.default_region)
        augments = list(S3_AUGMENT_TABLE)

        for info in augments:
            # we use the offset, as tests manipulate the augments table
            method_name, key, default, select = info[:4]
            if key not in self.augment_fields:
                continue

            method = getattr(client, method_name)

            try:
                response = method(Bucket=bucket['Name'])
                # This is here as exception handling will change to defaults if not present
                response.pop('ResponseMetadata', None)
                value = response
                if select and select in value:
                    value = value[select]
            except (ssl.SSLError, SSLError) as e:
                # Proxy issue most likely
                log.warning("Bucket ssl error %s: %s %s",
                            bucket['Name'], bucket.get('Location', 'unknown'),
                            e)
                continue
            except ClientError as e:
                code = e.response['Error']['Code']
                if code.startswith("NoSuch") or "NotFound" in code:
                    value = default
                elif code == 'PermanentRedirect':
                    # (09/2025)- its not clear how we get here given a client region switch post
                    # location detection.
                    #
                    # change client region
                    client = self.get_client(get_region(bucket))
                    # requeue now that we have correct region
                    augments.append((method_name, key, default, select))
                    continue
                else:
                    # for auth errors record as attribute and move on
                    if e.response['Error']['Code'] == 'AccessDenied':
                        bucket.setdefault('c7n:DeniedMethods', []).append(method_name)
                        continue
                    # else log and raise
                    log.warning(
                        "Bucket:%s unable to invoke method:%s error:%s ",
                        bucket['Name'], method_name, e.response['Error']['Message'])
                    raise
            if key == 'Location' and value:
                self.normalize_region(value)

            bucket[key] = value

            if key == 'Location':
                if get_region(bucket) != client.meta.region_name:
                    client = self.get_client(get_region(bucket))
        return bucket


def bucket_client(session, b, kms=False):
    region = get_region(b)

    if kms:
        # Need v4 signature for aws:kms crypto, else let the sdk decide
        # based on region support.
        config = Config(
            signature_version='s3v4',
            read_timeout=200, connect_timeout=120)
    else:
        config = Config(read_timeout=200, connect_timeout=120)
    return session.client('s3', region_name=region, config=config)


def modify_bucket_tags(session_factory, buckets, add_tags=(), remove_tags=()):
    for bucket in buckets:
        client = bucket_client(local_session(session_factory), bucket)
        # Bucket tags are set atomically for the set/document, we want
        # to refetch against current to guard against any staleness in
        # our cached representation across multiple policies or concurrent
        # modifications.

        if 'get_bucket_tagging' in bucket.get('c7n:DeniedMethods', []):
            # avoid the additional API call if we already know that it's going
            # to result in AccessDenied. The chances that the resource's perms
            # would have changed between fetching the resource and acting on it
            # here are pretty low-- so the check here should suffice.
            log.warning(
                "Unable to get new set of bucket tags needed to modify tags,"
                "skipping tag action for bucket: %s" % bucket["Name"])
            continue

        try:
            bucket['Tags'] = client.get_bucket_tagging(
                Bucket=bucket['Name']).get('TagSet', [])
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchTagSet':
                raise
            bucket['Tags'] = []

        new_tags = {t['Key']: t['Value'] for t in add_tags}
        for t in bucket.get('Tags', ()):
            if (t['Key'] not in new_tags and t['Key'] not in remove_tags):
                new_tags[t['Key']] = t['Value']
        tag_set = [{'Key': k, 'Value': v} for k, v in new_tags.items()]

        try:
            client.put_bucket_tagging(
                Bucket=bucket['Name'], Tagging={'TagSet': tag_set})
        except ClientError as e:
            log.exception(
                'Exception tagging bucket %s: %s', bucket['Name'], e)
            continue


def get_region(b):
    """Tries to get the bucket region from Location.LocationConstraint

    Special cases:
        LocationConstraint EU defaults to eu-west-1
        LocationConstraint null defaults to us-east-1

    Args:
        b (object): A bucket object

    Returns:
        string: an aws region string
    """
    remap = {None: 'us-east-1', 'EU': 'eu-west-1'}
    region = b.get('Location', {}).get('LocationConstraint')
    return remap.get(region, region)


@filters.register('metrics')
class S3Metrics(MetricsFilter):
    """S3 CW Metrics need special handling for attribute/dimension
    mismatch, and additional required dimension.
    """

    def get_dimensions(self, resource):
        dims = [{'Name': 'BucketName', 'Value': resource['Name']}]
        if (self.data['name'] == 'NumberOfObjects' and
                'dimensions' not in self.data):
            dims.append(
                {'Name': 'StorageType', 'Value': 'AllStorageTypes'})
        return dims


@filters.register('cross-account')
class S3CrossAccountFilter(CrossAccountAccessFilter):
    """Filters cross-account access to S3 buckets

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-acl
                resource: s3
                region: us-east-1
                filters:
                  - type: cross-account
    """
    permissions = ('s3:GetBucketPolicy',)

    def get_accounts(self):
        """add in elb access by default

        ELB Accounts by region
         https://docs.aws.amazon.com/elasticloadbalancing/latest/classic/enable-access-logs.html

        Redshift Accounts by region
        https://docs.aws.amazon.com/redshift/latest/mgmt/db-auditing.html#db-auditing-manage-log-files
         https://docs.aws.amazon.com/redshift/latest/mgmt/db-auditing.html#rs-db-auditing-cloud-trail-rs-acct-ids

        Cloudtrail Accounts by region
         https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-supported-regions.html
        """
        accounts = super(S3CrossAccountFilter, self).get_accounts()
        return accounts.union(
            [
                # ELB accounts
                '127311923021',  # us-east-1
                '033677994240',  # us-east-2
                '027434742980',  # us-west-1
                '797873946194',  # us-west-2
                '098369216593',  # af-south-1
                '985666609251',  # ca-central-1
                '054676820928',  # eu-central-1
                '897822967062',  # eu-north-1
                '635631232127',  # eu-south-1
                '156460612806',  # eu-west-1
                '652711504416',  # eu-west-2
                '009996457667',  # eu-west-3
                '754344448648',  # ap-east-1
                '582318560864',  # ap-northeast-1
                '600734575887',  # ap-northeast-2
                '383597477331',  # ap-northeast-3
                '114774131450',  # ap-southeast-1
                '783225319266',  # ap-southeast-2
                '718504428378',  # ap-south-1
                '076674570225',  # me-south-1
                '507241528517',  # sa-east-1
                '048591011584',  # us-gov-west-1 or gov-cloud-1
                '190560391635',  # us-gov-east-1
                '638102146993',  # cn-north-1
                '037604701340',  # cn-northwest-1

                # Redshift audit logging
                '193672423079',  # us-east-1
                '391106570357',  # us-east-2
                '262260360010',  # us-west-1
                '902366379725',  # us-west-2
                '365689465814',  # af-south-1
                '313564881002',  # ap-east-1
                '865932855811',  # ap-south-1
                '090321488786',  # ap-northeast-3
                '760740231472',  # ap-northeast-2
                '361669875840',  # ap-southeast-1
                '762762565011',  # ap-southeast-2
                '404641285394',  # ap-northeast-1
                '907379612154',  # ca-central-1
                '053454850223',  # eu-central-1
                '210876761215',  # eu-west-1
                '307160386991',  # eu-west-2
                '945612479654',  # eu-south-1
                '915173422425',  # eu-west-3
                '729911121831',  # eu-north-1
                '013126148197',  # me-south-1
                '075028567923',  # sa-east-1

                # Cloudtrail accounts (psa. folks should be using
                # cloudtrail service in bucket policies)
                '086441151436',  # us-east-1
                '475085895292',  # us-west-2
                '388731089494',  # us-west-1
                '113285607260',  # us-west-2
                '819402241893',  # ca-central-1
                '977081816279',  # ap-south-1
                '492519147666',  # ap-northeast-2
                '903692715234',  # ap-southeast-1
                '284668455005',  # ap-southeast-2
                '216624486486',  # ap-northeast-1
                '035351147821',  # eu-central-1
                '859597730677',  # eu-west-1
                '282025262664',  # eu-west-2
                '814480443879',  # sa-east-1
            ])


@filters.register('global-grants')
class GlobalGrantsFilter(Filter):
    """Filters for all S3 buckets that have global-grants

    *Note* by default this filter allows for read access
    if the bucket has been configured as a website. This
    can be disabled per the example below.

    :example:

    .. code-block:: yaml

       policies:
         - name: remove-global-grants
           resource: s3
           filters:
            - type: global-grants
              allow_website: false
           actions:
            - delete-global-grants

    """

    schema = type_schema(
        'global-grants',
        allow_website={'type': 'boolean'},
        operator={'type': 'string', 'enum': ['or', 'and']},
        permissions={
            'type': 'array', 'items': {
                'type': 'string', 'enum': [
                    'READ', 'WRITE', 'WRITE_ACP', 'READ_ACP', 'FULL_CONTROL']}})

    GLOBAL_ALL = "http://acs.amazonaws.com/groups/global/AllUsers"
    AUTH_ALL = "http://acs.amazonaws.com/groups/global/AuthenticatedUsers"

    def process(self, buckets, event=None):
        with self.executor_factory(max_workers=5) as w:
            results = w.map(self.process_bucket, buckets)
            results = list(filter(None, list(results)))
            return results

    def process_bucket(self, b):
        acl = b.get('Acl', {'Grants': []})
        if not acl or not acl['Grants']:
            return

        results = []
        allow_website = self.data.get('allow_website', True)
        perms = self.data.get('permissions', [])

        for grant in acl['Grants']:
            if 'URI' not in grant.get("Grantee", {}):
                continue
            if grant['Grantee']['URI'] not in [self.AUTH_ALL, self.GLOBAL_ALL]:
                continue
            if allow_website and grant['Permission'] == 'READ' and b['Website']:
                continue
            if not perms or (perms and grant['Permission'] in perms):
                results.append(grant['Permission'])

        if results:
            set_annotation(b, 'GlobalPermissions', results)
            return b


class BucketActionBase(BaseAction):

    def get_permissions(self):
        return self.permissions

    def get_std_format_args(self, bucket):
        return {
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region,
            'bucket_name': bucket['Name'],
            'bucket_region': get_region(bucket)
        }

    def process(self, buckets):
        return self._process_with_futures(buckets)

    def _process_with_futures(self, buckets, *args, max_workers=3, **kwargs):
        errors = 0
        results = []
        with self.executor_factory(max_workers=max_workers) as w:
            futures = {}
            for b in buckets:
                futures[w.submit(self.process_bucket, b, *args, **kwargs)] = b
            for f in as_completed(futures):
                if f.exception():
                    b = futures[f]
                    self.log.error(
                        'error modifying bucket: policy:%s action:%s bucket:%s error:%s',
                        self.manager.data.get('name'), self.name, b['Name'], f.exception()
                    )
                    errors += 1
                    continue
                results += filter(None, [f.result()])
        if errors:
            self.log.error('encountered %d errors while processing %s', errors, self.name)
            raise PolicyExecutionError('%d resources failed', errors)
        return results


class BucketFilterBase(Filter):
    def get_std_format_args(self, bucket):
        return {
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region,
            'bucket_name': bucket['Name'],
            'bucket_region': get_region(bucket)
        }


@S3.action_registry.register("post-finding")
class BucketFinding(PostFinding):

    resource_type = 'AwsS3Bucket'

    def format_resource(self, r):
        owner = r.get("Acl", {}).get("Owner", {})
        resource = {
            "Type": self.resource_type,
            "Id": "arn:aws:s3:::{}".format(r["Name"]),
            "Region": get_region(r),
            "Tags": {t["Key"]: t["Value"] for t in r.get("Tags", [])},
            "Details": {self.resource_type: {
                "OwnerId": owner.get('ID', 'Unknown')}}
        }

        if "DisplayName" in owner:
            resource["Details"]["AwsS3Bucket"]["OwnerName"] = owner['DisplayName']

        return filter_empty(resource)


@S3.filter_registry.register('has-statement')
class S3HasStatementFilter(HasStatementFilter):
    def get_std_format_args(self, bucket):
        return {
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region,
            'bucket_name': bucket['Name'],
            'bucket_region': get_region(bucket)
        }


@S3.filter_registry.register('lock-configuration')
class S3LockConfigurationFilter(ValueFilter):
    """
    Filter S3 buckets based on their object lock configurations

    :example:

    Get all buckets where lock configuration mode is COMPLIANCE

        .. code-block:: yaml

                policies:
                  - name: lock-configuration-compliance
                    resource: aws.s3
                    filters:
                      - type: lock-configuration
                        key: Rule.DefaultRetention.Mode
                        value: COMPLIANCE

    """
    schema = type_schema('lock-configuration', rinherit=ValueFilter.schema)
    permissions = ('s3:GetBucketObjectLockConfiguration',)
    annotate = True
    annotation_key = 'c7n:ObjectLockConfiguration'

    def _process_resource(self, client, resource):
        try:
            config = client.get_object_lock_configuration(
                Bucket=resource['Name']
            )['ObjectLockConfiguration']
        except ClientError as e:
            if e.response['Error']['Code'] == 'ObjectLockConfigurationNotFoundError':
                config = None
            else:
                raise
        resource[self.annotation_key] = config

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('s3')
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for res in resources:
                if self.annotation_key in res:
                    continue
                futures.append(w.submit(self._process_resource, client, res))
            for f in as_completed(futures):
                exc = f.exception()
                if exc:
                    self.log.error(
                        "Exception getting bucket lock configuration \n %s" % (
                            exc))
        return super().process(resources, event)

    def __call__(self, r):
        return super().__call__(r.setdefault(self.annotation_key, None))


ENCRYPTION_STATEMENT_GLOB = {
    'Effect': 'Deny',
    'Principal': '*',
    'Action': 's3:PutObject',
    "Condition": {
        "StringNotEquals": {
            "s3:x-amz-server-side-encryption": ["AES256", "aws:kms"]}}}


@filters.register('no-encryption-statement')
class EncryptionEnabledFilter(Filter):
    """Find buckets with missing encryption policy statements.

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-bucket-not-encrypted
                resource: s3
                filters:
                  - type: no-encryption-statement
    """
    schema = type_schema(
        'no-encryption-statement')

    def get_permissions(self):
        perms = self.manager.get_resource_manager('s3').get_permissions()
        return perms

    def process(self, buckets, event=None):
        return list(filter(None, map(self.process_bucket, buckets)))

    def process_bucket(self, b):
        p = b.get('Policy')
        if p is None:
            return b
        p = json.loads(p)
        encryption_statement = dict(ENCRYPTION_STATEMENT_GLOB)

        statements = p.get('Statement', [])
        check = False
        for s in list(statements):
            if 'Sid' in s:
                encryption_statement["Sid"] = s["Sid"]
            if 'Resource' in s:
                encryption_statement["Resource"] = s["Resource"]
            if s == encryption_statement:
                check = True
                break
        if check:
            return None
        else:
            return b


@filters.register('missing-statement')
@filters.register('missing-policy-statement')
class MissingPolicyStatementFilter(Filter):
    """Find buckets missing a set of named policy statements.

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-bucket-missing-statement
                resource: s3
                filters:
                  - type: missing-statement
                    statement_ids:
                      - RequiredEncryptedPutObject
    """

    schema = type_schema(
        'missing-policy-statement',
        aliases=('missing-statement',),
        statement_ids={'type': 'array', 'items': {'type': 'string'}})

    def __call__(self, b):
        p = b.get('Policy')
        if p is None:
            return b

        p = json.loads(p)

        required = list(self.data.get('statement_ids', []))
        statements = p.get('Statement', [])
        for s in list(statements):
            if s.get('Sid') in required:
                required.remove(s['Sid'])
        if not required:
            return False
        return True


@filters.register('bucket-notification')
class BucketNotificationFilter(ValueFilter):
    """Filter based on bucket notification configuration.

    :example:

    .. code-block:: yaml

            policies:
              - name: delete-incorrect-notification
                resource: s3
                filters:
                  - type: bucket-notification
                    kind: lambda
                    key: Id
                    value: "IncorrectLambda"
                    op: eq
                actions:
                  - type: delete-bucket-notification
                    statement_ids: matched
    """

    schema = type_schema(
        'bucket-notification',
        required=['kind'],
        kind={'type': 'string', 'enum': ['lambda', 'sns', 'sqs']},
        rinherit=ValueFilter.schema)
    schema_alias = False
    annotation_key = 'c7n:MatchedNotificationConfigurationIds'

    permissions = ('s3:GetBucketNotification',)

    FIELDS = {
        'lambda': 'LambdaFunctionConfigurations',
        'sns': 'TopicConfigurations',
        'sqs': 'QueueConfigurations'
    }

    def process(self, buckets, event=None):
        return super(BucketNotificationFilter, self).process(buckets, event)

    def __call__(self, bucket):

        field = self.FIELDS[self.data['kind']]
        found = False
        for config in bucket.get('Notification', {}).get(field, []):
            if self.match(config):
                set_annotation(
                    bucket,
                    BucketNotificationFilter.annotation_key,
                    config['Id'])
                found = True
        return found


@filters.register('bucket-logging')
class BucketLoggingFilter(BucketFilterBase):
    """Filter based on bucket logging configuration.

    :example:

    .. code-block:: yaml

            policies:
              - name: add-bucket-logging-if-missing
                resource: s3
                filters:
                  - type: bucket-logging
                    op: disabled
                actions:
                  - type: toggle-logging
                    target_bucket: "{account_id}-{region}-s3-logs"
                    target_prefix: "{source_bucket_name}/"

            policies:
              - name: update-incorrect-or-missing-logging
                resource: s3
                filters:
                  - type: bucket-logging
                    op: not-equal
                    target_bucket: "{account_id}-{region}-s3-logs"
                    target_prefix: "{account}/{source_bucket_name}/"
                actions:
                  - type: toggle-logging
                    target_bucket: "{account_id}-{region}-s3-logs"
                    target_prefix: "{account}/{source_bucket_name}/"
    """

    schema = type_schema(
        'bucket-logging',
        op={'enum': ['enabled', 'disabled', 'equal', 'not-equal', 'eq', 'ne']},
        required=['op'],
        target_bucket={'type': 'string'},
        target_prefix={'type': 'string'})
    schema_alias = False
    account_name = None

    permissions = ("s3:GetBucketLogging", "iam:ListAccountAliases")

    def process(self, buckets, event=None):
        return list(filter(None, map(self.process_bucket, buckets)))

    def process_bucket(self, b):
        if self.match_bucket(b):
            return b

    def match_bucket(self, b):
        op = self.data.get('op')

        logging = b.get('Logging', {})
        if op == 'disabled':
            return logging == {}
        elif op == 'enabled':
            return logging != {}

        if self.account_name is None:
            session = local_session(self.manager.session_factory)
            self.account_name = get_account_alias_from_sts(session)

        variables = self.get_std_format_args(b)
        variables.update({
            'account': self.account_name,
            'source_bucket_name': b['Name'],
            'source_bucket_region': get_region(b),
            'target_bucket_name': self.data.get('target_bucket'),
            'target_prefix': self.data.get('target_prefix'),
        })
        data = format_string_values(self.data, **variables)
        target_bucket = data.get('target_bucket')
        target_prefix = data.get('target_prefix', b['Name'] + '/')

        target_config = {
            "TargetBucket": target_bucket,
            "TargetPrefix": target_prefix
        } if target_bucket else {}

        if op in ('not-equal', 'ne'):
            return logging != target_config
        else:
            return logging == target_config


@actions.register('delete-bucket-notification')
class DeleteBucketNotification(BucketActionBase):
    """Action to delete S3 bucket notification configurations"""

    schema = type_schema(
        'delete-bucket-notification',
        required=['statement_ids'],
        statement_ids={'oneOf': [
            {'enum': ['matched']},
            {'type': 'array', 'items': {'type': 'string'}}]})

    permissions = ('s3:PutBucketNotification',)

    def process_bucket(self, bucket):
        n = bucket['Notification']
        if not n:
            return

        statement_ids = self.data.get('statement_ids')
        if statement_ids == 'matched':
            statement_ids = bucket.get(BucketNotificationFilter.annotation_key, ())
        if not statement_ids:
            return

        cfg = defaultdict(list)

        for t in BucketNotificationFilter.FIELDS.values():
            for c in n.get(t, []):
                if c['Id'] not in statement_ids:
                    cfg[t].append(c)

        client = bucket_client(local_session(self.manager.session_factory), bucket)
        client.put_bucket_notification_configuration(
            Bucket=bucket['Name'],
            NotificationConfiguration=cfg)


@actions.register('no-op')
class NoOp(BucketActionBase):

    schema = type_schema('no-op')
    permissions = ('s3:ListAllMyBuckets',)

    def process(self, buckets):
        return None


@actions.register('set-statements')
class SetPolicyStatement(BucketActionBase):
    """Action to add or update policy statements to S3 buckets

    :example:

    .. code-block:: yaml

            policies:
              - name: force-s3-https
                resource: s3
                actions:
                  - type: set-statements
                    statements:
                      - Sid: "DenyHttp"
                        Effect: "Deny"
                        Action: "s3:GetObject"
                        Principal:
                          AWS: "*"
                        Resource: "arn:aws:s3:::{bucket_name}/*"
                        Condition:
                          Bool:
                            "aws:SecureTransport": false
    """

    permissions = ('s3:PutBucketPolicy',)

    schema = type_schema(
        'set-statements',
        **{
            'statements': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'Sid': {'type': 'string'},
                        'Effect': {'type': 'string', 'enum': ['Allow', 'Deny']},
                        'Principal': {'anyOf': [{'type': 'string'},
                            {'type': 'object'}, {'type': 'array'}]},
                        'NotPrincipal': {'anyOf': [{'type': 'object'}, {'type': 'array'}]},
                        'Action': {'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                        'NotAction': {'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                        'Resource': {'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                        'NotResource': {'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                        'Condition': {'type': 'object'}
                    },
                    'required': ['Sid', 'Effect'],
                    'oneOf': [
                        {'required': ['Principal', 'Action', 'Resource']},
                        {'required': ['NotPrincipal', 'Action', 'Resource']},
                        {'required': ['Principal', 'NotAction', 'Resource']},
                        {'required': ['NotPrincipal', 'NotAction', 'Resource']},
                        {'required': ['Principal', 'Action', 'NotResource']},
                        {'required': ['NotPrincipal', 'Action', 'NotResource']},
                        {'required': ['Principal', 'NotAction', 'NotResource']},
                        {'required': ['NotPrincipal', 'NotAction', 'NotResource']}
                    ]
                }
            }
        }
    )

    def process_bucket(self, bucket):
        policy = bucket.get('Policy') or '{}'

        target_statements = format_string_values(
            copy.deepcopy({s['Sid']: s for s in self.data.get('statements', [])}),
            **self.get_std_format_args(bucket))

        policy = json.loads(policy)
        bucket_statements = policy.setdefault('Statement', [])

        for s in bucket_statements:
            if s.get('Sid') not in target_statements:
                continue
            if s == target_statements[s['Sid']]:
                target_statements.pop(s['Sid'])

        if not target_statements:
            return

        bucket_statements.extend(target_statements.values())
        policy = json.dumps(policy)

        s3 = bucket_client(local_session(self.manager.session_factory), bucket)
        s3.put_bucket_policy(Bucket=bucket['Name'], Policy=policy)
        return {'Name': bucket['Name'], 'Policy': policy}


@actions.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """Action to remove policy statements from S3 buckets

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-remove-encrypt-put
                resource: s3
                filters:
                  - type: has-statement
                    statement_ids:
                      - RequireEncryptedPutObject
                actions:
                  - type: remove-statements
                    statement_ids:
                      - RequiredEncryptedPutObject
    """

    permissions = ("s3:PutBucketPolicy", "s3:DeleteBucketPolicy")

    def process(self, buckets):
        with self.executor_factory(max_workers=3) as w:
            futures = {}
            results = []
            for b in buckets:
                futures[w.submit(self.process_bucket, b)] = b
            for f in as_completed(futures):
                if f.exception():
                    b = futures[f]
                    self.log.error('error modifying bucket:%s\n%s',
                                   b['Name'], f.exception())
                results += filter(None, [f.result()])
            return results

    def process_bucket(self, bucket):
        p = bucket.get('Policy')
        if p is None:
            return

        p = json.loads(p)

        statements, found = self.process_policy(
            p, bucket, CrossAccountAccessFilter.annotation_key)

        if not found:
            return

        s3 = bucket_client(local_session(self.manager.session_factory), bucket)

        if not statements:
            s3.delete_bucket_policy(Bucket=bucket['Name'])
        else:
            s3.put_bucket_policy(Bucket=bucket['Name'], Policy=json.dumps(p))
        return {'Name': bucket['Name'], 'State': 'PolicyRemoved', 'Statements': found}


@actions.register('set-replication')
class SetBucketReplicationConfig(BucketActionBase):
    """Action to add or remove replication configuration statement from S3 buckets

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-unapproved-account-replication
                resource: s3
                filters:
                  - type: value
                    key: Replication.ReplicationConfiguration.Rules[].Destination.Account
                    value: present
                  - type: value
                    key: Replication.ReplicationConfiguration.Rules[].Destination.Account
                    value_from:
                      url: 's3:///path/to/file.json'
                      format: json
                      expr: "approved_accounts.*"
                    op: ni
                actions:
                  - type: set-replication
                    state: enable
    """
    schema = type_schema(
        'set-replication',
        state={'type': 'string', 'enum': ['enable', 'disable', 'remove']})
    permissions = ("s3:GetReplicationConfiguration", "s3:PutReplicationConfiguration")

    def process(self, buckets):
        with self.executor_factory(max_workers=3) as w:
            futures = {w.submit(self.process_bucket, bucket): bucket for bucket in buckets}
            errors = []
            for future in as_completed(futures):
                bucket = futures[future]
                try:
                    future.result()
                except ClientError as e:
                    errors.append("Message: %s Bucket: %s", e, bucket['Name'])
            if errors:
                raise Exception('\n'.join(map(str, errors)))

    def process_bucket(self, bucket):
        s3 = bucket_client(local_session(self.manager.session_factory), bucket)
        state = self.data.get('state')
        if state is not None:
            if state == 'remove':
                s3.delete_bucket_replication(Bucket=bucket['Name'])
                return {'Name': bucket['Name'], 'State': 'ReplicationConfigRemoved'}
            if state in ('enable', 'disable'):
                config = s3.get_bucket_replication(Bucket=bucket['Name'])
                for rule in config['ReplicationConfiguration']['Rules']:
                    rule['Status'] = 'Enabled' if state == 'enable' else 'Disabled'
                s3.put_bucket_replication(
                    Bucket=bucket['Name'],
                    ReplicationConfiguration=config['ReplicationConfiguration']
                )
                return {'Name': bucket['Name'], 'State': 'ReplicationConfigUpdated'}


@filters.register('check-public-block')
class FilterPublicBlock(Filter):
    """Filter for s3 bucket public blocks

    If no filter paramaters are provided it checks to see if any are unset or False.

    If parameters are provided only the provided ones are checked.

    :example:

    .. code-block:: yaml

            policies:
              - name: CheckForPublicAclBlock-Off
                resource: s3
                region: us-east-1
                filters:
                  - type: check-public-block
                    BlockPublicAcls: true
                    BlockPublicPolicy: true
    """

    schema = type_schema(
        'check-public-block',
        BlockPublicAcls={'type': 'boolean'},
        IgnorePublicAcls={'type': 'boolean'},
        BlockPublicPolicy={'type': 'boolean'},
        RestrictPublicBuckets={'type': 'boolean'})
    permissions = ("s3:GetBucketPublicAccessBlock",)
    keys = (
        'BlockPublicPolicy', 'BlockPublicAcls', 'IgnorePublicAcls', 'RestrictPublicBuckets')
    annotation_key = 'c7n:PublicAccessBlock'

    def process(self, buckets, event=None):
        results = []
        with self.executor_factory(max_workers=2) as w:
            futures = {w.submit(self.process_bucket, bucket): bucket for bucket in buckets}
            for f in as_completed(futures):
                if f.result():
                    results.append(futures[f])
        return results

    def process_bucket(self, bucket):
        s3 = bucket_client(local_session(self.manager.session_factory), bucket)
        config = dict(bucket.get(self.annotation_key, {key: False for key in self.keys}))
        if self.annotation_key not in bucket:
            try:
                config = s3.get_public_access_block(
                    Bucket=bucket['Name'])['PublicAccessBlockConfiguration']
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'NoSuchPublicAccessBlockConfiguration':
                    pass
                elif error_code == 'AccessDenied':
                    # Follow the same logic as `assemble_bucket` - log and continue on access
                    # denied errors rather than halting a policy altogether
                    method = 'GetPublicAccessBlock'
                    log.warning(
                        "Bucket:%s unable to invoke method:%s error:%s ",
                        bucket['Name'], method, e.response['Error']['Message']
                    )
                    bucket.setdefault('c7n:DeniedMethods', []).append(method)
                else:
                    raise
            bucket[self.annotation_key] = config
        return self.matches_filter(config)

    def matches_filter(self, config):
        key_set = [key for key in self.keys if key in self.data]
        if key_set:
            return all([self.data.get(key) is config[key] for key in key_set])
        else:
            return not all(config.values())


@actions.register('set-public-block')
class SetPublicBlock(BucketActionBase):
    """Action to update Public Access blocks on S3 buckets

    If no action parameters are provided all settings will be set to the `state`, which defaults

    If action parameters are provided, those will be set and other extant values preserved.

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-public-block-enable-all
                resource: s3
                filters:
                  - type: check-public-block
                actions:
                  - type: set-public-block

            policies:
              - name: s3-public-block-disable-all
                resource: s3
                filters:
                  - type: check-public-block
                actions:
                  - type: set-public-block
                    state: false

            policies:
              - name: s3-public-block-enable-some
                resource: s3
                filters:
                  - or:
                    - type: check-public-block
                      BlockPublicAcls: false
                    - type: check-public-block
                      BlockPublicPolicy: false
                actions:
                  - type: set-public-block
                    BlockPublicAcls: true
                    BlockPublicPolicy: true

    """

    schema = type_schema(
        'set-public-block',
        state={'type': 'boolean', 'default': True},
        BlockPublicAcls={'type': 'boolean'},
        IgnorePublicAcls={'type': 'boolean'},
        BlockPublicPolicy={'type': 'boolean'},
        RestrictPublicBuckets={'type': 'boolean'})
    permissions = ("s3:GetBucketPublicAccessBlock", "s3:PutBucketPublicAccessBlock")
    keys = FilterPublicBlock.keys
    annotation_key = FilterPublicBlock.annotation_key

    def process(self, buckets):
        with self.executor_factory(max_workers=3) as w:
            futures = {w.submit(self.process_bucket, bucket): bucket for bucket in buckets}
            for future in as_completed(futures):
                future.result()

    def process_bucket(self, bucket):
        s3 = bucket_client(local_session(self.manager.session_factory), bucket)
        config = dict(bucket.get(self.annotation_key, {key: False for key in self.keys}))
        if self.annotation_key not in bucket:
            try:
                config = s3.get_public_access_block(
                    Bucket=bucket['Name'])['PublicAccessBlockConfiguration']
            except ClientError as e:
                if e.response['Error']['Code'] != 'NoSuchPublicAccessBlockConfiguration':
                    raise

        key_set = [key for key in self.keys if key in self.data]
        if key_set:
            for key in key_set:
                config[key] = self.data.get(key)
        else:
            for key in self.keys:
                config[key] = self.data.get('state', True)
        s3.put_public_access_block(
            Bucket=bucket['Name'], PublicAccessBlockConfiguration=config)


@actions.register('toggle-versioning')
class ToggleVersioning(BucketActionBase):
    """Action to enable/suspend versioning on a S3 bucket

    Note versioning can never be disabled only suspended.

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-enable-versioning
                resource: s3
                filters:
                  - or:
                    - type: value
                      key: Versioning.Status
                      value: Suspended
                    - type: value
                      key: Versioning.Status
                      value: absent
                actions:
                  - type: toggle-versioning
                    enabled: true
    """

    schema = type_schema(
        'toggle-versioning',
        enabled={'type': 'boolean'})
    permissions = ("s3:PutBucketVersioning",)

    def process_versioning(self, resource, state):
        client = bucket_client(
            local_session(self.manager.session_factory), resource)
        try:
            client.put_bucket_versioning(
                Bucket=resource['Name'],
                VersioningConfiguration={
                    'Status': state})
        except ClientError as e:
            if e.response['Error']['Code'] != 'AccessDenied':
                log.error(
                    "Unable to put bucket versioning on bucket %s: %s" % (resource['Name'], e))
                raise
            log.warning(
                "Access Denied Bucket:%s while put bucket versioning" % resource['Name'])

    # mfa delete enablement looks like it needs the serial and a current token.
    def process(self, resources):
        enabled = self.data.get('enabled', True)
        for r in resources:
            if 'Versioning' not in r or not r['Versioning']:
                r['Versioning'] = {'Status': 'Suspended'}
            if enabled and (
                    r['Versioning']['Status'] == 'Suspended'):
                self.process_versioning(r, 'Enabled')
            if not enabled and r['Versioning']['Status'] == 'Enabled':
                self.process_versioning(r, 'Suspended')


@actions.register('toggle-logging')
class ToggleLogging(BucketActionBase):
    """Action to enable/disable logging on a S3 bucket.

    Target bucket ACL must allow for WRITE and READ_ACP Permissions
    Not specifying a target_prefix will default to the current bucket name.
    https://docs.aws.amazon.com/AmazonS3/latest/dev/enable-logging-programming.html

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-enable-logging
                resource: s3
                filters:
                  - "tag:Testing": present
                actions:
                  - type: toggle-logging
                    target_bucket: log-bucket
                    target_prefix: logs123/

            policies:
              - name: s3-force-standard-logging
                resource: s3
                filters:
                  - type: bucket-logging
                    op: not-equal
                    target_bucket: "{account_id}-{region}-s3-logs"
                    target_prefix: "{account}/{source_bucket_name}/"
                actions:
                  - type: toggle-logging
                    target_bucket: "{account_id}-{region}-s3-logs"
                    target_prefix: "{account}/{source_bucket_name}/"
    """
    schema = type_schema(
        'toggle-logging',
        enabled={'type': 'boolean'},
        target_bucket={'type': 'string'},
        target_prefix={'type': 'string'})

    permissions = ("s3:PutBucketLogging", "iam:ListAccountAliases")

    def validate(self):
        if self.data.get('enabled', True):
            if not self.data.get('target_bucket'):
                raise PolicyValidationError(
                    "target_bucket must be specified on %s" % (
                        self.manager.data,))
        return self

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        kwargs = {
            "enabled": self.data.get('enabled', True),
            "session": session,
            "account_name": get_account_alias_from_sts(session),
        }

        return self._process_with_futures(resources, **kwargs)

    def process_bucket(self, r, enabled=None, session=None, account_name=None):
        client = bucket_client(session, r)
        is_logging = bool(r.get('Logging'))

        if enabled:
            variables = self.get_std_format_args(r)
            variables.update({
                'account': account_name,
                'source_bucket_name': r['Name'],
                'source_bucket_region': get_region(r),
                'target_bucket_name': self.data.get('target_bucket'),
                'target_prefix': self.data.get('target_prefix'),
            })
            data = format_string_values(self.data, **variables)
            config = {
                'TargetBucket': data.get('target_bucket'),
                'TargetPrefix': data.get('target_prefix', r['Name'] + '/')
            }
            if not is_logging or r.get('Logging') != config:
                client.put_bucket_logging(
                    Bucket=r['Name'],
                    BucketLoggingStatus={'LoggingEnabled': config}
                )
                r['Logging'] = config

        elif not enabled and is_logging:
            client.put_bucket_logging(
                Bucket=r['Name'], BucketLoggingStatus={})
            r['Logging'] = {}


@actions.register('attach-encrypt')
class AttachLambdaEncrypt(BucketActionBase):
    """Action attaches lambda encryption policy to S3 bucket
       supports attachment via lambda bucket notification or sns notification
       to invoke lambda. a special topic value of `default` will utilize an
       extant notification or create one matching the bucket name.

       :example:


    .. code-block:: yaml


                policies:
                  - name: attach-lambda-encrypt
                    resource: s3
                    filters:
                      - type: missing-policy-statement
                    actions:
                      - type: attach-encrypt
                        role: arn:aws:iam::123456789012:role/my-role

    """
    schema = type_schema(
        'attach-encrypt',
        role={'type': 'string'},
        tags={'type': 'object'},
        topic={'type': 'string'})

    permissions = (
        "s3:PutBucketNotification", "s3:GetBucketNotification",
        # lambda manager uses quite a few perms to provision lambdas
        # and event sources, hard to disamgibuate punt for now.
        "lambda:*",
    )

    def __init__(self, data=None, manager=None):
        self.data = data or {}
        self.manager = manager

    def validate(self):
        if (not getattr(self.manager.config, 'dryrun', True) and
                not self.data.get('role', self.manager.config.assume_role)):
            raise PolicyValidationError(
                "attach-encrypt: role must be specified either "
                "via assume or in config on %s" % (self.manager.data,))

        return self

    def process(self, buckets):
        from c7n.mu import LambdaManager
        from c7n.ufuncs.s3crypt import get_function

        account_id = self.manager.config.account_id
        topic_arn = self.data.get('topic')

        func = get_function(
            None, self.data.get('role', self.manager.config.assume_role),
            account_id=account_id, tags=self.data.get('tags'))

        regions = {get_region(b) for b in buckets}

        # session managers by region
        region_sessions = {}
        for r in regions:
            region_sessions[r] = functools.partial(
                self.manager.session_factory, region=r)

        # Publish function to all of our buckets regions
        region_funcs = {}

        for r in regions:
            lambda_mgr = LambdaManager(region_sessions[r])
            lambda_mgr.publish(func)
            region_funcs[r] = func

        with self.executor_factory(max_workers=3) as w:
            results = []
            futures = []
            for b in buckets:
                region = get_region(b)
                futures.append(
                    w.submit(
                        self.process_bucket,
                        region_funcs[region],
                        b,
                        topic_arn,
                        account_id,
                        region_sessions[region]
                    ))
            for f in as_completed(futures):
                if f.exception():
                    log.exception(
                        "Error attaching lambda-encrypt %s" % (f.exception()))
                results.append(f.result())
            return list(filter(None, results))

    def process_bucket(self, func, bucket, topic, account_id, session_factory):
        from c7n.mu import BucketSNSNotification, BucketLambdaNotification
        if topic:
            topic = None if topic == 'default' else topic
            source = BucketSNSNotification(session_factory, bucket, topic)
        else:
            source = BucketLambdaNotification(
                {'account_s3': account_id}, session_factory, bucket)
        return source.add(func, None)


@actions.register('encryption-policy')
class EncryptionRequiredPolicy(BucketActionBase):
    """Action to apply an encryption policy to S3 buckets


    :example:

    .. code-block:: yaml

            policies:
              - name: s3-enforce-encryption
                resource: s3
                mode:
                  type: cloudtrail
                  events:
                    - CreateBucket
                actions:
                  - encryption-policy
    """

    permissions = ("s3:GetBucketPolicy", "s3:PutBucketPolicy")
    schema = type_schema('encryption-policy')

    def __init__(self, data=None, manager=None):
        self.data = data or {}
        self.manager = manager

    def process(self, buckets):
        with self.executor_factory(max_workers=3) as w:
            results = w.map(self.process_bucket, buckets)
            results = list(filter(None, list(results)))
            return results

    def process_bucket(self, b):
        p = b['Policy']
        if p is None:
            log.info("No policy found, creating new")
            p = {'Version': "2012-10-17", "Statement": []}
        else:
            p = json.loads(p)

        encryption_sid = "RequiredEncryptedPutObject"
        encryption_statement = {
            'Sid': encryption_sid,
            'Effect': 'Deny',
            'Principal': '*',
            'Action': 's3:PutObject',
            "Resource": "arn:aws:s3:::%s/*" % b['Name'],
            "Condition": {
                # AWS Managed Keys or KMS keys, note policy language
                # does not support custom kms (todo add issue)
                "StringNotEquals": {
                    "s3:x-amz-server-side-encryption": ["AES256", "aws:kms"]}}}

        statements = p.get('Statement', [])
        for s in list(statements):
            if s.get('Sid', '') == encryption_sid:
                log.debug("Bucket:%s Found extant encrypt policy", b['Name'])
                if s != encryption_statement:
                    log.info(
                        "Bucket:%s updating extant encrypt policy", b['Name'])
                    statements.remove(s)
                else:
                    return

        session = self.manager.session_factory()
        s3 = bucket_client(session, b)
        statements.append(encryption_statement)
        p['Statement'] = statements
        log.info('Bucket:%s attached encryption policy' % b['Name'])

        try:
            s3.put_bucket_policy(
                Bucket=b['Name'],
                Policy=json.dumps(p))
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                return
            self.log.exception(
                "Error on bucket:%s putting policy\n%s error:%s",
                b['Name'],
                json.dumps(statements, indent=2), e)
            raise
        return {'Name': b['Name'], 'State': 'PolicyAttached'}


class BucketScanLog:
    """Offload remediated key ids to a disk file in batches

    A bucket keyspace is effectively infinite, we need to store partial
    results out of memory, this class provides for a json log on disk
    with partial write support.

    json output format:
     - [list_of_serialized_keys],
     - [] # Empty list of keys at end when we close the buffer

    """

    def __init__(self, log_dir, name):
        self.log_dir = log_dir
        self.name = name
        self.fh = None
        self.count = 0

    @property
    def path(self):
        return os.path.join(self.log_dir, "%s.json" % self.name)

    def __enter__(self):
        # Don't require output directories
        if self.log_dir is None:
            return

        self.fh = open(self.path, 'w')
        self.fh.write("[\n")
        return self

    def __exit__(self, exc_type=None, exc_value=None, exc_frame=None):
        if self.fh is None:
            return
        # we need an empty marker list at end to avoid trailing commas
        self.fh.write("[]")
        # and close the surrounding list
        self.fh.write("\n]")
        self.fh.close()
        if not self.count:
            os.remove(self.fh.name)
        self.fh = None
        return False

    def add(self, keys):
        self.count += len(keys)
        if self.fh is None:
            return
        self.fh.write(dumps(keys))
        self.fh.write(",\n")


class ScanBucket(BucketActionBase):

    permissions = ("s3:ListBucket",)

    bucket_ops = {
        'standard': {
            'iterator': 'list_objects',
            'contents_key': ['Contents'],
            'key_processor': 'process_key'
        },
        'versioned': {
            'iterator': 'list_object_versions',
            'contents_key': ['Versions'],
            'key_processor': 'process_version'
        }
    }

    def __init__(self, data, manager=None):
        super(ScanBucket, self).__init__(data, manager)
        self.denied_buckets = set()

    def get_bucket_style(self, b):
        return (
            b.get('Versioning', {'Status': ''}).get('Status') in (
                'Enabled', 'Suspended') and 'versioned' or 'standard')

    def get_bucket_op(self, b, op_name):
        bucket_style = self.get_bucket_style(b)
        op = self.bucket_ops[bucket_style][op_name]
        if op_name == 'key_processor':
            return getattr(self, op)
        return op

    def get_keys(self, b, key_set):
        content_keys = self.get_bucket_op(b, 'contents_key')
        keys = []
        for ck in content_keys:
            keys.extend(key_set.get(ck, []))
        return keys

    def process(self, buckets):
        results = self._process_with_futures(self.process_bucket, buckets)
        self.write_denied_buckets_file()
        return results

    def _process_with_futures(self, helper, buckets, max_workers=3):
        results = []
        with self.executor_factory(max_workers) as w:
            futures = {}
            for b in buckets:
                futures[w.submit(helper, b)] = b
            for f in as_completed(futures):
                if f.exception():
                    b = futures[f]
                    self.log.error(
                        "Error on bucket:%s region:%s policy:%s error: %s",
                        b['Name'], b.get('Location', 'unknown'),
                        self.manager.data.get('name'), f.exception())
                    self.denied_buckets.add(b['Name'])
                    continue
                result = f.result()
                if result:
                    results.append(result)
        return results

    def write_denied_buckets_file(self):
        if (self.denied_buckets and
                self.manager.ctx.log_dir and
                not isinstance(self.manager.ctx.output, NullBlobOutput)):
            with open(
                    os.path.join(
                        self.manager.ctx.log_dir, 'denied.json'), 'w') as fh:
                json.dump(list(self.denied_buckets), fh, indent=2)
            self.denied_buckets = set()

    def process_bucket(self, b):
        log.info(
            "Scanning bucket:%s visitor:%s style:%s" % (
                b['Name'], self.__class__.__name__, self.get_bucket_style(b)))

        s = self.manager.session_factory()
        s3 = bucket_client(s, b)

        # The bulk of _process_bucket function executes inline in
        # calling thread/worker context, neither paginator nor
        # bucketscan log should be used across worker boundary.
        p = s3.get_paginator(
            self.get_bucket_op(b, 'iterator')).paginate(Bucket=b['Name'])

        with BucketScanLog(self.manager.ctx.log_dir, b['Name']) as key_log:
            with self.executor_factory(max_workers=10) as w:
                try:
                    return self._process_bucket(b, p, key_log, w)
                except ClientError as e:
                    if e.response['Error']['Code'] == 'NoSuchBucket':
                        log.warning(
                            "Bucket:%s removed while scanning" % b['Name'])
                        return
                    if e.response['Error']['Code'] == 'AccessDenied':
                        log.warning(
                            "Access Denied Bucket:%s while scanning" % b['Name'])
                        self.denied_buckets.add(b['Name'])
                        return
                    log.exception(
                        "Error processing bucket:%s paginator:%s" % (
                            b['Name'], p))

    __call__ = process_bucket

    def _process_bucket(self, b, p, key_log, w):
        count = 0

        for key_set in p:
            keys = self.get_keys(b, key_set)
            count += len(keys)
            futures = []

            for batch in chunks(keys, size=100):
                if not batch:
                    continue
                futures.append(w.submit(self.process_chunk, batch, b))

            for f in as_completed(futures):
                if f.exception():
                    log.exception("Exception Processing bucket:%s key batch %s" % (
                        b['Name'], f.exception()))
                    continue
                r = f.result()
                if r:
                    key_log.add(r)

            # Log completion at info level, progress at debug level
            if key_set['IsTruncated']:
                log.debug('Scan progress bucket:%s keys:%d remediated:%d ...',
                          b['Name'], count, key_log.count)
            else:
                log.info('Scan Complete bucket:%s keys:%d remediated:%d',
                         b['Name'], count, key_log.count)

        b['KeyScanCount'] = count
        b['KeyRemediated'] = key_log.count
        return {
            'Bucket': b['Name'], 'Remediated': key_log.count, 'Count': count}

    def process_chunk(self, batch, bucket):
        raise NotImplementedError()

    def process_key(self, s3, key, bucket_name, info=None):
        raise NotImplementedError()

    def process_version(self, s3, bucket, key):
        raise NotImplementedError()


@actions.register('encrypt-keys')
class EncryptExtantKeys(ScanBucket):
    """Action to encrypt unencrypted S3 objects

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-encrypt-objects
                resource: s3
                actions:
                  - type: encrypt-keys
                    crypto: aws:kms
                    key-id: 9c3983be-c6cf-11e6-9d9d-cec0c932ce01
    """

    permissions = (
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObjectVersion",
        "s3:RestoreObject",
    ) + ScanBucket.permissions

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['encrypt-keys']},
            'report-only': {'type': 'boolean'},
            'glacier': {'type': 'boolean'},
            'large': {'type': 'boolean'},
            'crypto': {'enum': ['AES256', 'aws:kms']},
            'key-id': {'type': 'string'}
        },
        'dependencies': {
            'key-id': {
                'properties': {
                    'crypto': {'pattern': 'aws:kms'}
                },
                'required': ['crypto']
            }
        }
    }

    metrics = [
        ('Total Keys', {'Scope': 'Account'}),
        ('Unencrypted', {'Scope': 'Account'})]

    def __init__(self, data, manager=None):
        super(EncryptExtantKeys, self).__init__(data, manager)
        self.kms_id = self.data.get('key-id')

    def get_permissions(self):
        perms = ("s3:GetObject", "s3:GetObjectVersion")
        if self.data.get('report-only'):
            perms += ('s3:DeleteObject', 's3:DeleteObjectVersion',
                      's3:PutObject',
                      's3:AbortMultipartUpload',
                      's3:ListBucket',
                      's3:ListBucketVersions')
        return perms

    def process(self, buckets):

        t = time.time()
        results = super(EncryptExtantKeys, self).process(buckets)
        run_time = time.time() - t
        remediated_count = object_count = 0

        for r in results:
            object_count += r['Count']
            remediated_count += r['Remediated']
            self.manager.ctx.metrics.put_metric(
                "Unencrypted", r['Remediated'], "Count", Scope=r['Bucket'],
                buffer=True)

        self.manager.ctx.metrics.put_metric(
            "Unencrypted", remediated_count, "Count", Scope="Account",
            buffer=True
        )
        self.manager.ctx.metrics.put_metric(
            "Total Keys", object_count, "Count", Scope="Account",
            buffer=True
        )
        self.manager.ctx.metrics.flush()

        log.info(
            ("EncryptExtant Complete keys:%d "
             "remediated:%d rate:%0.2f/s time:%0.2fs"),
            object_count,
            remediated_count,
            float(object_count) / run_time if run_time else 0,
            run_time)
        return results

    def process_chunk(self, batch, bucket):
        crypto_method = self.data.get('crypto', 'AES256')
        s3 = bucket_client(
            local_session(self.manager.session_factory), bucket,
            kms=(crypto_method == 'aws:kms'))
        b = bucket['Name']
        results = []
        key_processor = self.get_bucket_op(bucket, 'key_processor')
        for key in batch:
            r = key_processor(s3, key, b)
            if r:
                results.append(r)
        return results

    def process_key(self, s3, key, bucket_name, info=None):
        k = key['Key']
        if info is None:
            info = s3.head_object(Bucket=bucket_name, Key=k)

        # If the data is already encrypted with AES256 and this request is also
        # for AES256 then we don't need to do anything
        if info.get('ServerSideEncryption') == 'AES256' and not self.kms_id:
            return False

        if info.get('ServerSideEncryption') == 'aws:kms':
            # If we're not looking for a specific key any key will do.
            if not self.kms_id:
                return False
            # If we're configured to use a specific key and the key matches
            # note this is not a strict equality match.
            if self.kms_id in info.get('SSEKMSKeyId', ''):
                return False

        if self.data.get('report-only'):
            return k

        storage_class = info.get('StorageClass', 'STANDARD')

        if storage_class == 'GLACIER':
            if not self.data.get('glacier'):
                return False
            if 'Restore' not in info:
                # This takes multiple hours, we let the next c7n
                # run take care of followups.
                s3.restore_object(
                    Bucket=bucket_name,
                    Key=k,
                    RestoreRequest={'Days': 30})
                return False
            elif not restore_complete(info['Restore']):
                return False

            storage_class = 'STANDARD'

        crypto_method = self.data.get('crypto', 'AES256')
        key_id = self.data.get('key-id')
        # Note on copy we lose individual object acl grants
        params = {'Bucket': bucket_name,
                  'Key': k,
                  'CopySource': "/%s/%s" % (bucket_name, k),
                  'MetadataDirective': 'COPY',
                  'StorageClass': storage_class,
                  'ServerSideEncryption': crypto_method}

        if key_id and crypto_method == 'aws:kms':
            params['SSEKMSKeyId'] = key_id

        if info['ContentLength'] > MAX_COPY_SIZE and self.data.get(
                'large', True):
            return self.process_large_file(s3, bucket_name, key, info, params)

        s3.copy_object(**params)
        return k

    def process_version(self, s3, key, bucket_name):
        info = s3.head_object(
            Bucket=bucket_name,
            Key=key['Key'],
            VersionId=key['VersionId'])

        if 'ServerSideEncryption' in info:
            return False

        if self.data.get('report-only'):
            return key['Key'], key['VersionId']

        if key['IsLatest']:
            r = self.process_key(s3, key, bucket_name, info)
            # Glacier request processing, wait till we have the restored object
            if not r:
                return r
        s3.delete_object(
            Bucket=bucket_name,
            Key=key['Key'],
            VersionId=key['VersionId'])
        return key['Key'], key['VersionId']

    def process_large_file(self, s3, bucket_name, key, info, params):
        """For objects over 5gb, use multipart upload to copy"""
        part_size = MAX_COPY_SIZE - (1024 ** 2)
        num_parts = int(math.ceil(info['ContentLength'] / part_size))
        source = params.pop('CopySource')

        params.pop('MetadataDirective')
        if 'Metadata' in info:
            params['Metadata'] = info['Metadata']

        upload_id = s3.create_multipart_upload(**params)['UploadId']

        params = {'Bucket': bucket_name,
                  'Key': key['Key'],
                  'UploadId': upload_id,
                  'CopySource': source,
                  'CopySourceIfMatch': info['ETag']}

        def upload_part(part_num):
            part_params = dict(params)
            part_params['CopySourceRange'] = "bytes=%d-%d" % (
                part_size * (part_num - 1),
                min(part_size * part_num - 1, info['ContentLength'] - 1))
            part_params['PartNumber'] = part_num
            response = s3.upload_part_copy(**part_params)
            return {'ETag': response['CopyPartResult']['ETag'],
                    'PartNumber': part_num}

        try:
            with self.executor_factory(max_workers=2) as w:
                parts = list(w.map(upload_part, range(1, num_parts + 1)))
        except Exception:
            log.warning(
                "Error during large key copy bucket: %s key: %s, "
                "aborting upload", bucket_name, key, exc_info=True)
            s3.abort_multipart_upload(
                Bucket=bucket_name, Key=key['Key'], UploadId=upload_id)
            raise
        s3.complete_multipart_upload(
            Bucket=bucket_name, Key=key['Key'], UploadId=upload_id,
            MultipartUpload={'Parts': parts})
        return key['Key']


def restore_complete(restore):
    if ',' in restore:
        ongoing, _ = restore.split(',', 1)
    else:
        ongoing = restore
    return 'false' in ongoing


@filters.register('is-log-target')
class LogTarget(Filter):
    """Filter and return buckets are log destinations.

    Not suitable for use in lambda on large accounts, This is a api
    heavy process to detect scan all possible log sources.

    Sources:
      - elb (Access Log)
      - s3 (Access Log)
      - cfn (Template writes)
      - cloudtrail

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-log-bucket
                resource: s3
                filters:
                  - type: is-log-target
    """

    schema = type_schema(
        'is-log-target',
        services={'type': 'array', 'items': {'enum': [
            's3', 'elb', 'cloudtrail']}},
        self={'type': 'boolean'},
        value={'type': 'boolean'})

    def get_permissions(self):
        perms = self.manager.get_resource_manager('elb').get_permissions()
        perms += ('elasticloadbalancing:DescribeLoadBalancerAttributes',)
        return perms

    def process(self, buckets, event=None):
        log_buckets = set()
        count = 0

        services = self.data.get('services', ['elb', 's3', 'cloudtrail'])
        self_log = self.data.get('self', False)

        if 'elb' in services and not self_log:
            for bucket, _ in self.get_elb_bucket_locations():
                log_buckets.add(bucket)
                count += 1
            self.log.debug("Found %d elb log targets" % count)

        if 's3' in services:
            count = 0
            for bucket, _ in self.get_s3_bucket_locations(buckets, self_log):
                count += 1
                log_buckets.add(bucket)
            self.log.debug('Found %d s3 log targets' % count)

        if 'cloudtrail' in services and not self_log:
            for bucket, _ in self.get_cloud_trail_locations(buckets):
                log_buckets.add(bucket)

        self.log.info("Found %d log targets for %d buckets" % (
            len(log_buckets), len(buckets)))
        if self.data.get('value', True):
            return [b for b in buckets if b['Name'] in log_buckets]
        else:
            return [b for b in buckets if b['Name'] not in log_buckets]

    @staticmethod
    def get_s3_bucket_locations(buckets, self_log=False):
        """return (bucket_name, prefix) for all s3 logging targets"""
        for b in buckets:
            if b.get('Logging'):
                if self_log:
                    if b['Name'] != b['Logging']['TargetBucket']:
                        continue
                yield (b['Logging']['TargetBucket'],
                       b['Logging']['TargetPrefix'])
            if not self_log and b['Name'].startswith('cf-templates-'):
                yield (b['Name'], '')

    def get_cloud_trail_locations(self, buckets):
        session = local_session(self.manager.session_factory)
        client = session.client('cloudtrail')
        names = {b['Name'] for b in buckets}
        for t in client.describe_trails().get('trailList', ()):
            if t.get('S3BucketName') in names:
                yield (t['S3BucketName'], t.get('S3KeyPrefix', ''))

    def get_elb_bucket_locations(self):
        elbs = self.manager.get_resource_manager('elb').resources()
        get_elb_attrs = functools.partial(
            _query_elb_attrs, self.manager.session_factory)

        with self.executor_factory(max_workers=2) as w:
            futures = []
            for elb_set in chunks(elbs, 100):
                futures.append(w.submit(get_elb_attrs, elb_set))
            for f in as_completed(futures):
                if f.exception():
                    log.error("Error while scanning elb log targets: %s" % (
                        f.exception()))
                    continue
                for tgt in f.result():
                    yield tgt


def _query_elb_attrs(session_factory, elb_set):
    session = local_session(session_factory)
    client = session.client('elb')
    log_targets = []
    for e in elb_set:
        try:
            attrs = client.describe_load_balancer_attributes(
                LoadBalancerName=e['LoadBalancerName'])[
                    'LoadBalancerAttributes']
            if 'AccessLog' in attrs and attrs['AccessLog']['Enabled']:
                log_targets.append((
                    attrs['AccessLog']['S3BucketName'],
                    attrs['AccessLog']['S3BucketPrefix']))
        except Exception as err:
            log.warning(
                "Could not retrieve load balancer %s: %s" % (
                    e['LoadBalancerName'], err))
    return log_targets


@actions.register('remove-website-hosting')
class RemoveWebsiteHosting(BucketActionBase):
    """Action that removes website hosting configuration."""

    schema = type_schema('remove-website-hosting')

    permissions = ('s3:DeleteBucketWebsite',)

    def process(self, buckets):
        session = local_session(self.manager.session_factory)
        for bucket in buckets:
            client = bucket_client(session, bucket)
            client.delete_bucket_website(Bucket=bucket['Name'])


@actions.register('delete-global-grants')
class DeleteGlobalGrants(BucketActionBase):
    """Deletes global grants associated to a S3 bucket

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-delete-global-grants
                resource: s3
                filters:
                  - type: global-grants
                actions:
                  - delete-global-grants
    """

    schema = type_schema(
        'delete-global-grants',
        grantees={'type': 'array', 'items': {'type': 'string'}})

    permissions = ('s3:PutBucketAcl',)

    def process(self, buckets):
        with self.executor_factory(max_workers=5) as w:
            return list(filter(None, list(w.map(self.process_bucket, buckets))))

    def process_bucket(self, b):
        grantees = self.data.get(
            'grantees', [
                GlobalGrantsFilter.AUTH_ALL, GlobalGrantsFilter.GLOBAL_ALL])

        log.info(b)

        acl = b.get('Acl', {'Grants': []})
        if not acl or not acl['Grants']:
            return
        new_grants = []
        for grant in acl['Grants']:
            grantee = grant.get('Grantee', {})
            if not grantee:
                continue
            # Yuck, 'get_bucket_acl' doesn't return the grantee type.
            if 'URI' in grantee:
                grantee['Type'] = 'Group'
            else:
                grantee['Type'] = 'CanonicalUser'
            if ('URI' in grantee and
                grantee['URI'] in grantees and not
                    (grant['Permission'] == 'READ' and b['Website'])):
                # Remove this grantee.
                pass
            else:
                new_grants.append(grant)

        log.info({'Owner': acl['Owner'], 'Grants': new_grants})

        c = bucket_client(self.manager.session_factory(), b)
        try:
            c.put_bucket_acl(
                Bucket=b['Name'],
                AccessControlPolicy={
                    'Owner': acl['Owner'], 'Grants': new_grants})
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                return
        return b


@actions.register('tag')
class BucketTag(Tag):
    """Action to create tags on a S3 bucket

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-tag-region
                resource: s3
                region: us-east-1
                filters:
                  - "tag:RegionName": absent
                actions:
                  - type: tag
                    key: RegionName
                    value: us-east-1
    """

    def process_resource_set(self, client, resource_set, tags):
        modify_bucket_tags(self.manager.session_factory, resource_set, tags)


@actions.register('mark-for-op')
class MarkBucketForOp(TagDelayedAction):
    """Action schedules custodian to perform an action at a certain date

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-encrypt
                resource: s3
                filters:
                  - type: missing-statement
                    statement_ids:
                      - RequiredEncryptedPutObject
                actions:
                  - type: mark-for-op
                    op: attach-encrypt
                    days: 7
    """

    schema = type_schema(
        'mark-for-op', rinherit=TagDelayedAction.schema)


@actions.register('unmark')
@actions.register('remove-tag')
class RemoveBucketTag(RemoveTag):
    """Removes tag/tags from a S3 object

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-remove-owner-tag
                resource: s3
                filters:
                  - "tag:BucketOwner": present
                actions:
                  - type: remove-tag
                    tags: ['BucketOwner']
    """

    def process_resource_set(self, client, resource_set, tags):
        modify_bucket_tags(
            self.manager.session_factory, resource_set, remove_tags=tags)


@filters.register('data-events')
class DataEvents(Filter):
    """Find buckets for which CloudTrail is logging data events.

    Note that this filter only examines trails that are defined in the
    current account.
    """

    schema = type_schema('data-events', state={'enum': ['present', 'absent']})
    permissions = (
        'cloudtrail:DescribeTrails',
        'cloudtrail:GetEventSelectors')

    def get_event_buckets(self, session, trails):
        """Return a mapping of bucket name to cloudtrail.

        For wildcard trails the bucket name is ''.
        """
        regions = {t.get('HomeRegion') for t in trails}
        clients = {}
        for region in regions:
            clients[region] = session.client('cloudtrail', region_name=region)

        event_buckets = {}
        for t in trails:
            for events in clients[t.get('HomeRegion')].get_event_selectors(
                    TrailName=t['Name']).get('EventSelectors', ()):
                if 'DataResources' not in events:
                    continue
                for data_events in events['DataResources']:
                    if data_events['Type'] != 'AWS::S3::Object':
                        continue
                    for b in data_events['Values']:
                        event_buckets[b.rsplit(':')[-1].strip('/')] = t['Name']
        return event_buckets

    def process(self, resources, event=None):
        trails = self.manager.get_resource_manager('cloudtrail').resources()
        local_trails = self.filter_resources(
            trails,
            "split(':', TrailARN)[4]", (self.manager.account_id,)
        )
        session = local_session(self.manager.session_factory)
        event_buckets = self.get_event_buckets(session, local_trails)
        ops = {
            'present': lambda x: (
                x['Name'] in event_buckets or '' in event_buckets),
            'absent': (
                lambda x: x['Name'] not in event_buckets and ''
                not in event_buckets)}

        op = ops[self.data.get('state', 'present')]
        results = []
        for b in resources:
            if op(b):
                results.append(b)
        return results


@filters.register('inventory')
class Inventory(ValueFilter):
    """Filter inventories for a bucket"""
    schema = type_schema('inventory', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('s3:GetInventoryConfiguration',)

    def process(self, buckets, event=None):
        results = []
        with self.executor_factory(max_workers=2) as w:
            futures = {}
            for b in buckets:
                futures[w.submit(self.process_bucket, b)] = b

            for f in as_completed(futures):
                b = futures[f]
                if f.exception():
                    b.setdefault('c7n:DeniedMethods', []).append('GetInventoryConfiguration')
                    self.log.error(
                        "Error processing bucket: %s error: %s",
                        b['Name'], f.exception())
                    continue
                if f.result():
                    results.append(b)
        return results

    def process_bucket(self, b):
        if 'c7n:inventories' not in b:
            client = bucket_client(local_session(self.manager.session_factory), b)
            inventories = client.list_bucket_inventory_configurations(
                Bucket=b['Name']).get('InventoryConfigurationList', [])
            b['c7n:inventories'] = inventories

        for i in b['c7n:inventories']:
            if self.match(i):
                return True


@actions.register('set-inventory')
class SetInventory(BucketActionBase):
    """Configure bucket inventories for an s3 bucket.
    """
    schema = type_schema(
        'set-inventory',
        required=['name', 'destination'],
        state={'enum': ['enabled', 'disabled', 'absent']},
        name={'type': 'string', 'description': 'Name of inventory'},
        destination={'type': 'string', 'description': 'Name of destination bucket'},
        prefix={'type': 'string', 'description': 'Destination prefix'},
        encryption={'enum': ['SSES3', 'SSEKMS']},
        key_id={'type': 'string', 'description': 'Optional Customer KMS KeyId for SSE-KMS'},
        versions={'enum': ['All', 'Current']},
        schedule={'enum': ['Daily', 'Weekly']},
        format={'enum': ['CSV', 'ORC', 'Parquet']},
        fields={'type': 'array', 'items': {'enum': [
            'Size', 'LastModifiedDate', 'StorageClass', 'ETag',
            'IsMultipartUploaded', 'ReplicationStatus', 'EncryptionStatus',
            'ObjectLockRetainUntilDate', 'ObjectLockMode', 'ObjectLockLegalHoldStatus',
            'IntelligentTieringAccessTier', 'BucketKeyStatus', 'ChecksumAlgorithm',
            'ObjectAccessControlList', 'ObjectOwner']}})

    permissions = ('s3:PutInventoryConfiguration', 's3:GetInventoryConfiguration')

    def process(self, buckets):
        with self.executor_factory(max_workers=2) as w:
            futures = {w.submit(self.process_bucket, bucket): bucket for bucket in buckets}
            for future in as_completed(futures):
                bucket = futures[future]
                try:
                    future.result()
                except Exception as e:
                    self.log.error('Message: %s Bucket: %s', e, bucket['Name'])

    def process_bucket(self, b):
        inventory_name = self.data.get('name')
        destination = self.data.get('destination')
        prefix = self.data.get('prefix', '')
        schedule = self.data.get('schedule', 'Daily')
        fields = self.data.get('fields', ['LastModifiedDate', 'Size'])
        versions = self.data.get('versions', 'Current')
        state = self.data.get('state', 'enabled')
        encryption = self.data.get('encryption')
        inventory_format = self.data.get('format', 'CSV')

        if not prefix:
            prefix = "Inventories/%s" % (self.manager.config.account_id)

        client = bucket_client(local_session(self.manager.session_factory), b)
        if state == 'absent':
            try:
                client.delete_bucket_inventory_configuration(
                    Bucket=b['Name'], Id=inventory_name)
            except ClientError as e:
                if e.response['Error']['Code'] != 'NoSuchConfiguration':
                    raise
            return

        bucket = {
            'Bucket': "arn:aws:s3:::%s" % destination,
            'Format': inventory_format
        }

        inventory = {
            'Destination': {
                'S3BucketDestination': bucket
            },
            'IsEnabled': state == 'enabled' and True or False,
            'Id': inventory_name,
            'OptionalFields': fields,
            'IncludedObjectVersions': versions,
            'Schedule': {
                'Frequency': schedule
            }
        }

        if prefix:
            bucket['Prefix'] = prefix

        if encryption:
            bucket['Encryption'] = {encryption: {}}
            if encryption == 'SSEKMS' and self.data.get('key_id'):
                bucket['Encryption'] = {encryption: {
                    'KeyId': self.data['key_id']
                }}

        found = self.get_inventory_delta(client, inventory, b)
        if found:
            return
        if found is False:
            self.log.debug("updating bucket:%s inventory configuration id:%s",
                           b['Name'], inventory_name)
        client.put_bucket_inventory_configuration(
            Bucket=b['Name'], Id=inventory_name, InventoryConfiguration=inventory)

    def get_inventory_delta(self, client, inventory, b):
        inventories = client.list_bucket_inventory_configurations(Bucket=b['Name'])
        found = None
        for i in inventories.get('InventoryConfigurationList', []):
            if i['Id'] != inventory['Id']:
                continue
            found = True
            for k, v in inventory.items():
                if k not in i:
                    found = False
                    continue
                if isinstance(v, list):
                    v.sort()
                    i[k].sort()
                if i[k] != v:
                    found = False
        return found


@filters.register('intelligent-tiering')
class IntelligentTiering(ListItemFilter):
    """Filter for S3 buckets to look at intelligent tiering configurations

    The schema to supply to the attrs follows the schema here:
     https://botocore.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/list_bucket_intelligent_tiering_configurations.html

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-intelligent-tiering-configuration
                resource: s3
                filters:
                  - type: intelligent-tiering
                    attrs:
                      - Status: Enabled
                      - Filter:
                          And:
                            Prefix: test
                            Tags:
                              - Key: Owner
                                Value: c7n
                      - Tierings:
                          - Days: 100
                          - AccessTier: ARCHIVE_ACCESS

    """
    schema = type_schema(
        'intelligent-tiering',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )
    permissions = ('s3:GetIntelligentTieringConfiguration',)
    annotation_key = "c7n:IntelligentTiering"
    annotate_items = True

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.data['key'] = self.annotation_key

    def process(self, buckets, event=None):
        with self.executor_factory(max_workers=2) as w:
            futures = {w.submit(self.get_item_values, b): b for b in buckets}
            for future in as_completed(futures):
                b = futures[future]
                if future.exception():
                    self.log.error("Message: %s Bucket: %s", future.exception(), b['Name'])
                    continue
        return super().process(buckets, event)

    def get_item_values(self, b):
        if self.annotation_key not in b:
            client = bucket_client(local_session(self.manager.session_factory), b)
            try:
                int_tier_config = client.list_bucket_intelligent_tiering_configurations(
                    Bucket=b['Name'])
                b[self.annotation_key] = int_tier_config.get(
                    'IntelligentTieringConfigurationList', [])
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDenied':
                    method = 'list_bucket_intelligent_tiering_configurations'
                    log.warning(
                        "Bucket:%s unable to invoke method:%s error:%s ",
                          b['Name'], method, e.response['Error']['Message'])
                    b.setdefault('c7n:DeniedMethods', []).append(method)
        return b.get(self.annotation_key)


@actions.register('set-intelligent-tiering')
class ConfigureIntelligentTiering(BucketActionBase):
    """Action applies an intelligent tiering configuration to a S3 bucket

    The schema to supply to the configuration follows the schema here:
     https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_bucket_intelligent_tiering_configuration.html

    To delete a configuration, supply Status=delete with the either the Id or Id: matched

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-apply-intelligent-tiering-config
                resource: aws.s3
                filters:
                  - not:
                    - type: intelligent-tiering
                      attrs:
                        - Status: Enabled
                        - Filter:
                            And:
                              Prefix: helloworld
                              Tags:
                                - Key: Hello
                                  Value: World
                        - Tierings:
                          - Days: 123
                            AccessTier: ARCHIVE_ACCESS
                actions:
                  - type: set-intelligent-tiering
                    Id: c7n-default
                    IntelligentTieringConfiguration:
                      Id: c7n-default
                      Status: Enabled
                      Tierings:
                        - Days: 149
                          AccessTier: ARCHIVE_ACCESS

              - name: s3-delete-intelligent-tiering-configuration
                resource: aws.s3
                filters:
                  - type: intelligent-tiering
                    attrs:
                      - Status: Enabled
                      - Id: test-config
                actions:
                  - type: set-intelligent-tiering
                    Id: test-config
                    State: delete

              - name: s3-delete-intelligent-tiering-matched-configs
                resource: aws.s3
                filters:
                  - type: intelligent-tiering
                    attrs:
                      - Status: Enabled
                      - Id: test-config
                actions:
                  - type: set-intelligent-tiering
                    Id: matched
                    State: delete

    """

    annotation_key = 'c7n:ListItemMatches'
    shape = 'PutBucketIntelligentTieringConfigurationRequest'
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'oneOf': [
            {'required': ['type', 'Id', 'IntelligentTieringConfiguration']},
            {'required': ['type', 'Id', 'State']}],
        'properties': {
            'type': {'enum': ['set-intelligent-tiering']},
            'Id': {'type': 'string'},
            # delete intelligent tier configurations via state: delete
            'State': {'type': 'string', 'enum': ['delete']},
            'IntelligentTieringConfiguration': {'type': 'object'}
        },
    }

    permissions = ('s3:PutIntelligentTieringConfiguration',)

    def validate(self):
        # You can have up to 1,000 S3 Intelligent-Tiering configurations per bucket.
        # Hence, always use it with a filter
        found = False
        for f in self.manager.iter_filters():
            if isinstance(f, IntelligentTiering):
                found = True
                break
        if not found:
            raise PolicyValidationError(
                '`set-intelligent-tiering` may only be used in '
                'conjunction with `intelligent-tiering` filter on %s' % (self.manager.data,))
        cfg = dict(self.data)
        if 'IntelligentTieringConfiguration' in cfg:
            cfg['Bucket'] = 'bucket'
            cfg.pop('type')
            return shape_validate(
                cfg, self.shape, self.manager.resource_type.service)

    def process(self, buckets):
        with self.executor_factory(max_workers=3) as w:
            futures = {}

            for b in buckets:
                futures[w.submit(self.process_bucket, b)] = b

            for future in as_completed(futures):
                if future.exception():
                    bucket = futures[future]
                    self.log.error(
                      'error modifying bucket intelligent tiering configuration: %s\n%s',
                        bucket['Name'], future.exception())
                    continue

    def process_bucket(self, bucket):
        s3 = bucket_client(local_session(self.manager.session_factory), bucket)

        if 'list_bucket_intelligent_tiering_configurations' in bucket.get(
            'c7n:DeniedMethods', []):
            log.warning("Access Denied Bucket:%s while reading intelligent tiering configurations"
                        % bucket['Name'])
            return

        if self.data.get('Id') and self.data.get('IntelligentTieringConfiguration'):
            try:
                s3.put_bucket_intelligent_tiering_configuration(
                    Bucket=bucket['Name'], Id=self.data.get(
                      'Id'), IntelligentTieringConfiguration=self.data.get(
                        'IntelligentTieringConfiguration'))
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDenied':
                    log.warning(
                        "Access Denied Bucket:%s while applying intelligent tiering configuration"
                          % bucket['Name'])
        if self.data.get('State'):
            if self.data.get('Id') == 'matched':
                for config in bucket.get(self.annotation_key):
                    self.delete_intelligent_tiering_configurations(s3, config.get('Id'), bucket)
            else:
                self.delete_intelligent_tiering_configurations(s3, self.data.get('Id'), bucket)

    def delete_intelligent_tiering_configurations(self, s3_client, id, bucket):
        try:
            s3_client.delete_bucket_intelligent_tiering_configuration(Bucket=bucket['Name'], Id=id)
        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDenied':
                log.warning(
                    "Access Denied Bucket:%s while deleting intelligent tiering configuration"
                      % bucket['Name'])
            elif e.response['Error']['Code'] == 'NoSuchConfiguration':
                log.warning(
                  "No such configuration found:%s while deleting intelligent tiering configuration"
                    % bucket['Name'])


@actions.register('delete')
class DeleteBucket(ScanBucket):
    """Action deletes a S3 bucket

    :example:

    .. code-block:: yaml

            policies:
              - name: delete-unencrypted-buckets
                resource: s3
                filters:
                  - type: missing-statement
                    statement_ids:
                      - RequiredEncryptedPutObject
                actions:
                  - type: delete
                    remove-contents: true
    """

    schema = type_schema('delete', **{'remove-contents': {'type': 'boolean'}})

    permissions = ('s3:*',)

    bucket_ops = {
        'standard': {
            'iterator': 'list_objects',
            'contents_key': ['Contents'],
            'key_processor': 'process_key'
        },
        'versioned': {
            'iterator': 'list_object_versions',
            'contents_key': ['Versions', 'DeleteMarkers'],
            'key_processor': 'process_version'
        }
    }

    def process_delete_enablement(self, b):
        """Prep a bucket for deletion.

        Clear out any pending multi-part uploads.

        Disable versioning on the bucket, so deletes don't
        generate fresh deletion markers.
        """
        client = bucket_client(
            local_session(self.manager.session_factory), b)

        # Stop replication so we can suspend versioning
        if b.get('Replication') is not None:
            client.delete_bucket_replication(Bucket=b['Name'])

        # Suspend versioning, so we don't get new delete markers
        # as we walk and delete versions
        if (self.get_bucket_style(b) == 'versioned' and b['Versioning']['Status'] == 'Enabled' and
        self.data.get('remove-contents', True)):
            client.put_bucket_versioning(
                Bucket=b['Name'],
                VersioningConfiguration={'Status': 'Suspended'})

        # Clear our multi-part uploads
        uploads = client.get_paginator('list_multipart_uploads')
        for p in uploads.paginate(Bucket=b['Name']):
            for u in p.get('Uploads', ()):
                client.abort_multipart_upload(
                    Bucket=b['Name'],
                    Key=u['Key'],
                    UploadId=u['UploadId'])

    def process(self, buckets):
        # might be worth sanity checking all our permissions
        # on the bucket up front before disabling versioning/replication.
        if self.data.get('remove-contents', True):
            self._process_with_futures(self.process_delete_enablement, buckets)
            self.empty_buckets(buckets)

        results = self._process_with_futures(self.delete_bucket, buckets)
        self.write_denied_buckets_file()
        return results

    def delete_bucket(self, b):
        s3 = bucket_client(self.manager.session_factory(), b)
        try:
            self._run_api(s3.delete_bucket, Bucket=b['Name'])
        except ClientError as e:
            if e.response['Error']['Code'] == 'BucketNotEmpty':
                self.log.error(
                    "Error while deleting bucket %s, bucket not empty" % (
                        b['Name']))
            else:
                raise e

    def empty_buckets(self, buckets):
        t = time.time()
        results = super(DeleteBucket, self).process(buckets)
        run_time = time.time() - t
        object_count = 0

        for r in results:
            object_count += r['Count']
            self.manager.ctx.metrics.put_metric(
                "Total Keys", object_count, "Count", Scope=r['Bucket'],
                buffer=True)
        self.manager.ctx.metrics.put_metric(
            "Total Keys", object_count, "Count", Scope="Account", buffer=True)
        self.manager.ctx.metrics.flush()

        log.info(
            "EmptyBucket buckets:%d Complete keys:%d rate:%0.2f/s time:%0.2fs",
            len(buckets), object_count,
            float(object_count) / run_time if run_time else 0, run_time)
        return results

    def process_chunk(self, batch, bucket):
        s3 = bucket_client(local_session(self.manager.session_factory), bucket)
        objects = []
        for key in batch:
            obj = {'Key': key['Key']}
            if 'VersionId' in key:
                obj['VersionId'] = key['VersionId']
            objects.append(obj)
        results = s3.delete_objects(
            Bucket=bucket['Name'], Delete={'Objects': objects}).get('Deleted', ())
        if self.get_bucket_style(bucket) != 'versioned':
            return results


@actions.register('configure-lifecycle')
class Lifecycle(BucketActionBase):
    """Action applies a lifecycle policy to versioned S3 buckets

    The schema to supply to the rule follows the schema here:
     https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.put_bucket_lifecycle_configuration

    To delete a lifecycle rule, supply Status=absent

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-apply-lifecycle
                resource: s3
                actions:
                  - type: configure-lifecycle
                    rules:
                      - ID: my-lifecycle-id
                        Status: Enabled
                        Prefix: foo/
                        Transitions:
                          - Days: 60
                            StorageClass: GLACIER

    """

    schema = type_schema(
        'configure-lifecycle',
        **{
            'rules': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'required': ['ID', 'Status'],
                    'additionalProperties': False,
                    'properties': {
                        'ID': {'type': 'string'},
                        # c7n intercepts `absent`
                        'Status': {'enum': ['Enabled', 'Disabled', 'absent']},
                        'Prefix': {'type': 'string'},
                        'Expiration': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'Date': {'type': 'string'},  # Date
                                'Days': {'type': 'integer'},
                                'ExpiredObjectDeleteMarker': {'type': 'boolean'},
                            },
                        },
                        'Filter': {
                            'type': 'object',
                            'minProperties': 1,
                            'maxProperties': 1,
                            'additionalProperties': False,
                            'properties': {
                                'Prefix': {'type': 'string'},
                                'ObjectSizeGreaterThan': {'type': 'integer'},
                                'ObjectSizeLessThan': {'type': 'integer'},
                                'Tag': {
                                    'type': 'object',
                                    'required': ['Key', 'Value'],
                                    'additionalProperties': False,
                                    'properties': {
                                        'Key': {'type': 'string'},
                                        'Value': {'type': 'string'},
                                    },
                                },
                                'And': {
                                    'type': 'object',
                                    'additionalProperties': False,
                                    'properties': {
                                        'Prefix': {'type': 'string'},
                                        'ObjectSizeGreaterThan': {'type': 'integer'},
                                        'ObjectSizeLessThan': {'type': 'integer'},
                                        'Tags': {
                                            'type': 'array',
                                            'items': {
                                                'type': 'object',
                                                'required': ['Key', 'Value'],
                                                'additionalProperties': False,
                                                'properties': {
                                                    'Key': {'type': 'string'},
                                                    'Value': {'type': 'string'},
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        'Transitions': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'additionalProperties': False,
                                'properties': {
                                    'Date': {'type': 'string'},  # Date
                                    'Days': {'type': 'integer'},
                                    'StorageClass': {'type': 'string'},
                                },
                            },
                        },
                        'NoncurrentVersionTransitions': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'additionalProperties': False,
                                'properties': {
                                    'NoncurrentDays': {'type': 'integer'},
                                    'NewerNoncurrentVersions': {'type': 'integer'},
                                    'StorageClass': {'type': 'string'},
                                },
                            },
                        },
                        'NoncurrentVersionExpiration': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'NoncurrentDays': {'type': 'integer'},
                                'NewerNoncurrentVersions': {'type': 'integer'}
                            },
                        },
                        'AbortIncompleteMultipartUpload': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'DaysAfterInitiation': {'type': 'integer'},
                            },
                        },
                    },
                },
            },
        }
    )

    permissions = ('s3:GetLifecycleConfiguration', 's3:PutLifecycleConfiguration')

    def process(self, buckets):
        with self.executor_factory(max_workers=3) as w:
            futures = {}
            results = []

            for b in buckets:
                futures[w.submit(self.process_bucket, b)] = b

            for future in as_completed(futures):
                if future.exception():
                    bucket = futures[future]
                    self.log.error('error modifying bucket lifecycle: %s\n%s',
                                   bucket['Name'], future.exception())
                results += filter(None, [future.result()])

            return results

    def process_bucket(self, bucket):
        s3 = bucket_client(local_session(self.manager.session_factory), bucket)

        if 'get_bucket_lifecycle_configuration' in bucket.get('c7n:DeniedMethods', []):
            log.warning("Access Denied Bucket:%s while reading lifecycle" % bucket['Name'])
            return

        # Adjust the existing lifecycle by adding/deleting/overwriting rules as necessary
        config = (bucket.get('Lifecycle') or {}).get('Rules', [])
        for rule in self.data['rules']:
            for index, existing_rule in enumerate(config):
                if not existing_rule:
                    continue
                if rule['ID'] == existing_rule['ID']:
                    if rule['Status'] == 'absent':
                        config[index] = None
                    else:
                        config[index] = rule
                    break
            else:
                if rule['Status'] != 'absent':
                    config.append(rule)

        # The extra `list` conversion is required for python3
        config = list(filter(None, config))

        try:
            if not config:
                s3.delete_bucket_lifecycle(Bucket=bucket['Name'])
            else:
                s3.put_bucket_lifecycle_configuration(
                    Bucket=bucket['Name'], LifecycleConfiguration={'Rules': config})
        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDenied':
                log.warning("Access Denied Bucket:%s while applying lifecycle" % bucket['Name'])
            else:
                raise e


class KMSKeyResolverMixin:
    """Builds a dictionary of region specific ARNs"""

    def __init__(self, data, manager=None):
        self.arns = dict()
        self.data = data
        self.manager = manager

    def resolve_keys(self, buckets):
        key = self.data.get('key')
        if not key:
            return None

        regions = {get_region(b) for b in buckets}
        for r in regions:
            client = local_session(self.manager.session_factory).client('kms', region_name=r)
            try:
                key_meta = client.describe_key(
                    KeyId=key
                ).get('KeyMetadata', {})
                key_id = key_meta.get('KeyId')

                # We need a complete set of alias identifiers (names and ARNs)
                # to fully evaluate bucket encryption filters.
                key_aliases = client.list_aliases(
                    KeyId=key_id
                ).get('Aliases', [])

                self.arns[r] = {
                    'KeyId': key_id,
                    'Arn': key_meta.get('Arn'),
                    'KeyManager': key_meta.get('KeyManager'),
                    'Description': key_meta.get('Description'),
                    'Aliases': [
                        alias[attr]
                        for alias in key_aliases
                        for attr in ('AliasArn', 'AliasName')
                    ],
                }

            except ClientError as e:
                self.log.error('Error resolving kms ARNs for set-bucket-encryption: %s key: %s' % (
                    e, self.data.get('key')))

    def get_key(self, bucket):
        if 'key' not in self.data:
            return None
        region = get_region(bucket)
        key = self.arns.get(region)
        if not key:
            self.log.warning('Unable to resolve key %s for bucket %s in region %s',
                             self.data['key'], bucket.get('Name'), region)
        return key


@filters.register('bucket-encryption')
class BucketEncryption(KMSKeyResolverMixin, Filter):
    """Filters for S3 buckets that have bucket-encryption

    :example

    .. code-block:: yaml

            policies:
              - name: s3-bucket-encryption-AES256
                resource: s3
                region: us-east-1
                filters:
                  - type: bucket-encryption
                    state: True
                    crypto: AES256
              - name: s3-bucket-encryption-KMS
                resource: s3
                region: us-east-1
                filters:
                  - type: bucket-encryption
                    state: True
                    crypto: aws:kms
                    key: alias/some/alias/key
              - name: s3-bucket-encryption-off
                resource: s3
                region: us-east-1
                filters:
                  - type: bucket-encryption
                    state: False
              - name: s3-bucket-test-bucket-key-enabled
                resource: s3
                region: us-east-1
                filters:
                  - type: bucket-encryption
                    bucket_key_enabled: True
    """
    schema = type_schema('bucket-encryption',
                         state={'type': 'boolean'},
                         crypto={'type': 'string', 'enum': ['AES256', 'aws:kms']},
                         key={'type': 'string'},
                         bucket_key_enabled={'type': 'boolean'})

    permissions = ('s3:GetEncryptionConfiguration', 'kms:DescribeKey', 'kms:ListAliases')
    annotation_key = 'c7n:bucket-encryption'

    def validate(self):
        if self.data.get('bucket_key_enabled') is not None and self.data.get('key') is not None:
            raise PolicyValidationError(
                f'key and bucket_key_enabled attributes cannot both be set: {self.data}'
            )

    def process(self, buckets, event=None):
        self.resolve_keys(buckets)
        results = []
        with self.executor_factory(max_workers=2) as w:
            futures = {w.submit(self.process_bucket, b): b for b in buckets}
            for future in as_completed(futures):
                b = futures[future]
                if future.exception():
                    self.log.error("Message: %s Bucket: %s", future.exception(),
                                   b['Name'])
                    continue
                if future.result():
                    results.append(b)
        return results

    def process_bucket(self, b):

        client = bucket_client(local_session(self.manager.session_factory), b)
        rules = []
        if self.annotation_key not in b:
            try:
                be = client.get_bucket_encryption(Bucket=b['Name'])
                be.pop('ResponseMetadata', None)
            except ClientError as e:
                if e.response['Error']['Code'] != 'ServerSideEncryptionConfigurationNotFoundError':
                    raise
                be = {}
            b[self.annotation_key] = be
        else:
            be = b[self.annotation_key]

        rules = be.get('ServerSideEncryptionConfiguration', {}).get('Rules', [])
        # default `state` to True as previous impl assumed state == True
        # to preserve backwards compatibility
        if self.data.get('bucket_key_enabled'):
            for rule in rules:
                return self.filter_bucket_key_enabled(rule)
        elif self.data.get('bucket_key_enabled') is False:
            for rule in rules:
                return not self.filter_bucket_key_enabled(rule)

        if self.data.get('state', True):
            for sse in rules:
                return self.filter_bucket(b, sse)
            return False
        else:
            for sse in rules:
                return not self.filter_bucket(b, sse)
            return True

    def filter_bucket(self, b, sse):
        allowed = ['AES256', 'aws:kms']
        key = self.get_key(b)
        crypto = self.data.get('crypto')
        rule = sse.get('ApplyServerSideEncryptionByDefault')

        if not rule:
            return False
        algo = rule.get('SSEAlgorithm')

        if not crypto and algo in allowed:
            return True

        if crypto == 'AES256' and algo == 'AES256':
            return True
        elif crypto == 'aws:kms' and algo == 'aws:kms':
            if not key:
                # There are two broad reasons to have an empty value for
                # the regional key here:
                #
                # * The policy did not specify a key, in which case this
                #   filter should match _all_ buckets with a KMS default
                #   encryption rule.
                #
                # * The policy specified a key that could not be
                #   resolved, in which case this filter shouldn't match
                #   any buckets.
                return 'key' not in self.data

            # The default encryption rule can specify a key ID,
            # key ARN, alias name or alias ARN. Match against any of
            # those attributes. A rule specifying KMS with no master key
            # implies the AWS-managed key.
            key_ids = {key.get('Arn'), key.get('KeyId'), *key['Aliases']}
            return rule.get('KMSMasterKeyID', 'alias/aws/s3') in key_ids

    def filter_bucket_key_enabled(self, rule) -> bool:
        if not rule:
            return False
        return rule.get('BucketKeyEnabled')


@actions.register('set-bucket-encryption')
class SetBucketEncryption(KMSKeyResolverMixin, BucketActionBase):
    """Action enables default encryption on S3 buckets

    `enabled`: boolean Optional: Defaults to True

    `crypto`: aws:kms | AES256` Optional: Defaults to AES256

    `key`: arn, alias, or kms id key

    `bucket-key`: boolean Optional:
    Defaults to True.
    Reduces amount of API traffic from Amazon S3 to KMS and can reduce KMS request
    costsby up to 99 percent. Requires kms:Decrypt permissions for copy and upload
    on the AWS KMS Key Policy.

    Bucket Key Docs: https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-key.html

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-enable-default-encryption-kms
                resource: s3
                actions:
                  - type: set-bucket-encryption
                  # enabled: true <------ optional (true by default)
                    crypto: aws:kms
                    key: 1234abcd-12ab-34cd-56ef-1234567890ab
                    bucket-key: true

              - name: s3-enable-default-encryption-kms-alias
                resource: s3
                actions:
                  - type: set-bucket-encryption
                  # enabled: true <------ optional (true by default)
                    crypto: aws:kms
                    key: alias/some/alias/key
                    bucket-key: true

              - name: s3-enable-default-encryption-aes256
                resource: s3
                actions:
                  - type: set-bucket-encryption
                  # bucket-key: true <--- optional (true by default for AWS SSE)
                  # crypto: AES256 <----- optional (AES256 by default)
                  # enabled: true <------ optional (true by default)

              - name: s3-disable-default-encryption
                resource: s3
                actions:
                  - type: set-bucket-encryption
                    enabled: false
    """

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['set-bucket-encryption']},
            'enabled': {'type': 'boolean'},
            'crypto': {'enum': ['aws:kms', 'AES256']},
            'key': {'type': 'string'},
            'bucket-key': {'type': 'boolean'}
        },
        'dependencies': {
            'key': {
                'properties': {
                    'crypto': {'pattern': 'aws:kms'}
                },
                'required': ['crypto']
            }
        }
    }

    permissions = ('s3:PutEncryptionConfiguration', 's3:GetEncryptionConfiguration',
                   'kms:ListAliases', 'kms:DescribeKey')

    def process(self, buckets):
        if self.data.get('enabled', True):
            self.resolve_keys(buckets)

        with self.executor_factory(max_workers=3) as w:
            futures = {w.submit(self.process_bucket, b): b for b in buckets}
            for future in as_completed(futures):
                if future.exception():
                    self.log.error('Message: %s Bucket: %s', future.exception(),
                                   futures[future]['Name'])

    def process_bucket(self, bucket):
        default_key_desc = 'Default master key that protects my S3 objects when no other key is defined' # noqa
        s3 = bucket_client(local_session(self.manager.session_factory), bucket)
        if not self.data.get('enabled', True):
            s3.delete_bucket_encryption(Bucket=bucket['Name'])
            return
        algo = self.data.get('crypto', 'AES256')

        # bucket key defaults to True for alias/aws/s3 and AES256 (Amazon SSE)
        # and ignores False values for that crypto
        bucket_key = self.data.get('bucket-key', True)
        config = {
            'Rules': [
                {
                    'ApplyServerSideEncryptionByDefault': {
                        'SSEAlgorithm': algo,
                    },
                    'BucketKeyEnabled': bucket_key
                }
            ]
        }

        if algo == 'aws:kms':
            key = self.get_key(bucket)
            if not key:
                raise Exception('Valid KMS Key required but does not exist')

            config['Rules'][0]['ApplyServerSideEncryptionByDefault']['KMSMasterKeyID'] = key['Arn']
        s3.put_bucket_encryption(
            Bucket=bucket['Name'],
            ServerSideEncryptionConfiguration=config
        )


OWNERSHIP_CONTROLS = ['BucketOwnerEnforced', 'BucketOwnerPreferred', 'ObjectWriter']
VALUE_FILTER_MAGIC_VALUES = ['absent', 'present', 'not-null', 'empty']


@filters.register('ownership')
class BucketOwnershipControls(BucketFilterBase, ValueFilter):
    """Filter for object ownership controls

    Reference: https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership.html

    :example

    Find buckets with ACLs disabled

    .. code-block:: yaml

            policies:
              - name: s3-bucket-acls-disabled
                resource: aws.s3
                region: us-east-1
                filters:
                  - type: ownership
                    value: BucketOwnerEnforced

    :example

    Find buckets with object ownership preferred or enforced

    .. code-block:: yaml

            policies:
              - name: s3-bucket-ownership-preferred
                resource: aws.s3
                region: us-east-1
                filters:
                  - type: ownership
                    op: in
                    value:
                      - BucketOwnerEnforced
                      - BucketOwnerPreferred

    :example

    Find buckets with no object ownership controls

    .. code-block:: yaml

            policies:
              - name: s3-bucket-no-ownership-controls
                resource: aws.s3
                region: us-east-1
                filters:
                  - type: ownership
                    value: empty
    """
    schema = type_schema('ownership', rinherit=ValueFilter.schema, value={'oneOf': [
        {'type': 'string', 'enum': OWNERSHIP_CONTROLS + VALUE_FILTER_MAGIC_VALUES},
        {'type': 'array', 'items': {
            'type': 'string', 'enum': OWNERSHIP_CONTROLS + VALUE_FILTER_MAGIC_VALUES}}]})
    permissions = ('s3:GetBucketOwnershipControls',)
    annotation_key = 'c7n:ownership'

    def __init__(self, data, manager=None):
        super(BucketOwnershipControls, self).__init__(data, manager)

        # Ownership controls appear as an array of rules. There can only be one
        # ObjectOwnership rule defined for a bucket, so we can automatically
        # match against that if it exists.
        self.data['key'] = f'("{self.annotation_key}".Rules[].ObjectOwnership)[0]'

    def process(self, buckets, event=None):
        with self.executor_factory(max_workers=2) as w:
            futures = {w.submit(self.process_bucket, b): b for b in buckets}
            for future in as_completed(futures):
                b = futures[future]
                if future.exception():
                    self.log.error("Message: %s Bucket: %s", future.exception(),
                                   b['Name'])
                    continue
        return super(BucketOwnershipControls, self).process(buckets, event)

    def process_bucket(self, b):
        if self.annotation_key in b:
            return
        client = bucket_client(local_session(self.manager.session_factory), b)
        try:
            controls = client.get_bucket_ownership_controls(Bucket=b['Name'])
            controls.pop('ResponseMetadata', None)
        except ClientError as e:
            if e.response['Error']['Code'] != 'OwnershipControlsNotFoundError':
                raise
            controls = {}
        b[self.annotation_key] = controls.get('OwnershipControls')


@filters.register('bucket-replication')
class BucketReplication(ListItemFilter):
    """Filter for S3 buckets to look at bucket replication configurations

    The schema to supply to the attrs follows the schema here:
     https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/get_bucket_replication.html

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-bucket-replication
                resource: s3
                filters:
                  - type: bucket-replication
                    attrs:
                      - Status: Enabled
                      - Filter:
                          And:
                            Prefix: test
                            Tags:
                              - Key: Owner
                                Value: c7n
                      - ExistingObjectReplication: Enabled

    """
    schema = type_schema(
        'bucket-replication',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    permissions = ("s3:GetReplicationConfiguration",)
    annotation_key = 'Replication'
    annotate_items = True

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.data['key'] = self.annotation_key

    def get_item_values(self, b):
        client = bucket_client(local_session(self.manager.session_factory), b)
        # replication configuration is called in S3_AUGMENT_TABLE:
        bucket_replication = b.get(self.annotation_key)

        rules = []
        if bucket_replication is not None:
            rules = bucket_replication.get('ReplicationConfiguration', {}).get('Rules', [])
            for replication in rules:
                self.augment_bucket_replication(b, replication, client)

        return rules

    def augment_bucket_replication(self, b, replication, client):
        destination_bucket = replication.get('Destination').get('Bucket').split(':')[5]
        try:
            destination_region = inspect_bucket_region(destination_bucket, client.meta.endpoint_url)
        except ValueError:
            replication['DestinationBucketAvailable'] = False
            return
        source_region = get_region(b)
        replication['DestinationBucketAvailable'] = True
        replication['DestinationRegion'] = destination_region
        replication['CrossRegion'] = destination_region != source_region


@resources.register('s3-directory')
class S3Directory(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 's3'
        permission_prefix = "s3express"
        arn_service = "s3express"
        arn_type = 'bucket'
        enum_spec = ('list_directory_buckets', 'Buckets[]', None)
        name = id = 'Name'
        date = 'CreationDate'
        dimension = 'BucketName'
        cfn_type = 'AWS::S3Express::DirectoryBucket'
        permissions_enum = ("s3express:ListAllMyDirectoryBuckets",)
