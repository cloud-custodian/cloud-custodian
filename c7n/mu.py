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
"""
Cloud Custodian Lambda Provisioning Support

docs/lambda.rst
"""

import abc
import base64
import inspect
import fnmatch
import hashlib
import json
import logging
import os
import sys
import tempfile
import zipfile

from boto3.s3.transfer import S3Transfer, TransferConfig
from botocore.exceptions import ClientError

from concurrent.futures import ThreadPoolExecutor

import c7n

# Static event mapping to help simplify cwe rules creation
from c7n.cwe import CloudWatchEvents
from c7n.utils import parse_s3


log = logging.getLogger('custodian.lambda')


class PythonPackageArchive(object):
    """Creates a zip file for python lambda functions

    Packages up a virtualenv and a source package directory per lambda's
    directory structure.
    """

    def __init__(self, src_path, virtualenv_dir=None, skip=None,
                 lib_filter=None, src_filter=None):

        self.src_path = src_path
        if virtualenv_dir is None:
            virtualenv_dir = os.path.abspath(
                os.path.join(os.path.dirname(sys.executable), '..'))
        self.virtualenv_dir = virtualenv_dir
        self._temp_archive_file = None
        self._zip_file = None
        self._closed = False
        self.lib_filter = lib_filter
        self.src_filter = src_filter
        self.skip = skip

    @property
    def path(self):
        return self._temp_archive_file.name

    @property
    def size(self):
        if not self._closed:
            raise ValueError("Archive not closed, size not accurate")
        return os.stat(self._temp_archive_file.name).st_size

    def filter_files(self, files):
        if not self.skip:
            return files
        skip_files = set(fnmatch.filter(files, self.skip))
        return [f for f in files if f not in skip_files]

    def create(self):
        assert not self._temp_archive_file, "Archive already created"
        self._temp_archive_file = tempfile.NamedTemporaryFile()
        self._zip_file = zipfile.ZipFile(
            self._temp_archive_file, mode='w',
            compression=zipfile.ZIP_DEFLATED)

        prefix = os.path.dirname(self.src_path)
        if os.path.isfile(self.src_path):
            # Module Source
            self._zip_file.write(
                os.path.join(self.src_path), os.path.basename(self.src_path))
        elif os.path.isdir(self.src_path):
            # Package Source
            for root, dirs, files in os.walk(self.src_path):
                arc_prefix = os.path.relpath(
                    root, os.path.dirname(self.src_path))
                if self.src_filter:
                    self.src_filter(root, dirs, files)
                files = self.filter_files(files)
                for f in files:
                    self._zip_file.write(
                        os.path.join(root, f),
                        os.path.join(arc_prefix, f))

        # Library Source
        venv_lib_path = os.path.join(
            self.virtualenv_dir, 'lib', 'python2.7', 'site-packages')

        for root, dirs, files in os.walk(venv_lib_path):
            if self.lib_filter:
                dirs, files = self.lib_filter(root, dirs, files)
            arc_prefix = os.path.relpath(root, venv_lib_path)
            files = self.filter_files(files)
            for f in files:
                self._zip_file.write(
                    os.path.join(root, f),
                    os.path.join(arc_prefix, f))

    def add_file(self, src, dest):
        self._zip_file.write(src, dest)
        
    def add_contents(self, dest, contents):
        if not isinstance(dest, zipfile.ZipInfo):
            dest = zinfo(dest)
        # see zinfo function for some caveats
        assert not self._closed, "Archive closed"
        self._zip_file.writestr(dest, contents)

    def close(self):
        # Note underlying tempfile is removed when archive is garbage collected
        self._closed = True
        self._zip_file.close()
        log.debug(
            "Created custodian lambda archive size: %0.2fmb",
            (os.path.getsize(self._temp_archive_file.name) / (
                1024.0 * 1024.0)))
        return self

    def remove(self):
        # dispose of the temp file for garbag collection
        if self._temp_archive_file:
            self._temp_archive_file = None

    def get_checksum(self):
        """Return the b64 encoded sha256 checksum."""
        assert self._closed, "Archive not closed"
        with open(self._temp_archive_file.name) as fh:
            return base64.b64encode(checksum(fh, hashlib.sha256()))

    def get_bytes(self):
        # return the entire zip file as byte string.
        assert self._closed, "Archive not closed"
        return open(self._temp_archive_file.name, 'rb').read()


