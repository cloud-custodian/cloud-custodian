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
"""Ops feedback via log subscription
"""
import boto3

import base64
from datetime import datetime
import json
import textwrap
import zlib


sns = None


def init():
    global sns
    if sns is None:
        sns = boto3.client('sns')


def message_event(evt):
    dt = datetime.fromtimestamp(evt['timestamp']/1000.0)
    return "%s: %s" % (
        dt.ctime(), "\n".join(textwrap.wrap(evt['message'], 80)))


def process_log_event(event, context):
    """Format log events and relay via sns/email"""

    init()
    with open('config.json') as fh:
        config = json.load(fh)
    serialized = event['awslogs'].pop('data')
    data = json.loads(zlib.decompress(
        base64.b64decode(serialized), 16+zlib.MAX_WBITS))
    message = [
        "An error was detected",
        "",
        "Log Group: %s" % data['logGroup'],
        "Log Stream: %s" % data['logStream'],
        "Log Owner: %s" % data['owner'],
        "",
        "Log Contents",
        ""]

    for evt in data['logEvents']:
        message.append(message_event(evt))
        message.append("")

    params = dict(
        TopicArn=config['topic'],
        Subject=config['subject'],
        Message='\n'.join(message))
    sns.publish(**params)


def get_function(session_factory, name, role, sns_topic, log_groups,
                 subject="Lambda Error", pattern="Traceback"):
    """Lambda function provisioning.

    Self contained within the component, to allow for easier reuse.
    """

    # Lazy import to avoid runtime dependency
    import inspect
    import os

    import c7n
    from c7n.mu import (
        LambdaFunction, PythonPackageArchive, CloudWatchLogSubscription)

    config = dict(
        name='cloud-maid-error-notify',
        handler='logsub.process_log_event',
        runtime='python2.7',
        memory_size=512,
        timeout=15,
        role=role,
        description='Custodian Ops Error Notify',
        events=[
            CloudWatchLogSubscription(
                session_factory, log_groups, pattern)])

    archive = PythonPackageArchive(
        # Directory to lambda file
        os.path.join(
            os.path.dirname(inspect.getabsfile(c7n)), 'logsub.py'),
        # Don't include virtualenv deps
        lib_filter=lambda x, y, z: ([], []))
    archive.create()
    archive.add_contents(
        'config.json', json.dumps({
            'topic': sns_topic,
            'subject': subject
        }))
    archive.close()

    return LambdaFunction(config, archive)
