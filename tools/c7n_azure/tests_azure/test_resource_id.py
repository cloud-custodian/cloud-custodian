# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .azure_common import BaseTest
from c7n_azure.provider import resources


class ResourceMetaTest(BaseTest):

    def test_resource_id_meta(self):
        missing = []
        for name, resource in resources.items():
            if not getattr(resource.resource_type, 'id', None):
                missing.append(name)

        if missing:
            raise KeyError(
                "Following resources are missing id metadata %s" % " ".join(missing))
