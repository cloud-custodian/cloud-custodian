# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json

import re
import redis

try:
    import sqlite3
except ImportError:
    have_sqlite = False
else:
    have_sqlite = True
from ldap3 import Connection
from ldap3.core.exceptions import LDAPSocketOpenError


class LdapLookup:

    def __init__(self, config, logger):
        self.log = logger
        self.connection = self.get_connection(
            config.get('ldap_uri'),
            config.get('ldap_bind_user', None),
            config.get('ldap_bind_password', None)
        )
        self.base_dn = config.get('ldap_bind_dn')
        self.email_key = config.get('ldap_email_key', 'mail')
        self.manager_attr = config.get('ldap_manager_attribute', 'manager')
        self.uid_key = config.get('ldap_uid_attribute', 'sAMAccountName')
        self.attributes = ['displayName', self.uid_key, self.email_key, self.manager_attr]
        self.uid_regex = config.get('ldap_uid_regex', None)
        self.cache_engine = config.get('cache_engine', None)
        if self.cache_engine == 'redis':
            redis_host = config.get('redis_host')
            redis_port = int(config.get('redis_port', 6379))
            self.caching = self.get_redis_connection(redis_host, redis_port)
        elif self.cache_engine == 'sqlite':
            if not have_sqlite:
                raise RuntimeError('No sqlite available: stackoverflow.com/q/44058239')
            self.caching = LocalSqlite(config.get('ldap_cache_file', '/var/tmp/ldap.cache'), logger)

    def get_redis_connection(self, redis_host, redis_port):
        return Redis(redis_host=redis_host, redis_port=redis_port, db=0)

    def get_connection(self, ldap_uri, ldap_bind_user, ldap_bind_password):
        # note, if ldap_bind_user and ldap_bind_password are None
        # an anonymous bind will be attempted.
        try:
            return Connection(
                ldap_uri, user=ldap_bind_user, password=ldap_bind_password,
                auto_bind=True,
                receive_timeout=30,
                auto_referrals=False,
            )
        except LDAPSocketOpenError:
            self.log.error('Not able to establish a connection with LDAP.')

    def search_ldap(self, base_dn, ldap_filter, attributes):
        self.connection.search(base_dn, ldap_filter, attributes=self.attributes)
        if len(self.connection.entries) == 0:
            self.log.warning("user not found. base_dn: %s filter: %s", base_dn, ldap_filter)
            return {}
        if len(self.connection.entries) > 1:
            self.log.warning("too many results for search %s", ldap_filter)
            return {}
        return self.connection.entries[0]

    def get_email_to_addrs_from_uid(self, uid, manager=False):
        to_addrs = []
        uid_metadata = self.get_metadata_from_uid(uid)
        uid_email = uid_metadata.get(self.email_key, None)
        if uid_email:
            to_addrs.append(uid_email)
        if manager:
            uid_manager_dn = uid_metadata.get(self.manager_attr, None)
            uid_manager_email = None
            if uid_manager_dn:
                uid_manager = self.get_metadata_from_dn(uid_manager_dn)
                uid_manager_email = uid_manager.get('mail')
            if uid_manager_email:
                to_addrs.append(uid_manager_email)
        return to_addrs

    # eg, dn = uid=bill_lumbergh,cn=users,dc=initech,dc=com
    def get_metadata_from_dn(self, user_dn):
        if self.cache_engine:
            cache_result = self.caching.get(user_dn)
            if cache_result:
                cache_msg = 'Got ldap metadata from local cache for: %s' % user_dn
                self.log.debug(cache_msg)
                return cache_result
        ldap_filter = '(%s=*)' % self.uid_key
        ldap_results = self.search_ldap(user_dn, ldap_filter, attributes=self.attributes)
        if ldap_results:
            ldap_user_metadata = self.get_dict_from_ldap_object(self.connection.entries[0])
        else:
            self.caching.set(user_dn, {})
            return {}
        if self.cache_engine:
            self.log.debug('Writing user: %s metadata to cache engine.' % user_dn)
            self.caching.set(user_dn, ldap_user_metadata)
            self.caching.set(ldap_user_metadata[self.uid_key], ldap_user_metadata)
        return ldap_user_metadata

    def get_dict_from_ldap_object(self, ldap_user_object):
        ldap_user_metadata = {attr.key: attr.value for attr in ldap_user_object}
        ldap_user_metadata['dn'] = ldap_user_object.entry_dn

        email_key = ldap_user_metadata.get(self.email_key, None)
        uid_key = ldap_user_metadata.get(self.uid_key, None)

        if not email_key or not uid_key:
            return {}
        else:
            ldap_user_metadata['self.email_key'] = email_key.lower()
            ldap_user_metadata['self.uid_key'] = uid_key.lower()

        return ldap_user_metadata

    # eg, uid = bill_lumbergh
    def get_metadata_from_uid(self, uid):
        uid = uid.lower()
        if self.uid_regex:
            # for example if you set ldap_uid_regex in your mailer.yml to "^[0-9]{6}$" then it
            # would only query LDAP if your string length is 6 characters long and only digits.
            # re.search("^[0-9]{6}$", "123456")
            # Out[41]: <_sre.SRE_Match at 0x1109ab440>
            # re.search("^[0-9]{6}$", "1234567") returns None, or "12345a' also returns None
            if not re.search(self.uid_regex, uid):
                regex_msg = 'uid does not match regex: %s %s' % (self.uid_regex, uid)
                self.log.debug(regex_msg)
                return {}
        if self.cache_engine:
            cache_result = self.caching.get(uid)
            if cache_result or cache_result == {}:
                cache_msg = 'Got ldap metadata from local cache for: %s' % uid
                self.log.debug(cache_msg)
                return cache_result
        ldap_filter = '(%s=%s)' % (self.uid_key, uid)
        ldap_results = self.search_ldap(self.base_dn, ldap_filter, attributes=self.attributes)
        if ldap_results:
            ldap_user_metadata = self.get_dict_from_ldap_object(self.connection.entries[0])
            if self.cache_engine:
                self.log.debug('Writing user: %s metadata to cache engine.' % uid)
                if ldap_user_metadata.get('dn'):
                    self.caching.set(ldap_user_metadata['dn'], ldap_user_metadata)
                    self.caching.set(uid, ldap_user_metadata)
                else:
                    self.caching.set(uid, {})
        else:
            if self.cache_engine:
                self.caching.set(uid, {})
            return {}
        return ldap_user_metadata


