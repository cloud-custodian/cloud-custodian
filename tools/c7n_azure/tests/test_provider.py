from azure_common import BaseTest, DEFAULT_SUBSCRIPTION_ID
from mock import patch
from c7n_azure.provider import Azure
from c7n.config import Config


class ProviderTest(BaseTest):

    @patch('c7n_azure.session.Session.get_subscription_id', return_value=DEFAULT_SUBSCRIPTION_ID)
    def test_initialize_default_account_id(self, get_subscription_id_mock):
        options = Config.empty()
        azure = Azure()
        azure.initialize(options)

        self.assertEqual(options['account_id'], DEFAULT_SUBSCRIPTION_ID)

        session = azure.get_session_factory(options)()
        session._initialize_session()
        self.assertEqual(session.subscription_id, DEFAULT_SUBSCRIPTION_ID)

    @patch('c7n_azure.session.Session.get_subscription_id', return_value=DEFAULT_SUBSCRIPTION_ID)
    def test_initialize_custom_account_id(self, get_subscription_id_mock):
        sample_account_id = "00000000-5106-4743-99b0-c129bfa71a47"
        options = Config.empty()
        options['account_id'] = sample_account_id
        azure = Azure()
        azure.initialize(options)
        self.assertEqual(options['account_id'], sample_account_id)

        session = azure.get_session_factory(options)()
        session._initialize_session()
        self.assertEqual(session.subscription_id, sample_account_id)
