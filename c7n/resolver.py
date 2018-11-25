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
from __future__ import absolute_import, division, print_function, unicode_literals

import csv
import io
import jmespath
import json
import os.path
import logging
from six import text_type
from six.moves.urllib.request import urlopen
from six.moves.urllib.parse import parse_qsl, urlparse

from c7n.utils import format_string_values

log = logging.getLogger('custodian.resolver')


class URIResolver(object):

    def __init__(self, session_factory, cache):
        self.session_factory = session_factory
        self.cache = cache

    def resolve(self, uri):
        if uri.startswith('s3://'):
            contents = self.get_s3_uri(uri)
        else:
            # TODO: in the case of file: content and untrusted
            # third parties, uri would need sanitization
            fh = urlopen(uri)
            contents = fh.read().decode('utf-8')
            fh.close()
        self.cache.save(("uri-resolver", uri), contents)
        return contents

    def get_s3_uri(self, uri):
        parsed = urlparse(uri)
        client = self.session_factory().client('s3')
        params = dict(
            Bucket=parsed.netloc,
            Key=parsed.path[1:])
        if parsed.query:
            params.update(dict(parse_qsl(parsed.query)))
        result = client.get_object(**params)
        body = result['Body'].read()
        if isinstance(body, str):
            return body
        else:
            return body.decode('utf-8')


class ValuesFrom(object):
    """Retrieve values from a url.

    Supports json, csv and line delimited text files and expressions
    to retrieve a subset of values.

    Expression syntax
    - on json, a jmespath expr is evaluated
    - on csv, an integer column or jmespath expr can be specified
    - on csv2dict, a jmespath expr (the csv is parsed into a dictionary where
    the keys are the headers and the values are the remaining columns)

    Text files are expected to be line delimited values.

    Examples::

      value_from:
         url: s3://bucket/xyz/foo.json
         expr: [].AppId

      values_from:
         url: http://foobar.com/mydata
         format: json
         expr: Region."us-east-1"[].ImageId

      value_from:
         url: s3://bucket/abc/foo.csv
         format: csv2dict
         expr: key[1]

       # inferred from extension
       format: [json, csv, csv2dict, txt]
    """
    supported_formats = ('json', 'txt', 'csv', 'csv2dict')

    # intent is that callers embed this schema
    schema = {
        'type': 'object',
        'additionalProperties': 'False',
        'required': ['url'],
        'properties': {
            'url': {'type': 'string'},
            'format': {'enum': ['csv', 'json', 'txt', 'csv2dict']},
            'expr': {'oneOf': [
                {'type': 'integer'},
                {'type': 'string'}]}
        }
    }

    def __init__(self, data, manager):
        config_args = {
            'account_id': manager.config.account_id,
            'region': manager.config.region
        }
        self.data = format_string_values(data, **config_args)
        self.manager = manager
        self.resolver = URIResolver(manager.session_factory, manager._cache)

    def get_contents(self):
        _, format = os.path.splitext(self.data['url'])

        if not format or self.data.get('format'):
            format = self.data.get('format', '')
        else:
            format = format[1:]

        if format not in self.supported_formats:
            raise ValueError(
                "Unsupported format %s for url %s",
                format, self.data['url'])
        contents = text_type(self.resolver.resolve(self.data['url']))
        return contents, format

    def get_values(self):
        contents, format = self.get_contents()

        if format == 'json':
            data = json.loads(contents)
            if 'expr' in self.data:
                res = jmespath.search(self.data['expr'], data)
                if res is None:
                    log.warning('ValueFrom filter: %s key returned None' % self.data['expr'])
                return res
        elif format == 'csv' or format == 'csv2dict':
            data = csv.reader(io.StringIO(contents))
            if format == 'csv2dict':
                data = {x[0]: list(x[1:]) for x in zip(*data)}
            else:
                if isinstance(self.data.get('expr'), int):
                    return [d[self.data['expr']] for d in data]
                data = list(data)
            if 'expr' in self.data:
                res = jmespath.search(self.data['expr'], data)
                if res is None:
                    log.warning('ValueFrom filter: %s key returned None' % self.data['expr'])
                return res
            return data
        elif format == 'txt':
            return [s.strip() for s in io.StringIO(contents).readlines()]
