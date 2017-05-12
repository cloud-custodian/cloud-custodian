from common import BaseTest

class Route53DomainTest(BaseTest):

    def test_route53_domain_auto_renew(self):
        session_factory = self.replay_flight_data('test_route53_domain')
        p = self.load_policy({
             'name': 'r53domain-auto-renew',
             'resource': 'r53domain',
             'filters': [
                {
                'type': 'value',
                'key': 'AutoRenew',
                'value': False
                }
                ]},
             session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_route53_domain_transfer_lock(self):
        session_factory = self.replay_flight_data('test_route53_domain')
        p = self.load_policy({
             'name': 'r53domain-transfer-lock',
             'resource': 'r53domain',
             'filters': [
                {
                'type': 'value',
                'key': 'TransferLock',
                'value': False
                }
                ]},
             session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)