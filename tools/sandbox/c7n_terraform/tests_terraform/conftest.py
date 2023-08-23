# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest

from .tf_common import data_dir, build_visitor


@pytest.fixture()
def aws_complete():
    return build_visitor(data_dir / "aws-complete")


@pytest.fixture()
def aws_s3_bucket():
    return build_visitor(data_dir / "aws-s3-bucket")
