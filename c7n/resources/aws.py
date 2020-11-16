# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.provider import clouds, Provider

from collections import Counter, namedtuple
import contextlib
import copy
import datetime
import itertools
import logging
import os
import operator
import sys
import time
import threading
import traceback

import boto3

from botocore.validate import ParamValidator
from boto3.s3.transfer import S3Transfer

from c7n.credentials import SessionFactory
from c7n.config import Bag
from c7n.exceptions import PolicyValidationError
from c7n.log import CloudWatchLogHandler

from .resource_map import ResourceMap

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
    BlobOutput,
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
    class Context: pass  # NOQA

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
    if options.account_id:
        return
    elif options.assume_role:
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


def shape_validate(params, shape_name, service):
    session = fake_session()._session
    model = session.get_service_model(service)
    shape = model.shape_for(shape_name)
    validator = ParamValidator()
    report = validator.validate(params, shape)
    if report.has_errors():
        raise PolicyValidationError(report.generate_report())


class Arn(namedtuple('_Arn', (
        'arn', 'partition', 'service', 'region',
        'account_id', 'resource', 'resource_type', 'separator'))):

    __slots__ = ()

    def __repr__(self):
        return "<arn:%s:%s:%s:%s:%s%s%s>" % (
            self.partition,
            self.service,
            self.region,
            self.account_id,
            self.resource_type,
            self.separator,
            self.resource)

    @classmethod
    def parse(cls, arn):
        parts = arn.split(':', 5)
        # a few resources use qualifiers without specifying type
        if parts[2] in ('s3', 'apigateway', 'execute-api'):
            parts.append(None)
            parts.append(None)
        elif '/' in parts[-1]:
            parts.extend(reversed(parts.pop(-1).split('/', 1)))
            parts.append('/')
        elif ':' in parts[-1]:
            parts.extend(reversed(parts.pop(-1).split(':', 1)))
            parts.append(':')
        elif len(parts) == 6:
            parts.append('')
            parts.append('')
        return cls(*parts)


class ArnResolver:

    def __init__(self, manager):
        self.manager = manager

    @staticmethod
    def resolve_type(arn):
        for type_name, klass in AWS.resources.items():
            if type_name in ('rest-account', 'account') or klass.resource_type.arn is False:
                continue
            if arn.service != (klass.resource_type.arn_service or klass.resource_type.service):
                continue
            if (type_name in ('asg', 'ecs-task') and
                    "%s%s" % (klass.resource_type.arn_type, klass.resource_type.arn_separator)
                    in arn.resource_type):
                return type_name
            elif (klass.resource_type.arn_type is not None and
                    klass.resource_type.arn_type == arn.resource_type):
                return type_name


@metrics_outputs.register('aws')
class MetricsOutput(Metrics):
    """Send metrics data to cloudwatch
    """

    permissions = ("cloudWatch:PutMetricData",)
    retry = staticmethod(utils.get_retry(('Throttling',)))

    def __init__(self, ctx, config=None):
        super(MetricsOutput, self).__init__(ctx, config)
        self.namespace = self.config.get('namespace', DEFAULT_NAMESPACE)
        self.region = self.config.get('region')
        self.destination = (
            self.config.scheme == 'aws' and
            self.config.get('netloc') == 'master') and 'master' or None

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
            # Skip legacy static dimensions if using new capabilities
            if (self.destination or self.region) and k == 'Scope':
                continue
            d['Dimensions'].append({"Name": k, "Value": v})
        if self.region:
            d['Dimensions'].append(
                {'Name': 'Region', 'Value': self.ctx.options.region})
        if self.destination:
            d['Dimensions'].append(
                {'Name': 'Account', 'Value': self.ctx.options.account_id or ''})
        return d

    def _put_metrics(self, ns, metrics):
        if self.destination == 'master':
            watch = self.ctx.session_factory(
                assume=False).client('cloudwatch', region_name=self.region)
        else:
            watch = utils.local_session(
                self.ctx.session_factory).client('cloudwatch', region_name=self.region)
        return self.retry(
            watch.put_metric_data, Namespace=ns, MetricData=metrics)


