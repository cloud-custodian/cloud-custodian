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

from c7n import executor

import unittest


class Foo(object):

    def __init__(self, state):
        self.state = state

    def abc(self, *args, **kw):
        return args, kw

    @staticmethod
    def run(*args, **kw):
        return args, kw

    @classmethod
    def execute(cls, *args, **kw):
        return args, kw

    def __call__(self, *args, **kw):
        return args, kw

    
class ExecutorBase(object):

    def test_map_instance(self):
        with self.executor_factory(max_workers=3) as w:
            self.assertEqual(
                list(w.map(Foo('123'), [1, 2, 3])),
                [((1,), {}), ((2,), {}), ((3,), {})]
            )

class ProcessExecutorTest(ExecutorBase, unittest.TestCase):
    executor_factory = executor.ProcessPoolExecutor


class ThreadExecutorTest(ExecutorBase, unittest.TestCase):
    executor_factory = executor.ThreadPoolExecutor


class MainExecutorTest(ExecutorBase, unittest.TestCase):
    executor_factory = executor.MainThreadExecutor



if __name__ == '__main__':
    unittest.main()
