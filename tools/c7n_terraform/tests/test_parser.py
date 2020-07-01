import jmespath
import tempfile
from pathlib import Path
from c7n_terraform.parser import HclLocator, TerraformVisitor, Parser, VariableResolver

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
