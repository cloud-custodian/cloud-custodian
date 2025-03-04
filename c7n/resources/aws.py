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
import socket
import sys
import time
import threading
import traceback
from urllib import parse as urlparse
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

import boto3

from botocore.validate import ParamValidator
from boto3.s3.transfer import S3Transfer

from c7n.credentials import SessionFactory
from c7n.config import Bag
from c7n.exceptions import InvalidOutputConfig, PolicyValidationError
from c7n.log import CloudWatchLogHandler
from c7n.utils import parse_url_config, backoff_delays

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


def _default_bucket_region(options):
    # modify options to format s3 output urls with explicit region.
    if not options.output_dir.startswith('s3://'):
        return

    parsed = urlparse.urlparse(options.output_dir)
    s3_conf = parse_url_config(options.output_dir)
    if parsed.query and s3_conf.get("region"):
        return

    # s3 clients default to us-east-1 if no region is specified, but for partition
    # support we default to using a passed in region if given.
    region = None
    if options.regions:
        region = options.regions[0]

    # we're operating pre the expansion of symbolic name all into actual regions.
    if region == "all":
        region = None

    try:
        options.output_dir = get_bucket_url_with_region(options.output_dir, region)
    except ValueError as err:
        invalid_output = InvalidOutputConfig(str(err))
        invalid_output.__suppress_context__ = True
        raise invalid_output


def shape_validate(params, shape_name, service):
    session = fake_session()._session
    model = session.get_service_model(service)
    shape = model.shape_for(shape_name)
    validator = ParamValidator()
    report = validator.validate(params, shape)
    if report.has_errors():
        raise PolicyValidationError(report.generate_report())


def get_bucket_url_with_region(bucket_url, region):
    parsed = urlparse.urlparse(bucket_url)
    s3_conf = parse_url_config(bucket_url)
    params = {}
    if region:
        params['region_name'] = region

    client = boto3.client('s3', **params)
    region = inspect_bucket_region(s3_conf.netloc, client.meta.endpoint_url)
    if not region:
        raise ValueError(f"could not determine region for output bucket, use explicit ?region=region_name. {s3_conf.url}")  # noqa
    query = f"region={region}"
    if parsed.query:
        query = parsed.query + f"&region={region}"
    parts = parsed._replace(
        path=parsed.path.strip("/"),
        query=query
    )
    return urlparse.urlunparse(parts)


def inspect_bucket_region(bucket, s3_endpoint, allow_public=False):
    """Attempt to determine a bucket region without a client

    We can make an unauthenticated HTTP HEAD request to S3 in an attempt to find a bucket's
    region. This avoids some issues with cross-account/cross-region uses of the
    GetBucketLocation or HeadBucket API action. Because bucket names are unique within
    AWS partitions, we can make requests to a single regional S3 endpoint
    and get redirected if a bucket lives in another region within the
    same partition.

    This approach is inspired by some sample code from a Go SDK issue comment,
    which @sean-zou mentioned in #7593:

    https://github.com/aws/aws-sdk-go/issues/720#issuecomment-613038544

    Return a region string, or None if we're unable to determine one.
    """
    region = None
    s3_endpoint_parts = urlparse.urlparse(s3_endpoint)
    # Use a "path-style" S3 URL here to avoid failing TLS certificate validation
    # on buckets with a dot in the name.
    #
    # According to the following blog post, before deprecating path-style
    # URLs AWS will provide a way for virtual-hosted-style URLs to handle
    # buckets with dots in their names. Using path-style URLs here in
    # the meantime seems reasonable, compared to alternatives like forcing
    # HTTP or ignoring certificate validation.
    #
    # https://aws.amazon.com/blogs/aws/amazon-s3-path-deprecation-plan-the-rest-of-the-story/
    bucket_endpoint = f'https://{s3_endpoint_parts.netloc}/{bucket}'
    request = Request(bucket_endpoint, method='HEAD')
    try:
        # For private buckets the head request will always raise an
        # http error, the status code and response headers provide
        # context for where the bucket is. For public buckets we
        # default to raising an exception as unsuitable location at
        # least for the output use case.
        #
        # Dynamic use of urllib trips up static analyzers because of
        # the potential to accidentally allow unexpected schemes like
        # file:/. Here we're hardcoding the https scheme, so we can
        # ignore those specific checks.
        #
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected # noqa
        response = url_socket_retry(urlopen, request)  # nosec B310
        # Successful response indicates a public accessible bucket in the same region
        region = response.headers.get('x-amz-bucket-region')

        if not allow_public:
            raise ValueError("bucket: '{bucket}' is publicly accessible")
    except HTTPError as err:
        # Returns 404 'Not Found' for buckets that don't exist
        if err.status == 404:
            raise ValueError(f"bucket '{bucket}' does not exist")
        # Permission errors (403) or redirects (301) for valid buckets
        # should still contain a header we can use to determine the
        # bucket region. Permission errors are indicative of correct
        # region, while redirects are for cross region.
        region = err.headers.get('x-amz-bucket-region')

    return region


