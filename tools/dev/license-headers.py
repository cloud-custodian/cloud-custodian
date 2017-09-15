# Copyright 2016-2017 Capital One Services, LLC
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
"""Add License headers to all py files."""

import fnmatch
import os
import inspect
import sys

import c7n

header = """\
# Copyright 2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
"""


suffix = """\
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""


def update_headers(src_tree):
    """Main."""
    print "src tree", src_tree
    for root, dirs, files in os.walk(src_tree):
        py_files = fnmatch.filter(files, "*.py")
        for f in py_files:
            print "checking", f
            p = os.path.join(root, f)
            with open(p) as fh:
                contents = fh.read()
            if suffix in contents:
                continue
            print("Adding license header to %s" % p)
            with open(p, 'w') as fh:
                fh.write(
                    '%s%s%s' % (header, suffix, contents))


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


if __name__ == '__main__':
    main()
