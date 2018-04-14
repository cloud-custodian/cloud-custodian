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
import json
import os
import tempfile
from six import binary_type

from .common import BaseTest, ACCOUNT_ID, Bag, TestConfig as Config
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
        if isinstance(contents, binary_type):
            contents = contents.decode('utf8')
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
        self.assertEqual(list(cache.state.keys()), [('uri-resolver', uri)])

    def test_resolve_file(self):
        content = json.dumps({'universe': {'galaxy': {'system': 'sun'}}})
        cache = FakeCache()
        resolver = URIResolver(None, cache)
        with tempfile.NamedTemporaryFile(mode='w+', dir=os.getcwd()) as fh:
            fh.write(content)
            fh.flush()
            self.assertEqual(
                resolver.resolve('file:%s' % fh.name), content)


class UrlValueTest(BaseTest):

    def setUp(self):
        self.old_dir = os.getcwd()
        os.chdir(tempfile.gettempdir())

    def tearDown(self):
        os.chdir(self.old_dir)

    def get_values_from(self, data, content):
        config = Config.empty(account_id=ACCOUNT_ID)
        mgr = Bag({'session_factory': None, '_cache': None, 'config': config})
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
        with open('resolver_test.txt', 'w') as out:
            for i in ['a', 'b', 'c', 'd']:
                out.write('%s\n' % i)
        with open('resolver_test.txt', 'r') as out:
            values = self.get_values_from({'url': 'letters.txt'}, out.read())
        os.remove('resolver_test.txt')
        self.assertEqual(
            values.get_values(),
            ['a', 'b', 'c', 'd'])

    def test_csv_expr(self):
        with open('test_expr.csv', 'w') as out:
            writer = csv.writer(out)
            writer.writerows([range(5) for r in range(5)])
        with open('test_expr.csv', 'r') as out:
            values = self.get_values_from(
                {'url': 'sun.csv', 'expr': '[*][2]'},
                out.read(),
            )
        os.remove('test_expr.csv')
        self.assertEqual(values.get_values(), ['2', '2', '2', '2', '2'])

    def test_csv_expr_using_dict(self):
        with open('test_dict.csv', 'w') as out:
            writer = csv.writer(out)
            writer.writerow(['aa', 'bb', 'cc', 'dd', 'ee'])  # header row
            writer.writerows([range(5) for r in range(5)])
        with open('test_dict.csv', 'r') as out:
            values = self.get_values_from(
                {'url': 'sun.csv', 'expr': 'bb[1]', 'format': 'csv2dict'},
                out.read(),
            )
        os.remove('test_dict.csv')
        self.assertEqual(values.get_values(), '1')

    def test_csv_column(self):
        with open('test_column.csv', 'w') as out:
            writer = csv.writer(out)
            writer.writerows([range(5) for r in range(5)])
        with open('test_column.csv', 'r') as out:
            values = self.get_values_from(
                {'url': 'sun.csv', 'expr': 1},
                out.read(),
            )
        os.remove('test_column.csv')
        self.assertEqual(values.get_values(), ['1', '1', '1', '1', '1'])

    def test_csv_raw(self):
        with open('test_raw.csv', 'w') as out:
            writer = csv.writer(out)
            writer.writerows([range(3, 4) for r in range(5)])
        with open('test_raw.csv', 'r') as out:
            values = self.get_values_from({'url': 'sun.csv'}, out.read())
        os.remove('test_raw.csv')
        self.assertEqual(
            values.get_values(),
            [['3'], ['3'], ['3'], ['3'], ['3']])

    def test_value_from_vars(self):
        values = self.get_values_from(
            {'url': '{account_id}', 'expr': '["{region}"][]', 'format': 'json'},
            json.dumps({'us-east-1': 'east-resource'}))
        self.assertEqual(values.get_values(), ['east-resource'])
        self.assertEqual(values.data.get('url',''), ACCOUNT_ID)
