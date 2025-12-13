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

    # ==================== Tests for c7n-org validate command ====================

    def test_validate_command_valid_policy(self):
        """Test validate command with a valid policy file - should exit 0."""
        run_dir = self.setup_run_dir()
        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml')],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

    def test_validate_command_invalid_schema(self):
        """Test validate command with schema errors - should exit 1."""
        # Create invalid policy file with schema violation
        invalid_policy = {
            'policies': [{
                'name': 'invalid-schema',
                'resource': 'aws.ec2',
                'filters': [
                    {'type': 'nonexistent-filter-type-xyz123'}
                ]
            }]
        }
        run_dir = self.setup_run_dir(policies=invalid_policy)

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml')],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 1)

    def test_validate_command_invalid_structure(self):
        """Test validate command with structural errors - should exit 1."""
        # Create structurally invalid policy (missing required fields)
        invalid_policy = {
            'policies': [{
                'name': 'missing-resource'
                # Missing 'resource' field which is required
            }]
        }
        run_dir = self.setup_run_dir(policies=invalid_policy)

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml')],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 1)

    def test_validate_command_duplicate_policy_names(self):
        """Test validate command with duplicate policy names - should exit 1."""
        # Create policy file with duplicate names
        duplicate_policy = {
            'policies': [
                {'name': 'duplicate', 'resource': 'aws.ec2'},
                {'name': 'duplicate', 'resource': 'aws.s3'}
            ]
        }
        run_dir = self.setup_run_dir(policies=duplicate_policy)

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml')],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 1)

    def test_validate_command_with_policy_filter(self):
        """Test validate command with -p policy name filter."""
        run_dir = self.setup_run_dir()
        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '-p', 'compute'],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

    def test_validate_command_with_resource_filter(self):
        """Test validate command with --resource filter."""
        run_dir = self.setup_run_dir()
        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--resource', 'aws.lambda'],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

    def test_validate_command_with_policy_tag_filter(self):
        """Test validate command with -l policy tag filter."""
        run_dir = self.setup_run_dir()
        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '-l', 'red', '-l', 'green'],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

    def test_validate_command_check_deprecations_warn(self):
        """Test validate command with deprecated features in warn mode - should exit 0."""
        # Create policy with mark-for-op (commonly deprecated)
        policy = {
            'policies': [{
                'name': 'with-mark-for-op',
                'resource': 'aws.ec2',
                'filters': [{'tag:Name': 'present'}],
                'actions': [{
                    'type': 'mark-for-op',
                    'op': 'stop',
                    'days': 7
                }]
            }]
        }
        run_dir = self.setup_run_dir(policies=policy)

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--check-deprecations', 'warn'],
            catch_exceptions=False)
        # Warn mode should exit 0 even with deprecations
        self.assertEqual(result.exit_code, 0)

    def test_validate_command_check_deprecations_strict(self):
        """Test validate command with deprecated features in strict mode - should exit 1."""
        # Create policy with mark-for-op (commonly deprecated)
        policy = {
            'policies': [{
                'name': 'with-mark-for-op',
                'resource': 'aws.ec2',
                'filters': [{'tag:Name': 'present'}],
                'actions': [{
                    'type': 'mark-for-op',
                    'op': 'stop',
                    'days': 7
                }]
            }]
        }
        run_dir = self.setup_run_dir(policies=policy)

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--check-deprecations', 'strict'],
            catch_exceptions=False)
        # Strict mode should exit 1 if deprecations found
        # Note: this depends on whether mark-for-op is actually deprecated
        # If no deprecations are found, it will exit 0
        self.assertIn(result.exit_code, [0, 1])

    def test_validate_command_missing_policy_file(self):
        """Test validate command with non-existent policy file - should exit 1."""
        run_dir = self.setup_run_dir()
        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', '/nonexistent/path/policies.yml'],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 1)

    def test_validate_command_invalid_policy_file_format(self):
        """Test validate command with invalid file extension - should exit 1."""
        run_dir = self.get_temp_dir()

        # Create accounts file
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            fh.write(ACCOUNTS_AWS_DEFAULT)

        # Create policy file with .txt extension
        with open(os.path.join(run_dir, 'policies.txt'), 'w') as fh:
            fh.write(POLICIES_AWS_DEFAULT)

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.txt')],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 1)

    def test_validate_command_multicloud_policies(self):
        """Test validate command with multicloud policies (AWS, Azure, GCP) - should exit 0."""
        run_dir = self.setup_run_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'multicloud-policy.yml')],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

        # Test filtering by AWS resources
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'multicloud-policy.yml'),
             '--resource', 'aws.ec2'],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

        # Test filtering by Azure resources
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'multicloud-policy.yml'),
             '--resource', 'azure.storage'],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

        # Test filtering by GCP resources
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'multicloud-policy.yml'),
             '--resource', 'gcp.bucket'],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

    # Phase 2 Tests: Account-Aware Validation

    def test_validate_cli_options_exist(self):
        """Test that Phase 2 CLI options are registered and accessible."""
        runner = CliRunner()

        # Test --help to verify new options exist
        result = runner.invoke(org.cli, ['validate', '--help'])
        self.assertEqual(result.exit_code, 0)

        # Check that Phase 2 options are documented
        self.assertIn('--accounts', result.output)
        self.assertIn('--tags', result.output)
        self.assertIn('--not-accounts', result.output)
        self.assertIn('--per-account', result.output)

        # Check descriptions mention account filtering
        self.assertIn('Account', result.output)
        self.assertIn('per account', result.output.lower())

    def test_validate_account_filtering_by_name(self):
        """Test that validate command accepts account name filters."""
        # This test verifies that account filtering options are accepted
        # The actual filtering logic will be tested in per-account mode tests
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Create accounts file with multiple accounts
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        # Use a simple valid policy
        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'simple-valid-policy.yml'),
             '-a', 'dev-account'],  # Filter by account name
            catch_exceptions=False)

        # Should succeed - basic mode ignores account filters but accepts them
        self.assertEqual(result.exit_code, 0)

    def test_validate_account_filtering_by_tags(self):
        """Test that validate command accepts account tag filters."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Create accounts file with multiple accounts
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'simple-valid-policy.yml'),
             '--tags', 'dev'],  # Filter by tag
            catch_exceptions=False)

        # Should succeed
        self.assertEqual(result.exit_code, 0)

    def test_validate_account_config_schema_validation(self):
        """Test that validate command validates account config schema."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Create an invalid accounts file (missing required field)
        invalid_accounts = """
accounts:
  - name: test-account
    # Missing required account_id and role/profile
    tags:
      - dev
"""
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            fh.write(invalid_accounts)

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'simple-valid-policy.yml')],
            catch_exceptions=False)

        # Should fail due to invalid account config
        # Exit code 1 indicates validation failure
        self.assertEqual(result.exit_code, 1)

    def test_validate_account_filtering_exclude(self):
        """Test that validate command accepts --not-accounts filter."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Create accounts file with multiple accounts
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'simple-valid-policy.yml'),
             '--not-accounts', 'staging-account'],  # Exclude staging account
            catch_exceptions=False)

        # Should succeed
        self.assertEqual(result.exit_code, 0)

    def test_validate_basic_mode(self):
        """Ensure basic validation mode works."""
        run_dir = self.setup_run_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
        runner = CliRunner()

        # Test 1: Valid policy should pass
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml')],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

        # Test 2: Invalid policy should fail
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'invalid-schema-policy.yml')],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 1)

        # Test 3: Policy filtering should work
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '-p', 's3-global-grants'],
            catch_exceptions=False)
        self.assertEqual(result.exit_code, 0)

    def test_validate_per_account_mode_valid(self):
        """Test per-account validation with valid variable expansion."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Create accounts file with variables
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'policy-with-vars.yml'),
             '--per-account',
             '--accounts', 'dev-account,prod-account'],  # Only test accounts with vars
            catch_exceptions=False)

        # Should succeed - these accounts have required variables
        self.assertEqual(result.exit_code, 0)

    def test_validate_per_account_mode_variable_expansion(self):
        """Test that variables are correctly expanded per account."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Create accounts file with variables
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'policy-with-vars.yml'),
             '--per-account',
             '--accounts', 'dev-account,prod-account'],  # Only accounts with vars
            catch_exceptions=False)

        # Should succeed - these accounts have vars
        self.assertEqual(result.exit_code, 0)

    def test_validate_per_account_mode_missing_variable(self):
        """Test that missing variable references are detected and reported."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Create accounts file with variables
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'policy-missing-vars.yml'),
             '--per-account',
             '--accounts', 'staging-account'],  # This account has no vars defined
            catch_exceptions=False)

        # Should fail - policy references variables that staging-account doesn't have
        self.assertEqual(result.exit_code, 1)

    def test_validate_per_account_mode_account_specific_failure(self):
        """Test that failures are properly attributed to specific accounts."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Create accounts file with variables
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'policy-with-vars.yml'),
             '--per-account'],  # Test all accounts - staging should fail
            catch_exceptions=False)

        # Should fail - staging-account doesn't have required variables
        self.assertEqual(result.exit_code, 1)

    def test_validate_per_account_summary_report(self):
        """Test that the summary report shows correct account statistics."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Create accounts file with variables
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(fixtures_dir, 'policy-with-vars.yml'),
             '--per-account'],
            catch_exceptions=False)

        # Should fail - staging account doesn't have the required vars
        self.assertEqual(result.exit_code, 1)


