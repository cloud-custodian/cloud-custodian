# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import sys
import json
from os.path import dirname, join

# The working path for the Azure Function doesn't include this file's folder
sys.path.append(dirname(dirname(__file__)))

from c7n_mailer.azure_mailer import handle


def main(input):
    logger = logging.getLogger("custodian.mailer")
    config_file = join(dirname(__file__), "config.json")
    with open(config_file) as fh:
        config = json.load(fh)
    return handle.start_c7n_mailer(logger, config, join(dirname(__file__), "auth.json"))


# flake8: noqa