def checksum(fh, hasher, blocksize=65536):
    buf = fh.read(blocksize)
    while len(buf) > 0:
        hasher.update(buf)
        buf = fh.read(blocksize)
    return hasher.digest()


def custodian_archive(skip=None):
    """Create a lambda code archive for running custodian."""

    # Some aggressive shrinking
    required = ["concurrent", "yaml", "pkg_resources"]
    host_platform = os.uname()[0]

    def lib_filter(root, dirs, files):
        for f in list(files):
            # Don't bother with shared libs across platforms
            if f.endswith('.so') and host_platform != 'Linux':
                files.remove(f)
        if os.path.basename(root) == 'site-packages':
            for n in tuple(dirs):
                if n not in required:
                    dirs.remove(n)
        return dirs, files

    return PythonPackageArchive(
        os.path.dirname(inspect.getabsfile(c7n)),
        os.path.abspath(os.path.join(
            os.path.dirname(sys.executable), '..')),
        skip=skip,
        lib_filter=lib_filter)


class LambdaManager(object):
    """ Provides CRUD operations around lambda functions
    """
    def __init__(self, session_factory, s3_asset_path=None):
        self.session_factory = session_factory
        self.client = self.session_factory().client('lambda')
        self.s3_asset_path = s3_asset_path

    def list_functions(self, prefix=None):
        p = self.client.get_paginator('list_functions')
        for rp in p.paginate():
            for f in rp.get('Functions', []):
                if not prefix:
                    yield f
                if f['FunctionName'].startswith(prefix):
                    yield f

    def publish(self, func, alias=None, role=None, s3_uri=None):
        result, changed = self._create_or_update(func, role, s3_uri, qualifier=alias)
        func.arn = result['FunctionArn']
        if alias and changed:
            func.alias = self.publish_alias(result, alias)
        elif alias:
            func.alias = "%s:%s" % (func.arn, alias)
        else:
            func.alias = func.arn

        for e in func.get_events(self.session_factory):
            if e.add(func):
                log.debug(
                    "Added event source: %s to function: %s",
                    e, func.alias)
        return result

    def remove(self, func, alias=None):
        log.info("Removing lambda function %s", func.name)
        for e in func.get_events(self.session_factory):
            e.remove(func)
        try:
            self.client.delete_function(FunctionName=func.name)
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                raise

    def metrics(self, funcs, start, end, period=5*60):

        def func_metrics(f):
            metrics = self.session_factory().client('cloudwatch')
            values = {}
            for m in ('Errors', 'Invocations', 'Durations', 'Throttles'):
                values[m] = metrics.get_metric_statistics(
                    Namespace="AWS/Lambda",
                    Dimensions=[{
                        'Name': 'FunctionName',
                        'Value': (
                            isinstance(f, dict) and f['FunctionName']
                            or f.name)}],
                    Statistics=["Sum"],
                    StartTime=start,
                    EndTime=end,
                    Period=period,
                    MetricName=m)['Datapoints']
            return values

        with ThreadPoolExecutor(max_workers=3) as w:
            results = list(w.map(func_metrics, funcs))
            for m, f in zip(results, funcs):
                if isinstance(f, dict):
                    f['Metrics'] = m
        return results

    def logs(self, func):
        logs = self.session_factory().client('logs')
        group_name = "/aws/lambda/%s" % func.name
        log.info("Fetching logs from group: %s" % group_name)
        try:
            log_groups = logs.describe_log_groups(
                logGroupNamePrefix=group_name)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return
            raise
        try:
            log_streams = logs.describe_log_streams(
                logGroupName=group_name,
                orderBy="LastEventTime", limit=3, descending=True)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return
            raise
        for s in reversed(log_streams['logStreams']):
            result = logs.get_log_events(
                logGroupName=group_name, logStreamName=s['logStreamName'])
            for e in result['events']:
                yield e

    @staticmethod
    def delta_function(lambda_func, func, role):
        conf = func.get_config()
        # TODO feels a little wierd
        conf['Role'] = role
        for k in conf:
            if conf[k] != lambda_func['Configuration'][k]:
                return True

    def _create_or_update(self, func, role=None, s3_uri=None, qualifier=None):
        role = func.role or role
        assert role, "Lambda function role must be specified"
        archive = func.get_archive()
        lfunc = self.get(func.name, qualifier)

        if s3_uri:
            # TODO: support versioned buckets
            bucket, key = self._upload_func(s3_uri, func, archive)
            code_ref = {'S3Bucket': bucket, 'S3Key': key}
        else:
            code_ref = {'ZipFile': archive.get_bytes()}

        changed = False
        if lfunc:
            result = lfunc['Configuration']
            if archive.get_checksum() != lfunc['Configuration']['CodeSha256']:
                log.debug("Updating function %s code", func.name)
                params = dict(FunctionName=func.name, Publish=True)
                params.update(code_ref)
                result = self.client.update_function_code(**params)
                changed = True
            # TODO/Consider also set publish above to false, and publish
            # after configuration change?
            if self.delta_function(lfunc, func, role):
                log.debug("Updating function: %s config" % func.name)
                params = func.get_config()
                del params['Runtime']
                params['Role'] = role
                result = self.client.update_function_configuration(**params)
                changed = True
        else:
            log.info('Publishing custodian policy lambda function %s', func.name)
            params = func.get_config()
            params.update({'Publish': True, 'Code': code_ref, 'Role': role})
            result = self.client.create_function(**params)
            changed = True

        return result, changed

    def _upload_func(self, s3_uri, func, archive):
        _, bucket, key_prefix = parse_s3(s3_uri)
        key = "%s/%s" % (key_prefix, func.name)
        transfer = S3Transfer(
            self.session_factory().client('s3'),
            config=TransferConfig(
                multipart_threshold=1024*1024*4))
        transfer.upload_file(
            archive.path,
            bucket=bucket,
            key=key,
            extra_args={
                'ServerSideEncryption': 'AES256'})
        return bucket, key

    def publish_alias(self, func_data, alias):
        """Create or update an alias for the given function.
        """
        if not alias:
            return func_data['FunctionArn']
        func_name = func_data['FunctionName']
        func_version = func_data['Version']

        exists = resource_exists(
            self.client.get_alias, FunctionName=func_name, Name=alias)

        if not exists:
            log.debug("Publishing custodian lambda alias %s", alias)
            alias_result = self.client.create_alias(
                FunctionName=func_name,
                Name=alias,
                FunctionVersion=func_version)
        else:
            if (exists['FunctionVersion'] == func_version and
                exists['Name'] == alias):
                return exists['AliasArn']
            log.debug('Updating custodian lambda alias %s', alias)
            alias_result = self.client.update_alias(
                FunctionName=func_name,
                Name=alias,
                FunctionVersion=func_version)
        return alias_result['AliasArn']

    def get(self, func_name, qualifier=None):
        params = {'FunctionName': func_name}
        if qualifier:
            params['Qualifier'] = qualifier
        return resource_exists(
            self.client.get_function, **params)


