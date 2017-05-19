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
from __future__ import absolute_import, division, print_function, unicode_literals

import abc
import base64
import imp
import hashlib
import json
import logging
import os
import StringIO
import sys
import time
import tempfile
import zipfile

from boto3.s3.transfer import S3Transfer, TransferConfig
from botocore.exceptions import ClientError

from concurrent.futures import ThreadPoolExecutor

# Static event mapping to help simplify cwe rules creation
from c7n.cwe import CloudWatchEvents
from c7n.logs_support import _timestamp_from_string
from c7n.utils import parse_s3, local_session


log = logging.getLogger('custodian.lambda')
RUNTIME = 'python{}.{}'.format(
    sys.version_info.major,
    sys.version_info.minor,
)


class PythonPackageArchive(object):
    """Creates a zip file for python lambda functions.

    :param tuple modules: the Python modules to add to the archive

    Amazon doesn't give us straightforward docs here, only `an example
    <http://docs.aws.amazon.com/lambda/latest/dg/with-s3-example-deployment-pkg.html#with-s3-example-deployment-pkg-python>`_,
    from which we can infer that they simply unzip the file into a directory on
    ``sys.path``. So what we do is locate all of the ``modules`` specified, and
    add all of the ``.py`` files we find for these modules to a zip file.

    In addition to the modules specified during instantiation, you can add
    arbitrary additional files to the archive using :py:func:`add_file` and
    :py:func:`add_contents`. For example, since we only add ``*.py`` files for
    you, you'll need to manually add files for any compiled extension modules
    that your Lambda requires.

    """

    def __init__(self, *modules):
        self._temp_archive_file = tempfile.NamedTemporaryFile()
        self._zip_file = zipfile.ZipFile(
            self._temp_archive_file, mode='w',
            compression=zipfile.ZIP_DEFLATED)
        self._closed = False
        self.add_modules(*modules)

    @property
    def path(self):
        return self._temp_archive_file.name

    @property
    def size(self):
        if not self._closed:
            raise ValueError("Archive not closed, size not accurate")
        return os.stat(self._temp_archive_file.name).st_size

    def add_modules(self, *modules):
        """Add the named Python modules to the archive. For consistency's sake
        we only add ``*.py`` files, not ``*.pyc``. We also don't add other
        files, including compiled modules. You'll have to add such files
        manually using :py:meth:`add_file`.
        """
        for module in modules:
            path = imp.find_module(module)[1]
            if os.path.isfile(path):
                if not path.endswith('.py'):
                    raise ValueError('We need a *.py source file instead of ' + path)
                self.add_file(path)
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    arc_prefix = os.path.relpath(root, os.path.dirname(path))
                    for f in files:
                        if not f.endswith('.py'):
                            continue
                        f_path = os.path.join(root, f)
                        dest_path = os.path.join(arc_prefix, f)
                        self.add_file(f_path, dest_path)

    def add_file(self, src, dest=None):
        """Add the file at ``src`` to the archive.

        If ``dest`` is ``None`` then it is added under just the original
        filename. So ``add_file('foo/bar.txt')`` ends up at ``bar.txt`` in the
        archive, while ``add_file('bar.txt', 'foo/bar.txt')`` ends up at
        ``foo/bar.txt``.

        """
        dest = dest or os.path.basename(src)
        with open(src, 'rb') as fp:
            contents = fp.read()
        self.add_contents(dest, contents)

    def add_py_file(self, src, dest=None):
        """This is a special case of :py:meth:`add_file` that helps for adding
        a ``py`` when a ``pyc`` may be present as well. So for example, if
        ``__file__`` is ``foo.pyc`` and you do:

        .. code-block:: python

          archive.add_py_file(__file__)

        then this method will add ``foo.py`` instead if it exists, and raise
        ``IOError`` if it doesn't.

        """
        src = src[:-1] if src.endswith('.pyc') else src
        self.add_file(src, dest)

    def add_contents(self, dest, contents):
        """Add file contents to the archive under ``dest``.

        If ``dest`` is a path, it will be added compressed and world-readable
        (user-writeable). You may also pass a :py:class:`~zipfile.ZipInfo` for
        custom behavior.

        """
        assert not self._closed, "Archive closed"
        if not isinstance(dest, zipfile.ZipInfo):
            dest = zinfo(dest)  # see for some caveats
        self._zip_file.writestr(dest, contents)

    def close(self):
        """Close the zip file.

        Note underlying tempfile is removed when archive is garbage collected.
        """
        self._closed = True
        self._zip_file.close()
        log.debug(
            "Created custodian lambda archive size: %0.2fmb",
            (os.path.getsize(self._temp_archive_file.name) / (
                1024.0 * 1024.0)))
        return self

    def remove(self):
        """Dispose of the temp file for garbage collection."""
        if self._temp_archive_file:
            self._temp_archive_file = None

    def get_checksum(self):
        """Return the b64 encoded sha256 checksum of the archive."""
        assert self._closed, "Archive not closed"
        with open(self._temp_archive_file.name) as fh:
            return base64.b64encode(checksum(fh, hashlib.sha256()))

    def get_bytes(self):
        """Return the entire zip file as a byte string. """
        assert self._closed, "Archive not closed"
        return open(self._temp_archive_file.name, 'rb').read()

    def get_reader(self):
        """Return a read-only :py:class:`~zipfile.ZipFile`."""
        assert self._closed, "Archive not closed"
        io = StringIO.StringIO(self.get_bytes())
        return zipfile.ZipFile(io, mode='r')

    def get_filenames(self):
        """Return a list of filenames in the archive."""
        return [n.filename for n in self.get_reader().filelist]


