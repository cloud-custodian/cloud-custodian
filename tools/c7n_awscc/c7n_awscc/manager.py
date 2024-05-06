# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

from c7n.filters import Filter  # noqa

from .actions import Delete, Update
from .query import CloudControl
from .provider import resources

from c7n.query import TypeInfo, QueryResourceManager


_IndexData = None


def get_index():
    global _IndexData

    if _IndexData is not None:
        return _IndexData

    index_path = Path(__file__).parent / "data" / "index.json"
    _IndexData = json.loads(index_path.read_text(encoding="utf8"))
    return _IndexData


def initialize_resource(resource_name):
    """Load a resource class from its name"""
    rpath = Path(__file__).parent / "data" / f"aws_{resource_name}.json"
    if not rpath.exists():
        return None
    rinfo = json.loads(rpath.read_text(encoding="utf8"))

    type_info = type(
        "resource_type",
        (TypeInfo,),
        dict(
            id=rinfo["primaryIdentifier"][0].split("/", 1)[-1],
            service=rinfo["typeName"].split("::")[1].lower(),
            cfn_type=rinfo["typeName"],
        ),
    )

    rname = "_".join([s.lower() for s in rinfo["typeName"].split("::")[1:]])
    class_name = "".join([s.lower().capitalize() for s in rinfo["typeName"].split("::")[1:]])
    mod_name = f"c7n_awscc.resources.{resource_name}"

    permissions = rinfo.get("handlers", {}).get("read", {}).get("permissions", []) + rinfo.get(
        "handlers", {}
    ).get("list", {}).get("permissions", [])

    rtype = type(
        class_name,
        (QueryResourceManager,),
        dict(
            __module__=mod_name,
            source_mapping={"describe": CloudControl},
            resource_type=type_info,
            permissions=permissions,
            schema=rinfo,
        ),
    )

    rtype.action_registry.register(
        "delete",
        type(
            class_name + "Delete",
            (Delete,),
            {
                "permissions": rinfo["handlers"]["delete"]["permissions"],
                "__module__": mod_name,
            },
        ),
    )

    if "update" in rinfo["handlers"]:
        rtype.action_registry.register(
            "update",
            type(
                class_name + "Update",
                (Update,),
                {
                    "schema": get_update_schema(rtype.schema, rname),
                    "permissions": rinfo["handlers"]["update"]["permissions"],
                    "__module__": mod_name,
                },
            ),
        )

    process_supplementary_data(rtype)
    resources.register(rname, rtype)

    return {rtype.__name__: rtype}


def process_supplementary_data(rtype):
    idx = get_index()
    augment = idx["augment"][rtype.resource_type.cfn_type]
    rtype.resource_type.service = augment.get("service") or ""


def get_update_schema(schema, rname):
    prop_names = set(schema["properties"])
    create_only = {s.rsplit("/", 1)[-1] for s in schema.get("createOnlyProperties", ())}
    read_only = {s.rsplit("/", 1)[-1] for s in schema.get("readOnlyProperties", ())}

    updatable = prop_names - (create_only | read_only)
    update_schema = {
        "additionalProperties": False,
        "properties": {u: schema["properties"][u] for u in updatable},
    }
    update_schema["properties"]["type"] = {"enum": ["update"]}
    update_schema["properties"]["patch"] = {
        # This schema is pretty minimal
        "description": "Json patch to apply to resources",
        "type": "array",
        "items": {
            "type": "object",
            "required": ["op", "path"],
            "properties": {
                "path": {"type": "string"},
                "op": {"enum": ["add", "remove", "update", "replace", "move", "copy", "test"]},
            },
        },
    }

    if "definitions" in schema:
        update_schema["definitions"] = dict(schema["definitions"])
        update_refs(update_schema, rname)

    return update_schema


def update_refs(schema_node, rname):
    for k, v in schema_node.items():
        if k == "$ref" and v.startswith("#/definitions/"):
            # mutating while iterating but there's only ref value ever
            schema_node[k] = "#/definitions/resources/awscc.%s/actions/update/%s" % (
                rname,
                v[2:],
            )
        elif isinstance(v, dict):
            update_refs(v, rname)
