# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest, load_data
from c7n.config import Config, Bag
from c7n import manager, resources
import fnmatch


class TestIamGen(BaseTest):

    def check_permissions(self, perm_db, perm_set, path):
        invalid = []
        for p in perm_set:
            if ':' not in p:
                invalid.append(p)
                continue
            s, a = p.split(':', 1)
            if s not in perm_db:
                invalid.append(p)
                continue
            if '*' in a:
                if not fnmatch.filter(perm_db[s], a):
                    invalid.append(p)
                    continue
            elif a not in perm_db[s]:
                invalid.append(p)
        if not invalid:
            return []
        return [(path, invalid)]

    def test_iam_permissions_validity(self):
        cfg = Config.empty()
        missing = set()
        invalid = []

        perms = load_data('iam-actions.json')
        resources.load_available()

        for k, v in manager.resources.items():
            p = Bag({'name': 'permcheck', 'resource': k, 'provider_name': 'aws'})
            ctx = self.get_context(config=cfg, policy=p)
            mgr = v(ctx, p)
            # if getattr(mgr, 'permissions', None):
            #    print(mgr)

            found = False
            for s in (mgr.resource_type.service,
                      getattr(mgr.resource_type, 'permission_prefix', None)):
                if s in perms:
                    found = True
            if not found:
                missing.add("%s->%s|%s" % (
                    k, mgr.resource_type.service,
                    mgr.resource_type.permission_prefix))
                continue
            invalid.extend(self.check_permissions(perms, mgr.get_permissions(), k))

            for n, a in v.action_registry.items():
                p['actions'] = [n]
                invalid.extend(
                    self.check_permissions(
                        perms, a({}, mgr).get_permissions(),
                        "{k}.actions.{n}".format(k=k, n=n)))

            for n, f in v.filter_registry.items():
                if n in ('or', 'and', 'not', 'missing'):
                    continue
                p['filters'] = [n]
                invalid.extend(
                    self.check_permissions(
                        perms, f({}, mgr).get_permissions(),
                        "{k}.filters.{n}".format(k=k, n=n)))

        if missing:
            raise ValueError(
                "resources missing service %s" % ('\n'.join(sorted(missing))))

        if invalid:
            raise ValueError(
                "invalid permissions \n %s" % ('\n'.join(sorted(map(str, invalid)))))
