# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Iterable
import json
import logging
import os
from pathlib import Path
import re

import hcl2


TF_JSON_SUFFIX = ".tf.json"
TF_HCL_SUFFIX = ".tf"


class Block(dict):

    __slots__ = ()

    def __getattr__(self, k):
        return self[k]


class VariableResolver:

    log = logging.getLogger("c7n_terraform.hcl.variable")

    def __init__(self, resolver, value_map=None):
        self.resolver = resolver
        self.value_map = value_map or {}

    def resolve(self):
        for var in self.resolver.iter_blocks(tf_kind="variable"):
            source, value = self.resolve_value(var)
            serialized = Block(var)
            del serialized["source"]["lines"]
            del serialized["data"]
            for block, expr_path, expr in self.get_references(var):
                binding = {
                    "expr_path": expr_path,
                    "source": source,
                    "expr": expr,
                    "var": serialized,
                    "value": value,
                }

                block.setdefault("bindings", []).append(binding)
                # binding = dict(binding)
                # binding.pop('var')
                # binding['data_path'] = block.data_path
                # var.setdefault('bindings', []).append(binding)
                self._set(block, block.bindings[-1])

    def resolve_value(self, var):
        if var.name in self.value_map:
            value = self.value_map[var.name]
            source = "map"
        elif var.env_value:
            value = var.env_value
            source = "env"
        else:
            value = var.default
            source = "default"
        return source, value

    def get_references(self, var):
        regex = self.get_regex(var)
        for block in self.resolver.iter_blocks(path_parent=var.path.parent):
            for ref in self._search(regex, block.data):
                yield (block, *ref)

    def _set(self, block, binding):
        parent = self._traverse(block["data"], binding["expr_path"][:-1])
        part = binding["expr_path"][-1]
        regex = self.get_regex(binding["var"])
        literal = bool(re.match(r"^" + regex.pattern + "$", binding["expr"]))
        parent[part] = (
            binding["value"]
            if literal
            else regex.sub(re.escape(str(binding["value"])), binding["expr"])
        )

    def _traverse(self, data, path):
        cur = data
        for p in path:
            if isinstance(data, dict):
                cur = cur[p]
            elif isinstance(data, list):
                cur[p]
            else:
                return cur
        return cur

    def _search(self, regex, block, path=()):
        path = path is None and [] or path
        tblock = type(block)
        if tblock is dict:
            for k, v in block.items():
                kpath = list(path)
                kpath.append(k)
                for ref in self._search(regex, v, kpath):
                    yield ref
        elif tblock is list:
            for idx, v in enumerate(block):
                kpath = list(path)
                kpath.append(idx)
                for ref in self._search(regex, v, kpath):
                    yield ref
        elif tblock is str:
            if regex.findall(block):
                yield path, block

    def get_regex(self, var):
        regex = r"((?:\$\{)?"
        if var.type == "variable":
            regex += "var[.]" + re.escape(var.name) + r"(?:\})?)"
        if var.type == "local":
            regex += "locals[.]" + re.escape(var.name) + r"(?\})?)"
        return re.compile(regex)


def iterable(obj):
    return isinstance(obj, Iterable)


class HclLocator:

    log = logging.getLogger("c7n_terraform.hcl.locator")

    def __init__(self):
        self.file_cache = {}
        self.line_cache = {}

    def resolve_source(self, path, data_key):
        if path not in self.file_cache:
            self._get_lines(path)

        position = self._block_header_position(path, data_key)
        assert position
        return position

    def _block_header_position(self, path, data_key):
        start_line, end_line = 0, 0
        key_set = set(data_key)
        for cache_idx, (idx, line) in enumerate(self.line_cache[path]):
            tokens = [t.replace('"', "") for t in line.split()]
            if key_set.issubset(tokens):
                start_line = idx
                end_line = self._get_end_line(
                    start_line, cache_idx, self.line_cache[path]
                )
                break

        if not (start_line and end_line):
            return None
        return {
            "start": start_line,
            "end": end_line,
            "lines": self.file_cache[path][start_line - 1:end_line - 1],
        }

    def _get_end_line(self, start_line, cache_idx, lines):
        end_line = start_line
        idx = 1
        s, e = "{", "}"
        if s not in lines[cache_idx][1]:
            s, e = "(", ")"
        for lineno, l in lines[cache_idx + 1:]:
            if s in l:
                idx += 1
            if e in l:
                idx -= 1
                if idx == 0:
                    return lineno
        return end_line

    def _get_lines(self, path):
        with open(path) as fh:
            self.file_cache[path] = [(idx + 1, l) for idx, l in enumerate(fh)]
        lines = []
        for idx, line in self.file_cache[path]:
            line = line.strip()
            if not line:
                continue
            lines.append((idx, line))
        self.line_cache[path] = lines


