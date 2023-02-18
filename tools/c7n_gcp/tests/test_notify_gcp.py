# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

from gcp_common import BaseTest
from c7n_gcp.client import Session


class NotifyTest(BaseTest):

    @mock.patch("c7n.ctx.uuid.uuid4", return_value="00000000-0000-0000-0000-000000000000")
    @mock.patch("c7n.ctx.time.time", return_value=1661883360)
    @mock.patch("c7n_gcp.actions.notify.version", '0.9.18')
    def test_pubsub_notify(self, *args, **kwargs):
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
                        'data': ('eJzdU8tuwjAQvPsrkM9NgCJRyqmn3voFVYWMvYArx2vZa9QI8e/1g0eo2kv'
                                 'VUy0lh5ns7Myuc2Ac9mCJL0c2GnPHuJASo6WVVgnj0mBUjYyBUGlh+fWDH1'
                                 'gPW402k8KYDDg0WvYJODBuRQeZIgjUWCS96WtNwOhlobbStS6uQ1w3hE7Lz'
                                 'G+0IfAh0a9soOI8voOkMP5iY1wKwzhJ5Ua1TxVjR/ZWIlAyeRGk3hXBqyOC'
                                 'zhlBBVWwEdFQyeI1ek39agdCgc/sfcaT2+zkHE3b7ahqjWqnIomlHY8B/JP'
                                 'CTmjbSux4MURe2ODQU53T2VAdRK3O9n8dOsVmxyQDHyBjdnRa7+R0mm9e58'
                                 'Nv6gKJ4nI6n08Xi9lsPkn0Pm3ntPVJ+9hOF/wy5NtA/3jCg3v8Fzc1yckHu'
                                 '3wRJHegngd/QFXNC83PJ1zENtA=')
                    }}})
