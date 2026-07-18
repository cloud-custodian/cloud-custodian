# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from c7n_azure.provider import Azure

from c7n.config import Bag, Config
from c7n.ctx import ExecutionContext
from c7n.resources import load_resources

from .azure_common import BaseTest


class ReportMetadataTests(BaseTest):

    def test_report_metadata(self):
        load_resources(('azure.*',))
        ctx = ExecutionContext(None, Bag(), Config.empty())
        missing = set()
        for k, v in Azure.resources.items():
            model = v(ctx, Config.empty()).get_model()
            if not getattr(model, "id", None):
                missing.add("%s~%s" % (k, v))
            if not getattr(model, "name", None):
                missing.add("%s~%s" % (k, v))
            if not hasattr(model, "default_report_fields"):
                missing.add("%s~%s" % (k, v))

        if missing:
            raise AssertionError("Missing report metadata on \n %s" % (' \n'.join(sorted(missing))))
