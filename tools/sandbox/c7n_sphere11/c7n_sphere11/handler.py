# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
