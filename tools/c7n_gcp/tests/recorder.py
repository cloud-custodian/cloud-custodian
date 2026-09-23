# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import bz2
import json
import os
import re
import warnings
from urllib.parse import urlparse

from httplib2 import Http, Response

from c7n_gcp.client import get_default_project


PROJECT_ID = "cloud-custodian"


def sanitize_project_name(dirty_str):
    sanitized = 'projects/{}/'.format(PROJECT_ID)
    return re.sub(r'projects/([0-9a-zA-Z_-]+)/', sanitized, dirty_str)


# Stands in for the live project number in recordings.
PROJECT_NUMBER = "123456789012"
# The live project number turns up in many forms (ACL entities, generated
# bucket names, service agents), so it's scrubbed wherever it's known: set
# from the environment when recording, or learned from responses that
# report it.
PROJECT_NUMBER_ENV = "GOOGLE_CLOUD_PROJECT_NUMBER"

# Google-managed service agents embed the project number, e.g.
# service-<number>@gcp-sa-pubsub.iam.gserviceaccount.com,
# p<number>-<id>@gcp-sa-cloud-sql.iam.gserviceaccount.com and
# <number>-compute@developer.gserviceaccount.com. User-managed service
# accounts live under <project>.iam.gserviceaccount.com and aren't matched.
SERVICE_AGENT_NUMBER = re.compile(
    r'(?<![\w.-])(?P<prefix>service-|p)?(?P<number>[0-9]{10,13})'
    r'(?=(?:-[a-z0-9]+)?@(?:gcp-sa-[a-z0-9-]+\.iam|developer|cloudservices|cloudbuild)'
    r'\.gserviceaccount\.com)')

# e.g. storage's "projectNumber" and terraform's "project_number"
PROJECT_NUMBER_FIELD = re.compile(r'"(?:projectNumber|project_number)":\s*"?([0-9]+)"?')

# Project numbers learned so far, so they're scrubbed from later responses
# that don't report them.
learned_project_numbers = set()

EMAIL_RE = re.compile(r'[\w.+%-]+@[\w.-]+\.\w+')
PLACEHOLDER_EMAIL = 'user@example.com'


def get_project_numbers(dirty_str):
    learned_project_numbers.update(PROJECT_NUMBER_FIELD.findall(dirty_str))
    learned_project_numbers.update(
        m.group('number') for m in SERVICE_AGENT_NUMBER.finditer(dirty_str))
    numbers = set(learned_project_numbers)
    if os.environ.get(PROJECT_NUMBER_ENV):
        numbers.add(os.environ[PROJECT_NUMBER_ENV])
    numbers.discard(PROJECT_NUMBER)
    return numbers


def scrub_email(match):
    # Service accounts belong to the project rather than a person, and are
    # already scrubbed of the project id and number.
    email = match.group()
    return email if email.endswith('.gserviceaccount.com') else PLACEHOLDER_EMAIL


def sanitize_recording(dirty_str):
    """Scrub account details from recorded responses and terraform state."""
    sanitized = sanitize_project_name(dirty_str)
    # Bodies also carry the project outside of resource paths, e.g.
    # bigquery's "projectId" and "<project>:<dataset>" ids.
    # Only whole ids, so a short id can't rewrite values that merely contain
    # it (e.g. custodian inside cloud-custodian, or c7n inside c7n_test).
    project_id = get_default_project()
    if project_id and project_id != PROJECT_ID:
        sanitized = re.sub(
            r'(?<![\w-]){}(?![\w-])'.format(re.escape(project_id)), PROJECT_ID, sanitized)
    for project_number in get_project_numbers(dirty_str):
        sanitized = re.sub(
            r'(?<![0-9]){}(?![0-9])'.format(re.escape(project_number)), PROJECT_NUMBER, sanitized)
    sanitized = SERVICE_AGENT_NUMBER.sub(
        lambda m: (m.group('prefix') or '') + PROJECT_NUMBER, sanitized)
    return EMAIL_RE.sub(scrub_email, sanitized)


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

    def __init__(self, data_path=None, discovery_path=None):
        if not os.environ.get(PROJECT_NUMBER_ENV):
            warnings.warn(
                "%s is not set, the live project number may leak into recordings "
                "made before a response reports it"
                % PROJECT_NUMBER_ENV)
        super().__init__(data_path, discovery_path)

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
            fh.write(sanitize_recording(json.dumps(recorded, indent=2)).encode('utf8'))

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
