# Copyright 2015-2017 Capital One Services, LLC
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
Outputs metrics, logs, structured records across
a variety of sources.

See docs/usage/outputs.rst

"""
from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import gzip
import logging
import shutil
import tempfile

import os

from c7n.registry import PluginRegistry
from c7n.log import CloudWatchLogHandler
from c7n.utils import chunks, local_session, parse_s3, get_retry

DEFAULT_NAMESPACE = "CloudMaid"

log = logging.getLogger('custodian.output')


metrics_outputs = PluginRegistry('c7n.blob-outputs')
blob_outputs = PluginRegistry('c7n.blob-outputs')


@metrics_outputs.register('aws')
class MetricsOutput(object):
    """Send metrics data to cloudwatch
    """

    permissions = ("cloudWatch:PutMetricData",)

    retry = staticmethod(get_retry(('Throttling',)))

    BUFFER_SIZE = 20

    @staticmethod
    def select(metrics_selector):
        if not metrics_selector:
            return NullMetricsOutput
        # Compatibility for boolean configuration
        if isinstance(metrics_selector, bool):
            metrics_selector = 'aws'
        for k in metrics_outputs.keys():
            if k.startswith(metrics_selector):
                return metrics_outputs[k]
        raise ValueError("invalid metrics option %r" % metrics_selector)

    def __init__(self, ctx, namespace=DEFAULT_NAMESPACE):
        self.ctx = ctx
        self.namespace = namespace
        self.buf = []

    def get_timestamp(self):
        """
        Now, if C7N_METRICS_TZ is set to TRUE, UTC timestamp will be used.
        For backwards compatibility, if it is not set, UTC will be the default.
        To disable this and use the system's time zone, C7N_METRICS_TZ shoule be set to FALSE.
        """

        if os.getenv("C7N_METRICS_TZ", 'TRUE').upper() in ('TRUE', ''):
            return datetime.datetime.utcnow()
        else:
            return datetime.datetime.now()

    def flush(self):
        if self.buf:
            self._put_metrics(self.namespace, self.buf)
            self.buf = []

    def put_metric(self, key, value, unit, buffer=True, **dimensions):
        point = self._format_metric(key, value, unit, dimensions)
        self.buf.append(point)
        if buffer:
            # Max metrics in a single request
            if len(self.buf) == 20:
                self.flush()
        else:
            self.flush()

    def _format_metric(self, key, value, unit, dimensions):
        d = {
            "MetricName": key,
            "Timestamp": self.get_timestamp(),
            "Value": value,
            "Unit": unit}
        d["Dimensions"] = [
            {"Name": "Policy", "Value": self.ctx.policy.name},
            {"Name": "ResType", "Value": self.ctx.policy.resource_type}]
        for k, v in dimensions.items():
            d['Dimensions'].append({"Name": k, "Value": v})
        return d

    def _put_metrics(self, ns, metrics):
        watch = local_session(self.ctx.session_factory).client('cloudwatch')
        for metric_values in chunks(metrics, self.BUFFER_SIZE):
            return self.retry(
                watch.put_metric_data, Namespace=ns, MetricData=metrics)


class NullMetricsOutput(MetricsOutput):

    permissions = ()

    def __init__(self, ctx, namespace=DEFAULT_NAMESPACE):
        super(NullMetricsOutput, self).__init__(ctx, namespace)
        self.data = []

    def _put_metrics(self, ns, metrics):
        self.data.append({'Namespace': ns, 'MetricData': metrics})
        for m in metrics:
            if m['MetricName'] not in ('ActionTime', 'ResourceTime'):
                log.debug(self.format_metric(m))

    def format_metric(self, m):
        label = "metric:%s %s:%s" % (m['MetricName'], m['Unit'], m['Value'])
        for d in m['Dimensions']:
            label += " %s:%s" % (d['Name'].lower(), d['Value'].lower())
        return label


class LogOutput(object):

    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    def __init__(self, ctx):
        self.ctx = ctx

    def get_handler(self):
        raise NotImplementedError()

    def __enter__(self):
        log.debug("Storing output with %s" % repr(self))
        self.join_log()
        return self

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        self.leave_log()
        if exc_type is not None:
            log.exception("Error while executing policy")

    def join_log(self):
        self.handler = self.get_handler()
        self.handler.setLevel(logging.DEBUG)
        self.handler.setFormatter(logging.Formatter(self.log_format))
        mlog = logging.getLogger('custodian')
        mlog.addHandler(self.handler)

    def leave_log(self):
        mlog = logging.getLogger('custodian')
        mlog.removeHandler(self.handler)
        self.handler.flush()
        self.handler.close()


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


class FSOutput(LogOutput):

    @staticmethod
    def select(path):
        for k in blob_outputs.keys():
            if path.startswith('%s://' % k):
                return blob_outputs[k]
        # Fall back local disk
        return blob_outputs['file']

    @staticmethod
    def join(*parts):
        return os.path.join(*parts)

    def __init__(self, ctx):
        super(FSOutput, self).__init__(ctx)
        self.root_dir = self.ctx.output_path or tempfile.mkdtemp()

    def get_handler(self):
        return logging.FileHandler(
            os.path.join(self.root_dir, 'custodian-run.log'))

    def compress(self):
        # Compress files individually so thats easy to walk them, without
        # downloading tar and extracting.
        for root, dirs, files in os.walk(self.root_dir):
            for f in files:
                fp = os.path.join(root, f)
                with gzip.open(fp + ".gz", "wb", compresslevel=7) as zfh:
                    with open(fp, "rb") as sfh:
                        shutil.copyfileobj(sfh, zfh, length=2**15)
                    os.remove(fp)


@blob_outputs.register('file')
class DirectoryOutput(FSOutput):

    permissions = ()

    def __init__(self, ctx):
        super(DirectoryOutput, self).__init__(ctx)
        if self.root_dir.startswith('file://'):
            self.root_dir = self.root_dir[len('file://'):]
        if self.ctx.output_path is not None:
            if not os.path.exists(self.root_dir):
                os.makedirs(self.root_dir)

    def __repr__(self):
        return "<%s to dir:%s>" % (self.__class__.__name__, self.root_dir)


@blob_outputs.register('s3')
class S3Output(FSOutput):
    """
    Usage:

    .. code-block:: python

       with S3Output(session_factory, 's3://bucket/prefix'):
           log.info('xyz')  # -> log messages sent to custodian-run.log.gz

    """

    permissions = ('S3:PutObject',)

    def __init__(self, ctx):
        super(S3Output, self).__init__(ctx)
        self.date_path = datetime.datetime.now().strftime('%Y/%m/%d/%H')
        self.s3_path, self.bucket, self.key_prefix = parse_s3(
            self.ctx.output_path)
        self.root_dir = tempfile.mkdtemp()
        self.transfer = None

    def __repr__(self):
        return "<%s to bucket:%s prefix:%s>" % (
            self.__class__.__name__,
            self.bucket,
            "%s/%s" % (self.key_prefix, self.date_path))

    @staticmethod
    def join(*parts):
        return "/".join([s.strip('/') for s in parts])

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        from boto3.s3.transfer import S3Transfer, TransferConfig
        if exc_type is not None:
            log.exception("Error while executing policy")
        log.debug("Uploading policy logs")
        self.leave_log()
        self.compress()
        self.transfer = S3Transfer(
            self.ctx.session_factory(assume=False).client('s3'),
            config=TransferConfig(use_threads=False))
        self.upload()
        shutil.rmtree(self.root_dir)
        log.debug("Policy Logs uploaded")

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
                        'ACL': 'bucket-owner-full-control',
                        'ServerSideEncryption': 'AES256'})
