#!/usr/bin/env python3.6
# -*- coding: utf-8 -*-
"""Ratchet up successes under Python 3.6.
"""
from __future__ import (
    absolute_import, division, print_function, unicode_literals)

import sys
import xml.etree.ElementTree as Etree


INVALID_TYPE = 'E   botocore.exceptions.ParamValidationError: ' \
    'Parameter validation failed:     Invalid type for parameter '


class TestResults(object):

    def __init__(self, results_path):
        self.results_path = results_path
        self.failed = []
        self.failed_aggregates = {}
        self.stderr_output = []
        self.passed = []
        self._tree = None

    def parse(self):
        if self._tree:
            raise AssertionError("Already Parsed")
        self._tree = Etree.parse(self.results_path)
        for testcase in self._tree.findall('testcase'):
            self.process_testcase(testcase)
        return self

    def process_testcase(self, case):
        key = self.case_key(case)

        # look at children but throw away stderr output
        nonsuccess = [c for c in case if not c.tag == 'system-err']
        n = len(nonsuccess)
        if n > 1:
            raise AssertionError("multiple results for %s: %s" %
                (key, nonsuccess))
        elif n == 1:
            result = nonsuccess.pop()
            self.failed.append(key)
            message = result.get('message')
            if message is None:
                return
            if message.startswith(INVALID_TYPE):
                message = INVALID_TYPE
            self.failed_aggregates.setdefault(message, []).append(key)
        else:
            self.passed.append(key)

    @staticmethod
    def case_key(case):
        return "%s.%s" % (case.get('classname'), case.get('name'))

    def report(self, details=False):
        for k, v in sorted(
                self.failed_aggregates.items(),
                key = lambda i: len(i[1]),
                reverse=True):
            print("# %s" % k)
            for t in v:
                print(" - %s" % t)


def load_expected_failures(txt):
    expected_failures = open(txt).read()
    parsed = set()
    for line in expected_failures.splitlines():
        if not line or line.startswith('#'):
            continue
        parsed.add(line)
    return parsed


def list_tests(tests):
    for test in sorted(tests):
        print(' ', test)


def update_expectation(txt_path, tests):
    new = set(t + '\n' for t in tests)
    open(txt_path, 'w+').writelines(sorted(new))


def main(xml_path, txt_path):
    """Takes two paths, one to XML output from pytest, the other to a text file
    listing expected successes. Walks the former looking for the latter.
    """
    results = TestResults(xml_path).parse()

    if txt_path == '-':
        results.report()
        return

    previous = load_expected_failures(txt_path)
    current = set(results.failed)

    expected = previous - current
    if expected:
        print("Some tests expected to fail under Python 3.6 didn't:")
        list_tests(expected)
        update_expectation(txt_path, current)
        print("Conveniently, they have been removed from {} for you. Perhaps "
            "commit that?".format(txt_path))

    unexpected = current - previous
    if unexpected:
        print("Some tests not expected to fail under Python 3.6 did:")
        list_tests(unexpected)

    if expected or unexpected:
        print("Previously %d tests failed under Python 3.6, now %d did." %
            (len(previous), len(current)))
        return 1

    print('All and only tests expected to fail under Python 3.6 did.')
    return 0


if __name__ == '__main__':
    try:
        xml_path, txt_path = sys.argv[1:3]
    except ValueError:
        script = sys.argv[0]
        print('usage: {} <junitxml filepath> <expected successes filepath>'
              .format(script), file=sys.stderr)
        result = 1
    else:
        result = main(xml_path, txt_path)
    sys.exit(result)
