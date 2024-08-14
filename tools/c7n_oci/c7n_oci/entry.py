# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

# register OCI provider
from c7n_oci.provider import OCI  # noqa


def initialize_oci():
    import c7n_oci.session  # noqa

    # load the shared filters for all the OCI resources
    import c7n_oci.filters  # noqa

    # load the shared actions for all the OCI resources
    import c7n_oci.actions  # noqa

    # load the option to send output to OCI Object Storage
    import c7n_oci.output  # noqa