@log_outputs.register('aws')
class CloudWatchLogOutput(LogOutput):

    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'

    def __init__(self, ctx, config=None):
        super(CloudWatchLogOutput, self).__init__(ctx, config)
        if self.config['netloc'] == 'master' or not self.config['netloc']:
            self.log_group = self.config['path'].strip('/')
        else:
            # join netloc to path for casual usages of aws://log/group/name
            self.log_group = ("%s/%s" % (
                self.config['netloc'], self.config['path'].strip('/'))).strip('/')
        self.region = self.config.get('region', ctx.options.region)
        self.destination = (
            self.config.scheme == 'aws' and
            self.config.get('netloc') == 'master') and 'master' or None

    def construct_stream_name(self):
        if self.config.get('stream') is None:
            log_stream = self.ctx.policy.name
            if self.config.get('region') is not None:
                log_stream = "{}/{}".format(self.ctx.options.region, log_stream)
            if self.config.get('netloc') == 'master':
                log_stream = "{}/{}".format(self.ctx.options.account_id, log_stream)
        else:
            log_stream = self.config.get('stream').format(
                region=self.ctx.options.region,
                account=self.ctx.options.account_id,
                policy=self.ctx.policy.name,
                now=datetime.datetime.utcnow())
        return log_stream

    def get_handler(self):
        log_stream = self.construct_stream_name()
        params = dict(
            log_group=self.log_group, log_stream=log_stream,
            session_factory=(
                lambda x=None: self.ctx.session_factory(
                    region=self.region, assume=self.destination != 'master')))
        return CloudWatchLogHandler(**params)

    def __repr__(self):
        return "<%s to group:%s stream:%s>" % (
            self.__class__.__name__,
            self.ctx.options.log_group,
            self.ctx.policy.name)


class XrayEmitter:
    # implement https://github.com/aws/aws-xray-sdk-python/issues/51

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
                TraceSegmentDocuments=[s.serialize() for s in segment_set])


class XrayContext(Context):
    """Specialized XRay Context for Custodian.

    A context is used as a segment storage stack for currently in
    progress segments.

    We use a customized context for custodian as policy execution
    commonly uses a concurrent.futures threadpool pattern during
    execution for api concurrency. Default xray semantics would use
    thread local storage and treat each of those as separate trace
    executions. We want to aggregate/associate all thread pool api
    executions to the custoidan policy execution. XRay sdk supports
    this via manual code for every thread pool usage, but we don't
    want to explicitly couple xray integration everywhere across the
    codebase. Instead we use a context that is aware of custodian
    usage of threads and associates subsegments therein to the policy
    execution active subsegment.
    """

    def __init__(self, *args, **kw):
        super(XrayContext, self).__init__(*args, **kw)
        self._local = Bag()
        self._current_subsegment = None
        self._main_tid = threading.get_ident()

    def handle_context_missing(self):
        """Custodian has a few api calls out of band of policy execution.

        - Resolving account alias.
        - Cloudwatch Log group/stream discovery/creation (when using -l on cli)

        Also we want to folks to optionally based on configuration using xray
        so default to disabling context missing output.
        """

    # Annotate any segments/subsegments with their thread ids.
    def put_segment(self, segment):
        if getattr(segment, 'thread_id', None) is None:
            segment.thread_id = threading.get_ident()
        super().put_segment(segment)

    def put_subsegment(self, subsegment):
        if getattr(subsegment, 'thread_id', None) is None:
            subsegment.thread_id = threading.get_ident()
        super().put_subsegment(subsegment)

    # Override since we're not just popping the end of the stack, we're removing
    # the thread subsegment from the array by identity.
    def end_subsegment(self, end_time):
        subsegment = self.get_trace_entity()
        if self._is_subsegment(subsegment):
            subsegment.close(end_time)
            self._local.entities.remove(subsegment)
            return True
        else:
            log.warning("No subsegment to end.")
            return False

    # Override get trace identity, any worker thread will find its own subsegment
    # on the stack, else will use the main thread's sub/segment
    def get_trace_entity(self):
        tid = threading.get_ident()
        entities = self._local.get('entities', ())
        for s in reversed(entities):
            if s.thread_id == tid:
                return s
            # custodian main thread won't advance (create new segment)
            # with worker threads still doing pool work.
            elif s.thread_id == self._main_tid:
                return s
        return self.handle_context_missing()


