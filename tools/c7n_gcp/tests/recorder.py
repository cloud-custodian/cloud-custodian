# Copyright 2018 Capital One Services, LLC
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

import bz2
import json
import os

from httplib2 import Http, Response
from six.moves.urllib.parse import urlparse


class FlightRecorder(Http):

    def __init__(self, data_path=None, discovery_path=None):
        self._data_path = data_path
        self._discovery_path = discovery_path
        self._index = {}
        super(FlightRecorder, self).__init__()

    def get_next_file_path(self, uri, method, record=True):
        base_name = "%s%s" % (
            method.lower(), urlparse(uri).path.replace('/', '-').replace(':', '-'))
        data_dir = self._data_path

        is_discovery = False
        # We don't record authentication
        if base_name.startswith('post-oauth2-v4') or base_name.startswith('post-o-oauth2'):
            return
        # Use a common directory for discovery metadata across tests.
        if base_name.startswith('get-discovery'):
            data_dir = self._discovery_path
            is_discovery = True

        next_file = None
        while next_file is None:
            index = self._index.setdefault(base_name, 1)
            fn = os.path.join(data_dir, '{}_{}.json'.format(base_name, index))
            if is_discovery:
                fn += '.bz2'
            if os.path.exists(fn):
                # if we already have discovery metadata, don't re-record it.
                if record and is_discovery:
                    return None
                self._index[base_name] += 1
                if not record:
                    next_file = fn
            elif record:
                return fn
            else:
                raise IOError('response file ({0}) not found'.format(fn))

        return fn


class HttpRecorder(FlightRecorder):

    def request(self, uri, method="GET", body=None, headers=None,
                redirections=1, connection_type=None):
        response, content = super(HttpRecorder, self).request(
            uri, method, body, headers, redirections, connection_type)
        fpath = self.get_next_file_path(uri, method)

        if fpath is None:
            return response, content

        fopen = open
        if fpath.endswith('.bz2'):
            fopen = bz2.BZ2File
        with fopen(fpath, 'w') as fh:
            recorded = {}
            recorded['headers'] = dict(response)
            if not content:
                content = '{}'
            recorded['body'] = json.loads(content)
            json.dump(recorded, fh, indent=2)

        return response, content


class HttpReplay(FlightRecorder):

    static_responses = {
        ('POST', 'https://accounts.google.com/o/oauth2/token'): json.dumps({
            'access_token': 'ya29', 'token_type': 'Bearer',
            'expires_in': 3600}).encode('utf8')}

    _cache = {}

    def request(self, uri, method="GET", body=None, headers=None,
                redirections=1, connection_type=None):
        if (method, uri) in self.static_responses:
            return (
                Response({
                    'status': '200',
                    'content-type': 'application/json; charset=UTF-8'}),
                self.static_responses[(method, uri)])

        fpath = self.get_next_file_path(uri, method, record=False)
        fopen = open
        if fpath.endswith('.bz2'):
            if fpath in self._cache:
                return self._cache[fpath]
            fopen = bz2.BZ2File
        with fopen(fpath, 'r') as fh:
            data = json.load(fh)
            response = Response(data['headers'])
            serialized = json.dumps(data['body']).encode('utf8')
            if fpath.endswith('bz2'):
                self._cache[fpath] = response, serialized
            return response, serialized