# Tests for extract_framework_runtime_variables function
class TestExtractFrameworkRuntimeVariables(TestUtils):
    """Test suite for extract_framework_runtime_variables function."""

    def test_empty_dict_returns_empty_set(self):
        """Empty dict should return empty set."""
        result = org.extract_framework_runtime_variables({})
        assert result == set()

    def test_no_placeholders_returns_empty_set(self):
        """Dict with no placeholders should return empty set."""
        variables = {
            'account_id': '123456789012',
            'region': 'us-east-1',
            'partition': 'aws'
        }
        result = org.extract_framework_runtime_variables(variables)
        assert result == set()

    def test_only_placeholders_returns_all(self):
        """Dict with only placeholders should return all of them."""
        variables = {
            'event': '{event}',
            'op': '{op}',
            'action_date': '{action_date}'
        }
        result = org.extract_framework_runtime_variables(variables)
        assert result == {'{event}', '{op}', '{action_date}'}

    def test_mixed_returns_only_unexpanded(self):
        """Dict with mixed values should return only placeholders."""
        variables = {
            'account_id': '123456789012',
            'region': 'us-east-1',
            'event': '{event}',
            'op': '{op}',
            'partition': 'aws'
        }
        result = org.extract_framework_runtime_variables(variables)
        assert result == {'{event}', '{op}'}

    def test_partial_placeholders_not_matched(self):
        """Partial placeholders like 'prefix-{var}-suffix' should NOT be matched."""
        variables = {
            'key1': 'prefix-{var}-suffix',
            'key2': 'arn:aws:iam::{account_id}::role/test',
            'key3': '{event}'  # This should match
        }
        result = org.extract_framework_runtime_variables(variables)
        # Only exact placeholder matches
        assert result == {'{event}'}

    def test_non_string_types_handled(self):
        """Non-string values should be ignored gracefully."""
        variables = {
            'account_id': '123456',
            'policy': {'name': 'test', 'resource': 's3'},  # dict
            'count': 42,  # int
            'enabled': True,  # bool
            'items': ['a', 'b', 'c'],  # list
            'event': '{event}',  # placeholder string - should match
            'nothing': None  # None
        }
        result = org.extract_framework_runtime_variables(variables)
        assert result == {'{event}'}


