# Copyright 2018 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from .common import BaseTest

import fnmatch
import os
import time

from c7n.exceptions import PolicyExecutionError


class TestEcsService(BaseTest):

    def test_ecs_cluster_tag_augment(self):
        session_factory = self.replay_flight_data(
            'test_ecs_cluster_tag_augment')
        p = self.load_policy({
            'name': 'ctags', 'resource': 'ecs',
            'filters': [{'tag:Data': 'Magic'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['Tags'],
            [{'Key': 'Env', 'Value': 'Dev'},
             {'Key': 'Data', 'Value': 'Magic'}])

    def test_ecs_service_tag_augment(self):
        session_factory = self.replay_flight_data(
            'test_ecs_service_tag_augment')
        p = self.load_policy({
            'name': 'ctags', 'resource': 'ecs-service'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['Tags'],
            [{'Key': 'Name', 'Value': 'Dev'}])

    def test_ecs_service_by_arn(self):
        session_factory = self.replay_flight_data('test_ecs_service_by_arn')

        p = self.load_policy({
            'name': 'ecs-svc', 'resource': 'ecs-service'},
            session_factory=session_factory)
        svcs = p.resource_manager.get_resources(
            ["arn:aws:ecs:us-east-1:644160558196:service/test/test-no-delete"])
        self.assertEqual(len(svcs), 1)
        self.assertEqual(
            {t['Key']: t['Value'] for t in svcs[0]['Tags']},
            {'Env': 'Dev', 'Owner': '1'})

        self.assertRaises(
            PolicyExecutionError,
            p.resource_manager.get_resources,
            ["arn:aws:ecs:us-east-1:644160558196:service/test-no-delete"])

    def test_ecs_service_resource(self):
        session_factory = self.replay_flight_data("test_ecs_service")
        p = self.load_policy(
            {"name": "all-ecs", "resource": "ecs-service"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["serviceName"], "home-web")

    def test_ecs_service_metrics(self):
        session_factory = self.replay_flight_data("test_ecs_service_metrics")
        p = self.load_policy(
            {
                "name": "all-ecs",
                "resource": "ecs-service",
                "filters": [
                    {"serviceName": "home-web"},
                    {
                        "type": "metrics",
                        "name": "MemoryUtilization",
                        "op": "less-than",
                        "value": 1,
                    },
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("c7n.metrics" in resources[0])

    def test_ecs_service_delete(self):
        session_factory = self.replay_flight_data("test_ecs_service_delete")
        p = self.load_policy(
            {
                "name": "all-ecs",
                "resource": "ecs-service",
                "filters": [{"serviceName": "web"}],
                "actions": ["delete"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        svc = resources.pop()
        self.assertEqual(svc["serviceName"], "web")
        if self.recording:
            time.sleep(1)
        client = session_factory().client("ecs")
        svc_current = client.describe_services(
            cluster=svc["clusterArn"], services=[svc["serviceName"]]
        )[
            "services"
        ][
            0
        ]
        self.assertEqual(svc_current["serviceArn"], svc["serviceArn"])
        self.assertNotEqual(svc_current["status"], svc["status"])

    def test_ecs_service_task_def_filter(self):
        session_factory = self.replay_flight_data("test_ecs_task_def_filter")
        p = self.load_policy(
            {
                "name": "services-using-nginx",
                "resource": "ecs-service",
                "filters": [
                    {
                        "type": "task-definition",
                        "key": "containerDefinitions[].image",
                        "op": "in",
                        "value_type": "swap",
                        "value": "nginx:latest",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["serviceName"], "home-web")

    def test_ecs_service_tag(self):
        session_factory = self.replay_flight_data(
            "test_ecs_service_tag"
        )
        p = self.load_policy(
            {
                "name": "tag-ecs-service",
                "resource": "ecs-service",
                "filters": [{"serviceName": "test-service-tags"}, {"tag:TestKey": "empty"}],
                "actions": [{"type": "tag", "key": "TestKey", "value": "TestValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("ecs")
        tags = client.list_tags_for_resource(resourceArn=resources[0]["serviceArn"])["tags"]
        self.assertEqual(tags[0]["value"], "TestValue")

    def test_ecs_service_remove_tag(self):
        session_factory = self.replay_flight_data(
            "test_ecs_service_remove_tag"
        )
        p = self.load_policy(
            {
                "name": "tag-ecs-service",
                "resource": "ecs-service",
                "filters": [{"serviceName": "test-service-tags"}, {"tag:TestKey": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["TestKey"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("ecs")
        tags = client.list_tags_for_resource(resourceArn=resources[0]["serviceArn"])["tags"]
        self.assertEqual(len(tags), 0)

    def test_ecs_cluster_tag(self):
        session_factory = self.replay_flight_data(
            "test_ecs_cluster_tag"
        )
        p = self.load_policy(
            {
                "name": "tag-ecs-cluster",
                "resource": "ecs",
                "filters": [{"clusterName": "test"}, {"tag:TestKey": "empty"}],
                "actions": [{"type": "tag", "key": "TestKey", "value": "TestValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("ecs")
        tags = client.list_tags_for_resource(resourceArn=resources[0]["clusterArn"])["tags"]
        self.assertEqual(tags[0]["value"], "TestValue")

    def test_ecs_cluster_remove_tag(self):
        session_factory = self.replay_flight_data(
            "test_ecs_cluster_remove_tag"
        )
        p = self.load_policy(
            {
                "name": "tag-ecs-cluster",
                "resource": "ecs",
                "filters": [{"clusterName": "test"}, {"tag:TestKey": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["TestKey"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("ecs")
        tags = client.list_tags_for_resource(resourceArn=resources[0]["clusterArn"])["tags"]
        self.assertEqual(len(tags), 0)

    def test_ecs_cluster_mark_for_op(self):
        session_factory = self.replay_flight_data(
            "test_ecs_cluster_mark_for_op"
        )
        p = self.load_policy(
            {
                "name": "ecs-cluster-untagged-delete",
                "resource": "ecs",
                "filters": [
                    {"tag:TestKey": "absent"},
                    {"tag:custodian_tag": "absent"},
                    {"clusterName": "test"},
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_tag",
                        "op": "tag",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("ecs")
        tags = client.list_tags_for_resource(resourceArn=resources[0]["clusterArn"])["tags"]
        self.assertTrue(tags[0]["key"], "custodian_tag")

    def test_ecs_cluster_marked_for_op(self):
        session_factory = self.replay_flight_data(
            "test_ecs_cluster_marked_for_op"
        )
        p = self.load_policy(
            {
                "name": "ecs-untagged-tag",
                "resource": "ecs",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_tag",
                        "op": "tag",
                        "skew": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['clusterName'], 'test')

    def test_ecs_service_mark_for_op(self):
        session_factory = self.replay_flight_data(
            "test_ecs_service_mark_for_op"
        )
        p = self.load_policy(
            {
                "name": "ecs-service-untagged-tag",
                "resource": "ecs-service",
                "filters": [
                    {"tag:TestKey": "absent"},
                    {"tag:custodian_tag": "absent"},
                    {"serviceName": "test-service-tags"},
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_tag",
                        "op": "tag",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("ecs")
        tags = client.list_tags_for_resource(resourceArn=resources[0]["serviceArn"])["tags"]
        self.assertTrue(tags[0]["key"], "custodian_tag")

    def test_ecs_service_marked_for_op(self):
        session_factory = self.replay_flight_data(
            "test_ecs_service_marked_for_op"
        )
        p = self.load_policy(
            {
                "name": "ecs-service-untagged-tag",
                "resource": "ecs-service",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_tag",
                        "op": "tag",
                        "skew": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['serviceName'], 'test-service-tags')


class TestEcsTaskDefinition(BaseTest):

    def test_task_definition_resource(self):
        session_factory = self.replay_flight_data("test_ecs_task_def")
        p = self.load_policy(
            {"name": "task-defs", "resource": "ecs-task-definition"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 10)
        images = set()
        for r in resources:
            for c in r["containerDefinitions"]:
                images.add(c["image"])
        self.assertEqual(
            sorted(images), [
                '644160558196.dkr.ecr.us-east-1.amazonaws.com/' \
                    'omnissm-register/omnissm-register:latest', 
                'alpine:latest', 
                'busybox', 
                'capitalone/cloud-custodian', 
                'library/ubuntu', 
                'nginx:latest', 
                'redis:latest'
            ]
        )

    def test_task_definition_delete(self):
        session_factory = self.replay_flight_data("test_ecs_task_def_delete")
        p = self.load_policy(
            {
                "name": "task-defs",
                "resource": "ecs-task-definition",
                "filters": [{"family": "launch-me"}],
                "actions": ["delete"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["containerDefinitions"][0]["image"], 
            "capitalone/cloud-custodian"
        )
        self.assertEqual(resources[0]["status"], "ACTIVE")
        arns = session_factory().client("ecs").list_task_definitions(
            familyPrefix="launch-me", status="ACTIVE"
        ).get(
            "taskDefinitionArns"
        )
        self.assertEqual(arns, [])

    def test_task_definition_get_resources(self):
        session_factory = self.replay_flight_data("test_ecs_task_def_query")
        p = self.load_policy(
            {"name": "task-defs", "resource": "ecs-task-definition"},
            session_factory=session_factory,
        )
        arn = "arn:aws:ecs:us-east-1:644160558196:task-definition/ecs-read-only-root:1"
        resources = p.resource_manager.get_resources([arn])
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["taskDefinitionArn"], arn)
        self.assertEqual(
            len(
                fnmatch.filter(
                    os.listdir(
                        os.path.join(self.placebo_dir, "test_ecs_task_def_query")
                    ),
                    "*.json",
                )
            ),
            1,
        )

    def test_ecs_task_def_tag(self):
        session_factory = self.replay_flight_data(
            "test_ecs_task_def_tag"
        )
        arn = "arn:aws:ecs:us-east-1:644160558196:task-definition/c7n:1"
        p = self.load_policy(
            {
                "name": "tag-ecs-task-def",
                "resource": "ecs-task-definition",
                "filters": [
                    {"taskDefinitionArn": arn}, 
                    {"tag:TestKey": "empty"}
                ],
                "actions": [{"type": "tag", "key": "TestKey", "value": "TestValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("ecs")
        res = resources[0]["taskDefinitionArn"]
        tags = client.list_tags_for_resource(resourceArn=res)["tags"]
        self.assertEqual(tags[0]["value"], "TestValue")
    
    def test_ecs_task_def_remove_tag(self):
        session_factory = self.replay_flight_data(
            "test_ecs_task_def_remove_tag"
        )
        arn = "arn:aws:ecs:us-east-1:644160558196:task-definition/c7n:1"
        p = self.load_policy(
            {
                "name": "tag-ecs-task-def",
                "resource": "ecs-task-definition",
                "filters": [
                    {"taskDefinitionArn": arn}, 
                    {"tag:TestKey": "present"}
                ],
                "actions": [{"type": "remove-tag", "tags": ["TestKey"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("ecs")
        res = resources[0]["taskDefinitionArn"]
        tags = client.list_tags_for_resource(resourceArn=res)["tags"]
        self.assertEqual(len(tags), 0)

    def test_ecs_task_def_mark_for_op(self):
        session_factory = self.replay_flight_data(
            "test_ecs_task_def_mark_for_op"
        )
        tdArn = 'arn:aws:ecs:us-east-1:644160558196:task-definition/c7n:1'
        p = self.load_policy(
            {
                "name": "ecs-task-def-untagged-tag",
                "resource": "ecs-task-definition",
                "filters": [
                    {"tag:TestKey": "present"},
                    {"tag:custodian_tag": "absent"},
                    {"taskDefinitionArn": tdArn},
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_tag",
                        "op": "tag",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("ecs")
        arn = resources[0]["taskDefinitionArn"]
        tags = client.list_tags_for_resource(resourceArn=arn)["tags"]
        self.assertTrue(tags[0]["key"], "custodian_tag")

    def test_ecs_task_def_marked_for_op(self):
        session_factory = self.replay_flight_data(
            "test_ecs_task_def_marked_for_op"
        )
        p = self.load_policy(
            {
                "name": "ecs-task-def-untagged-tag",
                "resource": "ecs-task-definition",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_tag",
                        "op": "tag",
                        "skew": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        tdArn = 'arn:aws:ecs:us-east-1:644160558196:task-definition/c7n:1'
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['taskDefinitionArn'], tdArn)


class TestEcsTask(BaseTest):

    def test_task_by_arn(self):
        session_factory = self.replay_flight_data('test_ecs_task_by_arn')
        p = self.load_policy({
            'name': 'tasks', 'resource': 'ecs-task'}, session_factory=session_factory)
        tasks = p.resource_manager.get_resources([
            'arn:aws:ecs:us-east-1:644160558196:task/devx/21b23041dec947b996fcc7a8aa606d64'])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['launchType'], 'FARGATE')
        self.assertEqual(tasks[0]['lastStatus'], 'STOPPED')

        self.assertRaises(
            PolicyExecutionError,
            p.resource_manager.get_resources,
            ['arn:aws:ecs:us-east-1:644160558196:task/21b23041dec947b996fcc7a8aa606d64'])

    def test_task_resource(self):
        session_factory = self.replay_flight_data("test_ecs_task")
        p = self.load_policy(
            {"name": "tasks", "resource": "ecs-task"}, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 4)

    def test_task_delete(self):
        session_factory = self.replay_flight_data("test_ecs_task_delete")
        p = self.load_policy(
            {
                "name": "tasks",
                "resource": "ecs-task",
                "filters": [{"group": "service:home-web"}, {"startedBy": "present"}],
                "actions": ["stop"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        client = session_factory().client("ecs")
        tasks = client.list_tasks(cluster=resources[0]["clusterArn"])["taskArns"]
        self.assertFalse(set([r["taskArn"] for r in resources]).intersection(tasks))


class TestEcsContainerInstance(BaseTest):

    def test_container_instance_resource(self):
        session_factory = self.replay_flight_data("test_ecs_container_instance")
        p = self.load_policy(
            {"name": "container-instances", "resource": "ecs-container-instance"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_container_instance_update_agent(self):
        session_factory = self.replay_flight_data(
            "test_ecs_container_instance_update_agent"
        )
        p = self.load_policy(
            {
                "name": "container-instance-update-agent",
                "resource": "ecs-container-instance",
                "actions": [{"type": "update-agent"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        if self.recording:
            time.sleep(60)
        client = session_factory().client("ecs")
        updated_version = client.describe_container_instances(
            cluster="default",
            containerInstances=["a8a469ef-009f-40f8-9639-3a0d9c6a9b9e"],
        )[
            "containerInstances"
        ][
            0
        ][
            "versionInfo"
        ][
            "agentVersion"
        ]
        self.assertNotEqual(
            updated_version, resources[0]["versionInfo"]["agentVersion"]
        )

    def test_container_instance_set_state(self):
        session_factory = self.replay_flight_data(
            "test_ecs_container_instance_set_state"
        )
        p = self.load_policy(
            {
                "name": "container-instance-update-agent",
                "resource": "ecs-container-instance",
                "actions": [{"type": "set-state", "state": "DRAINING"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        client = session_factory().client("ecs")
        state = client.describe_container_instances(
            cluster="default", containerInstances=[resources[0]["containerInstanceArn"]]
        )[
            "containerInstances"
        ][
            0
        ][
            "status"
        ]
        self.assertEqual(state, "DRAINING")
