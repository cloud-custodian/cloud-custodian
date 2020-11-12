# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest
from c7n_gcp.client import Session

import mock


class NotifyTest(BaseTest):

    def test_pubsub_notify(self):
        factory = self.replay_flight_data("notify-action")

        orig_client = Session.client
        stub_client = mock.MagicMock()
        calls = []

        def client_factory(*args, **kw):
            calls.append(args)
            if len(calls) == 1:
                return orig_client(*args, **kw)
            return stub_client

        self.patch(Session, 'client', client_factory)

        p = self.load_policy({
            'name': 'test-notify',
            'resource': 'gcp.pubsub-topic',
            'filters': [
                {
                    'name': 'projects/cloud-custodian/topics/gcptestnotifytopic'
                }
            ],
            'actions': [
                {'type': 'notify',
                 'template': 'default',
                 'priority_header': '2',
                 'subject': 'testing notify action',
                 'to': ['user@domain.com'],
                 'transport':
                     {'type': 'pubsub',
                      'topic': 'projects/cloud-custodian/topics/gcptestnotifytopic'}
                 }
            ]}, session_factory=factory)

        resources = p.run()

        self.assertEqual(len(resources), 1)
        stub_client.execute_command.assert_called_once()

        stub_client.execute_command.assert_called_with(
            'publish', {
                'topic': 'projects/cloud-custodian/topics/gcptestnotifytopic',
                'body': {
                    'messages': {
                        'data': ('eJzdUrtqAzEQ7PUVh+qcjd2EuEqVLl8QgpFXe2cFnVZIq8Bh/O/'
                                 'RA58vkCqkSrHNDDuPZS9C4ic6lofOJWsfhFQAlBwfjc6YhBSZtFGu3'
                                 '+2fdvLO/0wGHA25wilrC+DJGpgzcBHSqQkLxRi5d8RmmNtOpBSgUiP4jU'
                                 '+nmE49kzdQ+MFYxhAz/SZWKj7QBwLHLVhKul+'
                                 'ybOti3GapYtR8mpi4ivfagHPIRZBnXwXviRgnbxVXVOOgkuXaJRgKhuf'
                                 'jGZXGUNh9wXPakuRWzbixa1pdc6qSVO1kihieNU3KuA3QJGsgDspFT4Hb'
                                 'nW6B2iHadon/69K5trguxb+b/OPWq9/6i+/JcvDoDq+'
                                 'K4Yz6ZfWVTbUcucwX+HoY5Q==')
                    }}})
