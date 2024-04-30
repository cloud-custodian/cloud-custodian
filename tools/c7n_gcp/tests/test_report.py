# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from c7n.resources import load_resources
from gcp_common import BaseTest

from c7n_gcp.provider import GoogleCloud


class ReportMetadataTests(BaseTest):

    def test_report_metadata(self):
        load_resources(('gcp.*',))

        missing = set()
        for k, v in GoogleCloud.resources.items():
            if not v.resource_type.id:
                missing.add("%s~%s" % (k, v))
            if not v.resource_type.name:
                missing.add("%s~%s" % (k, v))
            if not v.resource_type.default_report_fields:
                missing.add("%s~%s" % (k, v))

        if missing:
            raise AssertionError("Missing report metadata on \n %s" % (' \n'.join(sorted(missing))))
