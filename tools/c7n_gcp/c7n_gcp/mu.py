# Copyright 2017-2018 Capital One Services, LLC
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
import logging

from c7n.mu import custodian_archive as base_archive
from c7n.utils import local_session

log = logging.getLogger('c7n_gcp.mu')


handler = """\
exports.handler = (req, res) => {
  res.send('Hello World!');
};
"""


def custodian_archive():
    archive = base_archive()
    archive.add_contents('index.js', handler)
    archive.close()
    return archive


class CloudFunctionManager(object):

    def __init__(self, session_factory, region="-"):
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

    def publish(self, func):
        """publish the given function."""

        region = 'us-central1'
        project = self.session.get_default_project()

        source_url = self._upload(func, region)
        config = func.get_config()
        config['name'] = "projects/{}/locations/{}/functions/{}".format(
            project, region, func.name)
        config['httpsTrigger'] = {}
        config['sourceUploadUrl'] = source_url

        params = {
            'location': "projects/{}/locations/{}".format(
                self.session.get_default_project(), region),
            'body': config}
        response = self.client.execute_command('create', params)

        print response

    def metrics(self, funcs, start, end, period=5 * 60):
        """Get the metrics for a set of functions."""

    def logs(self, func, start, end):
        """Get the logs for a given function."""

    def delta_function(self, old_config, new_config):
        """Determine if the function has changed configuration"""

    def get(self, func_name, qualifier):
        """Get the details on a given function."""

    def _upload(self, func, region):
        """Upload function source and return source url
        """
        archive = func.get_archive()
        # Generate source upload url
        url = self.client.execute_command(
            'generateUploadUrl',
            {'parent': 'projects/{}/locations/{}'.format(
                self.session.get_default_project(),
                region)}).get('uploadUrl')
        log.info("function upload url %s", url)

        # Upload source
        http = self.client.http.__class__()
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

    def get_archive(self):
        return self.archive

    def get_config(self):
        conf = {
            'name': self.name,
            'timeout': self.timeout,
            'entryPoint': 'handler',
            'labels': {
                'deployment-tool': 'custodian',
                # have to figure out a way to encode this / under 63, alphanum + '-' + '_'
                #'checksum': self.archive.get_checksum(base64.b16encode).lower(),
            },
            'availableMemoryMb': self.memory_size
        }
        return conf


class PolicyFunction(CloudFunction):
    pass


class EventSource(object):

    def __init__(self, session):
        self.session = session


class HTTPEventSource(EventSource):

    def get(self):
        pass

    def add(self):
        pass

    def deleta(self):
        pass


class BucketEventSource(EventSource):

    label = 'cloud.pubsub'
    trigger = 'google.storage.object.finalize'
    collection_id = 'cloudfunctions.projects.buckets'

    events = [
        'google.storage.object.finalize',
        'google.storage.object.archive',
        'google.storage.object.delete',
        'google.storage.object.metadataUpdate']


class PubSubEventSource(EventSource):

    label = 'cloud.storage'
    trigger = 'google.pubsub.topic.publish'
    collection_id = 'pubsub.projects.topics'


class LogEventSource(object):
    """Composite as a log sink"""
