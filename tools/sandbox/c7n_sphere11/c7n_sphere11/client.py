# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from getpass import getuser
from urlparse import urlparse

import boto3
import requests
import logging
import os

from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

logging.getLogger('botocore').setLevel(logging.WARNING)

log = logging.getLogger('sphere11.client')


class Client:

    def __init__(self, endpoint, account_id=None, role=None, http=None, session=None):
        self.endpoint = endpoint
        self.api_role = role or os.environ.get('SPHERE11_USER_ROLE')
        self.account_id = account_id
        self.http = http or requests.Session()
        self.api_session = session or self.get_session()

    # client api

    def list_locks(self, account_id=None):
        """Get extant locks for the given account.
        """
        account_id = self.get_account_id(account_id)
        return self.http.get(
            "%s/%s/locks" % (self.endpoint, account_id),
            auth=self.get_api_auth())

    def lock_status(self, resource_id, parent_id=None, account_id=None):
        """Get the lock status for a given resource.

        for security groups, parent id is their vpc.
        """
        account_id = self.get_account_id(account_id)
        params = parent_id and {'parent_id': parent_id} or None
        return self.http.get(
            "%s/%s/locks/%s" % (self.endpoint, account_id, resource_id),
            params=params, auth=self.get_api_auth())

    def lock(self, resource_id, region, account_id=None):
        """Lock a given resource
        """
        account_id = self.get_account_id(account_id)
        return self.http.post(
            "%s/%s/locks/%s/lock" % (self.endpoint, account_id, resource_id),
            json={'region': region},
            auth=self.get_api_auth())

    def unlock(self, resource_id, account_id=None):
        account_id = self.get_account_id(account_id)
        return self.http.post(
            "%s/%s/locks/%s/unlock" % (self.endpoint, account_id, resource_id),
            auth=self.get_api_auth())

    def version(self):
        return self.http.get(self.endpoint, auth=self.get_api_auth())

    def delta(self, account_id, region):
        account_id = self.get_account_id(account_id)
        return self.http.post(
            "%s/%s/locks/delta" % (self.endpoint, account_id),
            json={'region': region},
            auth=self.get_api_auth())

    # implementation helpers

    def get_account_id(self, account_id):
        account = account_id or self.account_id
        assert account, "AccountId Required"
        return account

    def get_api_auth(self):
        return SignatureAuth(
            self.api_session.get_credentials(), "us-east-1", "execute-api")

    def get_session(self, session_name=None):
        session = boto3.Session()
        if self.api_role:
            log.info("assuming role for api credentials %s" % self.api_role)
            sts = session.client('sts')
            result = sts.assume_role(
                RoleArn=self.api_role,
                RoleSessionName=session_name or getuser()
            )['Credentials']
            return boto3.Session(
                aws_access_key_id=result['AccessKeyId'],
                aws_secret_access_key=result['SecretAccessKey'],
                aws_session_token=result['SessionToken'])
        return session


class SignatureAuth(requests.auth.AuthBase):
    """AWS V4 Request Signer for Requests.
    """

    def __init__(self, credentials, region, service):
        self.credentials = credentials
        self.region = region
        self.service = service

    def __call__(self, r):
        url = urlparse(r.url)
        path = url.path or '/'
        qs = url.query and '?%s' % url.query or ''
        safe_url = url.scheme + '://' + url.netloc.split(':')[0] + path + qs
        request = AWSRequest(
            method=r.method.upper(), url=safe_url, data=r.body)
        SigV4Auth(
            self.credentials, self.service, self.region).add_auth(request)
        r.headers.update(dict(request.headers.items()))
        return r
