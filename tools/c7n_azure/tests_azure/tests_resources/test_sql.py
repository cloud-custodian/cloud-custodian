# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest
from c7n_azure.session import Session
from c7n.utils import local_session


class SqlServerVulnerabilityAssessmentsTest(BaseTest):

    def setUp(self):
        super(SqlServerVulnerabilityAssessmentsTest, self).setUp()
        self.client = local_session(Session).client('azure.mgmt.sql.SqlManagementClient')

    def test_validate_schemas(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-sql-server-vulnerability-assessments-schema-validate',
                'resource': 'azure.sql-server-vulnerability-assessments'
            }, validate=True)
            self.assertTrue(p)
