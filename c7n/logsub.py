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

sns = boto3.client('sns')


def message_event(evt):
    dt = datetime.fromtimestamp(evt['timestamp']/1000.0)
    return "%s: %s" % (
        dt.ctime(), "\n".join(textwrap.wrap(evt['message'], 80)))


def process_log_event(event, context):
    """Format log events and relay via sns/email"""

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
