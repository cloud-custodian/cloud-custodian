# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from concurrent.futures import (ProcessPoolExecutor, ThreadPoolExecutor)  # noqa

import threading


class MainThreadExecutor:
    """ For running tests.

    c7n_async == True  -> catch exceptions and store them in the future.
    c7n_async == False -> let exceptions bubble up.
    """

    c7n_async = True

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
            if self.c7n_async:
                return MainThreadFuture(None, exception=e)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class MainThreadFuture:
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
