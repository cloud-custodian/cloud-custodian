# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from ..azure_common import BaseTest, arm_template


class RouteTableTest(BaseTest):

    route_table_name = 'cctestroutetable'
    vnet_name = 'ccroutetablevnet'
    allowed_subnet_name = 'cctestsubnet1'
    disallowed_subnet_name = 'cctestsubnet2'

    @staticmethod
    def _subnet_id_suffix(subnet):
        return '{}/subnets/{}'.format(RouteTableTest.vnet_name, subnet)

    def test_route_table_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-route-table',
                'resource': 'azure.routetable'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('route-table-and-vnet.json')
    def test_find_route_table_by_name(self):

        p = self.load_policy({
            'name': 'test-find-route-table-by-name',
            'resource': 'azure.routetable',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': RouteTableTest.route_table_name
                }
            ]
        })

        resources = p.run()
        self._assert_only_route_table_in_resources(resources)

    @arm_template('route-table-and-vnet.json')
    def test_detect_route_table_is_routing_to_correct_subnet(self):

        p = self.load_policy({
            'name': 'test-detect-route-table-is-routing-to-correct-subnet',
            'resource': 'azure.routetable',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': RouteTableTest.route_table_name
                },
                {
                    'type': 'value',
                    'key': 'properties.subnets[?ends_with(id, \'{}\')] | [0]'.format(
                        RouteTableTest._subnet_id_suffix(RouteTableTest.allowed_subnet_name)
                    ),
                    'value': 'not-null'
                }
            ]
        })

        resources = p.run()
        self._assert_only_route_table_in_resources(resources)

    @arm_template('route-table-and-vnet.json')
    def test_detect_route_table_not_routing_to_incorrect_subnet(self):

        p = self.load_policy({
            'name': 'test-detect-route-table-not-routing-to-incorrect-subnet',
            'resource': 'azure.routetable',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': RouteTableTest.route_table_name
                },
                {
                    'type': 'value',
                    'key': 'properties.subnets[?ends_with(id, \'{}\')] | [0]'.format(
                        RouteTableTest._subnet_id_suffix(RouteTableTest.disallowed_subnet_name)
                    ),
                    'value': 'not-null'
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 0, "A route table is routing to a disallowed subnet")

    @arm_template('route-table-and-vnet.json')
    def test_detect_route_only_routes_to_specific_subnets(self):

        p = self.load_policy({
            'name': 'test-detect-route-only-routes-to-specific-subnets',
            'resource': 'azure.routetable',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': RouteTableTest.route_table_name
                },
                {
                    'type': 'value',
                    'key': 'properties.subnets[?ends_with(id, \'{}\')] | [0]'.format(
                        RouteTableTest._subnet_id_suffix(RouteTableTest.allowed_subnet_name)
                    ),
                    'value': 'not-null'
                },
                {
                    'type': 'value',
                    'key': 'length(properties.subnets)',
                    'op': 'eq',
                    'value': 1
                }
            ]
        })

        resources = p.run()
        self._assert_only_route_table_in_resources(resources)

    def _assert_only_route_table_in_resources(self, resources):

        self.assertEqual(len(resources), 1, "Only one route table should be found")

        route_table = resources[0]
        self.assertEqual(RouteTableTest.route_table_name, route_table.get('name'),
                         "The wrong route table was found")

        properties = route_table.get('properties')
        self.assertIsNotNone(properties, "Missing properties")

        subnets = properties.get('subnets')
        self.assertIsNotNone(subnets, "Missing subnets")
        self.assertEqual(1, len(subnets), "There should only be one subnet")

        subnet = subnets[0]
        self.assertIn(RouteTableTest.allowed_subnet_name, subnet.get('id'), "Incorrect subnet")
