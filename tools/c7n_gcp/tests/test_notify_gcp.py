# Copyright 2019 Capital One Services, LLC
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

from gcp_common import BaseTest
from c7n_gcp.client import Session

import mock
import sys


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
        if sys.version_info.major < 3:
            return

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
