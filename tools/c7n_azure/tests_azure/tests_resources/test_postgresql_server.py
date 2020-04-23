# Copyright 2019 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import pytest

from ..azure_common import BaseTest, arm_template


class PostgresqlServerTest(BaseTest):

    def test_postgresql_server_schema_validate(self):
        p = self.load_policy({
            'name': 'test-postgresql-server-schema-validate',
            'resource': 'azure.postgresql-server'
        }, validate=True)
        self.assertTrue(p)

    @arm_template('postgresql.json')
    # Due to the COVID-19 Azure hardened quota limits for internal subscriptions and
    # postgresql can't be provisioned.
    @pytest.mark.skiplive
    def test_find_server_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-postgresql-server',
            'resource': 'azure.postgresql-server',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctestpostgresqlserver*'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
