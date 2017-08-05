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

from concurrent.futures import (
    ProcessPoolExecutor, ThreadPoolExecutor)

from c7n.registry import PluginRegistry

import threading


class ExecutorRegistry(PluginRegistry):

    def __init__(self, plugin_type):
        super(ExecutorRegistry, self).__init__(plugin_type)

        self.register('process', ProcessPoolExecutor)
        self.register('thread', ThreadPoolExecutor)
        self.register('main', MainThreadExecutor)


def executor(name, **kw):
    factory = executors.get(name)
    # post element refactoring
    # factory.validate(kw)
    if factory is None:
        raise ValueError("No Such Executor %s" % name)
    return factory(**kw)


class MainThreadExecutor(object):
    """ For running tests.

    async == True  -> catch exceptions and store them in the future.
    async == False -> let exceptions bubble up.
    """

    async = True

    # For Dev/Unit Testing with concurrent.futures
    def __init__(self, *args, **kw):
        self.args = args
        self.kw = kw

    def map(self, func, iterable):
        for args in iterable:
            yield func(args)

    def submit(self, func, *args, **kw):
        try:
            return MainThreadFuture(func(*args, **kw))
        except Exception as e:
            if self.async:
                return MainThreadFuture(None, exception=e)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class MainThreadFuture(object):
    # For Dev/Unit Testing with concurrent.futures

    def __init__(self, value, exception=None):
        self.value = value
        self._exception = exception
        # Sigh concurrent.futures pokes at privates
        self._state = 'FINISHED'
        self._waiters = []
        self._condition = threading.Condition()

    def cancel(self):
        return False

    def cancelled(self):
        return False

    def exception(self):
        return self._exception

    def done(self):
        return True

    def result(self, timeout=None):
        if self._exception:
            raise self._exception
        return self.value

    def add_done_callback(self, fn):
        return fn(self)


executors = ExecutorRegistry('executor')
executors.load_plugins()
