"""
Update Custodian Lambda Encrypt versions
"""


import click

from functools import partial

from boto3 import Session
from c7n.credentials import assumed_session
from c7n.mu import LambdaManager
from c7n.ufuncs.s3crypt import get_function


@click.cli()
@click.option('-e/--exec_role', required=True, help="Lambda Execution role")
@click.option('-r/--role', help="Role to assume")
def main(exec_role, role=None):

    if role is None:
        session_factory = Session
    else:
        session_factory = partial(assumed_session, role_arn=role, session_name='s3lambchops')

    manager = LambdaManager(session_factory)
    func = get_function(session_factory, exec_role, False)
    if manager._create_or_update(func):
        print "updated"
    else:
        print "already up to date"

    
if __name__ = '__main__':
    main()
        