@tracer_outputs.register('xray', condition=HAVE_XRAY)
class XrayTracer:

    emitter = XrayEmitter()

    in_lambda = 'LAMBDA_TASK_ROOT' in os.environ
    use_daemon = 'AWS_XRAY_DAEMON_ADDRESS' in os.environ
    service_name = 'custodian'

    @classmethod
    def initialize(cls, config):
        context = XrayContext()
        sampling = config.get('sample', 'true') == 'true' and True or False
        xray_recorder.configure(
            emitter=cls.use_daemon is False and cls.emitter or None,
            context=context,
            sampling=sampling,
            context_missing='LOG_ERROR')
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
            log.info(
                ('View XRay Trace https://console.aws.amazon.com/xray/home?region=%s#/'
                 'traces/%s' % (self.ctx.options.region, self.segment.trace_id)))
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
class S3Output(BlobOutput):
    """
    Usage:

    .. code-block:: python

       with S3Output(session_factory, 's3://bucket/prefix'):
           log.info('xyz')  # -> log messages sent to custodian-run.log.gz

    """

    permissions = ('S3:PutObject',)

    def __init__(self, ctx, config):
        super().__init__(ctx, config)
        # can't use a local session as we dont want an unassumed session cached.
        self.transfer = S3Transfer(
            self.ctx.session_factory(assume=False).client('s3'))

    def upload_file(self, path, key):
        self.transfer.upload_file(
            path, self.bucket, key,
            extra_args={
                'ACL': 'bucket-owner-full-control',
                'ServerSideEncryption': 'AES256'})


@clouds.register('aws')
class AWS(Provider):

    display_name = 'AWS'
    resource_prefix = 'aws'
    # legacy path for older plugins
    resources = PluginRegistry('resources')
    # import paths for resources
    resource_map = ResourceMap

    def initialize(self, options):
        """
        """
        _default_region(options)
        _default_account_id(options)
        if options.tracer and options.tracer.startswith('xray') and HAVE_XRAY:
            XrayTracer.initialize(utils.parse_url_config(options.tracer))

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
        filter out policies if they are being targetted to a region that
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
        if 'all' in options.regions:
            enabled_regions = {
                r['RegionName'] for r in
                get_profile_session(options).client('ec2').describe_regions(
                    Filters=[{'Name': 'opt-in-status',
                              'Values': ['opt-in-not-required', 'opted-in']}]
                ).get('Regions')}
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
                svc_regions = list(set(available_regions).intersection(enabled_regions))
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
                    options_copy.output_dir = join_output(options.output_dir, region)
                policies.append(
                    Policy(p.data, options_copy,
                           session_factory=policy_collection.session_factory()))

        return PolicyCollection(
            # order policies by region to minimize local session invalidation.
            # note relative ordering of policies must be preserved, python sort
            # is stable.
            sorted(policies, key=operator.attrgetter('options.region')),
            options)


def join_output(output_dir, suffix):
    if '{region}' in output_dir:
        return output_dir.rstrip('/')
    if output_dir.endswith('://'):
        return output_dir + suffix
    return output_dir.rstrip('/') + '/%s' % suffix


def fake_session():
    session = boto3.Session(
        region_name='us-east-1',
        aws_access_key_id='never',
        aws_secret_access_key='found')
    return session


def get_service_region_map(regions, resource_types):
    # we're not interacting with the apis just using the sdk meta information.

    session = fake_session()
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
