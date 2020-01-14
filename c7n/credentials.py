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
"""
Authentication utilities
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import json
import subprocess

from botocore.credentials import RefreshableCredentials
from botocore.session import get_session
from boto3 import Session

from c7n.version import version
from c7n.utils import get_retry


# we still have some issues (see #5023) to work through to switch to
# default regional endpoints, for now its opt-in.
USE_STS_REGIONAL = os.environ.get(
    'C7N_USE_STS_REGIONAL', '').lower() in ('yes', 'true')


class SessionFactory(object):

    def __init__(self, region, profile=None, assume_role=None, external_id=None, credential_helper=None):
        self.region = region
        self.profile = profile
        self.assume_role = assume_role
        self.external_id = external_id
        self.credential_helper = credential_helper
        self.user_agent_name = "CloudCustodian"
        self.session_name = "CloudCustodian"
        if 'C7N_SESSION_SUFFIX' in os.environ:
            self.session_name = "%s@%s" % (
                self.session_name, os.environ['C7N_SESSION_SUFFIX'])
        self._subscribers = []

    def _set_policy_name(self, name):
        self.user_agent_name = ("CloudCustodian(%s)" % name).strip()

    policy_name = property(None, _set_policy_name)

    def __call__(self, assume=True, region=None):
        if self.credential_helper:
            session = credential_helper_session(
                self.credential_helper, self.session_name, region or self.region)
        elif self.assume_role and assume:
            session = Session(profile_name=self.profile)
            session = assumed_session(
                self.assume_role, self.session_name, session,
                region or self.region, self.external_id)
        else:
            session = Session(
                region_name=region or self.region, profile_name=self.profile)

        return self.update(session)

    def update(self, session):
        session._session.user_agent_name = self.user_agent_name
        session._session.user_agent_version = version

        for s in self._subscribers:
            s(session)

        return session

    def set_subscribers(self, subscribers):
        self._subscribers = subscribers


class CredentialHelperError(Exception):
    pass

class UnableToParseCredentialOutput(CredentialHelperError):
    pass

class CredentialHelperExited(CredentialHelperError):
    pass

def credential_helper_session(command, session_name, region=None):
    """Role assumption / fetching, using a credential helper.

    The helper program is expected to return the same JSON payload
    as a call to STS would, just making it possible to use shell scripts.

    The command is run using a shell.
    """

    def fetch_credentials():
        env = os.environ.copy()
        env['CUSTODIAN_SESSION_NAME'] = session_name
        if region:
            env['CUSTODIAN_CREDENTIALS_REGION'] = region
        try:
            raw_response = subprocess.check_output(command, shell=True, env=env).strip()
            parseable_string = raw_response.decode('utf-8')
            parsed = json.loads(parseable_string)
            credentials = parsed['Credentials']

            return dict(
                access_key=credentials['AccessKeyId'],
                secret_key=credentials['SecretAccessKey'],
                token=credentials['SessionToken'],
                expiry_time=credentials['Expiration'])
        except subprocess.CalledProcessError as e:
            raise CredentialHelperExited("Credential Helper Exited Abnormally with status code %d" % e.returncode)
        except (AttributeError, TypeError, ValueError, json.decoder.JSONDecodeError):
            raise UnableToParseCredentialOutput("Unable to parse input:\n%s" % parseable_string)

    session_credentials = RefreshableCredentials.create_from_metadata(
        metadata=fetch_credentials(),
        refresh_using=fetch_credentials,
        method='credential-helper')
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
            get_sts_client(
                session, region).assume_role, **parameters)['Credentials']
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


def get_sts_client(session, region):
    """Get the AWS STS endpoint specific for the given region.

    Returns the global endpoint if region is not specified.

    For the list of regional endpoints, see https://amzn.to/2ohJgtR
    """
    if region and USE_STS_REGIONAL:
        endpoint_url = "https://sts.{}.amazonaws.com".format(region)
        region_name = region
    else:
        endpoint_url = None
        region_name = None
    return session.client(
        'sts', endpoint_url=endpoint_url, region_name=region_name)
