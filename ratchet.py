#!/usr/bin/env python3.6
# -*- coding: utf-8 -*-
"""Ratchet up successes under Python 3.6.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import sys
from xml.dom import minidom


MUST_PASS = '''\
tests.test_executor.ProcessExecutorTest.test_map_instance
tests.test_executor.ThreadExecutorTest.test_map_instance
tests.test_executor.MainExecutorTest.test_map_instance
'''


def handle_testcase(node, havent_passed):
    nchildren = len(node.childNodes)
    if nchildren > 1:
        return
    elif nchildren == 1:
        child = node.childNodes[0]
        if child.tagName == 'error':
            return
    attrs = dict(node.attributes.items())
    key = '.'.join((attrs['classname'], attrs['name']))
    if key in havent_passed:
        havent_passed.remove(key)


def walk(node, havent_passed):
    for child in node.childNodes:
        if child.nodeType != 1:
            continue
        handle = globals().get('handle_{}'.format(child.tagName))
        handle(child, havent_passed) if handle else walk(child, havent_passed)


def parse_must_pass(must_pass):
    parsed = set()
    for line in must_pass.splitlines():
        if not line:
            continue
        parsed.add(line)
    return parsed


def main(filepath):
    havent_passed = parse_must_pass(MUST_PASS)
    walk(minidom.parse(filepath), havent_passed)
    if havent_passed:
        print("Some tests required to pass under Python 3.6 didn't:")
        for key in sorted(havent_passed):
            print(' ', key)
        return 1
    print('All tests required to pass under Python 3.6 did.')
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
