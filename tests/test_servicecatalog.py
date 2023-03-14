# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest
import time
from c7n.exceptions import PolicyValidationError


class TestServiceCatalog(BaseTest):

    def test_portfolio_cross_account_remove_delete(self):
        session_factory = self.replay_flight_data("test_portfolio_cross_account_remove_delete")
        client = session_factory().client("servicecatalog")
        accounts = client.list_portfolio_access(PortfolioId='port-t24m4nifknphk').get('AccountIds')
        self.assertEqual(len(accounts), 1)
        p = self.load_policy(
            {
                "name": "servicecatalog-portfolio-cross-account",
                "resource": "catalog-portfolio",
                "filters": [{"type": "cross-account"}],
                "actions": [
                    {"type": "remove-shared-accounts", "accounts": "matched"},
                    {"type": "delete"}
                ],
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Id'], 'port-t24m4nifknphk')
        if self.recording:
            time.sleep(10)
        portfolios = client.list_portfolios()
        self.assertFalse('port-t24m4nifknphk' in [p.get(
            'Id') for p in portfolios.get('PortfolioDetails')])

    def test_remove_accounts_validation_error(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "catalog-portfolio-delete-shared-accounts",
                "resource": "aws.catalog-portfolio",
                "actions": [{"type": "remove-shared-accounts", "accounts": "matched"}],
            }
        )

    def test_portfolio_remove_share_accountid(self):
        session_factory = self.replay_flight_data("test_portfolio_remove_share_accountid")
        client = session_factory().client("servicecatalog")
        self.assertTrue('644160558196' in client.list_portfolio_access(
            PortfolioId='port-srkytozjwbzpc').get('AccountIds'))
        self.assertTrue('644160558196' in client.list_portfolio_access(
            PortfolioId='port-cpxttnlqoph32').get('AccountIds'))
        p = self.load_policy(
            {
                "name": "servicecatalog-portfolio-cross-account",
                "resource": "catalog-portfolio",
                "filters": [{"type": "cross-account"}],
                "actions": [{"type": "remove-shared-accounts", "accounts": ["644160558196"]}],
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertTrue(r['Id'] in ['port-cpxttnlqoph32', 'port-srkytozjwbzpc'] for r in resources)
        self.assertFalse('644160558196' in client.list_portfolio_access(
            PortfolioId='port-srkytozjwbzpc').get('AccountIds'))
        self.assertTrue('644160558196' in client.list_portfolio_access(
            PortfolioId='port-cpxttnlqoph32').get('AccountIds'))

    def test_portfolio_cross_account_whitelist(self):
        session_factory = self.replay_flight_data("test_portfolio_cross_account_whitelist")
        client = session_factory().client("servicecatalog")
        accounts = client.list_portfolio_access(PortfolioId='port-cpxttnlqoph32').get('AccountIds')
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts, ['644160558196'])
        p = self.load_policy(
            {
                "name": "servicecatalog-portfolio-cross-account",
                "resource": "catalog-portfolio",
                "filters": [{"type": "cross-account", "whitelist": ["644160558196"]}]
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_catalog_product_resource(self):
        session_factory = self.replay_flight_data('test_catalog_product_resource')
        p = self.load_policy(
            {
                'name': 'test-catalog-product',
                'resource': 'catalog-product',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'ProductId',
                        'value': 'test-6orqs3iobd7om'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['Name'], 'testProduct')
