# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Hello world Lambda function for mu testing.
"""
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
