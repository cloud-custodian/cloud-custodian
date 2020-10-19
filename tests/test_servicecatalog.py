# Copyright 2020 Capital One Services, LLC
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest
import time
from c7n.exceptions import PolicyValidationError


class TestServiceCatalog(BaseTest):

    def test_portfolio_cross_account_remove_delete(self):
        session_factory = self.replay_flight_data("test_portfolio_cross_account_remove_delete")
        client = session_factory().client("servicecatalog")
        accounts = client.list_portfolio_access(PortfolioId='port-3cfur4nmnvf4u').get('AccountIds')
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
        self.assertEqual(resources[0]['Id'], 'port-3cfur4nmnvf4u')
        if self.recording:
            time.sleep(10)
        portfolios = client.list_portfolios()
        self.assertFalse('port-3cfur4nmnvf4u' in [p.get(
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
            PortfolioId='port-hlgxpz7lc55iw').get('AccountIds'))
        self.assertTrue('644160558196' in client.list_portfolio_access(
            PortfolioId='port-srkytozjwbzpc').get('AccountIds'))
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
        self.assertTrue(r['Id'] in ['port-hlgxpz7lc55iw', 'port-srkytozjwbzpc'] for r in resources)
        self.assertFalse('644160558196' in client.list_portfolio_access(
            PortfolioId='port-hlgxpz7lc55iw').get('AccountIds'))
        self.assertTrue('644160558196' in client.list_portfolio_access(
            PortfolioId='port-srkytozjwbzpc').get('AccountIds'))
