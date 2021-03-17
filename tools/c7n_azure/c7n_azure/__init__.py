# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging

import adal

# Quiet logging from dependencies
adal.set_logging_options({'level': 'WARNING'})
logging.getLogger("msrest").setLevel(logging.ERROR)
logging.getLogger("keyring").setLevel(logging.WARNING)
logging.getLogger("azure.storage.common.storageclient").setLevel(logging.WARNING)
