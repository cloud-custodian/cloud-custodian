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

# import base64
from collections import namedtuple
import json
import logging
import hashlib

from c7n_gcp.client import errors
from c7n.mu import custodian_archive as base_archive
from c7n.utils import local_session

from googleapiclient.errors import HttpError

log = logging.getLogger('c7n_gcp.mu')


def custodian_archive(packages=None):
    if not packages:
        packages = []
    packages.append('c7n_gcp')
    archive = base_archive(packages)

    # Requirements are fetched server-side, which helps for binary extensions
    # but for pure python packages, if we have a local install and its
    # relatively small, it might be faster to just upload.
    #
    requirements = set()
    requirements.add('jmespath')
    requirements.add('retrying')
    requirements.add('ratelimiter>=1.2.0.post0')
    requirements.add('google-auth>=1.4.1')
    requirements.add('google-auth-httplib2>=0.0.3')
    requirements.add('google-api-python-client>=1.7.3')

    archive.add_contents(
        'requirements.txt',
        '\n'.join(sorted(requirements)))
    return archive


class CloudFunctionManager(object):

    def __init__(self, session_factory, region="us-central1"):
        self.session_factory = session_factory
        self.session = local_session(session_factory)
        self.client = self.session.client(
            'cloudfunctions', 'v1', 'projects.locations.functions')
        self.region = region

    def list_functions(self, prefix=None):
        """List extant cloud functions."""
        return self.client.execute_command(
            'list',
            {'parent': "projects/{}/locations/{}".format(
                self.session.get_default_project(),
                self.region)}
        ).get('functions', [])

    def remove(self, func):
        project = self.session.get_default_project()

        # delete event sources
        for e in func.events:
            e.remove(func)
        func_name = "projects/{}/locations/{}/functions/{}".format(
            project, self.region, func.name)
        try:
            return self.client.execute_command('delete', {'name': func_name})
        except errors.HttpError as e:
            if e.resp.status != 404:
                raise

    def publish(self, func):
        """publish the given function."""
        project = self.session.get_default_project()
        func_name = "projects/{}/locations/{}/functions/{}".format(
            project, self.region, func.name)
        func_info = self.get(func.name)
        source_url = None

        archive = func.get_archive()
        if not func_info or self._delta_source(archive, func_name):
            source_url = self._upload(archive, self.region)

        config = func.get_config()
        config['name'] = func_name
        if source_url:
            config['sourceUploadUrl'] = source_url

        # todo - we'll really need before() and after() for pre-provisioning of
        # resources (ie topic for function stream on create) and post provisioning (schedule
        # invocation of extant function).
        #
        # convergent event source creation
        for e in func.events:
            e.add(func)

        if func_info is None:
            log.info("creating function")
            response = self.client.execute_command(
                'create', {
                    'location': "projects/{}/locations/{}".format(
                        project, self.region),
                    'body': config})
        else:
            delta = delta_resource(func_info, config, ('httpsTrigger',))
            if not delta:
                response = None
            else:
                update_mask = ','.join(delta)
                log.info("updating function config %s", update_mask)
                response = self.client.execute_command(
                    'patch', {
                        'name': func_name,
                        'body': config,
                        'updateMask': update_mask})
        return response

    def metrics(self, funcs, start, end, period=5 * 60):
        """Get the metrics for a set of functions."""

    def logs(self, func, start, end):
        """Get the logs for a given function."""

    def get(self, func_name, qualifier=None):
        """Get the details on a given function."""
        project = self.session.get_default_project()
        func_name = "projects/{}/locations/{}/functions/{}".format(
            project, self.region, func_name)
        try:
            return self.client.execute_query('get', {'name': func_name})
        except errors.HttpError as e:
            if e.resp.status != 404:
                raise

    def _get_http_client(self, client):
        # Upload source, we need a class sans credentials as we're
        # posting to a presigned url.
        return self.client.get_http()

    def _delta_source(self, archive, func_name):
        checksum = archive.get_checksum(hasher=hashlib.md5)
        source_info = self.client.execute_command(
            'generateDownloadUrl', {'name': func_name, 'body': {}})
        http = self._get_http_client(self.client)
        source_headers, _ = http.request(source_info['downloadUrl'], 'HEAD')
        # 'x-goog-hash': 'crc32c=tIfQ9A==, md5=DqrN06/NbVGsG+3CdrVK+Q=='
        deployed_checksum = source_headers['x-goog-hash'].split(',')[-1].split('=', 1)[-1]
        log.debug("archive checksum %r deployed checksum %r", checksum, deployed_checksum)
        return deployed_checksum != checksum

    def _upload(self, archive, region):
        """Upload function source and return source url
        """
        # Generate source upload url
        url = self.client.execute_command(
            'generateUploadUrl',
            {'parent': 'projects/{}/locations/{}'.format(
                self.session.get_default_project(),
                region)}).get('uploadUrl')
        log.debug("uploading function code %s", url)
        http = self._get_http_client(self.client)
        headers, response = http.request(
            url, method='PUT',
            headers={
                'content-type': 'application/zip',
                'Content-Length': '%d' % archive.size,
                'x-goog-content-length-range': '0,104857600'
            },
            body=open(archive.path)
        )
        log.info("function code uploaded")
        if headers['status'] != '200':
            raise RuntimeError("%s\n%s" % (headers, response))
        return url


