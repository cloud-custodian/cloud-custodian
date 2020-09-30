# Copyright 2020 Capital One Services, LLC
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest
import time
from c7n.exceptions import PolicyValidationError


class TestServiceCatalog(BaseTest):

    def test_portfolio_delete(self):
        session_factory = self.replay_flight_data("test_portfolio_delete")
        p = self.load_policy(
            {
                "name": "servicecatalog-portfolio-delete",
                "resource": "catalog-portfolio",
                "filters": [{"tag:name": "pratyush"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Id'], 'port-tb63f2b33cska')
        if self.recording:
            time.sleep(10)
        client = session_factory().client("servicecatalog")
        portfolios = client.list_portfolios()
        self.assertFalse('port-tb63f2b33cska' in [p.get(
            'Id') for p in portfolios.get('PortfolioDetails')])

    def test_portfolio_cross_account_remove(self):
        session_factory = self.replay_flight_data("test_portfolio_cross_account_remove")
        client = session_factory().client("servicecatalog")
        accounts = client.list_portfolio_access(PortfolioId='port-hlgxpz7lc55iw').get('AccountIds')
        self.assertEqual(len(accounts), 1)
        p = self.load_policy(
            {
                "name": "servicecatalog-portfolio-cross-account",
                "resource": "catalog-portfolio",
                "filters": [{"type": "cross-account"}],
                "actions": [{"type": "remove-shared-accounts", "accounts": "matched"}],
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Id'], 'port-hlgxpz7lc55iw')
        response = client.list_portfolio_access(PortfolioId='port-hlgxpz7lc55iw').get('AccountIds')
        self.assertEqual(len(response), 0)

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