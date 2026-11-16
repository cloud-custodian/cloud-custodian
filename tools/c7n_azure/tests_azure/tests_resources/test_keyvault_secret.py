# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime

import pytest

from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n_azure import utils

from ..azure_common import BaseTest, arm_template, cassette_name


class KeyVaultSecretsTest(BaseTest):

    def tearDown(self, *args, **kwargs):
        super(KeyVaultSecretsTest, self).tearDown(*args, **kwargs)

    def test_key_vault_secrets_schema_validate(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-secret',
        }, validate=True)
        self.assertTrue(p)

    @arm_template('keyvault.json')
    def test_key_vault_secrets_keyvault(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-secret',
            'filters': [
                {
                    'type': 'parent',
                    'filter': {
                        'type': 'value',
                        'key': 'name',
                        'op': 'glob',
                        'value': 'cfb*'
                    }
                },
            ]
        }, validate=True, cache=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('keyvault.json')
    def test_key_vault_secrets_expiry(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-secret',
            'filters': [
                {
                    'type': 'value',
                    'key': 'attributes.expires',
                    'op': 'equal',
                    'value': 'not-null'
                },
            ]
        }, validate=True, cache=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)


class KeyVaultSecretUpdateActionTest(BaseTest):

    def test_key_vault_secret_update_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-key-vault-secret-update',
                'resource': 'azure.keyvault-secret',
                'actions': [
                    {
                        'type': 'update',
                        'enabled': True,
                        'tags': {'owner': 'c7n'},
                        'content_type': 'text/plain',
                        'not_before': '2026-01-01 00:00:00',
                        'expires_in_days': 365
                    }
                ]
            }, validate=True)
            assert p

    def test_key_vault_secret_update_expires_mutually_exclusive(self):
        with self.sign_out_patch():
            with pytest.raises(PolicyValidationError, match='mutually exclusive'):
                self.load_policy({
                    'name': 'test-key-vault-secret-update',
                    'resource': 'azure.keyvault-secret',
                    'actions': [
                        {
                            'type': 'update',
                            'expires_on': '2026-12-31 00:00:00',
                            'expires_in_days': 365
                        }
                    ]
                }, validate=True)

    def test_key_vault_secret_update_invalid_date(self):
        for field in ('not_before', 'expires_on'):
            with self.sign_out_patch():
                with pytest.raises(PolicyValidationError, match=f"'{field}' must be an ISO"):
                    self.load_policy({
                        'name': 'test-key-vault-secret-update',
                        'resource': 'azure.keyvault-secret',
                        'actions': [
                            {
                                'type': 'update',
                                field: '12/31/2026'
                            }
                        ]
                    }, validate=True)

    def test_key_vault_secret_update_not_before_after_expires_on(self):
        with self.sign_out_patch():
            with pytest.raises(PolicyValidationError, match="must be earlier"):
                self.load_policy({
                    'name': 'test-key-vault-secret-update',
                    'resource': 'azure.keyvault-secret',
                    'actions': [
                        {
                            'type': 'update',
                            'not_before': '2027-06-01T00:00:00Z',
                            'expires_on': '2027-01-01T00:00:00Z'
                        }
                    ]
                }, validate=True)

    def test_key_vault_secret_update_not_before_after_expires_in_days(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-key-vault-secret-update',
                'resource': 'azure.keyvault-secret',
                'actions': [
                    {
                        'type': 'update',
                        'not_before': '2999-01-01T00:00:00Z',
                        'expires_in_days': 30
                    }
                ]
            }, validate=True)
            # The expiration is only resolved at run time, so the check runs
            # before any secret is updated.
            with pytest.raises(PolicyExecutionError, match="must be earlier"):
                p.resource_manager.actions[0].process([])

    @arm_template('keyvault-secret.json')
    @cassette_name('secret_update')
    def test_key_vault_secret_update_action(self):
        filters = [
            {
                'type': 'parent',
                'filter': {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value': 'cckvsecret*'
                }
            },
            {
                'type': 'value',
                'key': 'id',
                'op': 'glob',
                'value': '*/secrets/cctest-secret-noexp'
            },
            {
                'type': 'value',
                'key': 'attributes.expires',
                'value': None
            },
        ]

        # Discovery: resolve the secret and capture its baseline properties.
        p = self.load_policy({
            'name': 'test-key-vault-secret-discover',
            'resource': 'azure.keyvault-secret',
            'filters': filters,
        })
        resources = p.run()
        assert len(resources) == 1

        resource_id = resources[0]['vault_id']['resource_id']
        assert resource_id['name'] == 'cctest-secret-noexp'
        client = p.resource_manager.get_client(vault_url=resource_id['vault_url'])

        def get_properties():
            return next(
                s for s in client.list_properties_of_secrets()
                if s.name == resource_id['name']
            )

        before = get_properties()
        assert before.expires_on is None
        assert before.not_before is None
        assert before.content_type is None
        assert before.enabled is True

        # Mutation: set a 'Z'-suffixed activation date, a relative expiration
        # and a content type.
        p = self.load_policy({
            'name': 'test-key-vault-secret-update',
            'resource': 'azure.keyvault-secret',
            'filters': filters,
            'actions': [
                {
                    'type': 'update',
                    'not_before': '2026-01-01T00:00:00Z',
                    'expires_in_days': 365,
                    'content_type': 'text/plain'
                }
            ]
        })
        # Key Vault stores whole seconds and the clock is only pinned under VCR,
        # so bound the expiry by the time window around the run.
        lower = utils.utcnow().replace(microsecond=0)
        resources = p.run()
        assert len(resources) == 1

        after = get_properties()
        upper = utils.utcnow()
        delta = datetime.timedelta(days=365)
        expires_on = after.expires_on.replace(tzinfo=None)
        assert lower + delta <= expires_on <= upper + delta
        assert after.not_before == datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        assert after.content_type == 'text/plain'
        # Fields not in the action are left untouched.
        assert after.enabled is True

    @arm_template('keyvault-secret.json')
    @cassette_name('secret_update_tags')
    def test_key_vault_secret_update_action_merges_tags(self):
        filters = [
            {
                'type': 'parent',
                'filter': {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value': 'cckvsecret*'
                }
            },
            {
                'type': 'value',
                'key': 'id',
                'op': 'glob',
                'value': '*/secrets/cctest-secret-tags'
            },
        ]

        # Discovery: resolve the secret and capture its baseline tags.
        p = self.load_policy({
            'name': 'test-key-vault-secret-discover',
            'resource': 'azure.keyvault-secret',
            'filters': filters,
        })
        resources = p.run()
        assert len(resources) == 1

        resource_id = resources[0]['vault_id']['resource_id']
        assert resource_id['name'] == 'cctest-secret-tags'
        client = p.resource_manager.get_client(vault_url=resource_id['vault_url'])

        def get_properties():
            return next(
                s for s in client.list_properties_of_secrets()
                if s.name == resource_id['name']
            )

        before = get_properties()
        assert before.tags == {'env': 'prod', 'owner': 'team-a'}

        # Mutation: change one tag; tags not named in the action should be kept.
        p = self.load_policy({
            'name': 'test-key-vault-secret-update-tags',
            'resource': 'azure.keyvault-secret',
            'filters': filters,
            'actions': [
                {
                    'type': 'update',
                    'tags': {'owner': 'c7n'}
                }
            ]
        })
        resources = p.run()
        assert len(resources) == 1

        after = get_properties()
        assert after.tags == {'env': 'prod', 'owner': 'c7n'}
