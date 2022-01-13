from importlib.abc import MetaPathFinder, Loader
from importlib.machinery import ModuleSpec
import os


from .manager import initialize_resource


class ResourceFinder(MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if not fullname.startswith("c7n_awscc.resources."):
            return
        print(f"{fullname} {path} {target}")
        module_attrs = initialize_resource(fullname.rsplit(".", 1)[-1])
        if module_attrs is None:
            return
        return ModuleSpec(
            fullname,
            ResourceLoader(module_attrs),
            origin=path[0] + os.sep + fullname.rsplit(".", 1)[-1] + ".py",
        )


class ResourceLoader(Loader):
    def __init__(self, module_attrs):
        self.module_attrs = module_attrs

    def create_module(self, spec):
        print("create %s" % spec)
        return None

    def exec_module(self, module):
        print("exec %s" % module)
        for k, v in self.module_attrs.items():
            setattr(module, k, v)
