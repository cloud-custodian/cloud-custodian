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
from __future__ import absolute_import, division, print_function, unicode_literals

import functools
import json
import itertools
import logging
import math
import os
import time
import ssl

from botocore.client import Config
from botocore.exceptions import ClientError
from botocore.vendored.requests.exceptions import SSLError
from concurrent.futures import as_completed

from c7n.actions import ActionRegistry, BaseAction, AutoTagUser, PutMetric
from c7n.filters import (
    FilterRegistry, Filter, CrossAccountAccessFilter, MetricsFilter)
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import (
    chunks, local_session, set_annotation, type_schema, dumps)


log = logging.getLogger('custodian.s3')

filters = FilterRegistry('s3.filters')
actions = ActionRegistry('s3.actions')
filters.register('marked-for-op', TagActionFilter)
actions.register('auto-tag-user', AutoTagUser)
actions.register('put-metric', PutMetric)

MAX_COPY_SIZE = 1024 * 1024 * 1024 * 2


@resources.register('s3')
class S3(QueryResourceManager):

    class resource_type(object):
        service = 's3'
        type = 'bucket'
        enum_spec = ('list_buckets', 'Buckets[]', None)
        detail_spec = ('list_objects', 'Bucket', 'Contents[]')
        name = id = 'Name'
        filter_name = None
        date = 'CreationDate'
        dimension = 'BucketName'
        config_type = 'AWS::S3::Bucket'

    filter_registry = filters
    action_registry = actions

    def __init__(self, ctx, data):
        super(S3, self).__init__(ctx, data)
        self.log_dir = ctx.log_dir

    @classmethod
    def get_permissions(cls):
        perms = ["s3:ListAllMyBuckets"]
        perms.extend([n[0] for n in S3_AUGMENT_TABLE])
        return perms

    def augment(self, buckets):
        with self.executor_factory(
                max_workers=min((10, len(buckets) + 1))) as w:
            results = w.map(
                assemble_bucket,
                zip(itertools.repeat(self.session_factory), buckets))
            results = filter(None, results)
            return results


S3_AUGMENT_TABLE = (
    ('get_bucket_location', 'Location', None, None),
    ('get_bucket_tagging', 'Tags', [], 'TagSet'),
    ('get_bucket_policy', 'Policy', None, 'Policy'),
    ('get_bucket_acl', 'Acl', None, None),
    ('get_bucket_replication', 'Replication', None, None),
    ('get_bucket_versioning', 'Versioning', None, None),
    ('get_bucket_website', 'Website', None, None),
    ('get_bucket_logging', 'Logging', None, 'LoggingEnabled'),
    ('get_bucket_notification_configuration', 'Notification', None, None),
    ('get_bucket_lifecycle', 'Lifecycle', None, None),
    #        ('get_bucket_cors', 'Cors'),
)


def assemble_bucket(item):
    """Assemble a document representing all the config state around a bucket.

    TODO: Refactor this, the logic here feels quite muddled.
    """
    factory, b = item
    s = factory()
    c = s.client('s3')
    # Bucket Location, Current Client Location, Default Location
    b_location = c_location = location = "us-east-1"
    methods = list(S3_AUGMENT_TABLE)
    for m, k, default, select in methods:
        try:
            method = getattr(c, m)
            v = method(Bucket=b['Name'])
            v.pop('ResponseMetadata')
            if select is not None and select in v:
                v = v[select]
        except (ssl.SSLError, SSLError) as e:
            # Proxy issues? i assume
            log.warning("Bucket ssl error %s: %s %s",
                        b['Name'], b.get('Location', 'unknown'),
                        e)
            continue
        except ClientError as e:
            code = e.response['Error']['Code']
            if code.startswith("NoSuch") or "NotFound" in code:
                v = default
            elif code == 'PermanentRedirect':
                s = factory()
                c = bucket_client(s, b)
                # Requeue with the correct region given location constraint
                methods.append((m, k, default, select))
                continue
            else:
                log.warning(
                    "Bucket:%s unable to invoke method:%s error:%s ",
                    b['Name'], m, e.response['Error']['Message'])
                # We don't bail out, continue processing if we can.
                # Note this can lead to missing data, but in general is cleaner than
                # failing hard.
                continue
        # As soon as we learn location (which generally works)
        if k == 'Location' and v is not None:
            b_location = v.get('LocationConstraint')
            # Location == region for all cases but EU per https://goo.gl/iXdpnl
            if b_location is None:
                b_location = "us-east-1"
            elif b_location == 'EU':
                b_location = "eu-west-1"
                v['LocationConstraint'] = 'eu-west-1'
            if v and v != c_location:
                c = s.client('s3', region_name=b_location)
            elif c_location != location:
                c = s.client('s3', region_name=location)
        b[k] = v
    return b


