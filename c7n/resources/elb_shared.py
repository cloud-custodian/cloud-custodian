# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.utils import local_session
from c7n.resources.vpc import SGPermission
from c7n.filters import Filter

class AdvancedIpPermissionsFilter(Filter):
    # Can be overwritten by Child-Classes
    permissions_key = None

    def process(self, resources, event=None):
        f = SGPermission(data = self.data, manager = self.manager)
        f. ip_permissions_key = self.permissions_key
        ec2 = local_session(self.manager.session_factory).client('ec2')
        lbs = []
        for r in resources:
            if 'SecurityGroups' in r:
                sgs = ec2.describe_security_groups(
                    GroupIds=r['SecurityGroups']
                )
                filtered_sgs = f.process(sgs['SecurityGroups'])
                if len(filtered_sgs) > 0:
                    lbs.append(r)
        return lbs