def resource_exists(op, *args, **kw):
    try:
        return op(*args, **kw)
    except ClientError, e:
        if e.response['Error']['Code'] == "ResourceNotFoundException":
            return False
        raise


class AbstractLambdaFunction:
    """Abstract base class for lambda functions."""
    __metaclass__ = abc.ABCMeta

    alias = None

    @abc.abstractproperty
    def name(self):
        """Name for the lambda function"""

    @abc.abstractproperty
    def runtime(self):
        """ """

    @abc.abstractproperty
    def description(self):
        """ """

    @abc.abstractproperty
    def handler(self):
        """ """

    @abc.abstractproperty
    def memory_size(self):
        """ """

    @abc.abstractproperty
    def timeout(self):
        """ """

    @abc.abstractproperty
    def role(self):
        """ """

    @abc.abstractproperty
    def subnets(self):
        """ """

    @abc.abstractproperty
    def security_groups(self):
        """ """

    @abc.abstractmethod
    def get_events(self, session_factory):
        """event sources that should be bound to this lambda."""

    @abc.abstractmethod
    def get_archive(self):
        """Return the lambda distribution archive object."""

    def get_config(self):
        conf = {
            'FunctionName': self.name,
            'MemorySize': self.memory_size,
            'Role': self.role,
            'Description': self.description,
            'Runtime': self.runtime,
            'Handler': self.handler,
            'Timeout': self.timeout}
        if self.subnets and self.security_groups:
            conf['VpcConfig'] = {
                'SubnetIds': self.subnets,
                'SecurityGroupIds': self.security_groups}
        return conf


