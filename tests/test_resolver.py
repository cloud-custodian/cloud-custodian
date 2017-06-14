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
from __future__ import absolute_import, division, print_function, unicode_literals

import csv
import json
import os
from StringIO import StringIO
import tempfile

from .common import Bag, BaseTest
from .test_s3 import destroyBucket

from c7n.resolver import ValuesFrom, URIResolver


class FakeCache(object):

    def __init__(self):
        self.state = {}

    def get(self, key):
        return self.state.get(key)

    def save(self, key, data):
        self.state[key] = data


class FakeResolver(object):

    def __init__(self, contents):
        self.contents = contents

    def resolve(self, uri):
        return self.contents


class ResolverTest(BaseTest):

    def test_resolve_s3(self):
        session_factory = self.replay_flight_data('test_s3_resolver')
        session = session_factory()
        client = session.client('s3')
        resource = session.resource('s3')

        bname = 'custodian-byebye'
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        key = resource.Object(bname, 'resource.json')
        content = json.dumps({'moose': {'soup': 'duck'}})
        key.put(Body=content, ContentLength=len(content),
                ContentType='application/json')

        cache = FakeCache()
        resolver = URIResolver(session_factory, cache)
        uri = 's3://%s/resource.json?RequestPayer=requestor' % bname
        data = resolver.resolve(uri)
        self.assertEqual(content, data)
        self.assertEqual(cache.state.keys(), [('uri-resolver', uri)])

    def test_resolve_file(self):
        content = json.dumps({'universe': {'galaxy': {'system': 'sun'}}})
        cache = FakeCache()
        resolver = URIResolver(None, cache)
        with tempfile.NamedTemporaryFile(dir=os.getcwd()) as fh:
            fh.write(content)
            fh.flush()
            self.assertEqual(
                resolver.resolve('file:%s' % fh.name), content)


class UrlValueTest(BaseTest):

    def get_values_from(self, data, content):
        mgr = Bag({'session_factory': None, '_cache': None})
        values = ValuesFrom(data, mgr)
        values.resolver = FakeResolver(content)
        return values

    def test_json_expr(self):
        values = self.get_values_from(
            {'url': 'moon', 'expr': '[].bean', 'format': 'json'},
            json.dumps([{'bean': 'magic'}]))
        self.assertEqual(values.get_values(), ['magic'])

    def test_invalid_format(self):
        values = self.get_values_from({'url': 'mars'}, '')
        self.assertRaises(ValueError, values.get_values)

    def test_txt(self):
        out = StringIO()
        for i in ['a', 'b', 'c', 'd']:
            out.write('%s\n' % i)
        values = self.get_values_from({'url': 'letters.txt'}, out.getvalue())
        self.assertEqual(
            values.get_values(),
            ['a', 'b', 'c', 'd'])

    def test_csv_expr(self):
        out = StringIO()
        writer = csv.writer(out)
        writer.writerows([range(5) for r in range(5)])
        values = self.get_values_from(
            {'url': 'sun.csv', 'expr': '[*][2]'}, out.getvalue())
        self.assertEqual(values.get_values(), ['2', '2', '2', '2', '2'])

    def test_csv_expr_using_dict(self):
        out = StringIO()
        writer = csv.writer(out)
        writer.writerow(['aa', 'bb', 'cc', 'dd', 'ee'])  # header row
        writer.writerows([range(5) for r in range(5)])
        values = self.get_values_from(
            {'url': 'sun.csv', 'expr': 'bb[1]', 'format': 'csv2dict'}, out.getvalue())
        self.assertEqual(values.get_values(), '1')

    def test_csv_column(self):
        out = StringIO()
        writer = csv.writer(out)
        writer.writerows([range(5) for r in range(5)])
        values = self.get_values_from(
            {'url': 'sun.csv', 'expr': 1}, out.getvalue())
        self.assertEqual(values.get_values(), ['1', '1', '1', '1', '1'])

    def test_csv_raw(self):
        out = StringIO()
        writer = csv.writer(out)
        writer.writerows([range(3, 4) for r in range(5)])
        values = self.get_values_from({'url': 'sun.csv'}, out.getvalue())
        self.assertEqual(
            values.get_values(),
            [['3'], ['3'], ['3'], ['3'], ['3']])
