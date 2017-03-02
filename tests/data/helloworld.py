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
"""Hello world Lambda function for mu testing.
"""
import json
import sys


def main(event, context):
    json.dump(event, sys.stdout)


def get_function(session_factory, name, role, events):
    import os
    from c7n.mu import (LambdaFunction, PythonPackageArchive)

    config = dict(
        name=name,
        handler='helloworld.main',
        runtime='python2.7',
        memory_size=512,
        timeout=15,
        role=role,
        description='Hello World',
        events=events)

    archive = PythonPackageArchive(
        # Directory to lambda file
        os.path.abspath(__file__),
        # Don't include virtualenv deps
        lib_filter=lambda x, y, z: ([], []))
    archive.create()
    archive.close()

    return LambdaFunction(config, archive)
