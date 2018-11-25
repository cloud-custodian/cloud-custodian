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

from datetime import datetime, timedelta
import time

from c7n.config import Bag
from c7n.output import metrics_outputs
from c7n_gcp.output import StackDriverMetrics

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
        metrics = StackDriverMetrics(ctx)
        metrics.put_metric('ResourceCount', 43, 'Count', Scope='Policy')

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
                    datetime.utcnow() - timedelta(minutes=5)).isoformat('T') + 'Z',
                'interval_endTime': datetime.utcnow().isoformat('T') + 'Z'
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
