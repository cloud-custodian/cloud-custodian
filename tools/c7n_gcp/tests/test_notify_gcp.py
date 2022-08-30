# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

from gcp_common import BaseTest
from c7n_gcp.client import Session


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
                        'data': ('eJzdU8tuwyAQvPsrIs7FsR3HdnLqqbd+QVVFGOOECgO'
                                 'CJaoV5d/LI69KPVU99cBlhp2d2YVThtiRSUDbhXRCPG'
                                 'WIUKqchB0fPIaos6AGTiQuq02J7vzPpGF7rmTgiBAB0'
                                 'EpwOnvglCFJJhYoYBawVMDHOdVY5QyN1J7qXLveuh6D'
                                 '0pwGfuQCmLGefsseVLRRH4yCXVKh3IBvXpax0C69VGi'
                                 'U+iSx7Jy9xwTgTd4EYdZR8O4I2KQFgYgObCROQMxiuD'
                                 'Ic5t2BkYGZwFYB926Dk2s0LveLpLVInaKkiu2Qs8w8D'
                                 '2oiXOZUTSgaAkOk1cpAmtPVUBpEqg72fx3ax87OXoZ9'
                                 'MuqCo8tyyw1t26LvcdENBa67esR93Ve4W1XN2KzWpOj'
                                 'X6FudBRJdlk1Tdl3ZtF2+ruu2rf2to1/SZflFvsnLDt'
                                 '1m/T3XPx70w3P+iwfr5Wgrt68E6IENLw8fIamGvYbzB'
                                 'WEzOA0=')
                    }}})