class LambdaFunction(AbstractLambdaFunction):

    def __init__(self, func_data, archive):
        self.func_data = func_data
        required = set((
            'name', 'handler', 'memory_size',
            'timeout', 'role', 'runtime',
            'description'))
        missing = required.difference(func_data)
        if missing:
            raise ValueError("Missing required keys %s" % " ".join(missing))
        self.archive = archive

    @property
    def name(self):
        return self.func_data['name']

    @property
    def description(self):
        return self.func_data['description']

    @property
    def handler(self):
        return self.func_data['handler']

    @property
    def memory_size(self):
        return self.func_data['memory_size']

    @property
    def timeout(self):
        return self.func_data['timeout']

    @property
    def runtime(self):
        return self.func_data['runtime']

    @property
    def role(self):
        return self.func_data['role']

    @property
    def security_groups(self):
        return self.func_data.get('security_groups', None)

    @property
    def subnets(self):
        return self.func_data.get('subnets', None)

    def get_events(self, session_factory):
        return self.func_data.get('events', ())

    def get_archive(self):
        return self.archive


PolicyHandlerTemplate = """\
from c7n import handler

def run(event, context):
    return handler.dispatch_event(event, context)

"""


class PolicyLambda(AbstractLambdaFunction):
    """Wraps a custodian policy to turn it into lambda function.
    """
    handler = "custodian_policy.run"
    runtime = "python2.7"
    timeout = 60

    def __init__(self, policy):
        self.policy = policy
        self.archive = custodian_archive('*pyc')

    @property
    def name(self):
        return "custodian-%s" % self.policy.name

    @property
    def description(self):
        return self.policy.data.get(
            'description', 'cloud-custodian lambda policy')

    @property
    def role(self):
        return self.policy.data['mode'].get('role', '')

    @property
    def memory_size(self):
        return self.policy.data['mode'].get('memory', 512)

    @property
    def security_groups(self):
        return None

    @property
    def subnets(self):
        return None

    def get_events(self, session_factory):
        events = []
        events.append(CloudWatchEventSource(
            self.policy.data['mode'], session_factory))
        return events

    def get_archive(self):
        self.archive.create()
        self.archive.add_contents(
            'config.json', json.dumps(
                {'policies': [self.policy.data]}, indent=2))
        self.archive.add_contents('custodian_policy.py', PolicyHandlerTemplate)
        self.archive.close()
        return self.archive


def zinfo(fname):
    """Amazon lambda exec environment setup can break itself
    if zip files aren't constructed a particular way.

    ie. It respects file perm attributes from the zip including
    those that prevent lambda from working. Namely lambda
    extracts code as one user, and executes code as a different
    user without permissions for the executing user to read
    the file the lambda function is broken.

    Python's default zipfile.writestr does a 0600 perm which
    we modify here as a workaround.
    """
    info = zipfile.ZipInfo(fname)
    # Grant other users permissions to read
    info.external_attr = 0o644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


