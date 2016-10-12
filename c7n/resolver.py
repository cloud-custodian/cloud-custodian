# Copyright 2016 Capital One Services, LLC
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
import csv
import json
import os.path
from StringIO import StringIO
import urllib2
import urlparse

import jmespath


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
            fh = urllib2.urlopen(uri)
            contents = fh.read()
            fh.close()
        self.cache.save(("uri-resolver", uri), contents)
        return contents

    def get_s3_uri(self, uri):
        parsed = urlparse.urlparse(uri)
        client = self.session_factory().client('s3')
        params = dict(
            Bucket=parsed.netloc,
            Key=parsed.path[1:])
        if parsed.query:
            params.update(dict(urlparse.parse_qsl(parsed.query)))
        result = client.get_object(**params)
        return result['Body'].read()


class ValuesFrom(object):
    """Retrieve values from a url.

    Supports json, csv and line delimited text files and expressions
    to retrieve a subset of values.

    Expression syntax
    - on json, a jmespath expr is valuated
    - on csv, an integer column or jmespath expr can be specified

    Text files are expected to be line delimited values.

    Examples::

      value_from:
         url: s3://bucket/xyz/foo.json
         expr: [].AppId

      values_from:
         url: http://foobar.com/mydata
         format: json
         expr: Region."us-east-1"[].ImageId

       # inferred from extension
       format: [json, csv, txt]
    """
    supported_formats = ('json', 'txt', 'csv')

    # intent is that callers embed this schema
    schema = {
        'type': 'object',
        'additionalProperties': 'False',
        'required': ['url'],
        'properties': {
            'url': {'type': 'string'},
            'format': {'enum': ['csv', 'json', 'txt']},
            'expr': {'type': 'string'}
        }
    }

    def __init__(self, data, manager):
        self.data = data
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
        contents = self.resolver.resolve(self.data['url'])
        return contents, format

    def get_values(self):
        contents, format = self.get_contents()

        if format == 'json':
            data = json.loads(contents)
            if 'expr' in self.data:
                return jmespath.search(self.data['expr'], data)
        elif format == 'csv':
            data = csv.reader(StringIO(contents))
            if 'expr' in self.data and isinstance(self.data['expr'], int):
                return [d[self.data['expr']] for d in data]
            if 'expr' in self.data:
                return jmespath.search(self.data['expr'], list(data))
            return list(data)
        elif format == 'txt':
            return [s.strip() for s in StringIO(contents).readlines()]
