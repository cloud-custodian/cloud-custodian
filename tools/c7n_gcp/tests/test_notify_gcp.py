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
                        'data': ('eJzdU7tuAjEQ7P0VyHXu4EAiQJUqXb4gipCxF+LI57XsNcoJ8e/xg6dEFaW'
                                 'KJV8xo52d2fUdGIc9WOKrkY3GPDEupMRoaa1VwriMgVBpYZtuuuz4lX9Met'
                                 'hptJkTxmTAodFySMCBcSt6yBRBoMYi6e1QawJGLwu1k651cRPipiF0WmZ+q'
                                 'w2BD4l+ZzcqzuMXSApjaTCq5uJlXArDOEnlRrVPFWNH9lESUDJ5EaTBFcGr'
                                 'I4LeGUEFVbAV0VDJ4jV6TcP6E4QCn9lpxpPb7OQcTdvdqGqNaqciiaUdjwH'
                                 '8i8JeaNtK7HkxRF7Y4NBTndPZUB1Erc72fx06xWbHJAPfIGN2dFru5HSaB5'
                                 '/z4Xd1gURx2c3n3WIxm80nid6n7Zy2PmmXbbfglyHfB/rHE755x3/xUpOcf'
                                 'LarN0HyE9TrzR9QVfNC8/0BI3Q0PA==')
                    }}})
