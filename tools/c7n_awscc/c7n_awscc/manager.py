import json
from pathlib import Path

from c7n.resources import QueryResourceManager
from c7n.query import TypeInfo
from .query import CloudControl


def initialize_resource(resource_name: str) -> dict[str, QueryResourceManager]:
    """Load a resource class from its name"""
    rpath = Path(__file__).parent / "data" / f"{resource_name}.json"
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
    rtype = type(
        "".join([s.lower().capitalize() for s in rinfo["typeName"].split("::")[1:]]),
        (QueryResourceManager,),
        dict(
            source_mapping={"describe": CloudControl},
            resource_type=type_info,
            permissions=tuple(rinfo["handlers"]["read"])
            + tuple(rinfo["handlers"]["list"]),
        ),
    )

    return {rtype.__name__: rtype}
