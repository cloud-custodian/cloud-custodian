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
"""Ops feedback via log subscription
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import boto3

import base64
from datetime import datetime
import json
import textwrap
import zlib


config = logs = sns = None


def init():
    global sns, logs, config
    if sns is None:
        sns = boto3.client('sns')
    if logs is None:
        logs = boto3.client('logs')
    with open('config.json') as fh:
        config = json.load(fh)


def message_event(evt):
    dt = datetime.fromtimestamp(evt['timestamp'] / 1000.0)
    return "%s: %s" % (
        dt.ctime(), "\n".join(textwrap.wrap(evt['message'], 80)))


def process_log_event(event, context):
    """Format log events and relay via sns/email"""
    init()
    serialized = event['awslogs'].pop('data')
    data = json.loads(zlib.decompress(
        base64.b64decode(serialized), 16 + zlib.MAX_WBITS))

    # Fetch additional logs for context (20s window)
    timestamps = [e['timestamp'] for e in data['logEvents']]
    start = min(timestamps) - 1000 * 15
    end = max(timestamps) + 1000 * 5

    events = logs.get_log_events(
        logGroupName=data['logGroup'],
        logStreamName=data['logStream'],
        startTime=start,
        endTime=end,
        startFromHead=True)['events']

    message = [
        "An error was detected",
        "",
        "Log Group: %s" % data['logGroup'],
        "Log Stream: %s" % data['logStream'],
        "Log Owner: %s" % data['owner'],
        "",
        "Log Contents",
        ""]

    # We may get things delivered from log sub that are not in log events
    for evt in data['logEvents']:
        if evt not in events:
            events.append(evt)

    for evt in events:
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
    from c7n.mu import (
        LambdaFunction, PythonPackageArchive, CloudWatchLogSubscription)

    config = dict(
        name=name,
        handler='logsub.process_log_event',
        runtime='python2.7',
        memory_size=512,
        timeout=15,
        role=role,
        description='Custodian Ops Error Notify',
        events=[
            CloudWatchLogSubscription(
                session_factory, log_groups, pattern)])

    archive = PythonPackageArchive()
    archive.add_py_file(__file__)
    archive.add_contents(
        'config.json', json.dumps({
            'topic': sns_topic,
            'subject': subject
        }))
    archive.close()

    return LambdaFunction(config, archive)
