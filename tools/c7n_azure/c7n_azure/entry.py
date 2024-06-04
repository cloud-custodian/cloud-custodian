# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

# two azure packages seem to have this issue on invalid escape
# sequence on their generated code w/ python 3.12
# (azure.mgmt.resource, azure.mgmt.resourcgraph)
import warnings
warnings.filterwarnings("ignore", "SyntaxWarning")

# register provider
from c7n_azure.provider import Azure  # NOQA


def initialize_azure():
    # import execution modes
    import c7n_azure.policy
    import c7n_azure.container_host.modes
    import c7n_azure.output # noqa
