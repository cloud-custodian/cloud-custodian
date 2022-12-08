# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n import executor

import unittest


class Foo:

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


class ExecutorBase:

    def test_map_instance(self):
        with self.executor_factory(max_workers=3) as w:
            self.assertEqual(
                list(w.map(Foo("123"), [1, 2, 3])), [((1,), {}), ((2,), {}), ((3,), {})]
            )


class ThreadExecutorTest(ExecutorBase, unittest.TestCase):
    executor_factory = executor.ThreadPoolExecutor


class MainExecutorTest(ExecutorBase, unittest.TestCase):
    executor_factory = executor.MainThreadExecutor


if __name__ == "__main__":
    unittest.main()
