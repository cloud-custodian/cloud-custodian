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

import json
import os

from httplib2 import Http, Response
from six.moves.urllib.parse import urlparse


class FlightRecorder(Http):

    def __init__(self, data_path, discovery_path):
        self._data_path = data_path
        self._discovery_path = discovery_path
        self._index = {}
        super(FlightRecorder, self).__init__()
    
    def get_next_file_path(self, uri, method, record=True):
        base_name = "%s%s" % (
            method.lower(), urlparse(uri).path.replace('/', '-'))
        data_dir = self._data_path
        # We don't record authentication
        if base_name.startswith('post-oauth2-v4'):
            return
        # Use a common directory for discovery metadata across tests.
        if base_name.startswith('get-discovery'):
            data_dir = self._discovery_path

        next_file = None
        while next_file is None:
            index = self._index.setdefault(base_name, 1)
            fn = os.path.join(
                data_dir, '{}_{}.json'.format(base_name, index))
            if os.path.exists(fn):
                # if we already have discovery metadata, don't re-record it.
                if record and data_dir == self._discovery_path:
                    return None
                next_file = fn
                self._index[base_name] += 1
            elif index != 1:
                self._index[base_name] = 1
            elif record:
                return fn
            else:
                return IOError('response file ({0}) not found'.format(fn))
        return fn
    

class HttpRecorder(FlightRecorder):

    def request(self, uri, method="GET", body=None, headers=None,
                redirections=1, connection_type=None):
        response, content = super(HttpRecorder, self).request(
            uri, method, body, headers, redirections, connection_type)
        fpath = self.get_next_file_path(uri, method)
        if fpath is None:
            return response, content
        with open(fpath, 'w') as fh:
            recorded = {}
            recorded['headers'] = dict(response)
            recorded['body'] = json.loads(content)
            json.dump(recorded, fh, indent=2)
        return response, content


class HttpReplay(FlightRecorder):

    static_responses = {
        ('POST', 'https://www.googleapis.com/oauth2/v4/token'): json.dumps(
            {'access_token': 'ya29', 'token_type': 'Bearer',
             'expires_in': 3600})}

    def request(self, uri, method="GET", body=None, headers=None,
                redirections=1, connection_type=None):
        if (method, uri) in self.static_responses:
            return (
                Response({
                    'status': '200',
                    'content-type': 'application/json; charset=UTF-8'}),
                self.static_responses[(method, uri)])

        fpath = self.get_next_file_path(uri, method, record=False)
        with open(fpath, 'r') as fh:
            data = json.load(fh)
            response = Response(data['headers'])
            # serialize again, this runtime helps keep on the disk pretty.
            return response, json.dumps(data['body'])

        
