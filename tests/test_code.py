# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
from .common import BaseTest, event_data

from c7n.resources.aws import shape_validate
from botocore.exceptions import ClientError


class CodeArtifact(BaseTest):

    def test_delete_domain(self):
        factory = self.replay_flight_data('test_artifact_delete')
        p = self.load_policy({
            'name': 'nxdomain',
            'resource': 'artifact-domain',
            'filters': [{'name': 'pizzaspace'}],
            'actions': [{'type': 'delete', 'force': True}]},
            session_factory=factory)
        resources = p.run()
        assert len(resources) == 1
        if self.recording:
            time.sleep(3)
        assert factory().client('codeartifact').list_domains().get('domains') == []

    def test_cross_account_and_delete_repo(self):
        factory = self.replay_flight_data('test_artifact_repo_cross_account')
        p = self.load_policy({
            'name': 'no-xaccount',
            'resource': 'artifact-repo',
            'filters': ['cross-account'],
            'actions': ['delete']
        },
            session_factory=factory)
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['name'] == 'dop'
        if self.recording:
            time.sleep(3)
        assert factory().client('codeartifact').list_repositories().get('repositories') == []


class CodeCommit(BaseTest):

    def test_query_repos(self):
        factory = self.replay_flight_data("test_codecommit", region="us-east-2")
        p = self.load_policy(
            {"name": "get-repos", "resource": "codecommit", "filters": [
                {"type": "value", "key": "tag:Owner", "value": "aj@stacklet.io"},
            ]},
            session_factory=factory,
            config={"region": "us-east-2"},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["cloneUrlSsh"],
            "ssh://git-codecommit.us-east-2.amazonaws.com/v1/repos/demo-policies",
        )

    def test_get_repo_resources(self):
        factory = self.replay_flight_data('test_codecommit_get')
        p = self.load_policy({
            'name': 'get-repos', 'resource': 'codecommit'},
            session_factory=factory)
        m = p.resource_manager
        resources = m.get_resources(['fizzbuzz'])
        self.assertEqual(len(resources), 1)
        r = resources.pop()
        self.assertEqual(r['repositoryName'], 'fizzbuzz')

    def test_delete_repos(self):
        factory = self.replay_flight_data("test_codecommit_delete")
        p = self.load_policy(
            {
                "name": "delete-repos",
                "resource": "codecommit",
                "filters": [{"repositoryDescription": "placebo"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            sorted([r["repositoryName"] for r in resources]),
            ["test-delete-codecommit", "test-delete-codecommit3"],
        )
        client = factory().client("codecommit")
        remainder = client.list_repositories()["repositories"]
        self.assertEqual(len(remainder), 1)
        self.assertNotEqual(remainder[0]["repositoryName"], "test-delete-codecommit")
        self.assertNotEqual(remainder[0]["repositoryName"], "test-delete-codecommit3")


class CodeBuild(BaseTest):

    def test_config_source(self):
        factory = self.replay_flight_data('test_codebuild_config')
        config_resources = self.load_policy({
            'name': 'builders', 'resource': 'aws.codebuild', 'source': 'config'},
            session_factory=factory).run()
        resources = self.load_policy({
            'name': 'dbuilders', 'resource': 'aws.codebuild'},
            session_factory=factory).run()
        assert set(config_resources[0].keys()) == (
            set(resources[0].keys()).difference(('created', 'lastModified', 'badge')))

    def test_query_builds(self):
        factory = self.replay_flight_data("test_codebuild")
        p = self.load_policy(
            {"name": "get-builders", "resource": "codebuild"}, session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        self.assertEqual(
            resources[0]["environment"],
            {
                u"computeType": u"BUILD_GENERAL1_SMALL",
                u"environmentVariables": [],
                u"image": u"aws/codebuild/python:2.7.12",
                u"type": u"LINUX_CONTAINER",
            },
        )

    def test_delete_builds(self):
        factory = self.replay_flight_data("test_codebuild_delete")
        p = self.load_policy(
            {
                "name": "delete-builders",
                "resource": "codebuild",
                "filters": [{"description": "placebo"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["name"], "test-delete-codebuild")
        client = factory().client("codebuild")
        remainder = client.list_projects()["projects"]
        self.assertEqual(len(remainder), 2)
        self.assertNotIn("test-delete-codebuild", remainder)

    def test_post_finding_build(self):
        factory = self.replay_flight_data('test_codebuild_post_finding')
        p = self.load_policy({
            'name': 'codebuild',
            'resource': 'aws.codebuild',
            'actions': [
                {'type': 'post-finding',
                 'types': [
                     'Software and Configuration Checks/OrgStandard/abc-123']}]},
            session_factory=factory, config={'region': 'us-east-2'})
        builds = p.resource_manager.resources()
        self.assertEqual(len(builds), 1)
        self.maxDiff = None
        rfinding = p.resource_manager.actions[0].format_resource(builds[0])
        self.assertEqual(
            rfinding,
            {'Details': {
                'AwsCodeBuildProject': {
                    'EncryptionKey': 'arn:aws:kms:us-east-2:644160558196:alias/aws/s3',
                    'Environment': {'ImagePullCredentialsType': 'CODEBUILD',
                                    'Type': 'LINUX_CONTAINER'},
                    'Name': 'custodian',
                    'ServiceRole': 'arn:aws:iam::644160558196:role/service-role/codebuild-test-service-role',  # noqa
                    'Source': {'Location': 'https://github.com/kapilt/cloud-custodian',
                               'Type': 'GITHUB'}}},
             'Id': 'arn:aws:codebuild:us-east-2:644160558196:project/custodian',
             'Partition': 'aws',
             'Region': 'us-east-2',
             'Type': 'AwsCodeBuildProject'})

        shape_validate(
            rfinding['Details']['AwsCodeBuildProject'],
            'AwsCodeBuildProjectDetails',
            'securityhub')


class CodeBuildSourceCredentials(BaseTest):
    def test_get_source_credentials(self):
        p = self.load_policy(
            data={
                "name": "test-get-source-credentials",
                "resource": "aws.codebuild-credential",
                "filters": [{
                    "type": "value",
                    "key": "serverType",
                    "value": "GITHUB"
                }, {
                    "type": "value",
                    "key": "authType",
                    "value": "PERSONAL_ACCESS_TOKEN"
                }]
            },
            session_factory=self.replay_flight_data('test_codebuild_get_source_credentials')
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['arn'],
            'arn:aws:codebuild:eu-central-1:543742734891:token/github'
        )


class CodePipeline(BaseTest):

    def test_config_pipeline(self):
        p = self.load_policy({
            'name': 'config-pipe',
            'resource': 'aws.codepipeline',
            'source': 'config',
        })
        source = p.resource_manager.get_source('config')
        item = event_data('pipeline.json', 'config')
        resource = source.load_resource(item)
        assert resource['name'] == 'burnifyPipeline'
        assert resource['artifactStore'] == {
            'type': 'S3', 'location': 'mypipe-artifactbucketstore-4ebot00zlvbv'}
        assert len(resource['stages']) == 4

    def test_query_pipeline(self):
        factory = self.replay_flight_data("test_codepipeline")
        p = self.load_policy(
            {"name": "get-pipes", "resource": "codepipeline"},
            session_factory=factory, config={'account_id': '001100'},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            p.resource_manager.get_arns(resources),
            ['arn:aws:codepipeline:us-east-1:001100:custodian-deploy'])
        self.assertEqual(len(resources[0]["stages"]), 2)

    def test_delete_pipeline(self):
        factory = self.replay_flight_data('test_codepipeline_delete')
        p = self.load_policy(
            {'name': 'del-pipe', 'resource': 'aws.codepipeline',
             'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('codepipeline')
        if self.recording:
            time.sleep(2)
        self.assertFalse(client.list_pipelines().get('pipelines'))


class CodeDeploy(BaseTest):

    def test_delete_codedeploy_application(self):
        factory = self.replay_flight_data('test_delete_codedeploy_application')
        p = self.load_policy(
            {
                "name": "codedeploy-delete-application",
                "resource": "codedeploy-app",
                "filters": [{"linkedToGitHub": False}],
                "actions": ["delete"],
            },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('codedeploy')
        if self.recording:
            time.sleep(2)
        self.assertFalse(client.list_applications().get('applications'))

    def test_tag_untag_codedeploy_application(self):
        factory = self.replay_flight_data('test_tag_untag_codedeploy_application')
        p = self.load_policy(
            {
                "name": "codedeploy-tag-application",
                "resource": "codedeploy-app",
                "filters": [{"tag:c7n": "test"}],
                "actions": [{"type": "remove-tag", "tags": ["c7n"]}],
            },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('codedeploy')
        arn = p.resource_manager.generate_arn(resources[0]["applicationName"])
        self.assertEqual(len(client.list_tags_for_resource(ResourceArn=arn).get('Tags')), 0)

    def test_codedeploy_deploymentgroup_delete(self):
        factory = self.replay_flight_data('test_codedeploy_deploymentgroup_delete')
        p = self.load_policy(
            {
                "name": "codedeploy-delete-deploymentgroup",
                "resource": "codedeploy-group",
                "filters": [
                    {
                        "type": "value",
                        "key": "targetRevision.revisionType",
                        "value": "S3"
                    }
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('codedeploy')
        with self.assertRaises(ClientError) as e:
            client.get_deployment_group(applicationName=resources[0]['applicationName'],
            deploymentGroupName=resources[0]['deploymentGroupName'])
        self.assertEqual(
            e.exception.response['Error']['Code'], 'DeploymentGroupDoesNotExistException')

    def test_codedeploy_list_deployment_configs(self):
        factory = self.replay_flight_data(
            'test_codedeploy_list_deployment_configs'
        )
        p = self.load_policy({
            "name": "codedeploy-list-deployment-configs",
            "resource": "aws.codedeploy-config",
            "filters": [{
                "type": "value",
                "key": "computePlatform",
                "value": "Lambda"
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['deploymentConfigId'], 'my-test-configuration')
        self.assertEqual(resources[0]['deploymentConfigName'], 'my-test-configuration')

    def test_codedeploy_group_config_filter(self):
        factory = self.replay_flight_data(
            'test_codedeploy_group_config_filter'
        )
        p = self.load_policy({
            "name": "codedeploy-group-with-lambda-config",
            "resource": "aws.codedeploy-group",
            "filters": [{
                "type": "config",
                "key": "computePlatform",
                "value": "Lambda"
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:DeploymentConfig']['deploymentConfigId'],
                         'my-test-configuration')
