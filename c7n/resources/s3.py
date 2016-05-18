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
from botocore.client import Config
from botocore.exceptions import ClientError
from concurrent.futures import as_completed

import functools
import json
import itertools
import logging
import os
import time

from c7n import executor
from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry, Filter
from c7n.manager import ResourceManager, resources
from c7n.utils import chunks, local_session, set_annotation, type_schema

"""
TODO:
 - How does replication status effect in place encryption.
 - Test glacier support
"""

log = logging.getLogger('custodian.s3')

filters = FilterRegistry('s3.filters')
actions = ActionRegistry('s3.actions')


@resources.register('s3')
class S3(ResourceManager):

    executor_factory = executor.ThreadPoolExecutor
    filter_registry = filters
    action_registry = actions

    def __init__(self, ctx, data):
        super(S3, self).__init__(ctx, data)
        self.log_dir = ctx.log_dir

    def get_resources(self, resource_ids):
        with self.executor_factory(
                max_workers=min((5, len(resource_ids)))) as w:
            buckets = {'Name': r for r in resource_ids}
            results = w.map(
                assemble_bucket,
                zip(itertools.repeat(self.session_factory), buckets))
            results = filter(None, results)
        return results

    def resources(self):
        if self._cache.load():
            buckets = self._cache.get({'resource': 's3'})
            if buckets is not None:
                log.info("Using cached s3 buckets")
                return self.filter_resources(buckets)

        c = self.session_factory().client('s3')
        log.debug('Retrieving buckets')
        response = c.list_buckets()
        buckets = response['Buckets']
        log.debug('Got %d buckets' % len(buckets))
        log.debug('Assembling bucket documents')
        with self.executor_factory(max_workers=10) as w:
            results = w.map(
                assemble_bucket,
                zip(itertools.repeat(self.session_factory), buckets))
            results = filter(None, results)

        self._cache.save({'resource': 's3'}, results)
        return self.filter_resources(results)


S3_AUGMENT_TABLE = (
    ('get_bucket_location', 'Location', None, None),
    ('get_bucket_tagging', 'Tags', [], 'TagSet'),
    ('get_bucket_policy',  'Policy', None, None),
    ('get_bucket_acl', 'Acl', None, None),
    ('get_bucket_replication', 'Replication', None, None),
    ('get_bucket_versioning', 'Versioning', None, None),
    ('get_bucket_website', 'Website', None, None),
    ('get_bucket_logging', 'Logging', None, 'LoggingEnabled'),
    ('get_bucket_notification_configuration', 'Notification', None, None)
#        ('get_bucket_lifecycle', 'Lifecycle', None, None),
#        ('get_bucket_cors', 'Cors'),
)


