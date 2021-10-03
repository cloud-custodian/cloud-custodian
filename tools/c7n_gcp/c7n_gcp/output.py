# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""

TODO: provider policy execution initialization for outputs


"""
import datetime
import logging
import time

try:
    from google.cloud.storage import Bucket, Client as StorageClient
except ImportError:
    Bucket, StorageClient = None, None

try:
    from google.cloud.logging import Client as LogClient
    from google.cloud.logging.handlers import CloudLoggingHandler
    from google.cloud.logging import Resource
except ImportError:
    LogClient = None


from c7n.output import (
    blob_outputs,
    log_outputs,
    metrics_outputs,
    BlobOutput,
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
            'type': '{}/{}'.format(METRICS_PREFIX, 'resourcecount'),
            'valueType': 'INT64',
            'units': 'items',
            'description': 'Number of resources that matched the given policy',
            'displayName': 'Resources',
        },
        'resourcetime': {
            'type': '{}/{}'.format(METRICS_PREFIX, 'resourcetime'),
            'valueType': 'DOUBLE',
            'units': 's',
            'description': 'Time to query the resources for a given policy',
            'displayName': 'Query Time',
        },
        'actiontime': {
            'type': '{}/{}'.format(METRICS_PREFIX, 'actiontime'),
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
        self.project_id = local_session(self.ctx.session_factory).get_default_project()
        self.write_metrics_project_id = self.config.get('project_id', self.project_id)

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
        params = {'name': "projects/{}".format(self.write_metrics_project_id),
                  'body': {'timeSeries': metrics}}
        client.execute_command('create', params)


@log_outputs.register('gcp', condition=bool(LogClient))
class StackDriverLogging(LogOutput):

    def get_log_group(self):
        log_group = self.config.netloc
        if log_group:
            log_group = "custodian-%s-%s" % (log_group, self.ctx.policy.name)
        else:
            log_group = "custodian-%s" % self.ctx.policy.name
        return log_group

    def get_handler(self):
        # TODO drop these grpc variants for the REST versions, and we can drop
        # protobuf/grpc deps, and also so we can record tests.

        log_group = self.get_log_group()
        project_id = local_session(self.ctx.session_factory).get_default_project()
        client = LogClient(project_id)
        return CloudLoggingHandler(
            client,
            log_group,
            labels={
                'policy': self.ctx.policy.name,
                'resource': self.ctx.policy.resource_type},
            resource=Resource(type='project', labels={'project_id': project_id}))

    def leave_log(self):
        super(StackDriverLogging, self).leave_log()
        # Flush and stop the background thread
        self.handler.transport.flush()
        self.handler.transport.worker.stop()


@blob_outputs.register('gs', condition=bool(StorageClient))
class GCPStorageOutput(BlobOutput):

    def __init__(self, ctx, config=None):
        super().__init__(ctx, config)
        self.bucket = Bucket(StorageClient(), self.bucket)

    def upload_file(self, path, key):
        blob = self.bucket.blob(key)
        blob.upload_from_filename(path)
