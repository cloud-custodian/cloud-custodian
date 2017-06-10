# Copyright 2017 Capital One Services, LLC
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


class CodeCommit(BaseTest):

    def test_query_repos(self):
        factory = self.replay_flight_data('test_codecommit')
        p = self.load_policy({
            'name': 'get-repos',
            'resource': 'codecommit',
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['cloneUrlSsh'],
            "ssh://git-codecommit.us-east-2.amazonaws.com/v1/repos/custodian-config-repo")


class CodeBuild(BaseTest):

    def test_query_builds(self):
        factory = self.replay_flight_data('test_codebuild')
        p = self.load_policy({
            'name': 'get-builders',
            'resource': 'codebuild',
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        self.assertEqual(
            resources[0]['environment'],
            {u'computeType': u'BUILD_GENERAL1_SMALL',
             u'environmentVariables': [],
             u'image': u'aws/codebuild/python:2.7.12',
             u'type': u'LINUX_CONTAINER'})


class CodePipeline(BaseTest):

    def test_query_pipeline(self):
        factory = self.replay_flight_data('test_codepipeline')
        p = self.load_policy({
            'name': 'get-pipes',
            'resource': 'codepipeline',
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['stages']), 2)
