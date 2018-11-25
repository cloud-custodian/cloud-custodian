# Copyright 2016-2017 Capital One Services, LLC
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

import datetime
from dateutil.parser import parse as date_parse

from .common import BaseTest
from .test_offhours import mock_datetime_now
from time import sleep


class ElasticBeanstalkEnvironment(BaseTest):

    def test_resource_manager(self):
        factory = self.replay_flight_data("test_elasticbeanstalk_describe_envs")
        p = self.load_policy(
            {"name": "eb-env-query", "resource": "elasticbeanstalk-environment"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_eb_env_regex(self):
        factory = self.replay_flight_data("test_elasticbeanstalk_describe_envs")
        p = self.load_policy(
            {
                "name": "eb-find-inactive",
                "resource": "elasticbeanstalk-environment",
                "filters": [
                    {
                        "type": "value",
                        "key": "CNAME",
                        "op": "regex",
                        "value": ".*inactive.*",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_eb_env_uptime(self):
        factory = self.replay_flight_data("test_elasticbeanstalk_describe_envs")
        p = self.load_policy(
            {
                "name": "eb-find-inactive",
                "resource": "elasticbeanstalk-environment",
                "filters": [
                    {
                        "type": "value",
                        "key": "DateCreated",
                        "value": 1,
                        "value_type": "age",
                        "op": "greater-than",
                    }
                ],
            },
            session_factory=factory,
        )
        with mock_datetime_now(date_parse("2017-12-19"), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 2)


class EbEnvBaseTest(BaseTest):

    def query_env_status(self, session, env_name):
        client = session.client("elasticbeanstalk")
        res = client.describe_environments(EnvironmentNames=[env_name])
        if len(res["Environments"]) > 0:
            return res["Environments"][0]["Status"]
        return None

    def env_tags_dict(self, session, env_arn):
        client = session.client("elasticbeanstalk")
        tagres = client.list_tags_for_resource(ResourceArn=env_arn)
        tags = tagres["ResourceTags"]
        return {t["Key"]: t["Value"] for t in tags}


class TestTerminate(EbEnvBaseTest):

    def test_eb_env_terminate(self):
        envname = "c7n-eb-tag-test-inactive"
        session_factory = self.replay_flight_data("test_eb_env_terminate")
        assert self.query_env_status(session_factory(), envname) == "Ready"
        p = self.load_policy(
            {
                "name": "eb-env-term",
                "resource": "elasticbeanstalk-environment",
                "filters": [{"EnvironmentName": envname}],
                "actions": [{"type": "terminate"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        assert resources[0]["EnvironmentName"] == envname
        assert self.query_env_status(session_factory(), envname) == "Terminating"


class TestEBEnvTagging(EbEnvBaseTest):

    def test_tag_delayed(self):
        envname = "c7n-eb-tag-test-inactive"
        envarn = ("arn:aws:elasticbeanstalk:us-east-1:012345678901:"
                  "environment/re-jenkins/%s" % envname)
        factory = self.replay_flight_data("test_elasticbeanstalk_env_tag_delayed")
        p = self.load_policy(
            {
                "name": "eb-tag-delayed",
                "resource": "elasticbeanstalk-environment",
                "filters": [
                    {
                        "type": "value",
                        "key": "CNAME",
                        "op": "regex",
                        "value": ".*inactive.*",
                    }
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "op": "terminate",
                        "days": 7,
                        "tag": "c7n-eb-tag-test",
                    }
                ],
            },
            session_factory=factory,
        )
        if self.recording:
            resources = p.run()
        else:
            with mock_datetime_now(date_parse("2017-11-10"), datetime):
                resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["EnvironmentName"], envname)
        if self.recording:
            sleep(4)
        while self.query_env_status(factory(), envname) != "Ready":
            if self.recording:
                sleep(30)
            pass
        self.assertEqual(
            self.env_tags_dict(factory(), envarn).get("c7n-eb-tag-test"),
            "Resource does not meet policy: terminate@2017/12/12",
        )

    def test_tag(self):
        envname = "c7n-eb-tag-test-inactive"
        envarn = ("arn:aws:elasticbeanstalk:us-east-1:012345678901:"
                  "environment/re-jenkins/%s" % envname)
        factory = self.replay_flight_data("test_elasticbeanstalk_env_tag")
        p = self.load_policy(
            {
                "name": "eb-tag",
                "resource": "elasticbeanstalk-environment",
                "filters": [
                    {
                        "type": "value",
                        "key": "CNAME",
                        "op": "regex",
                        "value": ".*inactive.*",
                    }
                ],
                "actions": [
                    {"type": "tag", "key": "tagTestKey", "value": "tagTestValue"}
                ],
            },
            session_factory=factory,
        )
        if self.recording:
            resources = p.run()
        else:
            with mock_datetime_now(date_parse("2017-11-10"), datetime):
                resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["EnvironmentName"], envname)
        if self.recording:
            sleep(5)
        while self.query_env_status(factory(), envname) != "Ready":
            if self.recording:
                sleep(30)
            pass
        self.assertEqual(
            self.env_tags_dict(factory(), envarn).get("tagTestKey"), "tagTestValue"
        )

    def test_unmark(self):
        envname = "c7n-eb-tag-test-inactive"
        envarn = ("arn:aws:elasticbeanstalk:us-east-1:012345678901:"
                  "environment/re-jenkins/%s" % envname)
        factory = self.replay_flight_data("test_elasticbeanstalk_env_unmark")
        p = self.load_policy(
            {
                "name": "eb-tag",
                "resource": "elasticbeanstalk-environment",
                "filters": [
                    {
                        "type": "value",
                        "key": "CNAME",
                        "op": "regex",
                        "value": ".*inactive.*",
                    }
                ],
                "actions": [{"type": "remove-tag", "tags": ["tagTestKey"]}],
            },
            session_factory=factory,
        )
        if self.recording:
            resources = p.run()
        else:
            with mock_datetime_now(date_parse("2017-11-10"), datetime):
                resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["EnvironmentName"], envname)
        if self.recording:
            sleep(5)
        while self.query_env_status(factory(), envname) != "Ready":
            if self.recording:
                sleep(30)
            pass
        self.assertIsNone(self.env_tags_dict(factory(), envarn).get("tagTestKey"))
