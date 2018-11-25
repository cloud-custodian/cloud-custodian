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
"""Filters for api integration with tools/c7n_sphere11
"""
from datetime import datetime
from six.moves.urllib_parse import urlparse

from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.vendored import requests

from dateutil.tz import tzutc

from c7n.credentials import assumed_session
from c7n.filters import Filter
from c7n.utils import local_session, type_schema


class Locked(Filter):
    """Has the resource been locked using sphere11
    """
    permissions = ('sts:AssumeRole',)

    schema = type_schema(
        'locked',
        role={'type': 'string'},
        endpoint={'type': 'string'},
        region={'type': 'string'},
        required=('endpoint',))

    def process(self, resources, event=None):
        self._model = self.manager.get_model()
        self._auth = self.get_api_credentials()
        results = []
        for r in resources:
            data = self.get_lock_status(r)
            if 'Message' in data:
                raise RuntimeError(data['Message'])
            if data['LockStatus'] == 'locked':
                r['c7n:locked_date'] = datetime.utcfromtimestamp(
                    data['RevisionDate']).replace(tzinfo=tzutc())
                results.append(r)
        return results

    def get_api_credentials(self):
        session = local_session(self.manager.session_factory)
        if self.data.get('role'):
            api_session = assumed_session(
                self.data.get('role'), 'CustodianSphere11', session)
        else:
            api_session = session
        credentials = api_session.get_credentials()
        region = self.data.get('region', 'us-east-1')
        auth = SignatureAuth(credentials, region, 'execute-api')
        return auth

    def get_lock_status(self, resource):
        endpoint = self.data['endpoint'].rstrip('/')
        account_id = self.manager.config.account_id
        params = {'parent_id': self.get_parent_id(resource, account_id)}
        result = requests.get("%s/%s/locks/%s" % (
            endpoint,
            account_id,
            resource[self._model.id]), params=params, auth=self._auth)
        return result.json()

    def get_parent_id(self, resource, account_id):
        return account_id


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
