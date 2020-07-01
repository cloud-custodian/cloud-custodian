from pathlib import Path
from c7n_terraform.parser import HclLocator, TerraformVisitor, Parser, VariableResolver


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
