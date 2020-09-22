# Copyright 2016-2018 Capital One Services, LLC
# SPDX-License-Identifier: Apache-2.0
"""Add License headers to all py files."""

from difflib import SequenceMatcher
import fnmatch
import os
import inspect
import sys

import c7n

apache_license_header = [l + '\n' for l in """\
# SPDX-License-Identifier: Apache-2.0
""".splitlines()]

target_license_header = """\
# SPDX-License-Identifier: Apache-2.0
"""

target_copyright_header = """\
# Copyright The Cloud Custodian Authors.
"""


def update_license_header(p):
    # switch from apache pre-amble to spdx identifier
    with open(p) as fh:
        contents = list(fh.readlines())

    matcher = SequenceMatcher(None, apache_license_header, contents)
    match = matcher.find_longest_match(
        0, len(apache_license_header), 0, len(contents))

    if match.size != len(apache_license_header):
        return

    contents[match.b: match.b + match.size] = [target_license_header]
    print("Adding license header to %s" % (p,))
    with open(p, 'w') as fh:
        fh.write("".join(contents))
        fh.flush()


def update_copyright_header(p):
    with open(p) as fh:
        contents = list(fh.readlines())

    if target_copyright_header in contents:
        return

    try:
        idx = contents.index(target_license_header)
    except ValueError:
        print('no license header %s' % p)
        return

    contents[idx:idx] = [target_copyright_header]
    print("Adding copyright header to %s" % (p, ))
    with open(p, 'w') as fh:
        fh.write("".join(contents))
        fh.flush()


def update_headers(src_tree):
    """Main."""
    print("src tree", src_tree)
    for root, dirs, files in os.walk(src_tree):
        py_files = fnmatch.filter(files, "*.py")
        for f in py_files:
            print("checking", f)
            p = os.path.join(root, f)
            update_license_header(p)
            update_copyright_header(p)


def main():
    explicit = False
    if len(sys.argv) == 2:
        explicit = True
        srctree = os.path.abspath(sys.argv[1])
    else:
        srctree = os.path.dirname(inspect.getabsfile(c7n))

    update_headers(srctree)

    if not explicit:
        update_headers(os.path.abspath('tests'))
        update_headers(os.path.abspath('ftests'))
        update_headers(os.path.abspath('tools'))


if __name__ == '__main__':
    main()
