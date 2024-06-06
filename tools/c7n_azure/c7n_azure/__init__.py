# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import warnings

import adal

# two azure packages seem to have this issue on invalid escape
# sequence on their generated code w/ python 3.12
# (azure.mgmt.resource, azure.mgmt.resourcgraph)
warnings.filterwarnings("ignore", category=SyntaxWarning)


# Quiet logging from dependencies
adal.set_logging_options({'level': 'WARNING'})
logging.getLogger("msrest").setLevel(logging.ERROR)
logging.getLogger("keyring").setLevel(logging.WARNING)
logging.getLogger("azure.storage.common.storageclient").setLevel(logging.WARNING)
logging.getLogger("azure.cosmosdb.table.common.storageclient").setLevel(logging.WARNING)

# This logger is spamming INFO with a bunch of requests data
logging.getLogger('azure.identity').setLevel(logging.WARNING)
logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)
