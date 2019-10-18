from .azure_common import BaseTest, DEFAULT_SUBSCRIPTION_ID
from mock import patch
from c7n_azure.provider import Azure
from c7n.config import Config


class ProviderTest(BaseTest):
    def test_initialize_default_account_id(self):
        # Patch get_subscription_id during provider initialization
        with patch('c7n_azure.session.Session.get_subscription_id',
                   return_value=DEFAULT_SUBSCRIPTION_ID):
            options = Config.empty()
            azure = Azure()
            azure.initialize(options)
            self.assertEqual(options['account_id'], DEFAULT_SUBSCRIPTION_ID)
            session = azure.get_session_factory(options)()

        self.assertEqual(DEFAULT_SUBSCRIPTION_ID, session.get_subscription_id())

    def test_initialize_custom_account_id(self):
        sample_account_id = "00000000-5106-4743-99b0-c129bfa71a47"
        options = Config.empty()
        options['account_id'] = sample_account_id
        azure = Azure()
        azure.initialize(options)
        self.assertEqual(options['account_id'], sample_account_id)

        session = azure.get_session_factory(options)()
        self.assertEqual(sample_account_id, session.get_subscription_id())
