
from common import BaseTest, Bag, Config

from c7n.manager import resources


class PolicyPermissions(BaseTest):

    def test_action_permissions(self):
        self.capture_logging('c7n.cache')
        missing = []
        cfg = Config.empty()
        for k, v in resources.items():
            self.assertTrue(v.get_permissions())

            p = Bag({'name': 'permcheck', 'resource': k})
            ctx = self.get_context(config=cfg, policy=p)

            mgr = v(ctx, p)
            perms = mgr.get_permissions()
            if not perms:
                missing.append(k)

            for n, a in v.action_registry.items():
                p['actions'] = [n]
                perms = a({}, mgr).get_permissions()
                found = bool(perms)
                if not isinstance(perms, (list, tuple, set)):
                    found = False

                if not found:
                    missing.append("%s.actions.%s" % (
                        k, n))

            for n, f in v.filter_registry.items():
                if n in ('and', 'or'):
                    continue
                p['filters'] = [n]
                perms = f({}, mgr).get_permissions()
                if not isinstance(perms, (tuple, list, set)):
                    missing.append("%s.filters.%s" % (
                        k, n))

        if missing:
            self.fail("Missing permissions %d on \n\t%s" % (
                len(missing),
                "\n\t".join(sorted(missing))))