class TerraformVisitor:

    log = logging.getLogger("c7n_terraform.hcl.visitor")

    def __init__(self, data, root_path):
        self.data = data
        self.root_path = root_path
        self.hcl_locator = HclLocator()
        self.blocks = ()

    def iter_blocks(self, path_parent=None, tf_kind=None, name=None):
        for b in self.blocks:
            if path_parent and b.path.parent != path_parent:
                continue
            if tf_kind and b.type != tf_kind:
                continue
            if name:
                continue
            yield b

    def visit(self):
        # first pass get annotated blocks
        blocks = []
        visitor_map = {
            "data": self.visit_data,
            "variable": self.visit_variable,
            "terraform": self.visit_terraform,
            "module": self.visit_module,
            "output": self.visit_output,
            "locals": self.visit_local,
            "provider": self.visit_provider,
            "resource": self.visit_resource,
        }

        for path, path_data in self.data.items():
            for data_type, data_instances in path_data.items():
                for instance in data_instances:
                    block = visitor_map[data_type](path, instance)
                    if block is None:
                        continue
                    elif isinstance(block, dict):
                        blocks.append(block)
                    elif iterable(block):
                        blocks.extend(block)
        self.blocks = blocks

        # second pass resolve variables

        # yield resolved blocks

    def dump(self, path, sort="type"):
        import json
        import operator

        class PathEncoder(json.JSONEncoder):
            def default(self, o):
                if isinstance(o, Path):
                    return str(o)
                return super().default(o)

        blocks = []
        for b in self.blocks:
            b = dict(b)
            b["path"] = str(b["path"])
            del b["source"]
            blocks.append(b)

        with open(path, "w") as fh:
            print("dump %d blocks path %s" % (len(blocks), path))
            json.dump(
                sorted(blocks, key=operator.itemgetter(sort)),
                cls=PathEncoder,
                indent=2,
                fp=fh,
            )

    def visit_data(self, path, data_block):
        provider_type = next(iter(data_block))
        for name, resource in data_block[provider_type].items():
            data_path = ["data", provider_type, name]
            yield self._block(path, data_block, data_path=data_path)

    def visit_resource(self, path, data_block):
        provider_type = next(iter(data_block))
        for name, resource in data_block[provider_type].items():
            data_path = ["resource", provider_type, name]
            yield Block(
                type="resource",
                provider_type=provider_type,
                name=name,
                path=path,
                data_path=data_path,
                data=resource,
                source=self.hcl_locator.resolve_source(path, data_path),
            )

    def visit_variable(self, path, data_block):
        name = next(iter(data_block))
        default = data_block[name].get("default")
        if default:
            default = default
        data_path = ["variable", name]
        block = Block(
            type="variable",
            name=name,
            path=path,
            data_path=data_path,
            data=data_block,
            source=self.hcl_locator.resolve_source(path, data_path),
            value_type=(
                "type" in data_block[name]
                and data_block[name].get(
                    "type",
                )[0]
                or infer_type(default)
            ),
            default=default,
            env_value=os.environ.get("TF_VAR_%s" % name),
        )

        return block

    def visit_provider(self, path, data_block):
        self.log.debug("provider %s", data_block)
        provider = next(iter(data_block))
        alias = data_block[provider].get("alias", None)
        if alias:
            alias = next(iter(data_block))
        data_path = ["provider", provider]
        return Block(
            type="provider",
            name=alias or provider,
            path=path,
            data_path=data_path,
            data=data_block,
            source=self.hcl_locator.resolve_source(path, data_path),
        )

    def visit_local(self, path, data_block):
        self.log.debug("local %s", data_block)
        data_path = ["local", next(iter(data_block))]
        source = self.hcl_locator.resolve_source(path, data_path[1:])
        return self._block(path, data_block, type="local", source=source)

    def visit_module(self, path, data_block):
        self.log.debug("module %s", data_block)
        return self._block(path, data_block, type="module")

    def visit_terraform(self, path, data_block):
        self.log.debug("terraform %s", data_block)
        data_path = ["terraform", next(iter(data_block))]
        source = self.hcl_locator.resolve_source(path, data_path[:1])
        return self._block(
            path, data_block, data_path=["terraform"], type="terraform", source=source
        )

    def visit_output(self, path, data_block):
        self.log.debug("output %s", data_block)
        return self._block(path, data_block, type="output")

    def _block(self, path, data_block, type=None, data_path=None, source=True, **kw):
        if data_path:
            type = data_path[0]
            name = data_path[-1]
        else:
            name = next(iter(data_block))
            data_path = [type, name]
        if isinstance(source, bool):
            source = self.hcl_locator.resolve_source(path, data_path)

        return Block(
            type=type,
            name=name,
            path=path,
            data_path=data_path,
            data=data_block,
            source=source,
            **kw,
        )


