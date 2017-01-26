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
import logging
import os
from ldap3 import (
    Connection,
    Server,
)
from ldap3.core.exceptions import LDAPSocketOpenError


log = logging.getLogger('custodian.ldap')

CONN = None


def get_connection(ldap_uri, bind_user, bind_password):
    if not (bind_user and bind_password):
        if 'SSO_USER' in os.environ:
            bind_user = os.environ['SSO_USER']
            bind_password = os.environ['SSO_PASS']
        else:
            raise ValueError("missing ldap credentials")
    server = Server(ldap_uri)
    try:
        conn = Connection(
            server, user=bind_user, password=bind_password,
            auto_bind=True,
            receive_timeout=30,
            auto_referrals=False,
        )
    except LDAPSocketOpenError:
        conn = None
    return conn


def get_user(eid, bind_user=None, bind_password=None,
             manager=True, ldap_uri=None, base_dn=None):

    global CONN
    if CONN is None:
        CONN = get_connection(ldap_uri, bind_user, bind_password)

    if CONN is None:
        fallback = "blackhole@example.com"
        log.exception("LDAP Bind Failure! - falling back to %s" % fallback)
        return {'mail': fallback}

    # https://github.com/Trietptm-on-Security/powertools-1/blob/master/Get-User/Get-User.ps1
    # mostly standard active directory stuff, we should make this configurable i suppose
    attributes = [
        'businessUnitDesc', 'displayName',
        'mail', 'department']

    if manager:
        attributes.append('manager')

    query = '(sAMAccountName={0})'.format(eid)
    CONN.search(base_dn, query, attributes=attributes)
    if len(CONN.entries) == 0:
        log.warning("userid not found %s", eid)
        return None
    if len(CONN.entries) > 1:
        log.warning("too many results for search %s", query)
        return None

    entry = CONN.entries[0]
    info = {attr.key: attr.value for attr in entry}

    if manager:
        manager_eid = info['manager'].split(',', 1)[0].split('=')[1]
        manager = get_user(manager_eid, manager=False)
        if manager is not None:
            info['manager_email'] = manager['mail']
            info['manager_name'] = manager['displayName']
        info.pop('manager')
    return info
