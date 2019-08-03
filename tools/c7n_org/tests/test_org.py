import copy
import mock
import os
import yaml

from c7n.testing import TestUtils
from click.testing import CliRunner

from c7n_org import cli as org


ACCOUNTS_AWS_DEFAULT = yaml.safe_dump({
    'accounts': [
        {'name': 'dev',
         'account_id': 'foobar',
         'tags': ['red', 'black'],
         'role': 'arn:aws:iam:{account_id}::/role/foobar'},
        {'name': 'qa',
         'account_id': 'barfoo',
         'tags': ['red', 'green'],
         'role': 'arn:aws:iam:{account_id}::/role/foobar'},
    ],
}, default_flow_style=False)

POLICIES_AWS_DEFAULT = yaml.safe_dump({
    'policies': [
        {'name': 'compute',
         'resource': 'aws.ec2',
         'tags': ['red', 'green']},
        {'name': 'serverless',
         'resource': 'aws.lambda',
         'tags': ['red', 'black']},

    ],
}, default_flow_style=False)


class OrgTest(TestUtils):

    def setup_run_dir(self, accounts=None, policies=None):
        root = self.get_temp_dir()

        if accounts:
            accounts = yaml.safe_dump(accounts, default_flow_style=False)
        else:
            accounts = ACCOUNTS_AWS_DEFAULT

        with open(os.path.join(root, 'accounts.yml'), 'w') as fh:
            fh.write(accounts)

        if policies:
            policies = yaml.safe_dump(policies, default_flow_style=False)
        else:
            policies = POLICIES_AWS_DEFAULT

        with open(os.path.join(root, 'policies.yml'), 'w') as fh:
            fh.write(policies)

        cache_path = os.path.join(root, 'cache')
        os.makedirs(cache_path)
        return root

    def test_cli_run_aws(self):
        run_dir = self.setup_run_dir()
        logger = mock.MagicMock()
        run_account = mock.MagicMock()
        run_account.return_value = (
            {'compute': 24, 'serverless': 12}, True)
        self.patch(org, 'logging', logger)
        self.patch(org, 'run_account', run_account)
        self.change_cwd(run_dir)
        log_output = self.capture_logging('c7n_org')
        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['run', '-c', 'accounts.yml', '-u', 'policies.yml',
             '--debug', '-s', 'output', '--cache-path', 'cache',
             '--metrics-uri', 'aws://'],
            catch_exceptions=False)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(
            log_output.getvalue().strip(),
            "Policy resource counts Counter({'compute': 96, 'serverless': 48})")

    def test_filter_policies(self):
        d = {'policies': [
            {'name': 'find-ml',
             'tags': ['bar:xyz', 'red', 'black'],
             'resource': 'gcp.instance'},
            {'name': 'find-serverless',
             'resource': 'aws.lambda',
             'tags': ['blue', 'red']}]}

        t1 = copy.deepcopy(d)
        org.filter_policies(t1, [], [], [], [])
        self.assertEqual(
            [n['name'] for n in t1['policies']],
            ['find-ml', 'find-serverless'])

        t2 = copy.deepcopy(d)
        org.filter_policies(t2, ['blue', 'red'], [], [], [])
        self.assertEqual(
            [n['name'] for n in t2['policies']], ['find-serverless'])

        t3 = copy.deepcopy(d)
        org.filter_policies(t3, [], ['find-ml'], [], [])
        self.assertEqual(
            [n['name'] for n in t3['policies']], ['find-ml'])

        t4 = copy.deepcopy(d)
        org.filter_policies(t4, [], [], 'gcp.instance', [])
        self.assertEqual(
            [n['name'] for n in t4['policies']], ['find-ml'])

    def test_resolve_regions(self):
        self.assertEqual(
            org.resolve_regions(['us-west-2']),
            ['us-west-2'])
        self.assertEqual(
            org.resolve_regions([]),
            ('us-east-1', 'us-west-2'))

    def test_filter_accounts(self):

        d = {'accounts': [
            {'name': 'dev',
             'tags': ['blue', 'red']},
            {'name': 'prod',
             'tags': ['green', 'red']}]}

        t1 = copy.deepcopy(d)
        org.filter_accounts(t1, [], [], [])
        self.assertEqual(
            [a['name'] for a in t1['accounts']],
            ['dev', 'prod'])

        t2 = copy.deepcopy(d)
        org.filter_accounts(t2, [], [], ['prod'])
        self.assertEqual(
            [a['name'] for a in t2['accounts']],
            ['dev'])

        t3 = copy.deepcopy(d)
        org.filter_accounts(t3, [], ['dev'], [])
        self.assertEqual(
            [a['name'] for a in t3['accounts']],
            ['dev'])

        t4 = copy.deepcopy(d)
        org.filter_accounts(t4, ['red', 'blue'], [], [])
        self.assertEqual(
            [a['name'] for a in t4['accounts']],
            ['dev'])
