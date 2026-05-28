# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

PROJECT_ID = 'cloud-custodian'


class TestNCC:
    def test_ncc_spoke_query(self, test):
        factory = test.replay_flight_data('ncc-spoke-query', project_id=PROJECT_ID)
        p = test.load_policy(
            {'name': 'ncc-spoke-query', 'resource': 'gcp.ncc-spoke'},
            session_factory=factory,
        )
        resources = p.run()
        assert len(resources) == 5
        assert resources[0]['name'] == (
            'projects/cloud-custodian/locations/global/spokes/custodian-center-spoke'
        )

    def test_ncc_spoke_get(self, test):
        factory = test.replay_flight_data('ncc-spoke-get', project_id=PROJECT_ID)
        p = test.load_policy(
            {'name': 'ncc-spoke-get', 'resource': 'gcp.ncc-spoke'},
            session_factory=factory,
        )
        resource = p.resource_manager.get_resource(
            {
                'name': 'projects/cloud-custodian/locations/global/spokes/custodian-center-spoke',
                'project_id': PROJECT_ID,
            }
        )
        assert resource['name'] == (
            'projects/cloud-custodian/locations/global/spokes/custodian-center-spoke'
        )

    def test_ncc_spoke_delete(self, test):
        factory = test.replay_flight_data('ncc-spoke-delete', project_id=PROJECT_ID)
        p = test.load_policy(
            {
                'name': 'ncc-spoke-delete',
                'resource': 'gcp.ncc-spoke',
                'filters': [
                    {
                        'name': (
                            'projects/cloud-custodian/locations/global/spokes/'
                            'custodian-edge-spoke-1'
                        )
                    }
                ],
                'actions': ['delete'],
            },
            session_factory=factory,
        )
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['name'] == (
            'projects/cloud-custodian/locations/global/spokes/custodian-edge-spoke-1'
        )
