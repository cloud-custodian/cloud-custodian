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