def checksum(fh, hasher, blocksize=65536):
    buf = fh.read(blocksize)
    while len(buf) > 0:
        hasher.update(buf)
        buf = fh.read(blocksize)
    return hasher.digest()


def custodian_archive():
    """Create a lambda code archive for running custodian."""
    return PythonPackageArchive('c7n', 'pkg_resources', 'ipaddress')


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
                elif f['FunctionName'].startswith(prefix):
                    yield f

    def publish(self, func, alias=None, role=None, s3_uri=None):
        result, changed = self._create_or_update(
            func, role, s3_uri, qualifier=alias)
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

    def metrics(self, funcs, start, end, period=5 * 60):

        def func_metrics(f):
            metrics = local_session(self.session_factory).client('cloudwatch')
            values = {}
            for m in ('Errors', 'Invocations', 'Durations', 'Throttles'):
                values[m] = metrics.get_metric_statistics(
                    Namespace="AWS/Lambda",
                    Dimensions=[{
                        'Name': 'FunctionName',
                        'Value': (
                            isinstance(f, dict) and f['FunctionName'] or f.name)}],
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

    def logs(self, func, start, end):
        logs = self.session_factory().client('logs')
        group_name = "/aws/lambda/%s" % func.name
        log.info("Fetching logs from group: %s" % group_name)
        try:
            logs.describe_log_groups(
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
        start = _timestamp_from_string(start)
        end = _timestamp_from_string(end)
        for s in reversed(log_streams['logStreams']):
            result = logs.get_log_events(
                logGroupName=group_name,
                logStreamName=s['logStreamName'],
                startTime=start,
                endTime=end,
            )
            for e in result['events']:
                yield e

    @staticmethod
    def delta_function(old_config, new_config):
        for k in new_config:
            if k not in old_config or new_config[k] != old_config[k]:
                return True

    @staticmethod
    def diff_tags(old_tags, new_tags):
        add = {}
        remove = set()
        for k,v in new_tags.items():
            if k not in old_tags or old_tags[k] != v:
                add[k] = v
        for k in old_tags:
            if k not in new_tags:
                remove.add(k)
        return add, list(remove)

    def _create_or_update(self, func, role=None, s3_uri=None, qualifier=None):
        role = func.role or role
        assert role, "Lambda function role must be specified"
        archive = func.get_archive()
        existing = self.get(func.name, qualifier)

        if s3_uri:
            # TODO: support versioned buckets
            bucket, key = self._upload_func(s3_uri, func, archive)
            code_ref = {'S3Bucket': bucket, 'S3Key': key}
        else:
            code_ref = {'ZipFile': archive.get_bytes()}

        changed = False
        if existing:
            old_config = existing['Configuration']
            if archive.get_checksum() != old_config['CodeSha256']:
                log.debug("Updating function %s code", func.name)
                params = dict(FunctionName=func.name, Publish=True)
                params.update(code_ref)
                result = self.client.update_function_code(**params)
                changed = True
            # TODO/Consider also set publish above to false, and publish
            # after configuration change?

            new_config = func.get_config()
            new_config['Role'] = role
            del new_config['Runtime']
            new_tags = new_config.pop('Tags', {})

            if self.delta_function(old_config, new_config):
                log.debug("Updating function: %s config" % func.name)
                result = self.client.update_function_configuration(**new_config)
                changed = True

            # tag dance
            base_arn = old_config['FunctionArn']
            if base_arn.count(':') > 6:  # trim version/alias
                base_arn = base_arn.rsplit(':', 1)[0]

            old_tags = self.client.list_tags(Resource=base_arn)['Tags']
            tags_to_add, tags_to_remove = self.diff_tags(old_tags, new_tags)

            if tags_to_add:
                log.debug("Adding/updating tags: %s config" % func.name)
                self.client.tag_resource(
                    Resource=base_arn, Tags=tags_to_add)
            if tags_to_remove:
                log.debug("Removing tags: %s config" % func.name)
                self.client.untag_resource(
                    Resource=base_arn, TagKeys=tags_to_remove)

            if not changed:
                result = old_config
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
                multipart_threshold=1024 * 1024 * 4))
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


