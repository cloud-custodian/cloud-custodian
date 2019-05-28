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
from six.moves.urllib import request, parse
from six.moves.urllib.error import URLError

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
                    - resource_name: name
    """

    schema = utils.type_schema(
        'webhook',
        required=['url'],
        **{
            'url': {'type': 'string'},
            'body': {'type': 'string'},
            'batch': {'type': 'boolean'},
            'method': {'type': 'string'},
            'parameters': {
                "type": "object",
                "additionalProperties": {
                    "type": "string",
                    "description": "query string values"
                }
            }
        }
    )

    def process(self, resources, event=None):
        self.url = self.data['url']
        self.body = self.data.get('body')
        self.batch = self.data.get('batch', False)

        if self.batch:
            self._process_call(resources)
        else:
            for r in resources:
                self._process_call(r)

    def _process_call(self, resource):
        prepared_url = self._build_url(resource)
        prepared_body = self._build_body(resource)
        method = self.data.get('method', 'POST' if prepared_body else 'GET')

        req = request.Request(prepared_url, data=prepared_body, method=method)

        if prepared_body:
            req.add_header('Content-Type', 'application/json')

        try:
            response = request.urlopen(req)
            self.log.info("%s got response %s with URL %s" % (method, response.code, prepared_url))
        except URLError as e:
            self.log.error("Error calling %s. Reason: %s" % (prepared_url, e.reason))

    def _build_url(self, resource):
        params = self.data.get('parameters', {})

        if not params:
            return self.url

        evaluated_params = {k: jmespath.search(v, resource) for k, v in params.items()}

        url_parts = list(parse.urlparse(self.url))
        query = dict(parse.parse_qsl(url_parts[4]))
        query.update(evaluated_params)
        url_parts[4] = parse.urlencode(query)

        return parse.urlunparse(url_parts)

    def _build_body(self, resource):
        if not self.body:
            return None

        return json.dumps(jmespath.search(self.body, resource)).encode('utf-8')
