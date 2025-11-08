# Copyright 2020 Cloud Custodian Authors
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
from botocore.exceptions import ClientError
from .common import BaseTest


class TestQLDB(BaseTest):

    def test_qldb_describe(self):
        p = self.load_policy({
            'name': 'qldb', 'resource': 'aws.qldb'})
        resources = p.run()
        self.assertEqual(len(resources), 0)
