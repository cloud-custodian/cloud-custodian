# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import csv
import io
import json
import os.path
import logging
import itertools
from urllib.request import Request, urlopen
from urllib.parse import parse_qsl, urlparse
import zlib
from contextlib import closing

from c7n.cache import NullCache
from c7n.utils import format_string_values, local_session, jmespath_search

log = logging.getLogger('custodian.resolver')

ZIP_OR_GZIP_HEADER_DETECT = zlib.MAX_WBITS | 32


class URIResolver:

    def __init__(self, session_factory, cache):
        self.session_factory = session_factory
        self.cache = cache

    def resolve(self, uri, headers):
        contents = self.cache.get(("uri-resolver", uri))
        if contents is not None:
            return contents

        if uri.startswith('s3://'):
            contents = self.get_s3_uri(uri)
        else:
            headers.update({"Accept-Encoding": "gzip"})
            req = Request(uri, headers=headers)
            with closing(urlopen(req)) as response:  # nosec nosemgrep
                contents = self.handle_response_encoding(response)

        self.cache.save(("uri-resolver", uri), contents)
        return contents

    def handle_response_encoding(self, response):
        if response.info().get('Content-Encoding') != 'gzip':
            return response.read().decode('utf-8')

        data = zlib.decompress(response.read(),
                               ZIP_OR_GZIP_HEADER_DETECT).decode('utf8')
        return data

    def get_s3_uri(self, uri):
        parsed = urlparse(uri)
        client = local_session(self.session_factory).client('s3')
        params = dict(
            Bucket=parsed.netloc,
            Key=parsed.path[1:])
        if parsed.query:
            params.update(dict(parse_qsl(parsed.query)))
        region = params.pop('region', None)
        client = self.session_factory().client('s3', region_name=region)
        result = client.get_object(**params)
        body = result['Body'].read()
        if params['Key'].lower().endswith(('.gz', '.zip', '.gzip')):
            return zlib.decompress(body, ZIP_OR_GZIP_HEADER_DETECT).decode('utf-8')
        elif isinstance(body, str):
            return body
        else:
            return body.decode('utf-8')


class ValuesFrom:
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

      value_from:
         url: http://foobar.com/mydata
         format: json
         expr: Region."us-east-1"[].ImageId
         headers:
            authorization: my-token

      value_from:
         url: s3://bucket/abc/foo.csv
         format: csv2dict
         expr: key[1]

      # using cql against dynamodb
      value_from:
         url: dynamodb
         query: |
           select resource_id from exceptions
           where account_id = '{account_id} and policy = '{policy.name}'
         expr: [].resource_id
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
            'query': {'type': 'string'},
            'format': {'enum': ['csv', 'json', 'txt', 'csv2dict']},
            'expr': {'oneOf': [
                {'type': 'integer'},
                {'type': 'string'}]},
            'headers': {
                'type': 'object',
                'patternProperties': {
                    '': {'type': 'string'},
                },
            },
        }
    }

    def __init__(self, data, manager):
        config_args = {
            'account_id': manager.config.account_id,
            'region': manager.config.region
        }
        self.data = format_string_values(data, **config_args)
        self.manager = manager
        self.cache = manager._cache or NullCache({})
        self.resolver = URIResolver(manager.session_factory, self.cache)

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

        params = dict(
            uri=self.data.get('url'),
            headers=self.data.get('headers', {})
        )

        contents = str(self.resolver.resolve(**params))
        return contents, format

    def get_values(self):
        cache_key = [self.data.get(i) for i in ('url', 'format', 'expr', 'headers', 'query')]
        with self.cache:
            # use these values as a key to cache the result so if we have
            # the same filter happening across many resources, we can reuse
            # the results.
            contents = self.cache.get(("value-from", cache_key))
            if contents is not None:
                return contents
            if self.data['url'] == 'dynamodb':
                contents = self._get_ddb_values()
            else:
                contents = self._get_values()
            self.cache.save(("value-from", cache_key), contents)
            return contents

    def _get_ddb_values(self):
        if not self.data['query']:
            return
        if not self.data['query'].lower().startswith('select'):
            return

        from boto3.dynamodb.types import TypeDeserializer
        from botocore.paginate import Paginator

        client = local_session(self.manager.session_factory).client('dynamodb')

        pager = Paginator(
            client.execute_statement,
            {"input_token": "NextToken", "output_token": "NextToken", "result_key": "Items"},
            client.meta.service_model.operation_model('ExecuteStatement')
        )
        deserializer = TypeDeserializer()
        results = []

        record_singleton = False
        for page in pager.paginate(Statement=self.data['query']):
            for row in page.get("Items", []):
                record = {k: deserializer.deserialize(v) for k, v in row.items()}
                if record_singleton or len(record) == 1:
                    record_singleton = True
                    results.append(list(record.values())[0])
                else:
                    results.append(record)
        if not record_singleton or self.data.get('expr'):
            return self._get_resource_values(results)
        return results

    def _get_values(self):
        contents, format = self.get_contents()

        if format == 'json':
            data = json.loads(contents)
            if 'expr' in self.data:
                return self._get_resource_values(data)
            else:
                return data
        elif format == 'csv' or format == 'csv2dict':
            data = csv.reader(io.StringIO(contents))
            if format == 'csv2dict':
                data = {x[0]: list(x[1:]) for x in zip(*data)}
                if 'expr' in self.data:
                    return self._get_resource_values(data)
                else:
                    combined_data = set(itertools.chain.from_iterable(data.values()))
                    return combined_data
            else:
                if isinstance(self.data.get('expr'), int):
                    return set([d[self.data['expr']] for d in data])
                data = list(data)
                if 'expr' in self.data:
                    return self._get_resource_values(data)
                else:
                    combined_data = set(itertools.chain.from_iterable(data))
                    return combined_data
        elif format == 'txt':
            return set([s.strip() for s in io.StringIO(contents).readlines()])

    def _get_resource_values(self, data):
        res = jmespath_search(self.data['expr'], data)
        if res is None:
            log.warning(f"ValueFrom filter: {self.data['expr']} key returned None")
        if isinstance(res, list):
            res = set(res)
        return res
