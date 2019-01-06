# Copyright 2018-2019 Capital One Services, LLC
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

TODO: provider policy execution initialization for outputs


"""
import datetime
import logging
import os
import tempfile
import time

from c7n.output import (
    blob_outputs,
    metrics_outputs,
    DirectoryOutput,
    Metrics,
    LogOutput)
from c7n.utils import local_session


@metrics_outputs.register('gcp')
class StackDriverMetrics(Metrics):

    METRICS_PREFIX = 'custom.googleapis.com/custodian/policy'

    DESCRIPTOR_COMMON = {
        'metricsKind': 'GAUGE',
        'labels': [{
            'key': 'policy',
            'valueType': 'STRING',
            'description': 'Custodian Policy'}],
    }

    METRICS_DESCRIPTORS = {
        'resourcecount': {
            'type': '%s/%'.format(METRICS_PREFIX, 'resourcecount'),
            'valueType': 'INT64',
            'units': 'items',
            'description': 'Number of resources that matched the given policy',
            'displayName': 'Resources',
        },
        'resourcetime': {
            'type': '%s/%s'.format(METRICS_PREFIX, 'resourcetime'),
            'valueType': 'DOUBLE',
            'units': 's',
            'description': 'Time to query the resources for a given policy',
            'displayName': 'Query Time',
        },
        'actiontime': {
            'type': '%s/%s'.format(METRICS_PREFIX, 'actiontime'),
            'valueType': 'DOUBLE',
            'units': 's',
            'description': 'Time to perform actions for a given policy',
            'displayName': 'Action Time',
        },
    }
    # Custom metrics docs https://tinyurl.com/y8rrghwc

    log = logging.getLogger('c7n_gcp.metrics')

    def __init__(self, ctx, config=None):
        super(StackDriverMetrics, self).__init__(ctx, config)
        self.project_id = local_session(
            self.ctx.session_factory).get_default_project()

    def initialize(self):
        """One time initialization of metrics descriptors.

        # tbd - unclear if this adding significant value.
        """
        client = local_session(self.ctx.session_factory).client(
            'monitoring', 'v3', 'projects.metricDescriptors')
        descriptor_map = {
            n['type'].rsplit('/', 1)[-1]: n for n in client.execute_command('list', {
                'name': 'projects/%s' % self.project_id,
                'filter': 'metric.type=startswith("{}")'.format(self.METRICS_PREFIX)}).get(
                    'metricsDescriptors', [])}
        created = False
        for name in self.METRICS_DESCRIPTORS:
            if name in descriptor_map:
                continue
            created = True
            md = self.METRICS_DESCRIPTORS[name]
            md.update(self.DESCRIPTOR_COMMON)
            client.execute_command(
                'create', {'name': 'projects/%s' % self.project_id, 'body': md})

        if created:
            self.log.info("Initializing StackDriver Metrics Descriptors")
            time.sleep(5)

    def _format_metric(self, key, value, unit, dimensions):
        # Resource is a Google controlled vocabulary with artificial
        # limitations on resource type there's not much useful we can
        # utilize.
        now = datetime.datetime.utcnow()
        metrics_series = {
            'metric': {
                'type': 'custom.googleapis.com/custodian/policy/%s' % key.lower(),
                'labels': {
                    'policy': self.ctx.policy.name,
                    'project_id': self.project_id
                },
            },
            'metricKind': 'GAUGE',
            'valueType': 'INT64',
            'resource': {
                'type': 'global',
            },
            'points': [{
                'interval': {
                    'endTime': now.isoformat('T') + 'Z',
                    'startTime': now.isoformat('T') + 'Z'},
                'value': {'int64Value': int(value)}}]
        }
        return metrics_series

    def _put_metrics(self, ns, metrics):
        session = local_session(self.ctx.session_factory)
        client = session.client('monitoring', 'v3', 'projects.timeSeries')
        params = {'name': "projects/{}".format(self.project_id),
                  'body': {'timeSeries': metrics}}
        client.execute_command('create', params)


class StackDriverLogging(LogOutput):

    def get_handler(self):
        # gcp has three independent implementation of api bindings for python.
        # The one used by logging is not yet supported by our test recording.

        # TODO drop these grpc variants for the REST versions, and we can drop
        # protobuf/grpc deps, and also so we can record tests..
        # gcp has three different python sdks all independently maintained .. hmmm...
        # and random monkey shims on top of those :-(

        from google.cloud.logging import Client as LogClient
        from google.cloud.logging.handlers import CloudLoggingHandler
        from google.cloud.logging.resource import Resource

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
class GCPStorageOutput(DirectoryOutput):

    def __init__(self, ctx, config=None):
        super(GCPStorageOutput, self).__init__(ctx, config)
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
