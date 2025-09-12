# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import unittest

from common import get_ldap_lookup, PETER, BILL
from c7n_mailer.ldap_lookup import have_sqlite


SKIP_REASON = "Azure Pipelines still broken"


class MailerLdapTest(unittest.TestCase):
    def setUp(self):
        if not have_sqlite:
            return
        self.ldap_lookup = get_ldap_lookup(cache_engine="sqlite")

    def test_sqlite_cached_get_mail(self):
        michael_bolton = self.ldap_lookup.caching.get("michael_bolton")
        self.assertEqual(michael_bolton.get("mail"), "michael_bolton@initech.com")

    def test_regex_requiring_underscore(self):
        self.ldap_lookup.uid_regex = "_"
        michael_bolton = self.ldap_lookup.get_metadata_from_uid("michael_bolton")
        # since michael_bolton has an underscore, it should pass regex and return a result
        self.assertEqual(michael_bolton.get("mail"), "michael_bolton@initech.com")
        milton = self.ldap_lookup.get_metadata_from_uid("123456")
        # since '123456' doesn't have an underscore, it should return {}
        self.assertEqual(milton, {})

    def test_sqlite_cache_set_escaping(self):
        irish_guy = {
            "dn": "uid=john_oconnor,cn=users,dc=initech,dc=com",
            "mail": "john_oconnor@initech.com",
            "manager": "uid=bill_lumbergh,cn=users,dc=initech,dc=com",
            "displayName": "John O'Connor",
            "uid": "john_oconnor",
        }
        set_result = self.ldap_lookup.caching.set(irish_guy["uid"], irish_guy)
        self.assertEqual(set_result, None)
        get_result = self.ldap_lookup.caching.get(irish_guy["uid"])
        self.assertEqual(get_result, irish_guy)

    def test_regex_requiring_6chars_and_only_digits(self):
        # now we'll do some tests requiring the uid to be 6 characters only and digits
        self.ldap_lookup.uid_regex = "^[0-9]{6}$"
        milton = self.ldap_lookup.get_metadata_from_uid("123456")
        milton_email = milton.get("mail")
        self.assertEqual(milton_email, "milton@initech.com")

    def test_sqlite_cached_get_email_to_addr_without_manager(self):
        to_addr = self.ldap_lookup.get_email_to_addrs_from_uid("michael_bolton")
        self.assertEqual(to_addr, ["michael_bolton@initech.com"])

    def test_sqlite_cached_get_email_to_addrs_with_manager(self):
        to_addr = self.ldap_lookup.get_email_to_addrs_from_uid("michael_bolton", manager=True)
        self.assertEqual(to_addr, ["michael_bolton@initech.com", "milton@initech.com"])

    def test_uid_ldap_lookup(self):
        ldap_result = self.ldap_lookup.get_metadata_from_uid("peter")
        self.assertEqual(ldap_result["mail"], PETER[1]["mail"][0])
        self.assertEqual(ldap_result["uid"], PETER[1]["uid"][0])
        # make sure it set a value in the cache as well.
        cached_result = self.ldap_lookup.caching.get("peter")
        self.assertEqual(cached_result["mail"], PETER[1]["mail"][0])
        self.assertEqual(cached_result["uid"], PETER[1]["uid"][0])

    def test_dn_ldap_lookup(self):
        bill_metadata = self.ldap_lookup.get_metadata_from_dn(BILL[0])
        self.assertEqual(bill_metadata["mail"], BILL[1]["mail"][0])

    def test_to_addr_with_ldap_query(self):
        to_addr = self.ldap_lookup.get_email_to_addrs_from_uid("peter", manager=True)
        self.assertEqual(to_addr, ["peter@initech.com", "bill_lumberg@initech.com"])

    def test_that_dn_and_uid_write_to_cache_on_manager_lookup(self):
        bill_metadata = self.ldap_lookup.get_metadata_from_dn(BILL[0])
        bill_metadata_dn_lookup_cache = self.ldap_lookup.caching.get(BILL[0])
        self.assertEqual(bill_metadata, bill_metadata_dn_lookup_cache)
        bill_metadata_uid_lookup_cache = self.ldap_lookup.caching.get(BILL[1]["uid"][0])
        self.assertEqual(bill_metadata, bill_metadata_uid_lookup_cache)

    def test_that_dn_and_uid_write_to_cache_on_employee_lookup(self):
        peter_uid = PETER[1]["uid"][0]
        peter_metadata = self.ldap_lookup.get_metadata_from_uid(peter_uid)
        peter_metadata_dn_lookup_cache = self.ldap_lookup.caching.get(PETER[0])
        peter_metadata_uid_lookup_cache = self.ldap_lookup.caching.get(peter_uid)
        self.assertEqual(peter_metadata, peter_metadata_uid_lookup_cache)
        self.assertEqual(peter_metadata, peter_metadata_dn_lookup_cache)

    def test_random_string_dont_hit_ldap_twice_uid_lookup(self):
        # if we query ldap and get no result, we should never query ldap again
        # for that result, we should query the cache and just return {}
        to_addr = self.ldap_lookup.get_email_to_addrs_from_uid("doesnotexist", manager=True)
        self.assertEqual(to_addr, [])
        self.ldap_lookup.connection = None
        to_addr = self.ldap_lookup.get_email_to_addrs_from_uid("doesnotexist", manager=True)
        self.assertEqual(to_addr, [])
