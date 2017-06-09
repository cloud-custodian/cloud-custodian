#!/usr/bin/env python3.6
# -*- coding: utf-8 -*-
"""Ratchet up successes under Python 3.6.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import sys
from xml.dom import minidom


EXPECTED_SUCCESSES = '''\
tests.test_executor.ProcessExecutorTest.test_map_instance
tests.test_executor.ThreadExecutorTest.test_map_instance
tests.test_executor.MainExecutorTest.test_map_instance
'''


def handle_testcase(node, havent_passed, shouldnt_pass):
    nchildren = len(node.childNodes)
    if nchildren > 1:
        return
    elif nchildren == 1:
        child = node.childNodes[0]
        if child.tagName == 'error':
            return
    attrs = dict(node.attributes.items())
    testname = '.'.join((attrs['classname'], attrs['name']))
    if testname in havent_passed:
        havent_passed.remove(testname)
    else:
        shouldnt_pass.add(testname)


def walk(node, havent_passed, shouldnt_pass):
    for child in node.childNodes:
        if child.nodeType != 1:
            continue
        handle = globals().get('handle_{}'.format(child.tagName))
        if handle:
            handle(child, havent_passed, shouldnt_pass)
        else:
            walk(child, havent_passed, shouldnt_pass)


def parse_expected_successes(expected_successes):
    parsed = set()
    for line in expected_successes.splitlines():
        if not line:
            continue
        parsed.add(line)
    return parsed


def list_tests(tests):
    for test in sorted(tests):
        print(' ', test)


def main(filepath):
    expected = parse_expected_successes(EXPECTED_SUCCESSES)
    unexpected = set()
    walk(minidom.parse(filepath), expected, unexpected)

    if expected:
        print("Some tests required to pass under Python 3.6 didn't:")
        list_tests(expected)
    if unexpected:
        print("Some tests not required to pass under Python 3.6 did:")
        list_tests(unexpected)
        print("Please add them to ratchet.py!")
    if expected or unexpected:
        return 1
    print('All and only tests required to pass under Python 3.6 did.')
    return 0


if __name__ == '__main__':
    try:
        filepath = sys.argv[1]
    except IndexError:
        script = sys.argv[0]
        print('usage: {} <junitxml filepath>'.format(script), file=sys.stderr)
        result = 1
    else:
        result = main(filepath)
    sys.exit(result)