def assemble_bucket(item):
    """Assemble a document representing all the config state around a bucket.
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
        except ClientError, e:
            code =  e.response['Error']['Code']
            if code.startswith("NoSuch") or "NotFound" in code:
                v = default
            elif code == 'PermanentRedirect':
                # log.warning(e.response)
                s = factory()
                c = bucket_client(s, b)
                # Requeue with the correct region given location constraint
                methods.append((m, k))
                continue
            else:
                log.warning(
                    "Bucket:%s unable to invoke method:%s error:%s " % (
                        b['Name'], m, e.response['Error']['Message']))
                return None
        # As soon as we learn location (which generally works)
        if k == 'Location' and v is not None:
            b_location = v.get('LocationConstraint')
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
        # Need v4 signature for aws:kms crypto
        config = Config(signature_version='s3v4')
    else:
        config = None
    return session.client('s3', region_name=region, config=config)


@filters.register('global-grants')
class GlobalGrantsFilter(Filter):

    schema = type_schema('global-grants')

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
        for grant in acl['Grants']:
            if 'URI' not in grant.get("Grantee", {}):
                continue
            if grant['Grantee']['URI'] in [self.AUTH_ALL, self.GLOBAL_ALL]:
                if grant['Permission'] == 'READ' and b['Website']:
                    continue
                results.append(grant['Permission'])

        c = bucket_client(self.manager.session_factory(), b)

        if results:
            set_annotation(b, 'GlobalPermissions', results)
            return b


class BucketActionBase(BaseAction):

    def get_permissions(self):
        return self.permissions


@filters.register('has-statement')
class HasStatementFilter(Filter):
    """Find buckets with set of named policy statements."""
    schema = type_schema(
        'has-statement',
        statement_ids={'type': 'array', 'items': {'type': 'string'}})

    def process(self, buckets, event=None):
        return filter(None, map(self.process_bucket, buckets))

    def process_bucket(self, b):
        p = b['Policy']
        if p is None:
            return b
        p = json.loads(p['Policy'])
        required = list(self.data.get('statement_ids', []))
        statements = p.get('Statement', [])
        for s in list(statements):
            if s.get('StatementId') in required:
                required.remove(s['StatementId'])
        if not required:
            return b
        return None


@filters.register('missing-statement')
@filters.register('missing-policy-statement')
class MissingPolicyStatementFilter(Filter):
    """Find buckets missing a set of named policy statements."""

    schema = type_schema(
        'missing-policy-statement',
        aliases=('missing-statement',),
        statement_ids={'type': 'array', 'items': {'type': 'string'}})

    def process(self, buckets, event=None):
        return filter(None, map(self, buckets))

    def __call__(self, b):
        p = b['Policy']
        if p is None:
            return b

        p = json.loads(p['Policy'])

        required = list(self.data.get('statement_ids', []))
        statements = p.get('Statement', [])

        for s in list(statements):
            if s.get('StatementId') in required:
                required.remove(s['StatementId'])
        if not required:
            return False
        return True


@actions.register('no-op')
class NoOp(BucketActionBase):

    schema = type_schema('no-op')

    def process(self, buckets):
        return None


@actions.register('remove-statements')
class RemovePolicyStatement(BucketActionBase):

    schema = type_schema(
        'remove-statements',
        statement_ids={'type': 'array', 'items': {'type': 'string'}})

    def process(self, buckets):
        with self.executor_factory(max_workers=3) as w:
            results = w.map(self.process_bucket, buckets)
            return filter(None, list(results))

    def process_bucket(self, bucket):
        p = bucket['Policy']
        if p is None:
            return
        else:
            p = json.loads(p['Policy'])

        statements = p.get('Statement', [])
        found = []
        for s in list(statements):
            if s['Sid'] in self.data['statement_ids']:
                found.append(s)
                statements.remove(s)
        if not found:
            return

        s3 = local_session(self.manager.session_factory).client('s3')
        if not statements:
            s3.delete_bucket_policy(Bucket=bucket['Name'])
        else:
            s3.put_bucket_policy(Bucket=bucket['Name'], Policy=json.dumps(p))
        return {'Name': bucket['Name'], 'State': 'PolicyRemoved', 'Statements': found}


@actions.register('attach-encrypt')
class AttachLambdaEncrypt(BucketActionBase):
    schema = type_schema(
        'attach-encrypt', role={'type': 'string'})

    def __init__(self, data=None, manager=None):
        self.data = data or {}
        self.manager = manager

    def validate(self):
        if not self.data.get('role', self.manager.config.assume_role):
            raise ValueError(
                "attach-encrypt: role must be specified either"
                "via assume or in config")
        return self

    def process(self, buckets):
        from c7n.mu import LambdaManager
        from c7n.ufuncs.s3crypt import get_function
        func = get_function(
            None, self.data.get('role', self.manager.config.assume_role))

        # Publish function to all of our buckets regions
        region_funcs = {}
        regions = set([
            b.get('LocationConstraint', 'us-east-1') for b in buckets])
        for r in regions:
            lambda_mgr = LambdaManager(
                functools.partial(self.manager.session_factory, region=r))
            region_funcs[r] = lambda_mgr.publish(func)

        with self.executor_factory(max_workers=3) as w:
            results = []
            futures = []
            for b in buckets:
                futures.append(
                    w.submit(
                        self.process_bucket,
                        region_funcs[b.get('LocationConstraint', 'us-east-1')],
                        b))
            for f in as_completed(futures):
                if f.exception():
                    log.exception(
                        "Error attaching lambda-encrypt %s" % (f.exception()))
                results.append(f.result())
            return filter(None, results)

    def process_bucket(self, f, b):
        from c7n.mu import BucketNotification
        source = BucketNotification({}, self.manager.session_factory, b)
        return source.add(f)


@actions.register('encryption-policy')
class EncryptionRequiredPolicy(BucketActionBase):

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
            p = json.loads(p['Policy'])

        statements = p.get('Statement', [])
        found = False
        for s in list(statements):
            if s['Sid'] == 'RequireEncryptedPutObject':
                log.debug(
                    "Bucket:%s Found extant Encryption Policy" % b['Name'])
                return

        session = self.manager.session_factory()
        s3 = bucket_client(session, b)

        statements.append(
            {'Sid': 'RequireEncryptedPutObject',
             'Effect': 'Deny',
             'Principal': '*',
             'Action': 's3:PutObject',
             "Resource": "arn:aws:s3:::%s/*" % b['Name'],
             "Condition": {
                 # AWS Managed Keys or KMS keys, note policy language
                 # does not support custom kms (todo add issue)
                 "StringNotEquals": {
                     "s3:x-amz-server-side-encryption": ["AES256", "aws:kms"]}}
             })
        p['Statement'] = statements
        log.info('Bucket:%s attached encryption policy' % b['Name'])

        s3.put_bucket_policy(
            Bucket=b['Name'],
            Policy=json.dumps(p))
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
        self.fh = open(self.path, 'w')
        self.fh.write("[\n")
        return self

    def __exit__(self, exc_type=None, exc_value=None, exc_frame=None):
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
        self.fh.write(json.dumps(keys))
        self.fh.write(",\n")


class ScanBucket(BucketActionBase):

    permissions = ("s3:ListBucket",)

    bucket_ops = {
        'standard': {
            'iterator': 'list_objects',
            'contents_key': 'Contents',
            'key_processor': 'process_key'
            },
        'versioned': {
            'iterator': 'list_object_versions',
            'contents_key': 'Versions',
            'key_processor': 'process_version'
            }
        }

    def __init__(self, data, manager=None):
        super(ScanBucket, self).__init__(data, manager)
        self.denied_buckets = []

    def get_bucket_style(self, b):
        return (
            b.get('Versioning', {'Status': ''}).get('Status') == 'Enabled'
            and 'versioned' or 'standard')

    def get_bucket_op(self, b, op_name):
        bucket_style = self.get_bucket_style(b)
        op = self.bucket_ops[bucket_style][op_name]
        if op_name == 'key_processor':
            return getattr(self, op)
        return op

    def process(self, buckets):
        results = []
        with self.executor_factory(max_workers=3) as w:
            results.extend(
                f for f in w.map(self, buckets) if f)
        if self.denied_buckets:
            with open(
                    os.path.join(
                        self.manager.log_dir, 'denied.json'), 'w') as fh:
                json.dump(self.denied_buckets, fh, indent=2)
            self.denied_buckets = []
        return results

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
                        self.denied_buckets.append(b['Name'])
                        return
                    log.exception(
                        "Error processing bucket:%s paginator:%s" % (
                            b['Name'], p))

    __call__ = process_bucket

    def _process_bucket(self, b, p, key_log, w):
        content_key = self.get_bucket_op(b, 'contents_key')
        count = 0
        for key_set in p:
            count += len(key_set.get(content_key, []))

            # Empty bucket check
            if not content_key in key_set and not key_set['IsTruncated']:
                # annotate bucket
                b['KeyScanCount'] = count
                b['KeyRemediated'] = key_log.count
                return {'Bucket': b['Name'],
                        'Remediated': key_log.count,
                        'Count': count}
            futures = []
            for batch in chunks(key_set.get(content_key, []), size=100):
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

        return {'Bucket': b['Name'], 'Remediated': key_log.count, 'Count': count}

    def process_chunk(self, batch, bucket):
        raise NotImplementedError()

    def process_key(self, s3, key, bucket_name, info=None):
        raise NotImplementedError()

    def process_version(self, s3, bucket, key):
        raise NotImplementedError()


@actions.register('encrypt-keys')
class EncryptExtantKeys(ScanBucket):

    permissions = (
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObjectVersion",
        "s3:RestoreObject",
    ) + ScanBucket.permissions

    schema = {
        'type': 'object',
        'additonalProperties': False,
        'properties': {
            'report-only': {'type': 'boolean'},
            'glacier': {'type': 'boolean'},
            'crypto': {'enum': ['AES256', 'aws:kms']}
            }
        }

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

        if 'ServerSideEncryption' in info:
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
            storage_class == 'STANDARD'

        crypto_method = self.data.get('crypto', 'AES256')
        # Note on copy we lose individual object acl grants
        params = {'Bucket': bucket_name,
                  'Key': k,
                  'CopySource': "/%s/%s" % (bucket_name, k),
                  'MetadataDirective': 'COPY',
                  'StorageClass': storage_class,
                  'ServerSideEncryption': crypto_method}
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
    """

    schema = type_schema('is-log-target', value={'type': 'boolean'})
    executor_factory = executor.MainThreadExecutor

    def process(self, buckets, event=None):
        log_buckets = set()
        count = 0
        for bucket, _ in self.get_elb_bucket_locations():
            log_buckets.add(bucket)
            count += 1
        self.log.debug("Found %d elb log targets" % count)

        count = 0
        for bucket, _ in self.get_s3_bucket_locations(buckets):
            count += 1
            log_buckets.add(bucket)
        self.log.debug('Found %d s3 log targets' % count)

        for bucket, _ in self.get_cloud_trail_locations(buckets):
            log_buckets.add(bucket)

        self.log.info("Found %d log targets for %d buckets" % (
            len(log_buckets), len(buckets)))
        if self.data.get('value', True):
            return [b for b in buckets if b['Name'] in log_buckets]
        else:
            return [b for b in buckets if b['Name'] not in log_buckets]

    @staticmethod
    def get_s3_bucket_locations(buckets):
        """return (bucket_name, prefix) for all s3 logging targets"""
        for b in buckets:
            if b['Logging']:
                yield (b['Logging']['TargetBucket'],
                       b['Logging']['TargetPrefix'])
            if b['Name'].startswith('cf-templates-'):
                yield (b['Name'], '')

    def get_cloud_trail_locations(self, buckets):
        session = local_session(self.manager.session_factory)
        client = session.client('cloudtrail')
        names = set([b['Name'] for b in buckets])
        for t in client.describe_trails().get('trailList', ()):
            if t.get('S3BucketName') in names:
                yield (t['S3BucketName'], t.get('S3KeyPrefix', ''))

    def get_elb_bucket_locations(self):
        session = local_session(self.manager.session_factory)
        client = session.client('elb')

        # Try to use the cache if it exists
        elbs = self.manager._cache.get(
            {'region': self.manager.config.region, 'resource': 'elb'})

        # Sigh, post query refactor reuse, we can't save our cache here
        # as that resource manager does extra lookups on tags. Not
        # worth paginating, since with cache usage we have full set in
        # mem.
        if elbs is None:
            p = client.get_paginator('describe_load_balancers')
            results = p.paginate()
            elbs = results.build_full_result().get(
                'LoadBalancerDescriptions', ())
            self.log.info("Queried %d elbs", len(elbs))
        else:
            self.log.info("Using %d cached elbs", len(elbs))

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


@actions.register('delete-global-grants')
class DeleteGlobalGrants(BucketActionBase):

    schema = type_schema(
        'delete-global-grants',
        grantees={'type': 'array', 'items': {'type': 'string'}})

    def process(self, buckets):
        with self.executor_factory(max_workers=5) as w:
            return filter(None, list(w.map(self.process_bucket, buckets)))

    def process_bucket(self, b):
        grantees = self.data.get(
            'grantees', [
                GlobalGrantsFilter.AUTH_ALL, GlobalGrantsFilter.GLOBAL_ALL])

        s3 = bucket_client(self.manager.session_factory(), b)
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
        c.put_bucket_acl(
            Bucket=b['Name'],
            AccessControlPolicy={'Owner': acl['Owner'], 'Grants': new_grants})
        return b
