# Copyright 2018 Capital One Services, LLC
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

from c7n.provider import clouds

from collections import Counter
import contextlib
import copy
import datetime
import itertools
import logging
import os
import operator
import shutil
import sys
import tempfile
import time
import traceback

import boto3

from c7n.credentials import SessionFactory
from c7n.config import Bag
from c7n.log import CloudWatchLogHandler

# Import output registries aws provider extends.
from c7n.output import (
    api_stats_outputs,
    blob_outputs,
    log_outputs,
    metrics_outputs,
    tracer_outputs
)

# Output base implementations we extend.
from c7n.output import (
    Metrics,
    DeltaStats,
    DirectoryOutput,
    LogOutput,
)

from c7n.registry import PluginRegistry
from c7n import credentials, utils

log = logging.getLogger('custodian.aws')

try:
    from aws_xray_sdk.core import xray_recorder, patch
    from aws_xray_sdk.core.context import Context
    HAVE_XRAY = True
except ImportError:
    HAVE_XRAY = False
    class Context(object): pass  # NOQA

_profile_session = None


DEFAULT_NAMESPACE = "CloudMaid"


def get_profile_session(options):
    global _profile_session
    if _profile_session:
        return _profile_session

    profile = getattr(options, 'profile', None)
    _profile_session = boto3.Session(profile_name=profile)
    return _profile_session


def _default_region(options):
    marker = object()
    value = getattr(options, 'regions', marker)
    if value is marker:
        return

    if len(value) > 0:
        return

    try:
        options.regions = [get_profile_session(options).region_name]
    except Exception:
        log.warning('Could not determine default region')
        options.regions = [None]

    if options.regions[0] is None:
        log.error('No default region set. Specify a default via AWS_DEFAULT_REGION '
                  'or setting a region in ~/.aws/config')
        sys.exit(1)

    log.debug("using default region:%s from boto" % options.regions[0])


def _default_account_id(options):
    if options.assume_role:
        try:
            options.account_id = options.assume_role.split(':')[4]
            return
        except IndexError:
            pass
    try:
        session = get_profile_session(options)
        options.account_id = utils.get_account_id_from_sts(session)
    except Exception:
        options.account_id = None


@metrics_outputs.register('aws')
class MetricsOutput(Metrics):
    """Send metrics data to cloudwatch
    """

    permissions = ("cloudWatch:PutMetricData",)
    retry = staticmethod(utils.get_retry(('Throttling',)))

    def __init__(self, ctx, config=None):
        super(MetricsOutput, self).__init__(ctx, config)
        self.namespace = self.config.get('namespace', DEFAULT_NAMESPACE)

    def _format_metric(self, key, value, unit, dimensions):
        d = {
            "MetricName": key,
            "Timestamp": datetime.datetime.utcnow(),
            "Value": value,
            "Unit": unit}
        d["Dimensions"] = [
            {"Name": "Policy", "Value": self.ctx.policy.name},
            {"Name": "ResType", "Value": self.ctx.policy.resource_type}]
        for k, v in dimensions.items():
            d['Dimensions'].append({"Name": k, "Value": v})
        return d

    def _put_metrics(self, ns, metrics):
        watch = utils.local_session(self.ctx.session_factory).client('cloudwatch')
        return self.retry(
            watch.put_metric_data, Namespace=ns, MetricData=metrics)


@log_outputs.register('aws')
class CloudWatchLogOutput(LogOutput):

    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'

    def get_handler(self):
        return CloudWatchLogHandler(
            log_group=self.ctx.options.log_group,
            log_stream=self.ctx.policy.name,
            session_factory=lambda x=None: self.ctx.session_factory(
                assume=False))

    def __repr__(self):
        return "<%s to group:%s stream:%s>" % (
            self.__class__.__name__,
            self.ctx.options.log_group,
            self.ctx.policy.name)


class XrayEmitter(object):

    def __init__(self):
        self.buf = []
        self.client = None

    def send_entity(self, entity):
        self.buf.append(entity)
        if len(self.buf) > 49:
            self.flush()

    def flush(self):
        buf = self.buf
        self.buf = []
        for segment_set in utils.chunks(buf, 50):
            self.client.put_trace_segments(
                TraceSegmentDocuments=[
                    s.serialize() for s in segment_set])


class XrayContext(Context):

    def __init__(self, *args, **kw):
        super(XrayContext, self).__init__(*args, **kw)
        # We want process global semantics as policy execution
        # can span threads.
        self._local = Bag()
        self._current_subsegment = None

    def handle_context_missing(self):
        """Custodian has a few api calls out of band of policy execution.

        - Resolving account alias.
        - Cloudwatch Log group/stream discovery/creation (when using -l on cli)

        Also we want to folks to optionally based on configuration using xray
        so default to disabling context missing output.
        """