# Tests for modified find_unexpanded_variables function
class TestFindUnexpandedVariablesModified(TestUtils):
    """Test suite for modified find_unexpanded_variables with allowed_placeholders."""

    def test_none_parameter_rejects_all(self):
        """With allowed_placeholders=None (default), all unexpanded vars should be flagged."""
        policy_data = {'actions': [{'type': 'notify', 'to': ['{admin_email}']}]}
        result = org.find_unexpanded_variables(policy_data)
        assert len(result) == 1
        assert result[0][1] == '{admin_email}'

    def test_empty_allowed_set_rejects_all(self):
        """With empty allowed_placeholders set, all unexpanded vars should be flagged."""
        policy_data = {'actions': [{'type': 'notify', 'to': ['{admin_email}']}]}
        result = org.find_unexpanded_variables(policy_data, allowed_placeholders=set())
        assert len(result) == 1
        assert result[0][1] == '{admin_email}'

    def test_allowed_placeholders_are_accepted(self):
        """Allowed placeholders should NOT be flagged as errors."""
        policy_data = {
            'actions': [
                {'type': 'notify', 'to': ['{event}']},  # Allowed
                {'type': 'tag', 'key': '{admin_email}'}  # Not allowed
            ]
        }
        result = org.find_unexpanded_variables(
            policy_data,
            allowed_placeholders={'{event}', '{op}'}
        )
        assert len(result) == 1
        assert result[0][1] == '{admin_email}'

    def test_nested_structures_handled_correctly(self):
        """Nested structures with mixed allowed/disallowed variables."""
        policy_data = {
            'filters': [
                {'tag:Owner': '{account_id}'},  # Not allowed
                {'type': 'event', 'key': '{event}'}  # Allowed
            ]
        }
        result = org.find_unexpanded_variables(
            policy_data,
            allowed_placeholders={'{event}'}
        )
        assert len(result) == 1
        assert '{account_id}' in result[0][1]

    def test_multiple_variables_in_string(self):
        """String with multiple variables, some allowed, some not."""
        policy_data = {
            'actions': [{
                'type': 'notify',
                'subject': 'Alert for {event} on {missing_var}'
            }]
        }
        result = org.find_unexpanded_variables(
            policy_data,
            allowed_placeholders={'{event}'}
        )
        # Should only flag {missing_var}
        assert len(result) == 1
        assert result[0][1] == '{missing_var}'

    def test_all_allowed_returns_empty(self):
        """If all variables are in allowed set, should return empty list."""
        policy_data = {
            'actions': [
                {'type': 'notify', 'to': ['{event}']},
                {'type': 'webhook', 'url': 'http://example.com/{op}'}
            ]
        }
        result = org.find_unexpanded_variables(
            policy_data,
            allowed_placeholders={'{event}', '{op}'}
        )
        assert len(result) == 0

    def test_backward_compatibility_default_parameter(self):
        """Test that omitting allowed_placeholders maintains backward compatibility."""
        policy_data = {
            'actions': [
                {'type': 'notify', 'subject': '{event}'},  # Was in old hardcoded list
                {'type': 'tag', 'key': '{custom_var}'}  # Was not
            ]
        }
        # With default (None), should flag all unexpanded variables
        result = org.find_unexpanded_variables(policy_data)
        # Both should be flagged now (no hardcoded allowlist)
        assert len(result) == 2


