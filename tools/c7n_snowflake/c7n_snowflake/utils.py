# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import inspect
from typing import get_type_hints


def python_type_to_json_type(py_type):

    # this is a union type, likely an optional
    if hasattr(py_type, "__args__") and len(py_type.__args__) > 1:
        py_type = py_type.__args__[0]

    # Map Python types to JSON Schema types
    if py_type in [int]:
        return "integer"
    elif py_type in [float]:
        return "number"
    elif py_type in [str]:
        return "string"
    elif py_type in [bool]:
        return "boolean"
    elif py_type in [list, tuple, set]:
        return "array"
    elif py_type in [dict]:
        return "object"
    else:
        return "string"  # fallback


def class_init_to_jsonschema(cls):
    sig = inspect.signature(cls.__init__)
    hints = get_type_hints(cls.__init__)
    properties = {}
    required = []
    for name, param in list(sig.parameters.items())[1:]:  # skip 'self'
        # skip name as we pass that in via the action directly
        if name == "name":
            continue
        # Get type hint if available, else fallback to string
        py_type = hints.get(name, str)
        json_type = python_type_to_json_type(py_type)
        prop = {"type": json_type}
        if param.default is not inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(name)
        properties[name] = prop
    schema = {"type": "object", "properties": properties, "required": required}
    return schema