def resource_exists(op, NotFound="ResourceNotFoundException", *args, **kw):
    try:
        return op(*args, **kw)
    except ClientError, e:
        if e.response['Error']['Code'] == NotFound:
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

    @abc.abstractproperty
    def dead_letter_config(self):
        """ """

    @abc.abstractproperty
    def environment(self):
        """ """

    @abc.abstractproperty
    def kms_key_arn(self):
        """ """

    @abc.abstractproperty
    def tracing_config(self):
        """ """

    @abc.abstractproperty
    def tags(self):
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
            'Timeout': self.timeout,
            'DeadLetterConfig': self.dead_letter_config,
            'Environment': self.environment,
            'KMSKeyArn': self.kms_key_arn,
            'TracingConfig': self.tracing_config,
            'Tags': self.tags}
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

    @property
    def dead_letter_config(self):
        return self.func_data.get('dead_letter_config', {})

    @property
    def environment(self):
        return self.func_data.get('environment', {})

    @property
    def kms_key_arn(self):
        return self.func_data.get('kms_key_arn', '')

    @property
    def tracing_config(self):
        return self.func_data.get('tracing_config', {})

    @property
    def tags(self):
        return self.func_data.get('tags', {})

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

    def __init__(self, policy):
        self.policy = policy
        self.archive = custodian_archive()

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
    def timeout(self):
        return self.policy.data['mode'].get('timeout', 60)

    @property
    def security_groups(self):
        return None

    @property
    def subnets(self):
        return None

    @property
    def dead_letter_config(self):
        return self.policy.data['mode'].get('dead_letter_config', {})

    @property
    def environment(self):
        return self.policy.data['mode'].get('environment', {})

    @property
    def kms_key_arn(self):
        return self.policy.data['mode'].get('kms_key_arn', '')

    @property
    def tracing_config(self):
        return self.policy.data['mode'].get('tracing_config', {})

    @property
    def tags(self):
        return self.policy.data['mode'].get('tags', {})

    def get_events(self, session_factory):
        events = []
        if self.policy.data['mode']['type'] == 'config-rule':
            events.append(
                ConfigRule(self.policy.data['mode'], session_factory))
        else:
            events.append(
                CloudWatchEventSource(
                    self.policy.data['mode'], session_factory))
        return events

    def get_archive(self):
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
    user. Without permissions for the executing user to read
    the file the lambda function is broken.

    Python's default zipfile.writestr does a 0600 perm which
    we modify here as a workaround.
    """
    info = zipfile.ZipInfo(fname)
    # Grant other users permissions to read
    # http://unix.stackexchange.com/questions/14705/
    info.external_attr = 0o644 << 16L
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
        return "<CWEvent Type:%s Events:%s>" % (
            self.data.get('type'),
            ', '.join(map(str, self.data.get('events', []))))

    def resolve_cloudtrail_payload(self, payload):
        sources = self.data.get('sources', [])
        events = []
        for e in self.data.get('events'):
            if not isinstance(e, dict):
                events.append(e)
                event_info = CloudWatchEvents.get(e)
                if event_info is None:
                    continue
            else:
                event_info = e
                events.append(e['event'])
            sources.append(event_info['source'])

        payload['detail'] = {
            'eventSource': list(set(sources)),
            'eventName': events}

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

        self.client.put_targets(
            Rule=func.name, Targets=[{"Id": func.name, "Arn": func_arn}])

        return True

    def update(self, func):
        self.add(func)

    def pause(self, func):
        try:
            self.client.disable_rule(Name=func.name)
        except:
            pass

    def resume(self, func):
        try:
            self.client.enable_rule(Name=func.name)
        except:
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


class BucketLambdaNotification(object):
    """ Subscribe a lambda to bucket notifications directly. """

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
        func_arn = func.arn
        if func_arn.rsplit(':', 1)[-1].isdigit():
            func_arn = func_arn.rsplit(':', 1)[0]
        n_params = {
            'Id': func.name,
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
            FunctionName=func.name,
            StatementId=self.bucket['Name'],
            Action='lambda:InvokeFunction',
            Principal='s3.amazonaws.com')
        if self.data.get('account_s3'):
            params['SourceAccount'] = self.data['account_s3']
            params['SourceArn'] = 'arn:aws:s3:::*'
        else:
            params['SourceArn'] = 'arn:aws:s3:::%' % self.bucket['Name']
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
                FunctionName=func['FunctionName'],
                StatementId=self.bucket['Name'])
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

    iam_delay = 1.5

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
                log.debug("Added lambda ipo nvoke log group permission")
                # iam eventual consistency and propagation
                time.sleep(self.iam_delay)
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceConflictException':
                    raise
            # Consistent put semantics / ie no op if extant
            self.client.put_subscription_filter(
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


class SNSSubscription(object):
    """ Subscribe a lambda to one or more SNS topics.
    """

    iam_delay = 1.5

    def __init__(self, session_factory, topic_arns):
        self.topic_arns = topic_arns
        self.session_factory = session_factory
        self.session = session_factory()
        self.client = self.session.client('sns')

    @staticmethod
    def _parse_arn(arn):
        parts = arn.split(':')
        region, topic_name = parts[3], parts[5]
        statement_id = 'sns-topic-' + topic_name
        return region, topic_name, statement_id

    def add(self, func):
        lambda_client = self.session.client('lambda')
        for arn in self.topic_arns:
            region, topic_name, statement_id = self._parse_arn(arn)

            log.info("Subscribing %s to %s" % (func.name, topic_name))

            # Add permission to lambda for sns invocation.
            try:
                lambda_client.add_permission(
                    FunctionName=func.name,
                    StatementId='sns-topic-' + topic_name,
                    SourceArn=arn,
                    Action='lambda:InvokeFunction',
                    Principal='sns.amazonaws.com')
                log.debug("Added permission for sns to invoke lambda")
                # iam eventual consistency and propagation
                time.sleep(self.iam_delay)
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceConflictException':
                    raise

            # Subscribe the lambda to the topic.
            topic = self.session.resource('sns').Topic(arn)
            topic.subscribe(Protocol='lambda', Endpoint=func.arn)  # idempotent

    def remove(self, func):
        lambda_client = self.session.client('lambda')
        for topic_arn in self.topic_arns:
            region, topic_name, statement_id = self._parse_arn(topic_arn)

            try:
                response = lambda_client.remove_permission(
                    FunctionName=func.name,
                    StatementId=statement_id)
                log.debug("Removed lambda permission result: %s" % response)
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceNotFoundException':
                    raise

            paginator = self.client.get_paginator('list_subscriptions_by_topic')

            class Done(Exception):
                pass
            try:
                for page in paginator.paginate(TopicArn=topic_arn):
                    for subscription in page['Subscriptions']:
                        if subscription['Endpoint'] != func.arn:
                            continue
                        try:
                            response = self.client.unsubscribe(
                                SubscriptionArn=subscription['SubscriptionArn'])
                            log.debug("Unsubscribed %s from %s" %
                                (func.name, topic_name))
                        except ClientError as e:
                            code = e.response['Error']['Code']
                            if code != 'ResourceNotFoundException':
                                raise
                        raise Done  # break out of both for loops
            except Done:
                pass


class BucketSNSNotification(SNSSubscription):
    """ Subscribe a lambda to bucket notifications via SNS. """

    def __init__(self, session_factory, bucket, topic=None):
        # NB: We are overwriting __init__ vs. extending.
        self.session_factory = session_factory
        self.session = session_factory()
        self.topic_arns = self.get_topic(bucket) if topic is None else [topic]
        self.client = self.session.client('sns')

    def get_topic(self, bucket):
        session = local_session(self.session_factory)
        sns = session.client('sns')
        s3 = session.client('s3')

        notifies = bucket['Notification']
        if 'TopicConfigurations' not in notifies:
            notifies['TopicConfigurations'] = []
        all_topics = notifies['TopicConfigurations']
        topic_arns = [t['TopicArn'] for t in all_topics
                      if 's3:ObjectCreated:*' in t['Events']]
        if not topic_arns:
            # No suitable existing topic. Create one.
            topic_arn = sns.create_topic(Name=bucket['Name'])['TopicArn']
            policy = {
                'Statement': [{
                    'Action': 'SNS:Publish',
                    'Effect': 'Allow',
                    'Resource': topic_arn,
                    'Principal': {'Service': 's3.amazonaws.com'}}]}
            sns.set_topic_attributes(
                TopicArn=topic_arn,
                AttributeName='Policy',
                AttributeValue=json.dumps(policy))
            notifies['TopicConfigurations'].append({
                'TopicArn': topic_arn,
                'Events': ['s3:ObjectCreated:*']})
            s3.put_bucket_notification_configuration(Bucket=bucket['Name'],
                NotificationConfiguration=notifies)
            topic_arns = [topic_arn]
        return topic_arns


class ConfigRule(object):
    """Use a lambda as a custom config rule.

    """

    def __init__(self, data, session_factory):
        self.data = data
        self.session_factory = session_factory
        self.session = session_factory()
        self.client = self.session.client('config')

    def __repr__(self):
        return "<ConfigRule>"

    def get_rule_params(self, func):
        # config does not support versions/aliases on lambda funcs
        func_arn = func.arn
        if func_arn.count(':') > 6:
            func_arn, version = func_arn.rsplit(':', 1)

        params = dict(
            ConfigRuleName=func.name,
            Description=func.description,
            Source={
                'Owner': 'CUSTOM_LAMBDA',
                'SourceIdentifier': func_arn,
                'SourceDetails': [{
                    'EventSource': 'aws.config',
                    'MessageType': 'ConfigurationItemChangeNotification'}]
            }
        )

        if isinstance(func, PolicyLambda):
            manager = func.policy.get_resource_manager()
            config_type = manager.get_model().config_type
            params['Scope'] = {
                'ComplianceResourceTypes': [config_type]}
        else:
            params['Scope']['ComplianceResourceTypes'] = self.data.get(
                'resource-types', ())
        return params

    def get(self, rule_name):
        rules = resource_exists(
            self.client.describe_config_rules,
            ConfigRuleNames=[rule_name],
            NotFound="NoSuchConfigRuleException")
        if not rules:
            return rules
        return rules['ConfigRules'][0]

    @staticmethod
    def delta(rule, params):
        # doesn't seem like we have anything mutable at the moment,
        # since we restrict params, maybe reusing the same policy name
        # with a different resource type.
        if rule['Scope'] != params['Scope']:
            return True
        if rule['Source'] != params['Source']:
            return True
        if rule.get('Description', '') != rule.get('Description', ''):
            return True
        return False

    def add(self, func):
        rule = self.get(func.name)
        params = self.get_rule_params(func)

        if rule and self.delta(rule, params):
            log.debug("Updating config rule for %s" % self)
            rule.update(params)
            return self.client.put_config_rule(ConfigRule=rule)
        elif rule:
            log.debug("Config rule up to date")
            return
        try:
            self.session.client('lambda').add_permission(
                FunctionName=func.name,
                StatementId=func.name,
                SourceAccount=func.arn.split(':')[4],
                Action='lambda:InvokeFunction',
                Principal='config.amazonaws.com')
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceConflictException':
                raise

        log.debug("Adding config rule for %s" % func.name)
        return self.client.put_config_rule(ConfigRule=params)

    def remove(self, func):
        rule = self.get(func.name)
        if not rule:
            return
        try:
            self.client.delete_config_rule(
                ConfigRuleName=func.name)
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                raise