# Use sqlite as a local cache for folks not running the mailer in lambda, avoids extra daemons
# as dependencies. This normalizes the methods to set/get functions, so you can interchangeable
# decide which caching system to use, a local file, or memcache, redis, etc
# If you don't want a redis dependency and aren't running the mailer in lambda this works well
class LocalSqlite:
    def __init__(self, local_filename, logger):
        self.log = logger
        self.sqlite = sqlite3.connect(local_filename)
        self.sqlite.execute('''CREATE TABLE IF NOT EXISTS ldap_cache(key text, value text)''')

    def get(self, key):
        sqlite_result = self.sqlite.execute("select * FROM ldap_cache WHERE key=?", (key,))
        result = sqlite_result.fetchall()
        if len(result) != 1:
            error_msg = 'Did not get 1 result from sqlite, something went wrong with key: %s' % key
            self.log.error(error_msg)
            return None
        return json.loads(result[0][1])

    def set(self, key, value):
        # note, the ? marks are required to ensure escaping into the database.
        self.sqlite.execute("INSERT INTO ldap_cache VALUES (?, ?)", (key, json.dumps(value)))
        self.sqlite.commit()


# redis can't write complex python objects like dictionaries as values (the way memcache can)
# so we turn our dict into a json string when setting, and json.loads when getting
class Redis:
    def __init__(self, redis_host=None, redis_port=6379, db=0):
        self.connection = redis.StrictRedis(host=redis_host, port=redis_port, db=db)

    def get(self, key):
        cache_value = self.connection.get(key)
        if cache_value:
            return json.loads(cache_value)

    def set(self, key, value):
        return self.connection.set(key, json.dumps(value))
