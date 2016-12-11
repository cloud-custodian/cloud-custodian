from botocore.exceptions import ClientError

from c7n.credentials import SessionFactory, assumed_session
from c7n.version import version

from common import BaseTest


class Credential(BaseTest):

    def test_session_factory(self):
        factory = SessionFactory('us-east-1')
        session = factory()
        self.assertTrue(
            session._session.user_agent().startswith(
                'CloudCustodian/%s' % version))

    def xtest_assumed_session(self):
        # placebo's datetime bug bites again
        # https://github.com/garnaat/placebo/pull/50
        factory = self.replay_flight_data('test_credential_sts')    
        user = factory().client('iam').get_user()
        session = assumed_session(
            "arn:aws:iam::644160558196:role/CloudCustodianRole",
            "custodian-dev",
            session=factory())
        try:
            session.client('iam').get_user()
        except ClientError as e:
            self.assertEqual(e.response['Error']['Code'], 'ValidationError')
        else:
            self.fail("sts user not identifyable this way")

        self.assertEqual(user['User']['UserName'], 'kapil')


