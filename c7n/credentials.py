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
from __future__ import absolute_import, division, print_function, unicode_literals

from botocore.credentials import RefreshableCredentials
from botocore.session import get_session
from boto3 import Session

from c7n.version import version
from c7n.utils import get_retry


class SessionFactory(object):

    def __init__(self, region, profile=None, assume_role=None, external_id=None):
        self.region = region
        self.profile = profile
        self.assume_role = assume_role
        self.external_id = external_id

    def __call__(self, assume=True, region=None):
        if self.assume_role and assume:
            session = Session(profile_name=self.profile)
            session = assumed_session(
                self.assume_role, "CloudCustodian", session,
                region or self.region, self.external_id)
        else:
            session = Session(
                region_name=region or self.region, profile_name=self.profile)

        session._session.user_agent_name = "CloudCustodian"
        session._session.user_agent_version = version
        return session


def assumed_session(role_arn, session_name, session=None, region=None, external_id=None):
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

    retry = get_retry(('Throttling',))

    def refresh():

        parameters = {"RoleArn": role_arn, "RoleSessionName": session_name}

        if external_id is not None:
            parameters['ExternalId'] = external_id

        credentials = retry(
            session.client('sts').assume_role, **parameters)['Credentials']
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
    if region is None:
        region = s.get_config_variable('region') or 'us-east-1'
    s.set_config_variable('region', region)
    return Session(botocore_session=s)
