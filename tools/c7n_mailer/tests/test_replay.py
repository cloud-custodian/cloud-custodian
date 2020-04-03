# -*- coding: utf-8 -*-
import argparse
import unittest
from c7n_mailer import replay

class ReplayTests(unittest.TestCase):
    
    def test_parser_creation(self):
        parser = replay.setup_parser()
        self.assertIs(parser.__class__, argparse.ArgumentParser)