class CloudWatchEventSource(object):
    """Subscribe a lambda to cloud watch events.

    Cloud watch events supports a number of different event
    sources, from periodic timers with cron syntax, to
    real time instance state notifications, cloud trail
    events, and realtime asg membership changes.

    Event Pattern for Instance State

    .. code-block:: json

       {
         "source": ["aws.ec2"],
         "detail-type": ["EC2 Instance State-change Notification"],
         "detail": { "state": ["pending"]}
       }

    Event Pattern for Cloud Trail API

    .. code-block:: json

       {
         "detail-type": ["AWS API Call via CloudTrail"],
         "detail": {
            "eventSource": ["s3.amazonaws.com"],
            "eventName": ["CreateBucket", "DeleteBucket"]
         }
       }
    """
    ASG_EVENT_MAPPING = {
        'launch-success': 'EC2 Instance Launch Successful',
        'launch-failure': 'EC2 Instance Launch Unsuccessful',
        'terminate-success': 'EC2 Instance Terminate Successful',
        'terminate-failure': 'EC2 Instance Terminate Unsuccessful'}

    def __init__(self, data, session_factory, prefix="custodian-"):
        import time
        t = time.time()
        self.session_factory = session_factory
        self.session = session_factory()
        self.client = self.session.client('events')
        self.data = data
        self.prefix = prefix

    def _make_notification_id(self, function_name):
        if not function_name.startswith(self.prefix):
            return "%s%s" % (self.prefix, function_name)
        return function_name

    def get(self, rule_name):
        return resource_exists(
            self.client.describe_rule,
            Name=self._make_notification_id(rule_name))

    @staticmethod
    def delta(src, tgt):
        """Given two cwe rules determine if the configuration is the same.

        Name is already implied.
        """
        for k in ['State', 'EventPattern', 'ScheduleExpression']:
            if src.get(k) != tgt.get(k):
                return True
        return False

    def __repr__(self):
        return "<CWEvent Type:%s Sources:%s Events:%s>" % (
            self.data.get('type'),
            ', '.join(self.data.get('sources', [])),
            ', '.join(self.data.get('events', [])))

    def resolve_cloudtrail_payload(self, payload):
        ids = []
        sources = self.data.get('sources', [])

        for e in self.data.get('events'):
            event_info = CloudWatchEvents.get(e)
            if event_info is None:
                continue
            sources.append(event_info['source'])

        payload['detail'] = {
            'eventSource': list(set(sources)),
            'eventName': self.data.get('events', [])}

    def render_event_pattern(self):
        event_type = self.data.get('type')
        payload = {}
        if event_type == 'cloudtrail':
            payload['detail-type'] = ['AWS API Call via CloudTrail']
            self.resolve_cloudtrail_payload(payload)

        elif event_type == "ec2-instance-state":
            payload['source'] = ['aws.ec2']
            payload['detail-type'] = [
                "EC2 Instance State-change Notification"]
            # Technically could let empty be all events, but likely misconfig
            payload['detail'] = {"state": self.data.get('events', [])}
        elif event_type == "asg-instance-state":
            payload['source'] = ['aws.autoscaling']
            events = []
            for e in self.data.get('events', []):
                events.append(self.ASG_EVENT_MAPPING.get(e, e))
            payload['detail-type'] = events
        elif event_type == 'periodic':
            pass
        else:
            raise ValueError(
                "Unknown lambda event source type: %s" % event_type)
        if not payload:
            return None
        return json.dumps(payload)

    def add(self, func):
        params = dict(
            Name=func.name, Description=func.description, State='ENABLED')

        pattern = self.render_event_pattern()
        if pattern:
            params['EventPattern'] = pattern
        schedule = self.data.get('schedule')
        if schedule:
            params['ScheduleExpression'] = schedule

        rule = self.get(func.name)

        if rule and self.delta(rule, params):
            log.debug("Updating cwe rule for %s" % self)
            response = self.client.put_rule(**params)
        elif not rule:
            log.debug("Creating cwe rule for %s" % (self))
            response = self.client.put_rule(**params)
        else:
            response = {'RuleArn': rule['Arn']}

        try:
            self.session.client('lambda').add_permission(
                FunctionName=func.name,
                StatementId=func.name,
                SourceArn=response['RuleArn'],
                Action='lambda:InvokeFunction',
                Principal='events.amazonaws.com')
            log.debug('Added lambda invoke cwe rule permission')
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceConflictException':
                raise

        # Add Targets
        found = False
        response = self.client.list_targets_by_rule(Rule=func.name)
        # CWE seems to be quite picky about function arns (no aliases/versions)
        func_arn = func.arn

        if func_arn.count(':') > 6:
            func_arn, version = func_arn.rsplit(':', 1)
        for t in response['Targets']:
            if func_arn == t['Arn']:
                found = True

        if found:
            return

        log.debug('Creating cwe rule target for %s on func:%s' % (
            self, func_arn))

        result = self.client.put_targets(
            Rule=func.name, Targets=[{"Id": func.name, "Arn": func_arn}])

        return True

    def update(self, func):
        self.add(func)

    def pause(self, func):
        try:
            self.client.disable_rule(Name=func.name)
        except ClientError as e:
            pass

    def resume(self, func):
        try:
            self.client.enable_rule(Name=func.name)
        except ClientError as e:
            pass

    def remove(self, func):
        if self.get(func.name):
            try:
                targets = self.client.list_targets_by_rule(
                    Rule=func.name)['Targets']
                self.client.remove_targets(
                    Rule=func.name,
                    Ids=[t['Id'] for t in targets])
            except ClientError as e:
                log.warning(
                    "Could not remove targets for rule %s error: %s",
                    func.name, e)
            self.client.delete_rule(Name=func.name)


