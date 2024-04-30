# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy
from unittest import mock
import os

import pytest
import yaml

from c7n.testing import TestUtils
from click.testing import CliRunner

from c7n_org import cli as org


ACCOUNTS_AWS_DEFAULT = yaml.safe_dump({
    'accounts': [
        {'name': 'dev',
         'account_id': '112233445566',
         'tags': ['red', 'black'],
         'role': 'arn:aws:iam:{account_id}::/role/foobar'},
        {'name': 'qa',
         'account_id': '002244668899',
         'tags': ['red', 'green'],
         'role': 'arn:aws:iam:{account_id}::/role/foobar'},
    ],
}, default_flow_style=False)

ACCOUNTS_AZURE = {
    'subscriptions': [{
        'subscription_id': 'ea42f556-5106-4743-99b0-c129bfa71a47',
        'name': 'devx',
    }]
}

ACCOUNTS_AZURE_GOV = {
    'subscriptions': [{
        'subscription_id': 'ea42f556-5106-4743-22aa-aabbccddeeff',
        'name': 'azure_gov',
        'region': 'AzureUSGovernment'
    }]
}

ACCOUNTS_GCP = {
    'projects': [{
        'project_id': 'custodian-1291',
        'name': 'devy'
    }],
}

ACCOUNTS_OCI = {
    "tenancies": [{
        "name": "DEFAULT",
        "profile": "DEFAULT",
        }]
}


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

    def test_validate_azure_provider(self):
        run_dir = self.setup_run_dir(
            accounts=ACCOUNTS_AZURE,
            policies={'policies': [{
                'name': 'vms',
                'resource': 'azure.vm'}]
            })
        logger = mock.MagicMock()
        run_account = mock.MagicMock()
        run_account.return_value = ({}, True)
        self.patch(org, 'logging', logger)
        self.patch(org, 'run_account', run_account)
        self.change_cwd(run_dir)
        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['run', '-c', 'accounts.yml', '-u', 'policies.yml',
             '--debug', '-s', 'output', '--cache-path', 'cache'],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

    # This test won't run with real credentials unless the
    # tenant is actually in Azure US Government
    @pytest.mark.skiplive
    def test_validate_azure_provider_gov(self):
        run_dir = self.setup_run_dir(
            accounts=ACCOUNTS_AZURE_GOV,
            policies={'policies': [{
                'name': 'vms',
                'resource': 'azure.vm'}]
            })
        logger = mock.MagicMock()
        run_account = mock.MagicMock()
        run_account.return_value = ({}, True)
        self.patch(org, 'logging', logger)
        self.patch(org, 'run_account', run_account)
        self.change_cwd(run_dir)
        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['run', '-c', 'accounts.yml', '-u', 'policies.yml',
             '--debug', '-s', 'output', '--cache-path', 'cache'],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

    def test_validate_gcp_provider(self):
        run_dir = self.setup_run_dir(
            accounts=ACCOUNTS_GCP,
            policies={
                'policies': [{
                    'resource': 'gcp.instance',
                    'name': 'instances'}]
            })
        logger = mock.MagicMock()
        run_account = mock.MagicMock()
        run_account.return_value = ({}, True)
        self.patch(org, 'logging', logger)
        self.patch(org, 'run_account', run_account)
        self.change_cwd(run_dir)
        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['run', '-c', 'accounts.yml', '-u', 'policies.yml',
             '--debug', '-s', 'output', '--cache-path', 'cache'],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

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

    def test_resolve_regions_comma_separated(self):
        self.assertEqual(
            org.resolve_regions([
                'us-west-2,eu-west-1,us-east-1,us-west-2',
                'eu-west-1,us-east-2,us-east-1'], None),
            ['us-west-2', 'eu-west-1', 'us-east-1', 'us-east-2'])

    def test_resolve_regions(self):
        account = {"name": "dev",
                   "account_id": "112233445566",
                   "role": "arn:aws:iam:112233445566::/role/foobar"
                   }
        self.assertEqual(
            org.resolve_regions(['us-west-2'], account),
            ['us-west-2'])
        self.assertEqual(
            org.resolve_regions([], account),
            ('us-east-1', 'us-west-2'))

    def test_filter_accounts(self):

        d = {'accounts': [
            {'name': 'dev',
             'account_id': '123456789012',
             'tags': ['blue', 'red']},
            {'name': 'prod',
             'account_id': '123456789013',
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

        t5 = copy.deepcopy(d)
        org.filter_accounts(t5, [], [], ['123456789013'])
        self.assertEqual(
            [a['name'] for a in t5['accounts']],
            ['dev'])

        t6 = copy.deepcopy(d)
        org.filter_accounts(t6, [], [], ['dev'])
        self.assertEqual(
            [a['name'] for a in t6['accounts']],
            ['prod'])

    def test_accounts_iterator(self):
        config = {
            "vars": {"default_tz": "Sydney/Australia"},
            "accounts": [
                {
                    'name': 'dev',
                    'account_id': '123456789012',
                    'tags': ["environment:dev"],
                    "vars": {"environment": "dev"},
                },
                {
                    'name': 'dev2',
                    'account_id': '123456789013',
                    'tags': ["environment:dev"],
                    "vars": {"environment": "dev", "default_tz": "UTC"},
                },
            ]
        }
        accounts = [a for a in org.accounts_iterator(config)]
        accounts[0]["vars"]["default_tz"] = "Sydney/Australia"
        # NOTE allow override at account level
        accounts[1]["vars"]["default_tz"] = "UTC"

    def test_cli_nothing_to_do(self):
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

        cli_args = [
            'run', '-c', 'accounts.yml', '-u', 'policies.yml',
            '--debug', '-s', 'output', '--cache-path', 'cache',
            '--metrics-uri', 'aws://',
        ]

        # No policies to run
        result = runner.invoke(
            org.cli,
            cli_args + ['--policytags', 'nonsense'],
            catch_exceptions=False
        )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(
            log_output.getvalue().strip(),
            "Targeting accounts: 2, policies: 0. Nothing to do.",
        )

        # No accounts to run against
        log_output.truncate(0)
        log_output.seek(0)
        result = runner.invoke(
            org.cli,
            cli_args + ['--tags', 'nonsense'],
            catch_exceptions=False
        )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(
            log_output.getvalue().strip(),
            "Targeting accounts: 0, policies: 2. Nothing to do.",
        )

    def test_validate_oci_provider(self):
        run_dir = self.setup_run_dir(
            accounts=ACCOUNTS_OCI,
            policies={"policies": [{
                "name": "instances",
                "resource": "oci.instance"}]
                })
        logger = mock.MagicMock()
        run_account = mock.MagicMock()
        run_account.return_value = ({}, True)
        self.patch(org, "logging", logger)
        self.patch(org, "run_account", run_account)
        self.change_cwd(run_dir)
        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ["run", "-c", "accounts.yml", "-u", "policies.yml",
             "--debug", "-s", "output", "--cache-path", "cache"],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)
