# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest

import fnmatch
import os
import time

from c7n.exceptions import PolicyExecutionError
from c7n.resources.aws import Arn


class TestEcs(BaseTest):
    def test_ecs_container_insights_enabled(self):
        session_factory = self.replay_flight_data(
            'test_ecs_container_insights_enabled')
        p = self.load_policy(
            {
                "name": "ecs-container-insights",
                "resource": 'ecs',
                "filters": [
                    {
                        "type": "value",
                        "key": "settings[?(name=='containerInsights')].value",
                        "op": "contains",
                        "value": "disabled",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_ecs_container_insights_disabled(self):
        session_factory = self.replay_flight_data(
            'test_ecs_container_insights_disabled')
        p = self.load_policy(
            {
                "name": "ecs-container-insights",
                "resource": 'ecs',
                "filters": [
                    {
                        "type": "value",
                        "key": "settings[?(name=='containerInsights')].value",
                        "op": "contains",
                        "value": "disabled",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_ecs_cluster_storage(self):
        session_factory = self.replay_flight_data("test_ecs_cluster_storage")
        p = self.load_policy(
            {
                "name": "ecs-cluster-storage",
                "resource": "ecs",
                "filters": [
                    {
                        "type": "ebs-storage",
                        "key": "Encrypted",
                        "op": "eq",
                        "value": True
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_ecs_cluster_exec_cw_logging(self):
        session_factory = self.replay_flight_data("test_ecs_cluster_exec_cw_logging")
        p = self.load_policy(
        {
            "name": "ecs-cluster-exec-cw-logging",
            "resource": "ecs",
            "filters": [
                {
                    "type": "value",
                    "key": "configuration.executeCommandConfiguration."
                           "logConfiguration.cloudWatchLogGroupName",
                    "value": "present"
                },
                {
                    "type": "value",
                    "key": "configuration.executeCommandConfiguration."
                           "logConfiguration.cloudWatchEncryptionEnabled",
                    "value": False
                }
            ],
        },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


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

    def test_ecs_service_config(self):
        session_factory = self.replay_flight_data(
            'test_ecs_service_config')
        p = self.load_policy({
            'name': 'ctags', 'resource': 'ecs-service', 'source': 'config'},
            session_factory=session_factory)
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['name'] == 'queue-processor'
        assert resources[0]['clusterArn'].endswith('cluster/dev')

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

    def test_ecs_service_modify_definition(self):
        factory = self.replay_flight_data("test_ecs_service_update_definition", region="us-east-2")
        p = self.load_policy(
            {"name": "update-definition",
             "resource": "aws.ecs-service",
             "filters": [
                 {'serviceName': 'redash-server'},
                 "cost-optimization"],
             "actions": ["modify-definition"]},
            config={"region": "us-east-2"},
            session_factory=factory,
        )
        resources = p.run()
        assert len(resources) == 1
        rservice = resources.pop()
        client = factory().client('ecs')
        cluster, service_name = Arn.parse(rservice['serviceArn']).resource.split('/')
        cservice = client.describe_services(
            cluster=cluster,
            services=[service_name]
        )["services"][0]

        rtask = client.describe_task_definition(
            taskDefinition=rservice['taskDefinition'])['taskDefinition']
        ctask = client.describe_task_definition(
            taskDefinition=cservice['taskDefinition'])['taskDefinition']

        assert cservice['taskDefinition'] != rservice['taskDefinition']
        assert rtask['cpu'] != ctask['cpu']
        assert rtask['memory'] != ctask['memory']

    def test_ecs_service_update(self):
        session_factory = self.replay_flight_data("test_ecs_service_update")
        test_service_name = 'custodian-service-update-test'

        p = self.load_policy(
            {
                "name": "all-ecs-to-update",
                "resource": "ecs-service",
                "filters": [
                    {"networkConfiguration.awsvpcConfiguration.assignPublicIp": "ENABLED"},
                    {"serviceName": test_service_name}
                ],
                "actions": [
                    {
                        'type': 'modify',
                        'update': {
                            'networkConfiguration': {
                                'awsvpcConfiguration': {
                                    'assignPublicIp': 'DISABLED',
                                }
                            },
                        }
                    }
                ],
            },
            session_factory=session_factory,
        )
        result = p.run()
        self.assertEqual(len(result), 1)

        client = session_factory().client("ecs")
        svc_current = client.describe_services(
            cluster="arn:aws:ecs:us-east-1:644160558196:cluster/test-cluster",
            services=[test_service_name]
        )["services"][0]
        self.assertEqual(svc_current['networkConfiguration'][
            'awsvpcConfiguration']['assignPublicIp'], 'DISABLED')

    def test_ecs_service_autoscaling_offhours(self):
        session_factory = self.replay_flight_data("test_ecs_service_autoscaling_offhours")
        test_service_name = 'custodian-service-autoscaling-test'

        p = self.load_policy(
            {
                "name": "all-ecs-to-autoscaling",
                "resource": "ecs-service",
                "filters": [
                    {"serviceName": test_service_name}
                ],
                "actions": [
                    {
                        'type': 'resize',
                        'min-capacity': 0,
                        'desired': 0,
                        'save-options-tag': 'OffHoursPrevious',
                        'suspend-scaling': True,
                    }
                ],
            },
            session_factory=session_factory,
        )
        result = p.run()
        self.assertEqual(len(result), 1)

        client = session_factory().client("ecs")
        svc_current = client.describe_services(
            cluster="arn:aws:ecs:us-east-1:644160558196:cluster/test-cluster",
            services=[test_service_name]
        )["services"][0]
        self.assertEqual(svc_current['desiredCount'], 0)

    def test_ecs_service_autoscaling_onhours(self):
        session_factory = self.replay_flight_data("test_ecs_service_autoscaling_onhours")
        test_service_name = 'custodian-service-autoscaling-test'

        p = self.load_policy(
            {
                "name": "all-ecs-to-autoscaling",
                "resource": "ecs-service",
                "filters": [
                    {"serviceName": test_service_name}
                ],
                "actions": [
                    {
                        'type': 'resize',
                        'restore-options-tag': 'OffHoursPrevious',
                        'restore-scaling': True,
                    }
                ],
            },
            session_factory=session_factory,
        )
        result = p.run()
        self.assertEqual(len(result), 1)

        client = session_factory().client("ecs")
        svc_current = client.describe_services(
            cluster="arn:aws:ecs:us-east-1:644160558196:cluster/test-cluster",
            services=[test_service_name]
        )["services"][0]
        self.assertEqual(svc_current['desiredCount'], 1)

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

    def test_ecs_service_taggable(self):
        services = [
            {"serviceArn": "arn:aws:ecs:us-east-1:644160558196:service/test/test-yes-tag",
             "serviceName": "test-yes-tag",
             "clusterArn": "arn:aws:ecs:us-east-1:644160558196:cluster/test"},
            {"serviceArn": "arn:aws:ecs:us-east-1:644160558196:service/test-no-tag",
             "serviceName": "test-no-tag",
             "clusterArn": "arn:aws:ecs:us-east-1:644160558196:cluster/test"}]
        p = self.load_policy({
            "name": "ecs-service-taggable",
            "resource": "ecs-service",
            "filters": [
                {"type": "taggable", "state": True}]})
        resources = p.resource_manager.filter_resources(services)
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['serviceName'], 'test-yes-tag')

    def test_ecs_service_subnet(self):
        session_factory = self.replay_flight_data("test_ecs_service_subnet")
        p = self.load_policy(
            {
                "name": "ecs-service-subnets",
                "resource": "ecs-service",
                "filters": [
                    {
                        "type": "subnet",
                        "key": "tag:Name",
                        "value": "implied"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["serviceName"], "c7n-test")

    def test_ecs_service_taskset_delete(self):
        session_factory = self.replay_flight_data("test_ecs_service_taskset_delete")
        p = self.load_policy(
            {
                "name": "test-ecs-service-taskset-delete",
                "resource": "ecs-service",
                "filters": [{"serviceName": "test-task-set-delete"}],
                "actions": ["delete"],
            },
            session_factory=session_factory,
        )
        resources = p.run()

        # Remove duplicate response
        unique_services = {svc['serviceArn']: svc for svc in resources}.values()
        self.assertEqual(len(unique_services), 1)
        svc = resources.pop()
        self.assertEqual(svc["serviceName"], "test-task-set-delete")
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


class TestEcsTaskDefinition(BaseTest):

    def test_task_definition_resource(self):
        session_factory = self.replay_flight_data("test_ecs_task_def")
        p = self.load_policy(
            {"name": "task-defs", "resource": "ecs-task-definition"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        images = set()
        for r in resources:
            for c in r["containerDefinitions"]:
                images.add(c["image"])
        self.assertEqual(
            sorted(images), ["nginx:latest", "postgres:latest", "redis:latest"]
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
            resources[0]["containerDefinitions"][0]["image"], "postgres:latest"
        )
        self.assertEqual(resources[0]["status"], "ACTIVE")
        arns = session_factory().client("ecs").list_task_definitions(
            familyPrefix="launch-me", status="ACTIVE"
        ).get(
            "taskDefinitionArns"
        )
        self.assertEqual(arns, [])

    def test_task_definition_delete_permanently(self):
        session_factory = self.replay_flight_data("test_ecs_task_def_delete_permanently")
        p = self.load_policy(
            {
                "name": "task-defs",
                "resource": "ecs-task-definition",
                "filters": [{"family": "test-delete-definition"}],
                "actions": [{"type": "delete", "force": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arns = session_factory().client("ecs").list_task_definitions(
            familyPrefix="test-delete-definition", status="DELETE_IN_PROGRESS"
        ).get(
            "taskDefinitionArns"
        )
        self.assertEqual(arns,
                         ["arn:aws:ecs:us-east-1:644160558196:task-definition/test-delete-definition:2"])

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

    def test_ecs_task_def_tags(self):
        session_factory = self.replay_flight_data(
            "test_ecs_task_def_tags"
        )
        arn = "arn:aws:ecs:us-east-1:644160558196:task-definition/c7n:1"
        p = self.load_policy(
            {
                "name": "tag-ecs-task-def",
                "resource": "ecs-task-definition",
                "filters": [
                    {"taskDefinitionArn": arn},
                    {"tag:Role": "present"}
                ],
                "actions": [
                    {"type": "tag", "key": "TestKey", "value": "TestValue"},
                    {"type": "tag", "key": "c7n-tag", "value": "present"},
                    {"type": "remove-tag", "tags": ["Role"]}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("ecs")
        tags = {t['key']: t['value'] for t in
                client.list_tags_for_resource(
                    resourceArn=resources[0]["taskDefinitionArn"]).get("tags")}
        self.assertEqual(tags, {"TestKey": "TestValue", "c7n-tag": "present"})

    def test_ecs_task_def_config(self):
        session_factory = self.replay_flight_data("test_ecs_task_def_config")
        p = self.load_policy(
            {
                "name": "ecs-task-def-config-tag",
                "resource": "ecs-task-definition",
                "source": "config",
                "filters": [
                    {"tag:test": "name"}
                ],
                "actions": [
                    {"type": "remove-tag", "tags": ["test"]}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        assert resources[0]['containerDefinitions'] == [
            {'command': ['/bin/sh -c "echo \'<html> <head> '
                         '<title>Amazon ECS Sample App</title> '
                         '<style>body {margin-top: 40px; '
                         'background-color: #333;} </style> '
                         '</head><body> <div '
                         'style=color:white;text-align:center> '
                         '<h1>Amazon ECS Sample App</h1> '
                         '<h2>Congratulations!</h2> <p>Your '
                         'application is now running on a '
                         'container in Amazon ECS.</p> '
                         "</div></body></html>' >  "
                         '/usr/local/apache2/htdocs/index.html '
                         '&& httpd-foreground"'],
             'cpu': 0,
             'entryPoint': ['sh', '-c'],
             'essential': True,
             'image': 'httpd:2.4',
             'mountPoints': [],
             'name': 'fargate-app-2',
             'portMappings': [{'containerPort': 80,
                               'hostPort': 80,
                               'protocol': 'tcp'}],
             'volumesFrom': []}]
        assert resources[0]['Tags'] == [{'Key': 'test', 'Value': 'name'}]
        client = session_factory().client("ecs")
        self.assertEqual(len(client.list_tags_for_resource(
            resourceArn=resources[0]["taskDefinitionArn"]).get("tags")), 0)


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

    def test_ecs_task_subnet(self):
        session_factory = self.replay_flight_data("test_ecs_task_subnet")
        p = self.load_policy(
            {
                "name": "ecs-task-fargate-subnets",
                "resource": "ecs-task",
                "filters": [
                    {
                        "type": "subnet",
                        "key": "tag:Name",
                        "value": "implied"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].get('attachments')[0].get(
            'details')[0].get('value'), "subnet-05b58b4afe5124322")

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
        self.assertFalse({r["taskArn"] for r in resources}.intersection(tasks))


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

    def test_ecs_container_instance_subnet(self):
        session_factory = self.replay_flight_data("test_ecs_container_instance_subnet")
        p = self.load_policy(
            {
                "name": "ecs-container-instance-subnet",
                "resource": "ecs-container-instance",
                "filters": [
                    {
                        "type": "subnet",
                        "key": "tag:NetworkLocation",
                        "value": "Public"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].get('c7n:matched-subnets')[0], 'subnet-914763e7')

    def test_ecs_service_sg_filter(self):
        session_factory = self.replay_flight_data("test_ecs_service_sg_filter")
        p = self.load_policy(
            {
                "name": "test-ecs-service-sg-filter",
                "resource": "ecs-service",
                "filters": [
                    {
                        "type": "security-group",
                        "key": "tag:NetworkLocation",
                        "value": "Customer"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["serviceName"], "c7n-test-service")

    def test_ecs_service_network_location_filter_subnet(self):
        session_factory = self.replay_flight_data("test_ecs_service_network_location_filter_subnet")
        p = self.load_policy(
            {
                "name": "test-ecs-service-network-location-filter-subnet",
                "resource": "ecs-service",
                "filters": [
                    {
                        "type": "network-location",
                        "compare": ["resource", "subnet"],
                        "key": "tag:NetworkLocation",
                        "match": "equal"
                    }
                ]
            },
            session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["serviceName"], "c7n-test-service")
        matched = resources.pop()
        self.assertEqual(
            matched["Tags"],
            [
                {
                    "Key": "NetworkLocation",
                    "Value": "Customer"
                }
            ]
        )

    def test_ecs_service_network_location_filter_sg(self):
        session_factory = self.replay_flight_data("test_ecs_service_network_location_filter_sg")
        p = self.load_policy(
            {
                "name": "test-ecs-service-network-location-filter-sg",
                "resource": "ecs-service",
                "filters": [
                    {
                        "type": "network-location",
                        "compare": ["resource", "security-group"],
                        "key": "tag:NetworkLocation",
                        "match": "equal"
                    }
                ]
            },
            session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["serviceName"], "c7n-test-service")
        matched = resources.pop()
        self.assertEqual(
            matched["Tags"],
            [
                {
                    "Key": "NetworkLocation",
                    "Value": "Customer"
                }
            ]
        )

    def test_ecs_task_sg_filter(self):
        session_factory = self.replay_flight_data("test_ecs_task_sg_filter")
        p = self.load_policy(
            {
                "name": "test-ecs-task-sg-filter",
                "resource": "ecs-task",
                "filters": [
                    {
                        "type": "security-group",
                        "key": "tag:NetworkLocation",
                        "value": "Customer"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["group"], "service:c7n-test-service")

    def test_ecs_task_network_location_filter_subnet(self):
        session_factory = self.replay_flight_data("test_ecs_task_network_location_filter_subnet")
        p = self.load_policy(
            {
                "name": "test-ecs-task-network-location-filter-subnet",
                "resource": "ecs-task",
                "filters": [
                    {
                        "type": "network-location",
                        "compare": ["resource", "subnet"],
                        "key": "tag:NetworkLocation",
                        "match": "equal"
                    }
                ]
            },
            session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        matched = resources.pop()
        self.assertEqual(
            matched["Tags"],
            [
                {
                    "Key": "NetworkLocation",
                    "Value": "Customer"
                }
            ]
        )

    def test_ecs_task_network_location_filter_sg(self):
        session_factory = self.replay_flight_data("test_ecs_task_network_location_filter_sg")
        p = self.load_policy(
            {
                "name": "test-ecs-task-network-location-filter-sg",
                "resource": "ecs-task",
                "filters": [
                    {
                        "type": "network-location",
                        "compare": ["resource", "security-group"],
                        "key": "tag:NetworkLocation",
                        "match": "equal"
                    }
                ]
            },
            session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        matched = resources.pop()
        self.assertEqual(
            matched["Tags"],
            [
                {
                    "Key": "NetworkLocation",
                    "Value": "Customer"
                }
            ]
        )