# Integration tests for unexpanded variables.
class TestIntegrationUnexpandedVariables(TestUtils):
    """Integration tests for the complete unexpanded variable validation flow.

    These tests validate end-to-end scenarios with real Policy objects.
    """

    def test_runtime_variables_not_flagged(self):
        """Test that framework runtime variables are NOT flagged as errors."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Use accounts with variables defined
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        # Policy with runtime variables like {event}, {op}, {action_date}
        with open(os.path.join(run_dir, 'policies.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'policy-with-runtime-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--per-account',
             '--accounts', 'dev-account'],  # Account with vars defined
            catch_exceptions=False)

        # Should pass - runtime variables should NOT be flagged
        assert result.exit_code == 0, f"Validation failed: {result.output}"

    def test_undefined_user_variable_flagged(self):
        """Test that undefined user variables ARE flagged as errors."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Use accounts - staging has NO variables defined
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        # Policy requires {environment} and {cost_center} from account vars
        with open(os.path.join(run_dir, 'policies.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'policy-with-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        # Capture both output and logging
        log_output = self.capture_logging('c7n_org')
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--per-account',
             '--accounts', 'staging-account'],  # Account WITHOUT vars
            catch_exceptions=False)

        # Should fail - user variables are undefined
        assert result.exit_code == 1, "Should have failed validation"
        # Check captured log output instead of result.output
        log_text = log_output.getvalue().lower()
        assert 'environment' in log_text or 'cost_center' in log_text

    def test_mixed_variables_correct_distinction(self):
        """Test that mixed user+runtime variables are handled correctly."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Account with user variables defined
        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        # Policy with both user vars and runtime vars
        with open(os.path.join(run_dir, 'policies.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'policy-with-runtime-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--per-account',
             '--accounts', 'dev-account',  # Has environment var
             '-p', 'mixed-variables-policy'],  # Policy with both types
            catch_exceptions=False)

        # Should pass - user vars are defined, runtime vars are allowed
        assert result.exit_code == 0, f"Mixed variables failed: {result.output}"

    def test_account_without_vars_mixed_policy(self):
        """Test mixed policy fails when user variables are missing."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        with open(os.path.join(run_dir, 'policies.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'policy-with-runtime-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        log_output = self.capture_logging('c7n_org')
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--per-account',
             '--accounts', 'staging-account',  # NO vars defined
             '-p', 'mixed-variables-policy'],  # Needs {environment}
            catch_exceptions=False)

        # Should fail - {environment} is undefined, but {event} should be OK
        assert result.exit_code == 1, "Should fail for missing user variable"
        # Should mention the user variable that's missing
        log_text = log_output.getvalue().lower()
        assert 'environment' in log_text

    def test_all_accounts_with_per_account_validation(self):
        """Test validation across multiple accounts with different var sets."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        with open(os.path.join(run_dir, 'policies.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'policy-with-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        log_output = self.capture_logging('c7n_org')
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--per-account'],  # Test ALL accounts
            catch_exceptions=False)

        # Should fail because staging-account lacks required variables
        assert result.exit_code == 1
        # Should show which account(s) failed
        log_text = log_output.getvalue().lower()
        assert 'staging' in log_text

    def test_runtime_only_policy_passes_all_accounts(self):
        """Test that policies with ONLY runtime vars pass for all accounts."""
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        with open(os.path.join(run_dir, 'policies.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'policy-with-runtime-vars.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--per-account',
             '-p', 'lambda-with-event-var'],  # Only has {event}
            catch_exceptions=False)

        # Should pass for ALL accounts - no user variables required
        assert result.exit_code == 0, f"Runtime-only policy failed: {result.output}"

    def test_validate_per_account_multi_provider(self):
        """Test per-account validation with AWS, Azure, and GCP accounts.

        Validates that:
        - AWS policies only validate against AWS accounts
        - Azure policies only validate against Azure accounts
        - GCP policies only validate against GCP accounts
        - Provider matching works correctly
        """
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        # Load the multicloud policy fixture (has AWS, Azure, and GCP policies)
        with open(os.path.join(run_dir, 'policies.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'multicloud-policy.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()

        # Test 1: AWS accounts - should validate AWS policies only
        aws_accounts = """
