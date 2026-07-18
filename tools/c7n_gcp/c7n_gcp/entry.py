# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

# register provider
import c7n_gcp.provider # noqa

# squelch inconsiderate logging
logging.getLogger('googleapiclient.discovery').setLevel(logging.WARNING)


# ruff: noqa
def initialize_gcp():
    """Load gcp provider"""

    # register execution modes
    import c7n_gcp.policy

    # load shared registered resources
    import c7n_gcp.actions
    import c7n_gcp.output
