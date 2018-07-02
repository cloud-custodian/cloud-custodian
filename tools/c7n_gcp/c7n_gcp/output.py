"""

Todo, provider policy execution initialization for outputs


"""
import datetime
import os
import tempfile
import time

# TODO drop these grpc variants for the REST versions, and we can drop
# protobuf/grpc deps, and also so we can record tests..
# gcp has three different python sdks all independently maintained .. hmmm...
# and random monkey shims on top of those :-(

from google.cloud.monitoring_v3 import MetricServiceClient
from google.cloud.monitoring_v3.types import TimeSeries
from google.cloud.logging import Client as LogClient
from google.cloud.logging.handlers import CloudLoggingHandler
from google.cloud.logging.resource import Resource

from c7n.output import MetricsOutput, LogOutput, FSOutput, blob_outputs
from c7n.utils import local_session


class StackDriverMonitoring(MetricsOutput):

    def put_metric(self, key, value, unit, buffer=False, **dimensions):
        pass

    def _format_metric(self, key, value, unit, buffer=False, **dimensions):
        series = TimeSeries()

        series.metrics.type = 'custom.googleapis.com/custodian/policy/%s' % key

        # Google controlled vocabulary with artificial limitations on resource type
        # there's not uch useful we can utilize.
        series.resource.type = 'global'

        # series.resource.labels['project_id'] =
        point = series.points.add()
        if unit == 'Count':
            point.value.int64 = value
        elif unit == 'Seconds':
            point.value.double_value = value
        now = time.time()
        point.interval.end_time.seconds = ns = int(now)
        point.interval.end_time.nanos = int((now - ns) * 10**9)
        return series

    def _put_metrics(self, ns, metrics):
        client = MetricServiceClient()
        client.create_time_series(metrics)


class StackDriverLogging(LogOutput):

    def get_handler(self):
        # gcp has three independent implementation of api bindings for python.
        # The one used by logging is not yet supported by our test recording.

        log_group = self.ctx.options.log_group
        if log_group.endswith('*'):
            log_group = "%s%s" % (log_group[:-1], self.ctx.policy.name)

        project_id = local_session(self.ctx.session_factory).get_default_project()
        client = LogClient(project_id)

        return CloudLoggingHandler(
            client,
            log_group,
            resource=Resource(type='project', labels={'project_id': project_id}))

    def leave_log(self):
        super(StackDriverLogging, self).leave_log()
        # Flush and stop the background thread
        self.handler.transport.flush()
        self.handler.transport.worker.stop()


@blob_outputs.register('gs')
class GCPStorageOutput(FSOutput):

    def __init__(self, ctx):
        super(GCPStorageOutput, self).__init__(ctx)
        self.date_path = datetime.datetime.now().strftime('%Y/%m/%d/%H')
        self.gs_path, self.bucket, self.key_prefix = parse_gs(
            self.ctx.output_path)
        self.root_dir = tempfile.mkdtemp()

    def __repr__(self):
        return "<%s to bucket:%s prefix:%s>" % (
            self.__class__.__name__,
            self.bucket,
            "%s/%s" % (self.key_prefix, self.date_path))

    def upload(self):
        for root, dirs, files in os.walk(self.root_dir):
            for f in files:
                key = "%s/%s%s" % (
                    self.key_prefix,
                    self.date_path,
                    "%s/%s" % (
                        root[len(self.root_dir):], f))
                key = key.strip('/')
                self.transfer.upload_file(
                    os.path.join(root, f), self.bucket, key,
                    extra_args={
                        'ServerSideEncryption': 'AES256'})


def parse_gs(gs_path):
    if not gs_path.startswith('gs://'):
        raise ValueError("Invalid gs path")
    ridx = gs_path.find('/', 5)
    if ridx == -1:
        ridx = None
    bucket = gs_path[5:ridx]
    gs_path = gs_path.rstrip('/')
    if ridx is None:
        key_prefix = ""
    else:
        key_prefix = gs_path[gs_path.find('/', 5):]
    return gs_path, bucket, key_prefix
