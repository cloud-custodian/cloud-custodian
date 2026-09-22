# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import bz2
import json
import os
import re
from urllib.parse import urlparse

from httplib2 import Http, Response


PROJECT_ID = "cloud-custodian"


def sanitize_project_name(dirty_str):
    sanitized = 'projects/{}/'.format(PROJECT_ID)
    return re.sub(r'projects/([0-9a-zA-Z_-]+)/', sanitized, dirty_str)


class FlightRecorder(Http):

    def __init__(self, data_path=None, discovery_path=None):
        self._data_path = data_path
        self._discovery_path = discovery_path
        self._index = {}
        super(FlightRecorder, self).__init__()

    def get_next_file_path(self, uri, method, record=True):
        uri = sanitize_project_name(uri)
        parsed = urlparse(uri)
        path = parsed.path.replace('/', '-').replace(':', '-')
        base_name = "%s%s" % (method.lower(), path)

        # We don't record authentication
        if (base_name.startswith('post-oauth2-v4') or
                base_name.startswith('post-o-oauth2') or
                base_name.startswith('post-token')):
            return

        data_dir = self._data_path
        is_discovery = False

        # Use a common directory for discovery metadata across tests.
        # Discovery docs are host-invariant, so this is keyed on path alone.
        if base_name.startswith('get-discovery'):
            data_dir = self._discovery_path
            is_discovery = True
        else:
            # Host-qualify the key so requests to different hosts sharing a
            # path (e.g. Vertex AI's per-region endpoints) can't collide.
            # New flight data is always recorded host-qualified. Data
            # recorded before this was added has no host in its name; when
            # replaying, prefer a host-qualified match if the fixture has
            # one, otherwise fall back to the legacy (host-less) name.
            host_qualified_base_name = "%s-%s%s" % (
                method.lower(), parsed.netloc.replace(':', '-'), path)
            if (record or
                os.path.exists(os.path.join(data_dir, f'{host_qualified_base_name}_1.json'))
                ):
                base_name = host_qualified_base_name

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
                # on replay always return the same discovery file
                if is_discovery:
                    return fn
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
        with fopen(fpath, 'wb') as fh:
            recorded = {}
            recorded['headers'] = dict(response)
            if not content:
                content = '{}'
            recorded['body'] = json.loads(content)
            fh.write(sanitize_project_name(json.dumps(recorded, indent=2)).encode('utf8'))

        return response, content


class HttpReplay(FlightRecorder):

    static_responses = {
        ('POST', 'https://accounts.google.com/o/oauth2/token'): json.dumps({
            'access_token': 'ya29', 'token_type': 'Bearer',
            'expires_in': 3600}).encode('utf8'),
        ('POST', 'https://oauth2.googleapis.com/token'): json.dumps({
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
        with fopen(fpath, 'rb') as fh:
            data = json.load(fh)
            response = Response(data['headers'])
            serialized = json.dumps(data['body']).encode('utf8')
            if fpath.endswith('bz2'):
                self._cache[fpath] = response, serialized
            return response, serialized