class BucketNotification(object):
    """ Subscribe a lambda to bucket notifications. """

    def __init__(self, data, session_factory, bucket):
        self.data = data
        self.session_factory = session_factory
        self.session = session_factory()
        self.bucket = bucket

    def delta(self, src, tgt):
        for k in ['Id', 'LambdaFunctionArn', 'Events', 'Filters']:
            if src.get(k) != tgt.get(k):
                return True
        return False

    def _get_notifies(self, s3, func):
        notifies = s3.get_bucket_notification_configuration(
            Bucket=self.bucket['Name'])
        found = False
        for f in notifies.get('LambdaFunctionConfigurations', []):
            if f['Id'] != func.name:
                continue
            found = f
        return notifies, found

    def add(self, func):
        s3 = self.session.client('s3')
        notifies, found = self._get_notifies(s3, func)
        notifies.pop('ResponseMetadata', None)
        func_arn = func['FunctionArn']
        if func_arn.rsplit(':', 1)[-1].isdigit():
            func_arn = func_arn.rsplit(':', 1)[0]
        n_params = {
            'Id': func['FunctionName'],
            'LambdaFunctionArn': func_arn,
            'Events': self.data.get('events', ['s3:ObjectCreated:*'])}
        if self.data.get('filters'):
            n_params['Filters'] = {
                'Key': {'FilterRules': self.filters}}

        if found:
            if self.delta(found, n_params):
                notifies['LambdaFunctionConfigurations'].remove(found)
            else:
                log.info("Bucket lambda notification present")
                return

        lambda_client = self.session.client('lambda')
        params = dict(
            FunctionName=func['FunctionName'],
            StatementId=self.bucket['Name'],
            Action='lambda:InvokeFunction',
            Principal='s3.amazonaws.com')
        if not self.data.get('account_s3'):
            params['SourceArn'] = 'arn:aws:s3:::%s' % self.bucket['Name']

        try:
            lambda_client.add_permission(**params)
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceConflictException':
                raise

        notifies.setdefault('LambdaFunctionConfigurations', []).append(n_params)
        s3.put_bucket_notification_configuration(
            Bucket=self.bucket['Name'], NotificationConfiguration=notifies)

        return True

    def remove(self, func):
        s3 = self.session.client('s3')
        notifies, found = self._get_notifies(s3, func)
        if not found:
            return

        lambda_client = self.session.client('lambda')
        try:
            response = lambda_client.remove_permission(
                FunctionName=func['FunctionName'], StatementId=self.bucket['Name'])
            log.debug("Removed lambda permission result: %s" % response)
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                raise

        notifies['LambdaFunctionConfigurations'].remove(found)
        s3.put_bucket_notification_configuration(
            Bucket=self.bucket['Name'],
            NotificationConfiguration=notifies)


class CloudWatchLogSubscription(object):
    """ Subscribe a lambda to a log group[s]
    """

    def __init__(self, session_factory, log_groups, filter_pattern):
        self.log_groups = log_groups
        self.filter_pattern = filter_pattern
        self.session_factory = session_factory
        self.session = session_factory()
        self.client = self.session.client('logs')

    def add(self, func):
        lambda_client = self.session.client('lambda')
        for group in self.log_groups:
            log.info(
                "Creating subscription filter for %s" % group['logGroupName'])
            region = group['arn'].split(':', 4)[3]
            try:
                lambda_client.add_permission(
                    FunctionName=func.name,
                    StatementId=group['logGroupName'][1:].replace('/', '-'),
                    SourceArn=group['arn'],
                    Action='lambda:InvokeFunction',
                    Principal='logs.%s.amazonaws.com' % region)
                log.debug("Added lambda invoke log group permission")
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceConflictException':
                    raise
            # Consistent put semantics / ie no op if extant
            response = self.client.put_subscription_filter(
                logGroupName=group['logGroupName'],
                filterName=func.name,
                filterPattern=self.filter_pattern,
                destinationArn=func.alias or func.arn)

    def remove(self, func):
        lambda_client = self.session.client('lambda')
        for group in self.log_groups:
            try:
                response = lambda_client.remove_permission(
                    FunctionName=func.name,
                    StatementId=group['logGroupName'][1:].replace('/', '-'))
                log.debug("Removed lambda permission result: %s" % response)
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceNotFoundException':
                    raise

            try:
                response = self.client.delete_subscription_filter(
                    logGroupName=group['logGroupName'], filterName=func.name)
                log.debug("Removed subscription filter from: %s",
                          group['logGroupName'])
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceNotFoundException':
                    raise
