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
from __future__ import print_function

import os
import logging
import pprint
import sys

from c7n.utils import format_event
from c7n.resources import load_resources

import app
import wsgigw

logging.root.setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)


load_resources()


def debug(event, context):
    print(sys.executable)
    print(sys.version)
    print(sys.path)
    pprint.pprint(os.environ)
    print(format_event(event))


def lambda_handler(event, context=None):

    # Periodic
    if event.get('detail-type') == 'Scheduled Event':
        debug(event, context)
        return app.on_timer(event)

    # SNS / Dynamodb / Kinesis
    elif event.get('Records'):
        records = event['Records']
        if records and records[0]['EventSource'] == 'aws:sns':
            return app.on_config_message(records)
        else:
            return debug(event, context)
    elif not event.get('path'):
        return debug(event, context)

    # API Gateway
    if app.config.get('sentry-dsn'):
        from raven import Client
        from raven.contrib.bottle import Sentry
        client = Client(app.config['sentry-dsn'])
        app.app.catchall = False
        wrapped_app = Sentry(app.app, client)
    else:
        wrapped_app = app.app

    return wsgigw.invoke(wrapped_app, event)
