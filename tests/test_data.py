# Copyright 2020 Kapil Thangavelu
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
import pytest

from c7n.exceptions import PolicyExecutionError
from .common import load_data, data_path


def test_data_policy(test):
    p = test.load_policy({
        'name': 'data-stuff',
        'resource': 'c7n.data',
        'source': 'static',
        'filters': [{'name': 'bob'}],
        'query': [
            {'records': [
                {'name': 'bob'},
                {'name': 'alice'}]}]})
    resources = p.run()
    assert resources == [
        {'name': 'bob', 'c7n:MatchedFilters': ['name']}]


def test_load_map_fails(test):
    p = test.load_policy({
        'name': 'data-nuff',
        'resource': 'c7n.data',
        'source': 'disk',
        'query': [
            {'path': data_path('config', 'app-elb.json')}]})

    with pytest.raises(PolicyExecutionError, match='in non list format'):
        p.run()


def test_load_map_expression_fails(test):
    p = test.load_policy({
        'name': 'data-nuff',
        'resource': 'c7n.data',
        'source': 'disk',
        'query': [
            {'path': data_path('config', 'app-elb.json'),
             'key': 'tags'}]})

    with pytest.raises(PolicyExecutionError, match='in non list format'):
        p.run()


def test_load_array_expression(test):
    p = test.load_policy({
        'name': 'data-nuff',
        'resource': 'c7n.data',
        'source': 'disk',
        'query': [
            {'path': data_path('iam-actions.json'),
             'key': 'account'}]})
    assert p.run() == ['DisableRegion', 'EnableRegion', 'ListRegions']


def test_load_dir_rglob(tmpdir, test):
    (tmpdir.mkdir('xyz') / 'foo.json').write(
        json.dumps(['a', 'b', 'c']))
    (tmpdir.mkdir('abc') / 'bar.json').write(
        json.dumps(['d', 'e', 'f']))
    p = test.load_policy({
        'name': 'stuff',
        'resource': 'c7n.data',
        'source': 'disk',
        'query': [
            {'path': str(tmpdir), 'glob': '**/*.json'}]})
    assert sorted(p.run()) == ['a', 'b', 'c', 'd', 'e', 'f']
