# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
from dateutil.parser import parse as date_parse
from unittest import mock
import shutil
import time

from c7n.ctx import ExecutionContext
from c7n.config import Bag, Config
from c7n.testing import mock_datetime_now
from c7n.output import metrics_outputs
from c7n.utils import parse_url_config, reset_session_cache

from c7n_gcp.output import (
    GCPStorageOutput, StackDriverLogging, StackDriverMetrics)

from gcp_common import BaseTest


class MetricsOutputTest(BaseTest):

    def test_metrics_selector(self):
        self.assertEqual(
            metrics_outputs.get('gcp'),
            StackDriverMetrics)

    def test_metrics_output(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('output-metrics', project_id=project_id)
        ctx = Bag(session_factory=factory,
                  policy=Bag(name='custodian-works', resource_type='gcp.function'))
        conf = Bag()
        metrics = StackDriverMetrics(ctx, conf)
        metrics.put_metric('ResourceCount', 43, 'Count', Scope='Policy')
        metrics.flush()

        if self.recording:
            time.sleep(42)

        session = factory()
        client = session.client('monitoring', 'v3', 'projects.timeSeries')
        results = client.execute_command(
            'list', {
                'name': 'projects/{}'.format(project_id),
                'filter': 'metric.type="custom.googleapis.com/custodian/policy/resourcecount"',
                'pageSize': 3,
                'interval_startTime': (
                    datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
                ).isoformat('T') + 'Z',
                'interval_endTime': datetime.datetime.utcnow().isoformat('T') + 'Z'
            })
        self.assertEqual(
            results['timeSeries'],
            [{u'metric': {
                u'labels': {
                    u'policy': u'custodian-works',
                    u'project_id': u'cloud-custodian'},
                u'type': u'custom.googleapis.com/custodian/policy/resourcecount'},
              u'metricKind': u'GAUGE',
              u'points': [{
                  u'interval': {
                      u'endTime': u'2018-08-12T22:30:53.524505Z',
                      u'startTime': u'2018-08-12T22:30:53.524505Z'},
                  u'value': {u'int64Value': u'43'}}],
              u'resource': {
                  u'labels': {u'project_id': u'cloud-custodian'},
                  u'type': u'global'},
              u'valueType': u'INT64'}])

    def test_metrics_output_set_write_project_id(self):
        project_id = 'cloud-custodian-sub'
        write_project_id = 'cloud-custodian'
        factory = self.replay_flight_data('output-metrics', project_id=project_id)
        ctx = Bag(session_factory=factory,
                  policy=Bag(name='custodian-works', resource_type='gcp.function'))
        conf = Bag(project_id=write_project_id)
        metrics = StackDriverMetrics(ctx, conf)
        metrics.put_metric('ResourceCount', 43, 'Count', Scope='Policy')
        metrics.flush()


def get_log_output(request, output_url):
    log = StackDriverLogging(
        ExecutionContext(
            lambda assume=False: mock.MagicMock(),
            Bag(name="xyz", provider_name="gcp", resource_type='gcp.function'),
            Config.empty(account_id='custodian-test')),
        parse_url_config(output_url)
    )
    request.addfinalizer(reset_session_cache)
    return log


def get_blob_output(request, output_url=None, cleanup=True):
    if output_url is None:
        output_url = "gs://cloud-custodian/policies"
    output = GCPStorageOutput(
        ExecutionContext(
            lambda assume=False: mock.MagicMock(),
            Bag(name="xyz", provider_name="gcp"),
            Config.empty(output_dir=output_url, account_id='custodian-test')),
        parse_url_config(output_url)
    )

    if cleanup:
        request.addfinalizer(lambda : shutil.rmtree(output.root_dir)) # noqa
    request.addfinalizer(reset_session_cache)
    return output


@mock.patch('c7n_gcp.output.LogClient')
@mock.patch('c7n_gcp.output.CloudLoggingHandler')
def test_gcp_logging(handler, client, request):
    output = get_log_output(request, 'gcp://')
    with output:
        assert 1

    handler().transport.flush.assert_called_once()
    handler().transport.worker.stop.assert_called_once()

    output = get_log_output(request, 'gcp://apples')
    assert output.get_log_group() == 'custodian-apples-xyz'


@mock.patch('c7n_gcp.output.StorageClient')
@mock.patch('c7n_gcp.output.Bucket')
def test_output(bucket, client, request):
    bucket().blob.return_value = key = mock.MagicMock()
    with mock_datetime_now(date_parse('2020/06/10 13:00'), datetime):
        output = get_blob_output(request)
        assert output.key_prefix == 'policies/xyz/2020/06/10/13'
        output.upload_file('resources.json', f"{output.key_prefix}/resources.json")
        key.upload_from_filename.assert_called_once()
