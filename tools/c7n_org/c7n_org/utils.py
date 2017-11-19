import os
from contextlib import contextmanager

def account_tags(account):
    tags = {'AccountName': account['name'], 'AccountId': account['account_id']}
    for t in account.get('tags'):
        if not ':' in t:
            continue
        k, v = t.split(':', 1)
        k = 'Account%s' % k.capitalize()
        tags[k] = v
    return tags

@contextmanager
def environ(**kw):
    current_env = dict(os.environ)
    for k, v in kw.items():
        os.environ[k] = v
    yield os.environ

    for k in kw.keys():
        del os.environ[k]
    os.environ.update(current_env)

