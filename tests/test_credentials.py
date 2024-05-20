# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import os
from botocore.exceptions import ClientError
import placebo

from c7n import credentials
from c7n.credentials import (
    CustodianSession, SessionFactory, assumed_session, get_sts_client
)
from c7n.version import version
from c7n.utils import local_session

from .common import BaseTest

import freezegun
import pytest


class Credential(BaseTest):

    def test_session_factory(self):
        factory = SessionFactory("us-east-1")
        session = factory()
        self.assertTrue(
            session._session.user_agent().startswith("c7n/%s" % version)
        )

    def test_regional_sts(self):
        factory = self.replay_flight_data('test_credential_sts_regional')

        self.patch(credentials, 'USE_STS_REGIONAL', True)
        client = get_sts_client(factory(), region='us-east-2')
        # unfortunately we have to poke at boto3 client internals to verify
        self.assertEqual(client._client_config.region_name, 'us-east-2')
        self.assertEqual(client._endpoint.host,
                         'https://sts.us-east-2.amazonaws.com')
        self.assertEqual(
            client.get_caller_identity()['Arn'],
            'arn:aws:iam::644160558196:user/kapil')

    def test_assumed_session(self):
        with freezegun.freeze_time('2019-09-29T22:07:46+00:00'):
            factory = self.replay_flight_data("test_credential_sts")
            session = assumed_session(
                role_arn='arn:aws:iam::644160558196:role/CustodianGuardDuty',
                session_name="custodian-dev",
                session=factory(),
            )

            # attach the placebo flight recorder to the new session.
            pill = placebo.attach(
                session, os.path.join(self.placebo_dir, 'test_credential_sts'))
            if self.recording:
                pill.record()
            else:
                pill.playback()
            self.addCleanup(pill.stop)

            try:
                identity = session.client("sts").get_caller_identity()
            except ClientError as e:
                self.assertEqual(e.response["Error"]["Code"], "ValidationError")

            self.assertEqual(
                identity['Arn'],
                'arn:aws:sts::644160558196:assumed-role/CustodianGuardDuty/custodian-dev')

    def test_session_policy_assumed_session(self):
        factory = self.replay_flight_data("test_session_policy_assumed_session")
        inline_session_policy = {"Version": "2012-10-17", "Statement": [{"Sid": "Statement1",
            "Effect": "Allow", "Action": ["lambda:ListFunctions"], "Resource": "*"}]}

        session = assumed_session(
            role_arn='arn:aws:iam::644160558196:role/CloudCustodianRole',
            session_name="CloudCustodian",
            session_policy=inline_session_policy,
            session=factory(),
        )

        pill = placebo.attach(
            session, os.path.join(self.placebo_dir, "test_session_policy_assumed_session"))
        if self.recording:
            pill.record()
        else:
            pill.playback()
        self.addCleanup(pill.stop)
        with freezegun.freeze_time("Wed, 15 May 2024 14:25:24 GMT"):
            with pytest.raises(ClientError) as ecm:
                session.client("lambda").list_layers()
            self.assertEqual(ecm.value.response["Error"]["Code"], "AccessDeniedException")
            self.assertEqual(
                ecm.value.response["Error"]["Message"],
                "User: arn:aws:sts::644160558196:assumed-role/CloudCustodianRole/CloudCustodian "
                "is not authorized to perform: lambda:ListLayers on resource: * because no "
                "session policy allows the lambda:ListLayers action")
            l_functions = session.client("lambda").list_functions()
            self.assertGreater(len((l_functions).get('Functions')), 0)

    def test_policy_name_user_agent(self):
        session = SessionFactory("us-east-1")
        session.policy_name = "test-policy-name-ua"
        client = session().client('s3')
        self.assertTrue(
            client.meta.config.user_agent.startswith(
                f"c7n/{version}"
            )
        )

        self.assertTrue(
            " c7n/policy#test-policy-name-ua" in client.meta.config.user_agent
        )

    def test_local_session_agent_update(self):
        factory = SessionFactory('us-east-1')
        factory.policy_name = "check-ebs"
        client = local_session(factory).client('ec2')
        self.assertTrue(
            'check-ebs' in client._client_config.user_agent)
        CustodianSession.close()
        factory.policy_name = "check-ec2"
        factory.update(local_session(factory))
        client = local_session(factory).client('ec2')
        self.assertTrue(
            'check-ec2' in client._client_config.user_agent)
