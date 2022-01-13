import json
from pathlib import Path

from c7n.filters import Filter  # noqa
from .actions import Delete, Update
from .query import CloudControl

from c7n.query import TypeInfo, QueryResourceManager


def initialize_resource(resource_name: str) -> dict[str, QueryResourceManager]:
    """Load a resource class from its name"""
    rpath = Path(__file__).parent / "data" / f"aws_{resource_name}.json"
    if not rpath.exists():
        return None
    rinfo = json.loads(rpath.read_text())

    type_info = type(
        "resource_type",
        (TypeInfo,),
        dict(
            id=rinfo["primaryIdentifier"][0].split("/", 1)[-1],
            service=rinfo["typeName"].split("::")[1].lower(),
            cfn_type=rinfo["typeName"],
        ),
    )

    # rname = "-".join([s.lower() for s in rinfo["typeName"].split("::")[1:]])
    class_name = "".join(
        [s.lower().capitalize() for s in rinfo["typeName"].split("::")[1:]]
    )
    mod_name = f"c7n_awscc.resources.{resource_name}"

    rtype = type(
        class_name,
        (QueryResourceManager,),
        dict(
            __module__=mod_name,
            source_mapping={"describe": CloudControl},
            resource_type=type_info,
            permissions=tuple(rinfo["handlers"]["read"]["permissions"])
            + tuple(rinfo["handlers"]["list"]["permissions"]),
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

    rtype.action_registry.register(
        "update",
        type(
            class_name + "Update",
            (Update,),
            {
                "schema": get_update_schema(rtype.schema),
                "permissions": rinfo["handlers"]["update"]["permissions"],
                "__module__": mod_name,
            },
        ),
    )

    return {rtype.__name__: rtype}


def get_update_schema(schema):
    prop_names = set(schema["properties"])
    create_only = {s.rsplit("/", 1)[-1] for s in schema.get("createOnlyProperties", ())}
    read_only = {s.rsplit("/", 1)[-1] for s in schema.get("readOnlyProperties", ())}

    updatable = prop_names - (create_only | read_only)
    update_schema = {
        "additionalProperties": False,
        "definitions": dict(schema["definitions"]),
        "properties": {u: schema["properties"][u] for u in updatable},
    }
    update_schema["properties"]["type"] = {"enum": ["delete"]}
    return update_schema
