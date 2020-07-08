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

import os
from pathlib import Path

from c7n_terraform.parser import TerraformVisitor, Parser, VariableResolver


data_dir = Path(__file__).parent / "data"


def setup_tf(tmp_path, file_map=None):
    file_map = file_map or {}
    for k, v in file_map.items():
        with open(os.path.join(tmp_path, k), "w") as fh:
            fh.write(v)

    data = Parser().parse_module(Path(str(tmp_path)))
    visitor = TerraformVisitor(data, tmp_path)
    visitor.visit()
    resolver = VariableResolver(visitor)
    resolver.resolve()
    return visitor