def bucket_client(session, b, kms=False):
    location = b.get('Location')
    if location is None:
        region = 'us-east-1'
    else:
        region = location['LocationConstraint'] or 'us-east-1'

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
        # all the tag marshalling back and forth is a bit gross :-(
        new_tags = {t['Key']: t['Value'] for t in add_tags}
        for t in bucket.get('Tags', ()):
            if (t['Key'] not in new_tags and
                    not t['Key'].startswith('aws') and
                    t['Key'] not in remove_tags):
                new_tags[t['Key']] = t['Value']
        tag_set = [{'Key': k, 'Value': v} for k, v in new_tags.items()]
        try:
            client.put_bucket_tagging(
                Bucket=bucket['Name'], Tagging={'TagSet': tag_set})
        except ClientError as e:
            log.exception(
                'Exception tagging bucket %s: %s', bucket['Name'], e)
            continue


@filters.register('metrics')
class S3Metrics(MetricsFilter):
    """S3 CW Metrics need special handling for attribute/dimension
    mismatch, and additional required dimension.
    """

    def get_dimensions(self, resource):
        return [
            {'Name': 'BucketName',
             'Value': resource['Name']},
            {'Name': 'StorageType',
             'Value': 'AllStorageTypes'}]


@filters.register('cross-account')
class S3CrossAccountFilter(CrossAccountAccessFilter):
    """Filters cross-account access to S3 buckets

    :example:

        .. code-block: yaml

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

        ELB Accounts by region http://goo.gl/a8MXxd

        Redshift Accounts by region https://goo.gl/MKWPTT

        Cloudtrail Accounts by region https://goo.gl/kWQk9D
        """
        accounts = super(S3CrossAccountFilter, self).get_accounts()
        return accounts.union(
            [
                # ELB accounts
                '127311923021',  # us-east-1
                '033677994240',  # us-east-2
                '797873946194',  # us-west-2
                '027434742980',  # us-west-1
                '985666609251',  # ca-central-1
                '156460612806',  # eu-west-1
                '054676820928',  # eu-central-1
                '652711504416',  # eu-west-2
                '582318560864',  # ap-northeast-1
                '600734575887',  # ap-northeast-2
                '114774131450',  # ap-southeast-1
                '783225319266',  # ap-southeast-2
                '718504428378',  # ap-south-1
                '507241528517',  # sa-east-1
                '048591011584',  # us-gov-west-1 or gov-cloud-1
                '638102146993',  # cn-north-1

                # Redshift accounts
                '368064434614',  # us-east-1
                '790247189693',  # us-east-2
                '703715109447',  # us-east-1
                '473191095985',  # us-west-2
                '408097707231',  # ap-south-1
                '713597048934',  # ap-northeast-2
                '960118270566',  # ap-southeast-1
                '485979073181',  # ap-southeast-2
                '615915377779',  # ap-northeast-1
                '764870610256',  # ca-central-1
                '434091160558',  # eu-central-1
                '246478207311',  # eu-west-1
                '885798887673',  # eu-west-2
                '392442076723',  # sa-east-1

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

    :example:

        .. code-block: yaml

            policies:
              - name: s3-delete-global-grants
                resource: s3
                filters:
                  - type: global-grants
                actions:
                  - delete-global-grants
    """

    schema = type_schema('global-grants', permissions={
        'type': 'array', 'items': {
            'type': 'string', 'enum': [
                'READ', 'WRITE', 'WRITE_ACP', 'READ', 'READ_ACP']}})

    GLOBAL_ALL = "http://acs.amazonaws.com/groups/global/AllUsers"
    AUTH_ALL = "http://acs.amazonaws.com/groups/global/AuthenticatedUsers"

    def process(self, buckets, event=None):
        with self.executor_factory(max_workers=5) as w:
            results = w.map(self.process_bucket, buckets)
            results = filter(None, list(results))
            return results

    def process_bucket(self, b):
        acl = b.get('Acl', {'Grants': []})
        if not acl or not acl['Grants']:
            return
        results = []
        perms = self.data.get('permissions', [])
        for grant in acl['Grants']:
            if 'URI' not in grant.get("Grantee", {}):
                continue
            if grant['Grantee']['URI'] not in [self.AUTH_ALL, self.GLOBAL_ALL]:
                continue
            if grant['Permission'] == 'READ' and b['Website']:
                continue
            if not perms or (perms and grant['Permission'] in perms):
                results.append(grant['Permission'])

        if results:
            set_annotation(b, 'GlobalPermissions', results)
            return b


class BucketActionBase(BaseAction):

    def get_permissions(self):
        return self.permissions


@filters.register('has-statement')
class HasStatementFilter(Filter):
    """Find buckets with set of named policy statements.

    :example:

        .. code-block: yaml

            policies:
              - name: s3-bucket-has-statement
                resource: s3
                filters:
                  - type: has-statement
                    statement_ids:
                      - RequiredEncryptedPutObject
    """
    schema = type_schema(
        'has-statement',
        statement_ids={'type': 'array', 'items': {'type': 'string'}})

    def process(self, buckets, event=None):
        return filter(None, map(self.process_bucket, buckets))

    def process_bucket(self, b):
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
            return b
        return None


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

        .. code-block: yaml

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
        return filter(None, map(self.process_bucket, buckets))

    def process_bucket(self, b):
        p = b.get('Policy')
        if p is None:
            return b
        p = json.loads(p)
        encryption_statement = ENCRYPTION_STATEMENT_GLOB

        statements = p.get('Statement', [])
        check = False
        for s in list(statements):
            try:
                encryption_statement["Sid"] = s["Sid"]
            except:
                log.info("Bucket:%s doesn't have Sid" % b['Name'])

            encryption_statement["Resource"] = s["Resource"]
            if s == encryption_statement:
                log.info(
                    "Bucket:%s contains correct encryption policy", b['Name'])
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

        .. code-block: yaml

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


@actions.register('no-op')
class NoOp(BucketActionBase):

    schema = type_schema('no-op')
    permissions = ('s3:ListAllMyBuckets',)

    def process(self, buckets):
        return None


@actions.register('remove-statements')
class RemovePolicyStatement(BucketActionBase):
    """Action to remove policy statements from S3 buckets

    :example:

        .. code-block: yaml

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

    schema = type_schema(
        'remove-statements',
        statement_ids={'type': 'array', 'items': {'type': 'string'}})
    permissions = ("s3:PutBucketPolicy", "s3:DeleteBucketPolicy")

    def process(self, buckets):
        with self.executor_factory(max_workers=3) as w:
            results = w.map(self.process_bucket, buckets)
            return filter(None, list(results))

    def process_bucket(self, bucket):
        p = bucket.get('Policy')
        if p is None:
            return
        else:
            p = json.loads(p)

        statements = p.get('Statement', [])
        found = []
        for s in list(statements):
            if s['Sid'] in self.data['statement_ids']:
                found.append(s)
                statements.remove(s)
        if not found:
            return

        s3 = bucket_client(local_session(self.manager.session_factory), bucket)
        if not statements:
            s3.delete_bucket_policy(Bucket=bucket['Name'])
        else:
            s3.put_bucket_policy(Bucket=bucket['Name'], Policy=json.dumps(p))
        return {'Name': bucket['Name'], 'State': 'PolicyRemoved', 'Statements': found}


@actions.register('toggle-versioning')
class ToggleVersioning(BucketActionBase):
    """Action to enable/suspend versioning on a S3 bucket

    Note versioning can never be disabled only suspended.

    :example:

        .. code-block: yaml

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

    # mfa delete enablement looks like it needs the serial and a current token.
    def process(self, resources):
        enabled = self.data.get('enabled', True)

        for r in resources:
            client = bucket_client(
                local_session(self.manager.session_factory), r)
            if 'Versioning' not in r or not r['Versioning']:
                r['Versioning'] = {'Status': 'Suspended'}
            if enabled and (
                    r['Versioning']['Status'] == 'Suspended'):
                client.put_bucket_versioning(
                    Bucket=r['Name'],
                    VersioningConfiguration={
                        'Status': 'Enabled'})
                continue
            if not enabled and r['Versioning']['Status'] == 'Enabled':
                client.put_bucket_versioning(
                    Bucket=r['Name'],
                    VersioningConfiguration={'Status': 'Suspended'})


@actions.register('toggle-logging')
class ToggleLogging(BucketActionBase):
    """Action to enable/disable logging on a S3 bucket.

    Target bucket ACL must allow for WRITE and READ_ACP Permissions
    Not specifying a target_prefix will default to the current bucket name.
    http://goo.gl/PiWWU2

    :example:

        .. code-block: yaml

            policies:
              - name: s3-enable-logging
                resource: s3
                filter:
                  - "tag:Testing": present
                actions:
                  - type: toggle-logging
                    target_bucket: log-bucket
                    target_prefix: logs123
    """

    schema = type_schema(
        'toggle-logging',
        enabled={'type': 'boolean'},
        target_bucket={'type': 'string'},
        target_prefix={'type': 'string'})
    permissions = ("s3:PutBucketLogging",)

    def process(self, resources):
        enabled = self.data.get('enabled', True)

        for r in resources:
            client = bucket_client(local_session(self.manager.session_factory), r)
            target_prefix = self.data.get('target_prefix', r['Name'])
            if 'TargetBucket' in r['Logging']:
                r['Logging'] = {'Status': 'Enabled'}
            else:
                r['Logging'] = {'Status': 'Disabled'}
            if enabled and (r['Logging']['Status'] == 'Disabled'):
                client.put_bucket_logging(
                    Bucket=r['Name'],
                    BucketLoggingStatus={
                        'LoggingEnabled': {
                            'TargetBucket': self.data.get('target_bucket'),
                            'TargetPrefix': target_prefix}})
                continue
            if not enabled and r['Logging']['Status'] == 'Enabled':
                client.put_bucket_logging(
                    Bucket=r['Name'],
                    BucketLoggingStatus={})
                continue


@actions.register('attach-encrypt')
class AttachLambdaEncrypt(BucketActionBase):
    """Action attaches lambda encryption policy to S3 bucket

    supports attachment via lambda bucket notification or sns notification
    to invoke lambda. a special topic value of `default` will utilize
    an extant notification or create one matching the bucket name.

    :example:

        .. code-block: yaml

            policies:
              - name: s3-logging-buckets
                resource: s3
                filters:
                  - type: missing-policy-statement
                actions:
                  - attach-encrypt
    """
    schema = type_schema(
        'attach-encrypt',
        role={'type': 'string'},
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
            raise ValueError(
                "attach-encrypt: role must be specified either "
                "via assume or in config")

        return self

    def process(self, buckets):
        from c7n.mu import LambdaManager
        from c7n.ufuncs.s3crypt import get_function

        account_id = self.manager.config.account_id
        topic_arn = self.data.get('topic')

        func = get_function(
            None, self.data.get('role', self.manager.config.assume_role),
            bool(topic_arn), account_id=account_id)

        regions = set([
            b.get('Location', {
                'LocationConstraint': 'us-east-1'})['LocationConstraint']
            for b in buckets])

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
                region = b.get('Location', {
                    'LocationConstraint': 'us-east-1'}).get(
                        'LocationConstraint')
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
            return filter(None, results)

    def process_bucket(self, func, bucket, topic, account_id, session_factory):
        from c7n.mu import BucketSNSNotification, BucketLambdaNotification
        if topic:
            topic = None if topic == 'default' else topic
            source = BucketSNSNotification(session_factory, bucket, topic)
        else:
            source = BucketLambdaNotification(
                {'account_s3': account_id}, session_factory, bucket)
        return source.add(func)


@actions.register('encryption-policy')
class EncryptionRequiredPolicy(BucketActionBase):
    """Action to apply an encryption policy to S3 buckets

    :example:

        .. code-block: yaml

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
            results = filter(None, list(results))
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


class BucketScanLog(object):
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
        if self.denied_buckets and self.manager.log_dir:
            with open(
                    os.path.join(
                        self.manager.log_dir, 'denied.json'), 'w') as fh:
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

        with BucketScanLog(self.manager.log_dir, b['Name']) as key_log:
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

        .. code-block: yaml

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
            float(object_count) / run_time,
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

        # If the data is already encrypted with KMS and the same key is provided
        # then we don't need to do anything
        if info.get('ServerSideEncryption') == 'aws:kms' and self.kms_id:
            # Test using `in` because SSEKMSKeyId is the full ARN
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
        ongoing, avail = restore.split(',', 1)
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

        .. code-block: yaml

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
            if b['Logging']:
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
        names = set([b['Name'] for b in buckets])
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

        .. code-block: yaml

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
            return filter(None, list(w.map(self.process_bucket, buckets)))

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

        .. code-block: yaml

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

    def process_resource_set(self, resource_set, tags):
        modify_bucket_tags(self.manager.session_factory, resource_set, tags)


@actions.register('mark-for-op')
class MarkBucketForOp(TagDelayedAction):
    """Action schedules custodian to perform an action at a certain date

    :example:

        .. code-block: yaml

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

    def process_resource_set(self, resource_set, tags):
        modify_bucket_tags(self.manager.session_factory, resource_set, tags)


@actions.register('unmark')
class RemoveBucketTag(RemoveTag):
    """Removes tag/tags from a S3 object

    :example:

        .. code-block: yaml

            policies:
              - name: s3-remove-owner-tag
                resource: s3
                filters:
                  - "tag:BucketOwner": present
                actions:
                  - type: unmark
                    tags: ['BucketOwner']
    """

    schema = type_schema(
        'unmark', aliases=('remove-tag'), tags={'type': 'array'})

    def process_resource_set(self, resource_set, tags):
        modify_bucket_tags(
            self.manager.session_factory, resource_set, remove_tags=tags)


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
        versions={'enum': ['All', 'Current']},
        schedule={'enum': ['Daily', 'Weekly']},
        fields={'type': 'array', 'items': {'enum': [
            'Size', 'LastModifiedDate', 'StorageClass', 'ETag',
            'IsMultipartUploaded', 'ReplicationStatus']}})

    permissions = ('s3:PutInventoryConfiguration', 's3:GetInventoryConfiguration')

    def process(self, buckets):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_bucket, buckets))

    def process_bucket(self, b):
        inventory_name = self.data.get('name')
        destination = self.data.get('destination')
        prefix = self.data.get('prefix', '')
        schedule = self.data.get('schedule', 'Daily')
        fields = self.data.get('fields', ['LastModifiedDate', 'Size'])
        versions = self.data.get('versions', 'Current')
        state = self.data.get('state', 'enabled')

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

        inventory = {
            'Destination': {
                'S3BucketDestination': {
                    'Bucket': "arn:aws:s3:::%s" % destination,
                    'Format': 'CSV'}
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
            inventory['Destination']['S3BucketDestination']['Prefix'] = prefix

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


@actions.register('delete')
class DeleteBucket(ScanBucket):
    """Action deletes a S3 bucket

    :example:

        .. code-block: yaml

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
            float(object_count) / run_time, run_time)
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
