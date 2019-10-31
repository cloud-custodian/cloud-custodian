# Copyright 2019 Hulu LLC. All Rights Reserved.
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


from c7n.utils import local_session, yaml_load

from .common import BaseTest


class TestQuotas(BaseTest):
    def test_service_quota_request_history_filter(self):
        session_factory = self.replay_flight_data('test_service_quota')
        policy = yaml_load("""
        name: service-quota-history-filter
        resource: aws.service-quota
        filters:
          - type: request-history
            key: "[].Status"
            value: CASE_CLOSED
            op: in
            value_type: swap
        """)
        p = self.load_policy(
            policy,
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(resources)

    def test_service_quota_request_increase(self):
        session_factory = self.replay_flight_data('test_service_quota')
        policy = yaml_load("""
        name: service-quota-request-increase
        resource: aws.service-quota
        filters:
          - QuotaCode: L-355B2B67
        actions:
          - type: request-increase
            multiplier: 1.2
        """)
        p = self.load_policy(policy, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(session_factory).client('service-quotas')
        changes = client.list_requested_service_quota_change_history_by_quota(
            ServiceCode=resources[0]['ServiceCode'],
            QuotaCode=resources[0]['QuotaCode']
        )['RequestedQuotas']
        self.assertTrue(changes)

    def test_usage_metric_filter(self):
        session_factory = self.replay_flight_data('test_service_quota')
        policy = yaml_load("""
        name: service-quota-usage-metric
        resource: aws.service-quota
        filters:
            - UsageMetric: present
            - type: usage-metric
              limit: 20
        """)
        p = self.load_policy(policy, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_put_request_in_template(self):
        session_factory = self.replay_flight_data('test_service_quota')
        policy = yaml_load("""
        name: put-service-quota-request-in-template
        resource: aws.service-quota
        filters:
            - QuotaCode: L-5D81802F
        actions:
            - type: add-to-template
              multiplier: 1.2
              regions:
                - us-east-1
                - us-west-2
        """)
        p = self.load_policy(policy, session_factory=session_factory)
        resources = p.run()
        self.assertTrue(resources)
        c = local_session(session_factory).client('service-quotas')
        resp = c.list_service_quota_increase_requests_in_template()
        quotas = resp['ServiceQuotaIncreaseRequestInTemplateList']
        self.assertTrue(quotas)

    def test_remove_request_from_template(self):
        session_factory = self.replay_flight_data('test_service_quota')
        policy = yaml_load("""
        name: remove-service-quota-request-from-template
        resource: aws.service-quota
        filters:
          - type: in-template
        actions:
            - type: remove-from-template
              regions:
                - us-east-1
                - us-west-2
        """)
        p = self.load_policy(policy, session_factory=session_factory)
        resources = p.run()
        self.assertTrue(resources)
        c = local_session(session_factory).client('service-quotas')
        resp = c.list_service_quota_increase_requests_in_template()
        quotas = resp['ServiceQuotaIncreaseRequestInTemplateList']
        self.assertFalse(quotas)