def url_socket_retry(func, *args, **kw):
    """retry a urllib operation in the event of certain errors.

    we want to retry on some common issues for cases where we are
    connecting through an intermediary proxy or where the downstream
    is overloaded.

    socket errors
     - 104 - Connection reset by peer
     - 110 - Connection timed out

    http errors
     - 503 - Slow Down | Service Unavailable
    """
    min_delay = 1
    max_delay = 32
    max_attempts = 4

    for idx, delay in enumerate(
            backoff_delays(min_delay, max_delay, jitter=True)):
        try:
            return func(*args, **kw)
        except HTTPError as err:
            if not (err.status == 503 and 'Slow Down' in err.reason):
                raise
            if idx == max_attempts - 1:
                raise
        except URLError as err:
            if not isinstance(err.reason, socket.error):
                raise
            if err.reason.errno not in (104, 110):
                raise
            if idx == max_attempts - 1:
                raise

        time.sleep(delay)


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
        if isinstance(arn, Arn):
            return arn
        parts = arn.split(':', 5)
        if len(parts) < 3:
            raise ValueError("Invalid Arn")
        # a few resources use qualifiers without specifying type
        if parts[2] in ('s3', 'apigateway', 'execute-api', 'emr-serverless'):
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
        # replace the literal 'arn' string with raw arn
        parts[0] = arn
        return cls(*parts)


class ArnResolver:

    def __init__(self, manager):
        self.manager = manager

    def resolve(self, arns):
        arns = map(Arn.parse, arns)
        a_service = operator.attrgetter('service')
        a_resource = operator.attrgetter('resource_type')
        kfunc = lambda a: (a_service(a), a_resource(a))  # noqa
        arns = sorted(arns, key=kfunc)
        results = {}
        for (service, arn_type), arn_set in itertools.groupby(arns, key=kfunc):
            arn_set = list(arn_set)
            rtype = ArnResolver.resolve_type(arn_set[0])
            rmanager = self.manager.get_resource_manager(rtype)
            if rtype == 'sns':
                resources = rmanager.get_resources(
                    [rarn.arn for rarn in arn_set])
            else:
                resources = rmanager.get_resources(
                    [rarn.resource for rarn in arn_set])
            for rarn, r in zip(rmanager.get_arns(resources), resources):
                results[rarn] = r

            for rarn in arn_set:
                if rarn.arn not in results:
                    results[rarn.arn] = None
        return results

    @staticmethod
    def resolve_type(arn):
        arn = Arn.parse(arn)

        # this would benefit from a class cache {service} -> rtypes
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
            elif (klass.resource_type.arn_service == arn.service and
                    klass.resource_type.arn_type == ""):
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
        self.ignore_zero = self.config.get('ignore_zero')
        am = self.config.get('active_metrics')
        self.active_metrics = am and am.split(',')
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

        # NOTE filter out value is 0 metrics data
        if self.ignore_zero in ['1', 'true', 'True']:
            metrics = [m for m in metrics if m.get("Value") != 0]
        # NOTE filter metrics data by the metric name configured
        if self.active_metrics:
            metrics = [m for m in metrics if m["MetricName"] in self.active_metrics]
        if not metrics:
            return
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
        self._transfer = None

    @property
    def transfer(self):
        if self._transfer:
            return self._transfer
        bucket_region = self.config.region or None
        self._transfer = S3Transfer(
            self.ctx.session_factory(region=bucket_region, assume=False).client('s3'))
        return self._transfer

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
        _default_bucket_region(options)

        if options.tracer and options.tracer.startswith('xray') and HAVE_XRAY:
            XrayTracer.initialize(utils.parse_url_config(options.tracer))
        return options

    def get_session_factory(self, options):
        return SessionFactory(
            options.region,
            options.profile,
            options.assume_role,
            options.external_id,
            options.session_policy)

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
            options.regions, policy_collection.resource_types, self.type)
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
    output_url_parts = urlparse.urlparse(output_dir)
    # for output urls, the end of the url may be a
    # query string. make sure we add a suffix to
    # the path component.
    output_url_parts = output_url_parts._replace(
        path=output_url_parts.path.rstrip('/') + '/%s' % suffix
    )
    return urlparse.urlunparse(output_url_parts)


