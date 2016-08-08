from common import BaseTest


class AccountTests(BaseTest):

    def test_root_mfa_enabled(self):
        session_factory = self.replay_flight_data('test_account_root_mfa')
        p = self.load_policy({
            'name': 'root-mfa',
            'resource': 'account',
            'filters': [
                {'type': 'iam-summary',
                 'key': 'AccountMFAEnabled', 'value': False}
            ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_root_api_keys(self):
        session_factory = self.replay_flight_data('test_account_root_api_keys')
        p = self.load_policy({
            'name': 'root-api',
            'resource': 'account',
            'filters': [
                {'type': 'iam-summary'}
            ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)        
        
    def test_cloudtrail_enabled(self):
        session_factory = self.replay_flight_data('test_account_trail')
        p = self.load_policy({
            'name': 'trail-enabled',
            'resource': 'account',
            'filters': [
                {'type': 'cloudtrail-enabled',
                 'multi-region': True,
                 'kms': True,
                 'file-digest': True,
                 'global-events': True}
            ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_cloudtrail_notifies(self):
        session_factory = self.replay_flight_data('test_account_trail')
        p = self.load_policy({
            'name': 'trail-enabled',
            'resource': 'account',
            'filters': [
                {'type': 'cloudtrail-enabled',
                 'notifies': True}
            ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        
    def test_config_enabled(self):
        session_factory = self.replay_flight_data('test_account_config')
        p = self.load_policy({
            'name': 'config-enabled',
            'resource': 'account',
            'filters': [
                {'type': 'config-enabled',
                 'all-resources': True,
                 'running': True}
            ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_config_enabled_global(self):
        session_factory = self.replay_flight_data('test_account_config_global')
        p = self.load_policy({
            'name': 'config-enabled',
            'resource': 'account',
            'filters': [
                {'type': 'config-enabled',
                 'global-resources': True}
            ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)        
        
