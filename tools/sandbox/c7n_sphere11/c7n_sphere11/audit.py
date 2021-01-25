# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import functools
import time
import os

import boto3
from bottle import request

from c7n.log import Transport

transport = Transport(None, 1, 1, boto3.Session)


def init_audit(log_group):

    def audit(f):

        @functools.wraps(f)
        def handle(account_id, *args, **kw):
            envelope = {
                'timestamp': int(time.time() * 1000),
                'message': json.dumps({
                    'user': request.environ.get('REMOTE_USER', ''),
                    'url': request.url,
                    'path': request.path,
                    'method': request.method,
                    'pid': os.getpid(),
                    'account_id': account_id,
                    'ip': request.remote_addr})
            }
            transport.send_group("%s=%s" % (log_group, account_id), [envelope])
            return f(account_id, *args, **kw)

        return handle

    return audit
