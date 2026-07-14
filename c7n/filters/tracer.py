"""Filter match tracing - second-pass per-resource trace of a filter tree.

Normal c7n filter evaluation runs first (unchanged). After matched resources
are identified, call attach_traces(filters, resources) to walk the filter tree
per-resource and attach a detailed match trace as ``c7n:MatchTrace`` on each
resource dict.
"""

MATCH_TRACE_KEY = "c7n:MatchTrace"
MATCH_TRACE_SUMMARY_KEY = "c7n:MatchTraceSummary"

_MARK = {True: "⊤", False: "⊥", None: "?"}  # logical true / false / unknown


def trace_filter(f, resource):
    """Recursively trace a single filter against one resource.

    Returns a dict describing the node's type, matched status, and -- for
    composite filters -- the children's individual trace nodes.

    `matched` is:
    - True / False when the filter was successfully evaluated per-resource
    - None when the filter cannot be evaluated per-resource (bulk-only)
    """
    from c7n.filters.core import Or, And, Not, ValueFilter

    if isinstance(f, Not):
        children = [trace_filter(c, resource) for c in f.filters]
        # NOT uses implicit-AND semantics: the whole NOT block matches when
        # the inner AND of its children is False (i.e. at least one child is
        # False). We compute the inner AND across non-None children.
        truthy = [c["matched"] for c in children if c["matched"] is not None]
        inner_matched = all(truthy) if truthy else True
        matched = not inner_matched
        return {"type": "not", "matched": matched, "children": children}

    if isinstance(f, Or):
        children = [trace_filter(c, resource) for c in f.filters]
        matched = any(c["matched"] for c in children if c["matched"] is not None)
        return {"type": "or", "matched": matched, "children": children}

    if isinstance(f, And):
        children = [trace_filter(c, resource) for c in f.filters]
        truthy = [c["matched"] for c in children if c["matched"] is not None]
        matched = all(truthy) if truthy else True
        return {"type": "and", "matched": matched, "children": children}

    if isinstance(f, ValueFilter):
        # Calling match() is idempotent -- content_initialized flag ensures
        # f.k/op/v are set on first call and frozen thereafter.
        matched = f.match(resource)
        # Retrieve the actual resource value using the already-initialised key.
        if f.k is not None:
            actual = f.get_resource_value(f.k, resource)
        else:
            actual = None
        return {
            "type": "value",
            "key": f.k,
            "op": f.op,
            "expected": f.v,
            "actual": actual,
            "value_type": getattr(f, "vtype", None),  # may be None for simple equality checks
            "matched": matched,
        }

    # Unknown / custom filter - attempt per-resource call.
    try:
        result = f(resource)
        return {"type": type(f).__name__, "matched": result}
    except Exception:
        # Bulk-only filters (e.g. resource_count) cannot be evaluated per
        # resource. Use matched=None so callers can distinguish "didn't
        # match" from "couldn't evaluate".
        return {
            "type": type(f).__name__,
            "matched": None,
            "reason": "non-per-resource filter",
        }


def format_trace(trace):
    """Render a trace_filter() node as a single human-readable expression.

    Composite nodes render as ``MARK TYPE(child, child, ...)``; value nodes
    render as ``MARK key op expected -> actual``. MARK is one of ✓ / ✗ / ?
    for matched True / False / None.
    """
    mark = _MARK[trace["matched"]]
    node_type = trace["type"]

    if node_type in ("and", "or", "not"):
        children = ", ".join(format_trace(c) for c in trace["children"])
        return f"{mark} {node_type.upper()}({children})"

    if node_type == "value":
        op = trace["op"] or "eq"
        return f"{mark} {trace['key']} {op} {trace['expected']!r} -> {trace['actual']!r}"

    return f"{mark} {node_type}"


def attach_traces(filters, resources):
    """Attach a match trace to each resource in *resources*.

    For each resource a top-level list of trace nodes (one per top-level
    filter) is computed by calling trace_filter on every filter and stored
    under the ``c7n:MatchTrace`` key directly on the resource dict. A
    condensed, human-readable rendering of the same traces (one string per
    top-level filter, via format_trace) is stored under
    ``c7n:MatchTraceSummary``.

    This function has no return value; it mutates the resource dicts in place.
    """
    for resource in resources:
        traces = [trace_filter(f, resource) for f in filters]
        resource[MATCH_TRACE_KEY] = traces
        resource[MATCH_TRACE_SUMMARY_KEY] = [format_trace(t) for t in traces]