def fake_session():
    session = boto3.Session(  # nosec nosemgrep
        region_name='us-east-1',
        aws_access_key_id='never',
        aws_secret_access_key='found')
    return session


def get_service_region_map(regions, resource_types, provider='aws'):
    # we're not interacting with the apis just using the sdk meta information.

    session = fake_session()
    normalized_types = []
    for r in resource_types:
        if r.startswith('%s.' % provider):
            normalized_types.append(r[len(provider) + 1:])
        else:
            normalized_types.append(r)
    resource_service_map = {
        r: clouds[provider].resources.get(r).resource_type.service
        for r in normalized_types if r != 'account'}
    # support for govcloud, china, and iso. We only utilize these regions if they
    # are explicitly passed in on the cli.
    partition_regions = {}
    for p in ('aws-cn', 'aws-us-gov', 'aws-iso'):
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


def shape_schema(service, shape_name, drop_fields=()):
    """Expand a shape's schema using service model shape data

        Repurpose some of the shape discovery/validation logic in
        c7n.resources.aws.shape_validate() to dynamically expand
        element schema using the latest service model shape information.

        Include available properties, their types, and enumerations of
        possible values where available.

        Args:
            service (str): The AWS service for the element. (required)
            shape_name (str): The service model request shape name. (required)
            drop_fields (Tuple[str]): List of fields to drop from the schema
                (e.g. resource_id param).
     """

    # Mapping of service model shape types to json schema types
    TYPE_MAP = {
        'string': 'string',
        'structure': 'object',
        'list': 'array',
        'integer': 'integer',
        'boolean': 'boolean',
        'long': 'number',
        'double': 'number',
        'map': 'object'
    }

    def _expand_shape_schema(shape):
        schema = {}
        for member, member_shape in shape.members.items():
            if member in drop_fields:
                continue
            _type = TYPE_MAP.get(member_shape.type_name)
            if _type is None:
                raise KeyError(f"Unknown type for {member_shape.name}: {member_shape.type_name}")
            member_schema = {'type': _type}
            if enum := getattr(member_shape, 'enum', None):
                member_schema['enum'] = enum
            if member_shape.type_name == 'structure':
                member_schema["properties"] = _expand_shape_schema(member_shape)
            elif member_shape.type_name == 'list':
                if member_shape.member.type_name == 'structure':
                    member_schema["items"] = {
                        'type': 'object',
                        'properties': _expand_shape_schema(member_shape.member)
                    }
                else:
                    member_schema["items"] = {
                        'type': TYPE_MAP.get(member_shape.member.type_name)
                    }
            elif member_shape.type_name == 'map':
                if member_shape.value.type_name in ('structure', 'list'):
                    member_schema["patternProperties"] = {
                        "^.*$": _expand_shape_schema(member_shape.value)
                    }
                else:
                    member_schema["patternProperties"] = {
                        "^.*$": {
                            'type': TYPE_MAP.get(member_shape.value.type_name)
                        }
                    }

            schema[member] = member_schema
        return schema
