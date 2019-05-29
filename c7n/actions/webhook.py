# Copyright 2019 Microsoft Corporation
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

import json

import jmespath
import requests
from six.moves.urllib import parse

from c7n import utils
from .core import EventAction


class Webhook(EventAction):
    """Calls a webhook with optional parameters and body
       populated from JMESPath queries.

        .. code-block:: yaml

          policies:
            - name: call-webhook
              resource: ec2
              description: |
                Call webhook with list of resource groups
              actions:
               - type: webhook
                 url: http://foo.com
                 parameters:
                    - resource_name: resource.name
                    - policy_name: policy.name
    """

    schema = utils.type_schema(
        'webhook',
        required=['url'],
        **{
            'url': {'type': 'string'},
            'body': {'type': 'string'},
            'batch': {'type': 'boolean'},
            'batch-size': {'type': 'number'},
            'method': {'type': 'string', 'enum': ['PUT', 'POST', 'GET', 'PATCH', 'DELETE']},
            'parameters': {
                "type": "object",
                "additionalProperties": {
                    "type": "string",
                    "description": "query string values"
                }
            },
            'headers': {
                "type": "object",
                "additionalProperties": {
                    "type": "string",
                    "description": "header values"
                }
            }
        }
    )

    def __init__(self, data=None, manager=None, log_dir=None):
        super(Webhook, self).__init__(data, manager, log_dir)
        self.url = self.data.get('url')
        self.body = self.data.get('body')
        self.batch = self.data.get('batch', False)
        self.batch_size = self.data.get('batch-size', 500)
        self.params = self.data.get('parameters', {})
        self.headers = self.data.get('headers', {})
        self.method = self.data.get('method', 'POST' if self.body else 'GET')
        self.lookup_data = {
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region,
            'execution_id': self.manager.ctx.execution_id,
            'execution_start': self.manager.ctx.start_time,
            'policy': self.manager.data
        }

    def process(self, resources, event=None):
        if self.batch:
            for chunk in utils.chunks(resources, self.batch_size):
                resource_data = self.lookup_data
                resource_data['resources'] = chunk
                self._process_call(resource_data)
        else:
            for r in resources:
                resource_data = self.lookup_data
                resource_data['resource'] = r
                self._process_call(resource_data)

    def _process_call(self, resource):
        prepared_url = self._build_url(resource)
        prepared_body = self._build_body(resource)
        prepared_headers = self._build_headers(resource)

        if prepared_body:
            prepared_headers['Content-Type'] = 'application/json'

        try:
            s = requests.Session()
            req = requests.Request(method=self.method,
                                   url=prepared_url,
                                   headers=prepared_headers,
                                   data=prepared_body)

            prepped = req.prepare()

            res = s.send(prepped)
            res.raise_for_status()

            self.log.info("%s got response %s with URL %s" %
                          (self.method, res.status_code, prepared_url))
        except requests.exceptions.HTTPError as e:
            self.log.error("Error calling %s. Code: %s" % (prepared_url, e.response.status_code))
        except requests.exceptions.ConnectionError:
            self.log.error("Failed to connect to %s." % prepared_url)

    def _build_headers(self, resource):
        return {k: jmespath.search(v, resource) for k, v in self.headers.items()}

    def _build_url(self, resource):
        """
        Compose URL with query string parameters.

        Will not lose existing static parameters in the URL string
        but does not support 'duplicate' parameter entries
        """

        if not self.params:
            return self.url

        evaluated_params = {k: jmespath.search(v, resource) for k, v in self.params.items()}

        url_parts = list(parse.urlparse(self.url))
        query = dict(parse.parse_qsl(url_parts[4]))
        query.update(evaluated_params)
        url_parts[4] = parse.urlencode(query)

        return parse.urlunparse(url_parts)

    def _build_body(self, resource):
        """Create a JSON body and dump it to encoded bytes."""

        if not self.body:
            return None

        return json.dumps(jmespath.search(self.body, resource)).encode('utf-8')