def delta_resource(old_config, new_config, ignore=()):
    found = []
    for k in new_config:
        if k in ignore:
            continue
        if new_config[k] != old_config[k]:
            found.append(k)
    return found


class CloudFunction(object):

    def __init__(self, func_data, archive=None):
        self.func_data = func_data
        self.archive = archive

    @property
    def name(self):
        return self.func_data['name']

    @property
    def timeout(self):
        return self.func_data.get('timeout', '60s')

    @property
    def memory_size(self):
        return self.func_data.get('memory-size', 512)

    @property
    def runtime(self):
        return self.func_data.get('runtime', 'python37')

    @property
    def labels(self):
        return dict(self.func_data.get('labels', {}))

    @property
    def environment(self):
        return self.func_data.get('environment', {})

    @property
    def network(self):
        return self.func_data.get('network')

    @property
    def max_instances(self):
        return self.func_data.get('max-instances')

    @property
    def events(self):
        return [e for e in self.func_data.get('events', ())]

    def get_archive(self):
        return self.archive

    def get_config(self):
        labels = self.labels
        labels['deployment-tool'] = 'custodian'
        conf = {
            'name': self.name,
            'timeout': self.timeout,
            'entryPoint': 'handler',
            'runtime': self.runtime,
            'labels': labels,
            'availableMemoryMb': self.memory_size}

        if self.environment:
            conf['environmentVariables'] = self.environment

        if self.network:
            conf['network'] = self.network

        if self.max_instances:
            conf['maxInstances'] = self.max_instances

        for e in self.events:
            conf.update(e.get_config(self))
        return conf


PolicyHandlerTemplate = """\

import base64
import json
import traceback
import os
import logging
import sys


def run(event, context=None):
    logging.info("starting function execution")
    event = json.loads(base64.b64decode(event['data']).decode('utf-8'))
    print("Event: %s" % (event,))
    try:
        from c7n_gcp.handler import run
        result = run(event, context)
        logging.info("function execution complete")
        return result
    except Exception as e:
        traceback.print_exc()
        raise
"""


class PolicyFunction(CloudFunction):

    def __init__(self, policy, archive=None, events=()):
        self.policy = policy
        self.func_data = self.policy.data['mode']
        self.archive = archive or custodian_archive()
        self._events = events

    @property
    def name(self):
        return self.policy.name

    @property
    def events(self):
        return self._events

    def get_archive(self):
        self.archive.add_contents('main.py', PolicyHandlerTemplate)
        self.archive.add_contents(
            'config.json', json.dumps(
                {'policies': [self.policy.data]}, indent=2))
        self.archive.close()
        return self.archive

    def get_config(self):
        config = super(PolicyFunction, self).get_config()
        config['entryPoint'] = 'run'
        return config


class EventSource(object):

    def __init__(self, session, data=None):
        self.data = data
        self.session = session

    def add(self, func):
        """Default no-op
        """

    def remove(self, func):
        """Default no-op
        """

    def get_config(self, func):
        return {}


