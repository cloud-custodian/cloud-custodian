# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from pytest_terraform import terraform

from gcp_common import BaseTest


class NotebookInstanceTest(BaseTest):

    def test_notebook_instance_query(self):
        project_id = self.project_id
        factory = self.replay_flight_data('test_notebook_instance_list_query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'notebook-instance-query',
             'resource': 'gcp.notebook'},
            session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'projects/cloud-custodian/'
                                               'locations/us-central1-a/instances/instancetest')
        assert p.resource_manager.get_urns(resources) == [
            f"gcp:notebooks:us-central1-a:{project_id}:instances/instancetest"
        ]


@terraform("notebook_v2")
def test_notebook_v2(test, notebook_v2):
    notebook_name = notebook_v2["google_workbench_instance.public_instance.name"]

    factory = test.replay_flight_data("notebook_v2")
    policy = test.load_policy(
        {
            "name": "notebook-v2",
            "resource": "gcp.notebook-v2",
            "filters": [
                {
                    "type": "value",
                    "key": "name",
                    "op": "regex",
                    "value": f".*{notebook_name}$",
                },
                {
                    "type": "value",
                    "key": "gceSetup.disablePublicIp",
                    "op": "ne",
                    "value": True,
                },
            ],
        },
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]["name"].endswith(notebook_name)
    assert resources[0]["gceSetup"]["networkInterfaces"][0]["accessConfigs"][0]["externalIp"]
