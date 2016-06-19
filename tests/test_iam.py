from unittest import TestCase
from common import load_data
from c7n.iamaccess import check_cross_account


class CrossAccountChecker(TestCase):

    def test_not_principal_allowed(self):
        policy = {
            'Id': 'Foo',
            "Version": "2012-10-17",
            'Statement': [
                {'Action': 'SQS:ReceiveMessage',
                 'Effect': 'Deny',
                 'Principal': '*'},
                {'Action': 'SQS:SendMessage',
                 'Effect': 'Allow',
                 'NotPrincipal': '90120'}]}
        self.assertTrue(
            bool(check_cross_account(policy, set(['221800032964']))))

    def test_sqs_policies(self):
        policies = load_data('iam/sqs-policies.json')
        for p, expected in zip(
                policies, [False, True, True, False,
                           False, False, False, False]):
            violations = check_cross_account(p, set(['221800032964']))
            self.assertEqual(bool(violations), expected)
