# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

"""Stubs for oci urllib3"""

from oci._vendor.urllib3.connectionpool import HTTPConnection, VerifiedHTTPSConnection
from oci.base_client import OCIConnection, OCIConnectionPool

from vcr.stubs import VCRHTTPConnection, VCRHTTPSConnection


class VCRRequestsHTTPConnection(VCRHTTPConnection, HTTPConnection):
    _baseclass = HTTPConnection


class VCRRequestsHTTPSConnection(VCRHTTPSConnection, VerifiedHTTPSConnection):
    _baseclass = VerifiedHTTPSConnection


class VCROCIConnection(VCRRequestsHTTPSConnection):
    _baseclass = OCIConnection


class VCROCIConnectionPool(OCIConnectionPool):
    _baseclass = OCIConnectionPool
