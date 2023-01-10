# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest

from c7n.config import Config
from c7n.schema import generate
from c7n.testing import CustodianTestCore


class BaseTest(CustodianTestCore):

    def addCleanup(self, func, *args, **kw):
        pass

    custodian_schema = generate()

    @property
    def account_id(self):
        return "100000750436"

    @pytest.fixture(autouse=True)
    def init(self, vcr):
        if vcr:
            self.recording = len(vcr.data) == 0
        else:
            self.recording = True

    def load_policy(self, data, *args, **kw):
        if "config" not in kw:
            config = Config.empty(**{
                "region": kw.pop("region", "ap-singapore"),
                "account_id": kw.pop('account_id', "100000750436"),
                "output_dir": "null://",
                "log_group": "null://",
                "cache": False,
            })
            kw['config'] = config
        if 'account_id' in kw:
            kw.pop('account_id')
        return super().load_policy(data, *args, **kw)