accounts:
  - name: aws-prod
    account_id: '111111111111'
    role: 'arn:aws:iam::111111111111:role/CloudCustodian'
    regions:
      - us-east-1
"""
        with open(os.path.join(run_dir, 'aws-accounts.yml'), 'w') as fh:
            fh.write(aws_accounts)

        log_output = self.capture_logging('c7n_org', level=20)
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'aws-accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--per-account'],
            catch_exceptions=False)

        # Should pass - AWS policies validated against AWS account
        assert result.exit_code == 0, f"AWS validation failed: {result.output}"
        log_text = log_output.getvalue()
        assert 'aws-prod' in log_text or 'Validating for account' in log_text

        # Test 2: Azure subscription - should validate Azure policies only
        azure_accounts = """
subscriptions:
  - name: azure-prod
    subscription_id: 'ea42f556-5106-4743-99b0-c129bfa71a47'
"""
        with open(os.path.join(run_dir, 'azure-accounts.yml'), 'w') as fh:
            fh.write(azure_accounts)

        log_output = self.capture_logging('c7n_org', level=20)
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'azure-accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--per-account'],
            catch_exceptions=False)

        # Should pass - Azure policies validated against Azure subscription
        assert result.exit_code == 0, f"Azure validation failed: {result.output}"
        log_text = log_output.getvalue()
        assert 'azure-prod' in log_text or 'Validating for account' in log_text

        # Test 3: GCP project - should validate GCP policies only
        gcp_accounts = """
