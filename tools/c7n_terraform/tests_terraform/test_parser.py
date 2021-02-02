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

import json
import functools

from c7n_terraform.parser import (
    HclLocator, TerraformVisitor, Parser, VariableResolver)
from .tf_common import data_dir, build_visitor


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


def test_variable_resolver(aws_s3_bucket):

    resource_blocks = list(aws_s3_bucket.iter_blocks(tf_kind="resource"))
    assert len(resource_blocks) == 1
    resource = resource_blocks[0]

    assert 'bindings' in resource
    bindings = resource['bindings']
    assert len(bindings) == 1
    binding = bindings[0]

    variable_blocks = list(aws_s3_bucket.iter_blocks(tf_kind="variable"))
    assert len(variable_blocks) == 1
    variable = variable_blocks[0]

    assert binding['expr_path'] == ['bucket', 0]
    assert binding['source'] == 'default'
    assert binding['expr'] == '${var.mybucket}'
    assert binding['var']['path'] == variable['path']
    assert binding['var']['default'] == variable['default']
    assert binding['var']['type'] == variable['type']
    assert binding['var']['value_type'] == variable['value_type']


def test_variable_resolver_value_map():
    variable_resolver = functools.partial(VariableResolver, value_map={"mybucket": "mybucket3"})
    visitor = build_visitor(data_dir / "aws-s3-bucket", resolver=variable_resolver)

    blocks = list(visitor.iter_blocks(tf_kind="resource"))
    assert len(blocks) == 1
    assert blocks[0]['data']['bucket'] == ['mybucket3']


def test_visitor_dump(aws_s3_bucket, tmpdir):
    visitor_json = tmpdir.join('dump.json')
    aws_s3_bucket.dump(visitor_json)

    with open(visitor_json) as f:
        json.load(f)


def test_visitor_provider(aws_complete):
    providers = list(aws_complete.iter_blocks(tf_kind="provider"))
    assert len(providers) == 1
    assert providers[0].name == "aws"


def test_visitor_module(aws_complete):
    blocks = list(aws_complete.iter_blocks(tf_kind="module"))
    assert len(blocks) == 1
    assert blocks[0].name == "atlantis"


def test_visitor_terraform(aws_complete):
    blocks = list(aws_complete.iter_blocks(tf_kind="terraform"))
    assert len(blocks) == 1
    assert blocks[0].name == "terraform"
