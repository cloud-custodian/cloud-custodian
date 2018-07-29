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
    requirements = packages and set(packages) or set()
    requirements.add('retrying')
    requirements.add('ratelimiter>=1.2.0.post0')
    requirements.add('google-auth>=1.4.1')
    requirements.add('google-auth-httplib2>=0.0.3')
    requirements.add('google-api-python-client>=1.7.3')
    # TODO: replace these deps
    # both of these bring in grpc :-( which in turn brings in a whole
    # pile of random threads and protobufs.
    requirements.add('google-cloud-monitoring>=0.3.0')
    requirements.add('google-cloud-logging>=1.6.0')

    archive.add_contents(
        'requirements.txt',
        '\n'.join(sorted(requirements)))
    archive.close()

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

        if func_info is None:
            response = self.client.execute_command(
                'create', {
                    'location': "projects/{}/locations/{}".format(
                        project, self.region),
                    'body': config})
        else:
            delta = self.delta_function(func_info, config)
            if not delta:
                response = None
            else:
                response = self.client.execute_command(
                    'patch', {
                        'name': func_name,
                        'body': config,
                        'updateMask': ','.join(delta)})
        # converge event source creation
        for e in func.events:
            e.add(func)
        return response

    @staticmethod
    def delta_function(old_config, new_config):
        found = []
        for k in new_config:
            if k in ('httpsTrigger',):
                continue
            if new_config[k] != old_config[k]:
                found.append(k)
        return found

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
        log.info("function upload url %s", url)
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
        if headers['status'] != '200':
            raise RuntimeError("%s\n%s" % (headers, response))
        return url


class CloudFunction(object):

    def __init__(self, func_data, archive):
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
        return self.func_data.get('memory-size', 256)

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
from c7n_gcp.handler import handler

def run(event, context=None):
    return handler.run(event, context)
"""


class PolicyFunction(CloudFunction):

    def get_archive(self):
        self.archive.add_file('main.py', PolicyHandlerTemplate)

    def get_config(self):
        config = super(CloudFunction, self).get_config()
        config['entryPoint'] = 'run'


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

    trigger = 'google.pubsub.topic.publish'
    collection_id = 'pubsub.projects.topics'

    # data -> topic

    def get_config(self, func):
        return {
            'eventTrigger': {
                'eventType': self.trigger,
                'resource': self.data['topic']}}

    def get_topic_param(self, topic=None, project=None):
        return {'topic': 'projects/{}/topics/{}'.format(
            project or self.session.get_default_project(),
            topic or self.data['topic'])}

    def ensure_topic(self):
        client = self.session.client('pubsub', 'v1', 'project.topics')
        topic = self.get_topic_param()
        try:
            client.execute_command('get', topic)
        except HttpError as e:
            if e.resp.status != 404:
                raise
        else:
            return topic

        client.execute_command('create', topic)
        return topic

    def add(self):
        self.ensure_topic()

    def remove(self):
        if not self.data.get('topic').startswith('custodian-auto'):
            return
        client = self.session.client('topic', 'v1', 'project.topics')
        client.execute_command('delete', self.get_topic_param())


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

    def __init__(self, data, session):
        self.data = data
        self.session = session
        self.pubsub = PubSubSource(data, session)

    def get_log(self):
        scope_type, scope_id, _, log_id = self.data['log'].split('/', 3)
        return LogInfo(
            scope_type=scope_type, scope_id=scope_id,
            id=log_id, name=self.data['log'])

    def get_log_filter(self):
        return self.data.get('filter')

    def get_parent(self, log_info):
        if self.data.get('scope', 'log') == 'log':
            if log_info != 'project':
                raise ValueError("Invalid log subscriber scope")
            parent = "%s/%s" % (log_info['scope_type'], log_info['scope_id'])
        if self.data['scope'] == 'project':
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

    def get_sink(self, topic_info):
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
                'destination': topic_info['topic']
            }
        }

        if log_filter is not None:
            sink['body']['filter'] = log_filter
        if scope != 'project':
            sink['body']['includeChildren'] = True
            sink['uniqueWriterIdentity'] = True
        return scope, sink

    def ensure_sink(self):
        topic_info = self.pubsub.ensure_topic()
        scope, sink_info = self.get_sink(topic_info)

        client = self.session.client('logging', 'v1', '%s.sinks' % scope)

        sink_path = '%s/sinks/%s' % (sink_info['parent'], sink_info['body']['name'])
        try:
            # todo, delta sink update on attribute change
            client.execute_command('get', {'sinkName': sink_path})
        except HttpError as e:
            if e.resp.status != 404:
                raise
        else:
            return sink_path

        client.execute_command('create', sink_info)
        return sink_path

    def add(self, func):
        return self.ensure_sink()

    def remove(self, func):
        if not self.data['name'].startswith('custodian-auto'):
            return
        parent = self.get_parent(self.get_log())
        client = self.session.client(
            'logging', 'v1', '%s.sinks' % (parent.split('/', 1)[0]))
        try:
            client.execute_command(
                'delete', {'sinkName': ''})
        except HttpError as e:
            if e.resp.status != 404:
                raise

    def get_config(self):
        return self.pubsub.get_config()


class ApiSubscriber(EventSource):
    """Subscribe to individual api calls
    """
    # https://cloud.google.com/logging/docs/reference/audit/auditlog/rest/Shared.Types/AuditLog

    # scope - project
    # api calls

    def __init__(self, data, session):
        self.data = data
        self.session = session

    def get_subscription(self, func):
        log_name = "%s/%s/logs/cloudaudit.googleapis.com%2Factivity" % (
            self.data.get('scope', 'project'),
            self.session.get_default_project())
        log_filter = 'logName = "%s"' % log_name
        log_filter += " AND protoPayload.methodName = (%s)" % (
            ' or '.join(['"%s"' % m for m in self.data['methods']]))
        return {
            'topic': 'custodian-auto-audit-%s' % func.name,
            'name': 'custodian-auto-audit-%s' % func.name,
            'log': log_name,
            'filter': log_filter}

    def add(self, func):
        return LogSubscriber(self.get_subscription(), self.session).add(func)

    def remove(self, func):
        return LogSubscriber(self.get_subscription(), self.session).remove(func)

    def get_config(self, func):
        return LogSubscriber(self.get_subscription(), self.session).get_config(func)

