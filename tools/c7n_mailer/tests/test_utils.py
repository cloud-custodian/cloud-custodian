# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import unittest

from c7n_mailer import utils


class FormatStruct(unittest.TestCase):

    def test_formats_struct(self):
        expected = '{\n  "foo": "bar"\n}'
        actual = utils.format_struct({'foo': 'bar'})
        self.assertEqual(expected, actual)
