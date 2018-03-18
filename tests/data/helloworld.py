# Copyright 2017 Capital One Services, LLC
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
"""Hello world Lambda function for mu testing.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import sys


def main(event, context):
    from c7n.utils import parse_cidr
    parse_cidr('10.0.0.0/24')  # while we're here, ensure ipaddress availability
    json.dump(event, sys.stdout)


def get_function(session_factory, name, role, events):
    from c7n.mu import (LambdaFunction, custodian_archive)

    config = dict(
        name=name,
        handler='helloworld.main',
        runtime='python2.7',
        memory_size=512,
        timeout=15,
        role=role,
        description='Hello World',
        events=events)

    archive = custodian_archive()
    archive.add_py_file(__file__)
    archive.close()

    return LambdaFunction(config, archive)