@tracer_outputs.register('xray', condition=HAVE_XRAY)
class XrayTracer(object):

    emitter = XrayEmitter()

    in_lambda = 'LAMBDA_TASK_ROOT' in os.environ
    use_daemon = 'AWS_XRAY_DAEMON_ADDRESS' in os.environ
    service_name = 'custodian'

    context = XrayContext()
    if HAVE_XRAY:
        xray_recorder.configure(
            emitter=use_daemon is False and emitter or None,
            context=context,
            sampling=True,
            context_missing='LOG_ERROR'
        )
        patch(['boto3', 'requests'])
        logging.getLogger('aws_xray_sdk.core').setLevel(logging.ERROR)

    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config or {}
        self.client = None
        self.metadata = {}

    @contextlib.contextmanager
    def subsegment(self, name):
        segment = xray_recorder.begin_subsegment(name)
        try:
            yield segment
        except Exception as e:
            stack = traceback.extract_stack(limit=xray_recorder.max_trace_back)
            segment.add_exception(e, stack)
            raise
        finally:
            xray_recorder.end_subsegment(time.time())

    def __enter__(self):
        if self.client is None:
            self.client = self.ctx.session_factory(assume=False).client('xray')

        self.emitter.client = self.client

        if self.in_lambda:
            self.segment = xray_recorder.begin_subsegment(self.service_name)
        else:
            self.segment = xray_recorder.begin_segment(
                self.service_name, sampling=True)

        p = self.ctx.policy
        xray_recorder.put_annotation('policy', p.name)
        xray_recorder.put_annotation('resource', p.resource_type)
        if self.ctx.options.account_id:
            xray_recorder.put_annotation('account', self.ctx.options.account_id)

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        metadata = self.ctx.get_metadata(('api-stats',))
        metadata.update(self.metadata)
        xray_recorder.put_metadata('custodian', metadata)
        if self.in_lambda:
            xray_recorder.end_subsegment()
            return
        xray_recorder.end_segment()
        if not self.use_daemon:
            self.emitter.flush()
        self.metadata.clear()


@api_stats_outputs.register('aws')
class ApiStats(DeltaStats):

    def __init__(self, ctx, config=None):
        super(ApiStats, self).__init__(ctx, config)
        self.api_calls = Counter()

    def get_snapshot(self):
        return dict(self.api_calls)

    def get_metadata(self):
        return self.get_snapshot()

    def __enter__(self):
        if isinstance(self.ctx.session_factory, credentials.SessionFactory):
            self.ctx.session_factory.set_subscribers((self,))
        self.push_snapshot()

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        if isinstance(self.ctx.session_factory, credentials.SessionFactory):
            self.ctx.session_factory.set_subscribers(())

        # With cached sessions, we need to unregister any events subscribers
        # on extant sessions to allow for the next registration.
        utils.local_session(self.ctx.session_factory).events.unregister(
            'after-call.*.*', self._record, unique_id='c7n-api-stats')

        self.ctx.metrics.put_metric(
            "ApiCalls", sum(self.api_calls.values()), "Count")
        self.pop_snapshot()

    def __call__(self, s):
        s.events.register(
            'after-call.*.*', self._record, unique_id='c7n-api-stats')

    def _record(self, http_response, parsed, model, **kwargs):
        self.api_calls["%s.%s" % (
            model.service_model.endpoint_prefix, model.name)] += 1


@blob_outputs.register('s3')
class S3Output(DirectoryOutput):
    """
    Usage:

    .. code-block:: python

       with S3Output(session_factory, 's3://bucket/prefix'):
           log.info('xyz')  # -> log messages sent to custodian-run.log.gz

    """

    permissions = ('S3:PutObject',)

    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config
        self.output_path = self.get_output_path(self.config['url'])
        self.s3_path, self.bucket, self.key_prefix = utils.parse_s3(
            self.output_path)
        self.root_dir = tempfile.mkdtemp()
        self.transfer = None

    def __repr__(self):
        return "<%s to bucket:%s prefix:%s>" % (
            self.__class__.__name__,
            self.bucket,
            self.key_prefix)

    def get_output_path(self, output_url):
        if '{' not in output_url:
            date_path = datetime.datetime.now().strftime('%Y/%m/%d/%H')
            return self.join(
                output_url, self.ctx.policy.name, date_path)
        return output_url.format(**self.get_output_vars())

    @staticmethod
    def join(*parts):
        return "/".join([s.strip('/') for s in parts])

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        from boto3.s3.transfer import S3Transfer
        if exc_type is not None:
            log.exception("Error while executing policy")
        log.debug("Uploading policy logs")
        self.compress()
        self.transfer = S3Transfer(
            self.ctx.session_factory(assume=False).client('s3'))
        self.upload()
        shutil.rmtree(self.root_dir)
        log.debug("Policy Logs uploaded")

    def upload(self):
        for root, dirs, files in os.walk(self.root_dir):
            for f in files:
                key = "%s%s" % (
                    self.key_prefix,
                    "%s/%s" % (
                        root[len(self.root_dir):], f))
                key = key.strip('/')
                self.transfer.upload_file(
                    os.path.join(root, f), self.bucket, key,
                    extra_args={
                        'ACL': 'bucket-owner-full-control',
                        'ServerSideEncryption': 'AES256'})


