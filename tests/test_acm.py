# Copyright 2016-2017 Capital One Services, LLC
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
from .common import BaseTest


class CertificateTest(BaseTest):

    def test_certificate_augment(self):
        factory = self.replay_flight_data("test_acm_certificate_augment")
        p = self.load_policy({
            'name': 'acm-cert-get',
            'resource': 'acm-certificate'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('NotAfter' in resources[0])

    def test_certificate_delete(self):
        factory = self.replay_flight_data("test_acm_certificate_delete")
        p = self.load_policy(
            {
                "name": "acm-certificate-delete",
                "resource": "acm-certificate",
                "filters": [{"type": "value", "key": "DomainName", "value": "foobar.com"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DomainName"], "foobar.com")

    def test_certificate_delete_in_use_error(self):
        factory = self.replay_flight_data("test_acm_certificate_delete_in_use_error")
        p = self.load_policy(
            {
                "name": "acm-certificate-delete",
                "resource": "acm-certificate",
                "filters": [{"type": "value", "key": "DomainName", "value": "foobar.com"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("acm")
        arn = "arn:aws:acm:us-west-2:644160558196:certificate/b867707e-33c3-4024-b45d-b6133c3b4c05"
        self.assertTrue(client.get_certificate(CertificateArn=arn))

    def test_certificate_tag_untag_mark(self):
        factory = self.replay_flight_data("test_certificate_tag_untag_mark")
        p = self.load_policy(
            {
                "name": "acm-tag",
                "resource": "acm-certificate",
                "filters": [{"tag:target-tag": "present"}],
                "actions": [
                    {"type": "remove-tag", "tags": ["target-tag"]},
                    {"type": "mark-for-op", "tag": "custodian_cleanup", "op": "delete", "days": 1}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("acm")
        tag = client.list_tags_for_certificate(CertificateArn=resources[0]['CertificateArn'])
        self.assertEqual(len(tag.get('Tags')), 1)
        self.assertEqual(tag.get('Tags')[0]['Key'], "custodian_cleanup")