class HTTPEvent(EventSource):
    """Internet exposed http endpoint for cloud function"""

    def get_config(self, func):
        return {'httpsTrigger': {}}


class BucketEvent(EventSource):

    trigger = 'google.storage.object.finalize'
    collection_id = 'cloudfunctions.projects.buckets'

    events = [
        # finalize is basically on write
        'google.storage.object.finalize',
        'google.storage.object.archive',
        'google.storage.object.delete',
        'google.storage.object.metadataUpdate',
        'providers/cloud.storage/eventTypes/object.change']

    def get_config(self, func):
        return {
            'eventTrigger': {
                'eventType': self.data.get('event', self.trigger),
                'resource': self.data['bucket']}}


class PubSubSource(EventSource):

    trigger = 'providers/cloud.pubsub/eventTypes/topic.publish'
    collection_id = 'pubsub.projects.topics'

    # data -> topic

    def get_config(self, func):
        return {
            'eventTrigger': {
                'eventType': self.trigger,
                'failurePolicy': {},
                'service': 'pubsub.googleapis.com',
                'resource': self.get_topic_param()}}

    def get_topic_param(self, topic=None, project=None):
        return 'projects/{}/topics/{}'.format(
            project or self.session.get_default_project(),
            topic or self.data['topic'])

    def ensure_topic(self):
        """Verify the pub/sub topic exists.

        Returns the topic qualified name.
        """
        client = self.session.client('pubsub', 'v1', 'projects.topics')
        topic = self.get_topic_param()
        try:
            client.execute_command('get', {'topic': topic})
        except HttpError as e:
            if e.resp.status != 404:
                raise
        else:
            return topic

        # bug in discovery doc.. apis say body must be empty but its required in the
        # discovery api for create.
        client.execute_command('create', {'name': topic, 'body': {}})
        return topic

    def ensure_iam(self, publisher=None):
        """Ensure the given identities are in the iam role bindings for the topic.
        """
        topic = self.get_topic_param()
        client = self.session.client('pubsub', 'v1', 'projects.topics')
        policy = client.execute_command('getIamPolicy', {'resource': topic})
        policy.pop('etag')
        found = False
        for binding in policy.get('bindings', {}):
            if binding['role'] != 'roles/pubsub.publisher':
                continue
            if publisher in binding['members']:
                return
            found = binding

        if not found:
            policy.setdefault(
                'bindings', {'members': [publisher], 'role': 'roles/pubsub.publisher'})
        else:
            found['members'].append(publisher)

        client.execute_command('setIamPolicy', {'resource': topic, 'body': {'policy': policy}})

    def add(self):
        self.ensure_topic()

    def remove(self):
        if not self.data.get('topic').startswith('custodian-auto'):
            return
        client = self.session.client('topic', 'v1', 'projects.topics')
        client.execute_command('delete', {'topic': self.get_topic_param()})


LogInfo = namedtuple('LogInfo', 'name scope_type scope_id id')