TypeMap = {
    str: "string",
    bool: "bool",
    float: "number",
    int: "number",
    set: "set",
    list: "list",
    dict: "map",
    tuple: "tuple",
    "string": str,
    "bool": bool,
    "number": [float, int],
    "set": set,
    "list": list,
    "map": dict,
    "tuple": tuple,
}


def infer_type(value, default="unknown"):
    return TypeMap.get(type(value), default)


class Parser:

    log = logging.getLogger("c7n_terraform.hcl.parser")

    _parser_map = {
        TF_HCL_SUFFIX: "_parse_hcl_file",
        TF_JSON_SUFFIX: "_parse_json_file",
    }

    def __init__(self):
        self.seen_dirs = set()
        self.errors = {}
        self.tf_resources = {}

    def _parse_hcl_file(self, tf_file):
        with open(tf_file) as fp:
            return self._parse_tf_data(hcl2.load(fp))

    def _parse_json_file(self, tf_file):
        with open(tf_file) as fp:
            return self._parse_tf_json_data(json.load(fp))

    def _parse_tf_json_data(self, data):
        def larkify(instance):
            """Emulate output performed during hcl2.load for JSON loaded data"""
            if isinstance(instance, list):
                return [larkify(el) if isinstance(el, dict) else el for el in instance]

            if isinstance(instance, dict):
                return {k: larkify(v) for k, v in instance.items()}

            return [instance]

        output = {}

        for block in data:
            output[block] = [
                {resource: larkify(instance)} for resource, instance in data.get(block, {}).items()
            ]

        return output

    def _parse_tf_data(self, data):
        for resource_type in data.get("resource", ()):
            for instance_name, instance in resource_type.items():
                # hcl2 parser injects dynamic for computation
                for block in instance.pop("dynamic", ()):
                    for field, value in block.items():
                        instance[field] = value
        return data

    def _resolve_modules(self, path, tf_data):
        for m in tf_data.get("module", ()):
            for module in m.values():
                mpath = (path / module["source"][0]).resolve()
                yield mpath

    def parse_module(self, path, rglob=False):
        directory = Path(path)
        modules = set()
        for pattern in ("*%s" % TF_HCL_SUFFIX, "*%s" % TF_JSON_SUFFIX):
            file_iter = rglob and directory.rglob or directory.glob
            for f in file_iter(pattern):
                self.seen_dirs.add(f.parent)
                try:
                    file_parser = getattr(self, self._parser_map.get(pattern.replace("*", "")))
                    self.tf_resources[f] = tf_data = file_parser(f)
                    modules.update(self._resolve_modules(f.parent, tf_data))
                except Exception as e:
                    self.log.info(f"error parsing {f}", exc_info=e)
                    self.errors[str(f)] = e
        for m in modules:
            if m not in self.seen_dirs:
                self.parse_module(m)
        return self.tf_resources