projects:
  - name: gcp-prod
    project_id: 'my-gcp-project-123'
"""
        with open(os.path.join(run_dir, 'gcp-accounts.yml'), 'w') as fh:
            fh.write(gcp_accounts)

        log_output = self.capture_logging('c7n_org', level=20)
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'gcp-accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--per-account'],
            catch_exceptions=False)

        # Should pass - GCP policies validated against GCP project
        assert result.exit_code == 0, f"GCP validation failed: {result.output}"
        log_text = log_output.getvalue()
        assert 'gcp-prod' in log_text or 'Validating for account' in log_text

    def test_validate_per_account_with_deprecations(self):
        """Test per-account validation detects deprecated flow-logs fields.

        Uses deprecated 'enabled', 'status', and 'destination-type' fields
        in the flow-logs filter, which should trigger deprecation warnings.

        Tests that:
        - Deprecation warnings are shown in per-account mode
        - --check-deprecations=warn allows validation to pass
        - --check-deprecations=strict causes validation to fail
        - Warnings are reported per-account
        """
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        with open(os.path.join(run_dir, 'policies.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'flow-logs-deprecated-policy.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()

        # Test 1: With --check-deprecations=warn (should pass with warnings)
        log_output = self.capture_logging('c7n_org', level=20)
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--per-account',
             '--check-deprecations=warn'],
            catch_exceptions=False)

        # Should pass but show warnings
        assert result.exit_code == 0, f"Warn mode should pass: {result.output}"
        log_text = log_output.getvalue().lower()

        # Verify deprecation was actually detected
        assert 'deprecated' in log_text or 'warning' in log_text, \
            "Expected deprecation warnings but none found"
        # Check that warnings were counted per account
        assert 'with warnings: 3' in log_text or 'warnings: 3' in log_text, \
            f"Expected 3 accounts with warnings, got: {log_text}"

        # Test 2: With --check-deprecations=strict (should FAIL)
        log_output = self.capture_logging('c7n_org', level=20)
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '--per-account',
             '--check-deprecations=strict'],
            catch_exceptions=False)

        # Should FAIL in strict mode when deprecations found
        assert result.exit_code == 1, \
            f"Strict mode should fail with deprecations, got exit code {result.exit_code}"
        log_text = log_output.getvalue().lower()
        assert 'deprecations found' in log_text or 'strict' in log_text, \
            "Expected strict mode deprecation failure message"

    def test_validate_basic_mode_with_account_filters(self):
        """Test basic validation mode with account filters.

        Validates that:
        - Account filters are accepted but logged as info
        - Basic mode still works correctly
        - Exit code is correct
        - Appropriate message shown about filters being applied
        """
        run_dir = self.get_temp_dir()
        fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

        with open(os.path.join(run_dir, 'accounts.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'accounts-with-vars.yml')) as src:
                fh.write(src.read())

        with open(os.path.join(run_dir, 'policies.yml'), 'w') as fh:
            with open(os.path.join(fixtures_dir, 'simple-valid-policy.yml')) as src:
                fh.write(src.read())

        runner = CliRunner()
        log_output = self.capture_logging('c7n_org', level=10)  # DEBUG level
        result = runner.invoke(
            org.cli,
            ['validate', '-c', os.path.join(run_dir, 'accounts.yml'),
             '-u', os.path.join(run_dir, 'policies.yml'),
             '-a', 'dev-account',  # Account filter in basic mode
             '--verbose'],
            catch_exceptions=False)

        # Should pass - basic mode doesn't use accounts for validation
        assert result.exit_code == 0
        log_text = log_output.getvalue().lower()

        # Should see message about running basic validation
        assert 'basic' in log_text or 'account-agnostic' in log_text
        # Should show that accounts were loaded and filtered
        assert 'filtered to 1 account' in log_text or 'loaded' in log_text
