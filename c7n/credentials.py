# Copyright 2016 Capital One Services, LLC
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
"""
Authentication utilities
"""
from botocore.credentials import RefreshableCredentials
from botocore.session import get_session
from boto3 import Session

from c7n.version import version


class SessionFactory(object):
    
    def __init__(self, region, profile=None, assume_role=None,
                 aws_access_key_id=None, aws_secret_access_key=None, 
                 aws_session_token=None):

        if profile and aws_access_key_id and aws_secret_access_key:
            raise Exception('You have passed 2 forms of authentication. \
                            Please pass either a profile or AWS keys')

        self.region = region
        self.profile = profile
        self.assume_role = assume_role
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_session_token = aws_session_token

    def __call__(self, assume=True, region=None):
        if self.aws_access_key_id and self.aws_secret_access_key:
            kwargs = {'aws_access_key_id': self.aws_access_key_id, 
                      'aws_secret_access_key': self.aws_secret_access_key,
                      'aws_session_token': self.aws_session_token if self.aws_session_token else None}
            session = Session(region_name=region or self.region, **kwargs)
        else:
            session = Session(
                region_name=region or self.region,
                profile_name=self.profile)

        if self.assume_role and assume:
            session = assumed_session(
                self.assume_role, "CloudCustodian", session)

        session._session.user_agent_name = "CloudCustodian"
        session._session.user_agent_version = version
        return session

def assumed_session(role_arn, session_name, session=None):
    """STS Role assume a boto3.Session

    With automatic credential renewal.

    Args:
      role_arn: iam role arn to assume
      session_name: client session identifier
      session: an optional extant session, note session is captured
      in a function closure for renewing the sts assumed role.

    :return: a boto3 session using the sts assumed role credentials

    Notes: We have to poke at botocore internals a few times
    """
    if session is None:
        session = Session()

    def refresh():
        credentials = session.client('sts').assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name)['Credentials']
        return dict(
            access_key=credentials['AccessKeyId'],
            secret_key=credentials['SecretAccessKey'],
            token=credentials['SessionToken'],
            # Silly that we basically stringify so it can be parsed again
            expiry_time=credentials['Expiration'].isoformat())

    session_credentials = RefreshableCredentials.create_from_metadata(
        metadata=refresh(),
        refresh_using=refresh,
        method='sts-assume-role')

    # so dirty.. it hurts, no clean way to set this outside of the
    # internals poke. There's some work upstream on making this nicer
    # but its pretty baroque as well with upstream support.
    # https://github.com/boto/boto3/issues/443
    # https://github.com/boto/botocore/issues/761
    
    s = get_session()
    s._credentials = session_credentials
    region = s.get_config_variable('region') or 'us-east-1'
    s.set_config_variable('region', region)
    return Session(botocore_session=s)
