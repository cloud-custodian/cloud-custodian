# Copyright 2020 Cloud Custodian Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from c7n_terraform.parser import (
    HclLocator, TerraformVisitor, Parser)
from .tf_common import data_dir


def test_parser_eof():
    data = Parser().parse_module(data_dir / "aws-s3-bucket")
    path = data_dir / "aws-s3-bucket" / "s3.tf"
    assert path in data
    assert len(data) == 3
    tf_assets = data[path]
    assert list(tf_assets) == ["resource"]
    assert list(tf_assets["resource"][0]) == ["aws_s3_bucket"]


def test_locator():
    locator = HclLocator()
    result = locator.resolve_source(
        data_dir / "aws-s3-bucket" / "s3.tf", ["resource", "aws_s3_bucket", "b"]
    )
    assert result["start"] == 1
    assert result["end"] == 24


def test_visitor():
    path = data_dir / "aws-s3-bucket"
    data = Parser().parse_module(path)
    visitor = TerraformVisitor(data, path)
    visitor.visit()
    blocks = list(visitor.iter_blocks(tf_kind="variable"))
    assert len(blocks) == 1
    myvar = blocks[0]
    assert myvar.name == "mybucket"
    assert myvar.default == "mybucket2"
