# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import csv
import io
import jmespath
import json
import os.path
import logging
import itertools

from c7n.utils import format_string_values, URIResolver

log = logging.getLogger('custodian.resolver')


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
        self.cache = manager._cache
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
        contents = str(self.resolver.resolve(self.data['url']))
        return contents, format

    def get_values(self):
        if self.cache:
            # use these values as a key to cache the result so if we have
            # the same filter happening across many resources, we can reuse
            # the results.
            key = [self.data.get(i) for i in ('url', 'format', 'expr')]
            contents = self.cache.get(("value-from", key))
            if contents is not None:
                return contents

        contents = self._get_values()
        if self.cache:
            self.cache.save(("value-from", key), contents)
        return contents

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
        res = jmespath.search(self.data['expr'], data)
        if res is None:
            log.warning(f"ValueFrom filter: {self.data['expr']} key returned None")
        if isinstance(res, list):
            res = set(res)
        return res