class LogSubscriber(EventSource):
    """Composite as a log sink

    subscriber = LogSubscriber(dict(
        log='projects/custodian-1291/logs/cloudaudit.googleapis.com%2Factivity'))

    function = CloudFunction(dict(name='log-sub', events=[subscriber])
    """

    # filter, log, topic, name
    # optional scope, scope_id (if scope != default)
    # + pub sub

    def __init__(self, session, data):
        self.data = data
        self.session = session
        self.pubsub = PubSubSource(session, data)

    def get_log(self):
        scope_type, scope_id, _, log_id = self.data['log'].split('/', 3)
        return LogInfo(
            scope_type=scope_type, scope_id=scope_id,
            id=log_id, name=self.data['log'])

    def get_log_filter(self):
        return self.data.get('filter')

    def get_parent(self, log_info):
        """Get the parent container for the log sink"""
        if self.data.get('scope', 'log') == 'log':
            if log_info.scope_type != 'projects':
                raise ValueError("Invalid log subscriber scope")
            parent = "%s/%s" % (log_info.scope_type, log_info.scope_id)
        elif self.data['scope'] == 'project':
            parent = 'projects/{}'.format(
                self.data.get('scope_id', self.session.get_default_project()))
        elif self.data['scope'] == 'organization':
            parent = 'organizations/{}'.format(self.data['scope_id'])
        elif self.data['scope'] == 'folder':
            parent = 'folders/{}'.format(self.data['scope_id'])
        elif self.data['scope'] == 'billing':
            parent = 'billingAccounts/{}'.format(self.data['scope_id'])
        else:
            raise ValueError(
                'invalid log subscriber scope %s' % (self.data))
        return parent

    def get_sink(self, topic_info=""):
        log_info = self.get_log()
        parent = self.get_parent(log_info)
        log_filter = self.get_log_filter()
        scope = parent.split('/', 1)[0]

        sink = {
            'parent': parent,
            'uniqueWriterIdentity': False,
            # Sink body
            'body': {
                'name': self.data['name'],
                'destination': "pubsub.googleapis.com/%s" % topic_info
            }
        }

        if log_filter is not None:
            sink['body']['filter'] = log_filter
        if scope != 'projects':
            sink['body']['includeChildren'] = True
            sink['uniqueWriterIdentity'] = True

        sink_path = '%s/sinks/%s' % (sink['parent'], sink['body']['name'])

        return scope, sink_path, sink

    def ensure_sink(self):
        """Ensure the log sink and its pub sub topic exist."""
        topic_info = self.pubsub.ensure_topic()
        scope, sink_path, sink_info = self.get_sink(topic_info)
        client = self.session.client('logging', 'v2', '%s.sinks' % scope)
        try:
            sink = client.execute_command('get', {'sinkName': sink_path})
        except HttpError as e:
            if e.resp.status != 404:
                raise
            sink = client.execute_command('create', sink_info)
        else:
            delta = delta_resource(sink, sink_info['body'])
            if delta:
                sink_info['updateMask'] = ','.join(delta)
                sink_info['sinkName'] = sink_path
                sink_info.pop('parent')
                sink = client.execute_command('update', sink_info)
            else:
                return sink_path

        self.pubsub.ensure_iam(publisher=sink['writerIdentity'])
        return sink_path

    def add(self, func):
        """Create any configured log sink if doesn't exist."""
        return self.ensure_sink()

    def remove(self, func):
        """Remove any provisioned log sink if auto created"""
        if not self.data['name'].startswith('custodian-auto'):
            return
        parent = self.get_parent(self.get_log())
        _, sink_path, _ = self.get_sink()
        client = self.session.client(
            'logging', 'v2', '%s.sinks' % (parent.split('/', 1)[0]))
        try:
            client.execute_command(
                'delete', {'sinkName': sink_path})
        except HttpError as e:
            if e.resp.status != 404:
                raise

    def get_config(self, func):
        return self.pubsub.get_config(func)


class ApiSubscriber(EventSource):
    """Subscribe to individual api calls

    via audit log -> filtered sink -> pub/sub topic -> cloud function.
    """
    # https://cloud.google.com/logging/docs/reference/audit/auditlog/rest/Shared.Types/AuditLog

    # scope - project
    # api calls

    def __init__(self, session, data):
        self.data = data
        self.session = session

    def get_subscription(self, func):
        log_name = "{}/{}/logs/cloudaudit.googleapis.com%2Factivity".format(
            self.data.get('scope', 'projects'),
            self.session.get_default_project())
        log_filter = 'logName = "%s"' % log_name
        log_filter += " AND protoPayload.methodName = (%s)" % (
            ' OR '.join(['"%s"' % m for m in self.data['methods']]))
        return {
            'topic': 'custodian-auto-audit-%s' % func.name,
            'name': 'custodian-auto-audit-%s' % func.name,
            'log': log_name,
            'filter': log_filter}

    def add(self, func):
        return LogSubscriber(self.session, self.get_subscription(func)).add(func)

    def remove(self, func):
        return LogSubscriber(self.session, self.get_subscription(func)).remove(func)

    def get_config(self, func):
        return LogSubscriber(self.session, self.get_subscription(func)).get_config(func)
