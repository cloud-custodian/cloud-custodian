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
import jmespath

from placebo import pill
import placebo

import fnmatch
import json
import unittest
import os
import shutil
import zipfile

import boto3


class ZippedPill(pill.Pill):

    def __init__(self, path, prefix=None, debug=False):
        super(ZippedPill, self).__init__(prefix, debug)
        self.path = path
        self._used = set()
        self.archive = None

    def playback(self):
        self.archive = zipfile.ZipFile(self.path, 'r')
        self._files = set(self.archive.namelist())
        return super(ZippedPill, self).playback()

    def record(self):
        self.archive = zipfile.ZipFile(self.path, 'a', zipfile.ZIP_DEFLATED)
        self._files = set()

        files = set([n for n in self.archive.namelist()
                     if n.startswith(self.prefix)])

        if not files:
            return super(ZippedPill, self).record()

        # We can't update files in a zip, so copy
        self.archive.close()
        os.rename(self.path, "%s.tmp" % self.path)
        src = zipfile.ZipFile("%s.tmp" % self.path, 'r')

        self.archive = zipfile.ZipFile(
            self.path, 'w', zipfile.ZIP_DEFLATED)

        for n in src.namelist():
            if n in files:
                continue
            self.archive.writestr(n, src.read(n))
        os.remove("%s.tmp" % self.path)
        return super(ZippedPill, self).record()

    def stop(self):
        super(ZippedPill, self).stop()
        if self.archive:
            self.archive.close()

    def save_response(self, service, operation, response_data,
                      http_response=200):

        filepath = self.get_new_file_path(service, operation)
        pill.LOG.debug('save_response: path=%s', filepath)
        json_data = {'status_code': http_response,
                     'data': response_data}
        self.archive.writestr(
            filepath,
            json.dumps(json_data, indent=4, default=pill.serialize),
            zipfile.ZIP_DEFLATED)
        self._files.add(filepath)

    def load_response(self, service, operation):
        response_file = self.get_next_file_path(service, operation)
        self._used.add(response_file)
        pill.LOG.debug('load_responses: %s', response_file)
        response_data = json.loads(
            self.archive.read(response_file), object_hook=pill.deserialize)
        return (pill.FakeHttpResponse(response_data['status_code']),
                response_data['data'])

    def get_new_file_path(self, service, operation):
        base_name = '{0}.{1}'.format(service, operation)
        if self.prefix:
            base_name = '{0}.{1}'.format(self.prefix, base_name)
        pill.LOG.debug('get_new_file_path: %s', base_name)
        index = 0
        glob_pattern = os.path.join(self._data_path, base_name + '*')

        for file_path in fnmatch.filter(self._files, glob_pattern):
            file_name = os.path.basename(file_path)
            m = self.filename_re.match(file_name)
            if m:
                i = int(m.group('index'))
                if i > index:
                    index = i
        index += 1
        return os.path.join(
            self._data_path, '{0}_{1}.json'.format(base_name, index))

    def get_next_file_path(self, service, operation):
        base_name = '{0}.{1}'.format(service, operation)
        if self.prefix:
            base_name = '{0}.{1}'.format(self.prefix, base_name)
        pill.LOG.debug('get_next_file_path: %s', base_name)
        next_file = None
        while next_file is None:
            index = self._index.setdefault(base_name, 1)
            fn = os.path.join(
                self._data_path, base_name + '_{0}.json'.format(index))
            if fn in self._files:
                next_file = fn
                self._index[base_name] += 1
                self._files.add(fn)
            elif index != 1:
                self._index[base_name] = 1
            else:
                # we are looking for the first index and it's not here
                raise IOError('response file ({0}) not found'.format(fn))
        return fn


def attach(session, data_path, prefix=None, debug=False):
    pill = ZippedPill(data_path, prefix=prefix, debug=debug)
    pill.attach(session, prefix)
    return pill


class PillTest(unittest.TestCase):

    archive_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'placebo_data.zip')

    placebo_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'data', 'placebo')

    def assertJmes(self, expr, instance, expected):
        value = jmespath.search(expr, instance)
        self.assertEqual(value, expected)

    def cleanUp(self):
        pass

    def record_flight_data(self, test_case, zdata=False):
        if not zdata:
            test_dir = os.path.join(self.placebo_dir, test_case)
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
            os.makedirs(test_dir)

        session = boto3.Session()
        if not zdata:
            pill = placebo.attach(session, test_dir, debug=True)
        else:
            pill = attach(session, self.archive_path, test_case, debug=True)

        pill.record()
        self.addCleanup(pill.stop)
        self.addCleanup(self.cleanUp)
        # return session factory
        return lambda region=None, assume=None: session

    def replay_flight_data(self, test_case, zdata=False):
        if not zdata:
            test_dir = os.path.join(self.placebo_dir, test_case)
            if not os.path.exists(test_dir):
                raise RuntimeError(
                    "Invalid Test Dir for flight data %s" % test_dir)

        session = boto3.Session()
        if not zdata:
            pill = placebo.attach(session, test_dir)
        else:
            pill = attach(session, self.archive_path, test_case, False)

        pill.playback()
        self.addCleanup(pill.stop)
        self.addCleanup(self.cleanUp)
        return lambda region=None, assume=None: session
