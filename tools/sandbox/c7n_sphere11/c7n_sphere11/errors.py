# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


class Sphere11Exception(Exception):
    pass


class AccountNotFound(Sphere11Exception):
    """The account specified is unknown."""


class UnknownResourceType(Sphere11Exception):
    """The resource type is not supported."""


class ResourceNotFound(Sphere11Exception):
    """The specified resource does not exist."""
