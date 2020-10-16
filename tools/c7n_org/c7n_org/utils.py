# Copyright 2017 Capital One Services, LLC
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import os
from c7n.utils import reset_session_cache
from contextlib import contextmanager


def account_tags(account):
    tags = {'AccountName': account['name'], 'AccountId': account['account_id']}
    for t in account.get('tags', ()):
        if ':' not in t:
            continue
        parts = t.split(':')
        key = 'Account{}'.format("".join([e.capitalize() for e in parts[:-1]]))
        value = parts[-1]

        tags[key] = value
    return tags


@contextmanager
def environ(**kw):
    current_env = dict(os.environ)
    for k, v in kw.items():
        os.environ[k] = v

    try:
        yield os.environ
    finally:
        for k in kw.keys():
            del os.environ[k]
        os.environ.update(current_env)
        reset_session_cache()