@clouds.register('aws')
class AWS(object):

    resource_prefix = 'aws'
    # legacy path for older plugins
    resources = PluginRegistry('resources')

    def initialize(self, options):
        """
        """
        _default_region(options)
        _default_account_id(options)
        return options

    def get_session_factory(self, options):
        return SessionFactory(
            options.region,
            options.profile,
            options.assume_role,
            options.external_id)

    def initialize_policies(self, policy_collection, options):
        """Return a set of policies targetted to the given regions.

        Supports symbolic regions like 'all'. This will automatically
        filter out policies if their being targetted to a region that
        does not support the service. Global services will target a
        single region (us-east-1 if only all specified, else first
        region in the list).

        Note for region partitions (govcloud and china) an explicit
        region from the partition must be passed in.
        """
        from c7n.policy import Policy, PolicyCollection
        policies = []
        service_region_map, resource_service_map = get_service_region_map(
            options.regions, policy_collection.resource_types)

        for p in policy_collection:
            if 'aws.' in p.resource_type:
                _, resource_type = p.resource_type.split('.', 1)
            else:
                resource_type = p.resource_type
            available_regions = service_region_map.get(
                resource_service_map.get(resource_type), ())

            # its a global service/endpoint, use user provided region
            # or us-east-1.
            if not available_regions and options.regions:
                candidates = [r for r in options.regions if r != 'all']
                candidate = candidates and candidates[0] or 'us-east-1'
                svc_regions = [candidate]
            elif 'all' in options.regions:
                svc_regions = available_regions
            else:
                svc_regions = options.regions

            for region in svc_regions:
                if available_regions and region not in available_regions:
                    level = ('all' in options.regions and
                             logging.DEBUG or logging.WARNING)
                    # TODO: fixme
                    policy_collection.log.log(
                        level, "policy:%s resources:%s not available in region:%s",
                        p.name, p.resource_type, region)
                    continue
                options_copy = copy.copy(options)
                options_copy.region = str(region)

                if len(options.regions) > 1 or 'all' in options.regions and getattr(
                        options, 'output_dir', None):
                    options_copy.output_dir = (
                        options.output_dir.rstrip('/') + '/%s' % region)
                policies.append(
                    Policy(p.data, options_copy,
                           session_factory=policy_collection.session_factory()))

        return PolicyCollection(
            # order policies by region to minimize local session invalidation.
            # note relative ordering of policies must be preserved, python sort
            # is stable.
            sorted(policies, key=operator.attrgetter('options.region')),
            options)


def get_service_region_map(regions, resource_types):
    # we're not interacting with the apis just using the sdk meta information.
    session = boto3.Session(
        region_name='us-east-1',
        aws_access_key_id='never',
        aws_secret_access_key='found')
    normalized_types = []
    for r in resource_types:
        if r.startswith('aws.'):
            normalized_types.append(r[4:])
        else:
            normalized_types.append(r)

    resource_service_map = {
        r: clouds['aws'].resources.get(r).resource_type.service
        for r in normalized_types if r != 'account'}
    # support for govcloud and china, we only utilize these regions if they
    # are explicitly passed in on the cli.
    partition_regions = {}
    for p in ('aws-cn', 'aws-us-gov'):
        for r in session.get_available_regions('s3', partition_name=p):
            partition_regions[r] = p

    partitions = ['aws']
    for r in regions:
        if r in partition_regions:
            partitions.append(partition_regions[r])

    service_region_map = {}
    for s in set(itertools.chain(resource_service_map.values())):
        for partition in partitions:
            service_region_map.setdefault(s, []).extend(
                session.get_available_regions(s, partition_name=partition))
    return service_region_map, resource_service_map
