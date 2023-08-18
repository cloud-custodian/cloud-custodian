# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import importlib
from urllib import parse as urlparse


def join_output(output_dir, suffix):
    if "{region}" in output_dir:
        return output_dir.rstrip("/")
    if output_dir.endswith("://"):
        return output_dir + suffix
    output_url_parts = urlparse.urlparse(output_dir)
    # for output urls, the end of the url may be a
    # query string. make sure we add a suffix to
    # the path component.
    output_url_parts = output_url_parts._replace(
        path=output_url_parts.path.rstrip("/") + "/%s" % suffix
    )
    return urlparse.urlunparse(output_url_parts)


def spec_version():
    return importlib.metadata.version("c7n_oci")
