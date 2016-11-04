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

# python ldap rhel 7.2 compile deps
# yum install -y gcc openssl-devel openldap-devel
# pip install python-ldap

import ldap
import logging
import os


log = logging.getLogger('custodian.ldap')

CONN = None


def get_connection(ldap_uri, bind_user, bind_password):
    conn = ldap.initialize(ldap_uri)
    conn.set_option(ldap.OPT_REFERRALS, 0)
    conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 30)
    conn.protocol_version = 3

    if not (bind_user and bind_password):
        if 'SSO_USER' in os.environ:
            bind_user = os.environ['SSO_USER']
            bind_password = os.environ['SSO_PASS']
        else:
            raise ValueError("missing ldap credentials")
    try:
        result = conn.simple_bind_s(bind_user, bind_password)
    except ldap.SERVER_DOWN:
        return None

    return conn


def get_user(eid, bind_user=None, bind_password=None,
             manager=True, ldap_uri=None, base_dn=None):

    assert ldap_uri and base_dn, "Ldap config required"
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

    query = 'sAMAccountName={0}'.format(eid)
    ldap_result_id = CONN.search(
        base_dn, ldap.SCOPE_SUBTREE, query, attributes)
    ok, results = CONN.result(ldap_result_id, 0)
    if ok != ldap.RES_SEARCH_ENTRY:
        log.warning("userid not found %s" % (eid))
        return None

    cn, info = results[0]
    info = {k: v[0] for k, v in info.items()}

    if manager:
        manager_eid = info['manager'].split(',', 1)[0].split('=')[1]
        manager = get_user(manager_eid, manager=False)
        info['manager_email'] = manager['mail']
        info['manager_name'] = manager['displayName']
        info.pop('manager')
    return info
