# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import unittest

from c7n.resources import load_resources
from c7n.schema import resource_vocabulary
from c7n_sphinxext.c7n_schema import CustodianDirective, CustodianSchema


load_resources()


class SchemaDirectiveTest(unittest.TestCase):

    CustodianDirective.vocabulary = resource_vocabulary()

    def test_schema_resolver(self):
        self.assertTrue(CustodianSchema.resolve('mode.periodic'))
        self.assertTrue(CustodianSchema.resolve('aws.ec2.actions.stop'))
        self.assertEqual(CustodianSchema.resolve('aws.ec2').type, 'ec2')


if __name__ == '__main__':
    unittest.main()
