# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

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
    # Doesn't filter by a name derived from the notebook_v2 terraform fixture
    # output: that fixture is function-scoped, so tf_resources.json on disk
    # reflects whichever @terraform("notebook_v2") test last provisioned its
    # own instance -- filtering by such a name here breaks whenever another
    # test using the same fixture is (re-)recorded.
    factory = test.replay_flight_data("notebook_v2")
    policy = test.load_policy(
        {
            "name": "notebook-v2",
            "resource": "gcp.notebook-v2",
            "filters": [
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
    assert resources[0]["gceSetup"]["networkInterfaces"][0]["accessConfigs"][0]["externalIp"]


@terraform("notebook_v2")
def test_notebook_v2_get(test, notebook_v2):
    factory = test.replay_flight_data("test_notebook_v2_get")
    policy = test.load_policy(
        {
            "name": "notebook-v2-get",
            "resource": "gcp.notebook-v2",
        },
        session_factory=factory,
    )

    listed = policy.run()
    assert len(listed) == 1

    fetched = policy.resource_manager.get_resource(
        {"resourceName": listed[0]["name"]}
    )
    assert fetched["name"] == listed[0]["name"]
    assert fetched["gceSetup"]["metadata"] == listed[0]["gceSetup"].get("metadata", {})


@terraform("notebook_v2")
def test_notebook_v2_update_metadata(test, notebook_v2):
    factory = test.replay_flight_data("test_notebook_v2_update_metadata")
    policy = test.load_policy(
        {
            "name": "notebook-v2-update-metadata",
            "resource": "gcp.notebook-v2",
            "actions": [
                {
                    "type": "update-metadata",
                    "metadata": {"idle-timeout-seconds": "3600"},
                },
            ],
        },
        session_factory=factory,
    )

    # notebooks.instances.list can lag briefly after instance creation.
    # Replay uses recorded responses, so only sleep while recording live.
    if test.recording:
        time.sleep(30)

    resources = policy.run()
    assert len(resources) == 1
    original_metadata = dict(resources[0]["gceSetup"].get("metadata", {}))

    # The patch call returns a long-running Operation -- give it time to
    # finish before checking the result.
    if test.recording:
        time.sleep(30)

    fetched = policy.resource_manager.get_resource(
        {"resourceName": resources[0]["name"]}
    )
    assert fetched["gceSetup"]["metadata"]["idle-timeout-seconds"] == "3600"
    for key, value in original_metadata.items():
        assert fetched["gceSetup"]["metadata"][key] == value
