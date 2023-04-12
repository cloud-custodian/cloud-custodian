import contextlib

from c7n.config import Bag
from c7n.output import tracer_outputs
from c7n.filters import ValueFilter
from rich.console import Console


class SegmentType:
    Policy = "policy"
    Filter = "filter:"
    Action = "action:"
    Unknown = "unknown"


@tracer_outputs.register("console")
class ConsoleTracer:
    colors = {
        SegmentType.Policy: "blue",
        SegmentType.Filter: "yellow",
        SegmentType.Action: "red",
        SegmentType.Unknown: "magenta",
    }

    boolean_blocks = set(("filter:or", "filter:and", "filter:not"))

    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config
        self.console = Console()
        self.stack = []

    @property
    def indent(self):
        return " " * len(self.stack)

    @property
    def policy_name(self):
        return self.ctx.policy.name

    def get_segment_type(self, name):
        if name.startswith(SegmentType.Policy):
            return SegmentType.Policy
        elif name.startswith(SegmentType.Filter):
            return SegmentType.Filter
        elif name.startswith(SegmentType.Action):
            return SegmentType.Action
        return SegmentType.Unknown

    def get_pre_message(self, name, segment_type, color, element, metadata):
        msg = None
        if segment_type == SegmentType.Policy:
            msg = f"{self.indent} [{color}]{self.policy_name}[/{color}] begin {name} on"
            if "resource_count" in metadata:
                msg += f" {metadata['resource_count']} {element.resource_type}"
            else:
                msg += f" {element.resource_type}"
        elif segment_type == SegmentType.Filter and name in self.boolean_blocks:
            msg = f"{self.indent} [{color}]{self.policy_name} [/{color}] begin {name}"
        return msg

    def get_post_message(self, name, segment_type, color, segment):
        msg = f"{name}"
        if segment_type == SegmentType.Policy:
            msg = f"end {name}"
        if segment_type == SegmentType.Filter:
            msg = (
                f"filtered from {segment.metadata.get('count-before', 'na')}"
                f" to {segment.metadata.get('count-after', 'na')}"
            )

            if name in self.boolean_blocks:
                msg = f"end {name} - {msg}"
            else:
                msg = f"[{color}]{name}[/{color}] - {msg}"

            if segment.element and segment.element.__class__ is ValueFilter:
                key = (
                    segment.element.data.get("key")
                    or list(segment.element.data.keys()).pop()
                )
                op = segment.element.data.get("op", "equal")
                msg += f" on key:{key} op:{op}"
        return msg

    def get_color(self, name, segment_type):
        color = self.colors[segment_type]
        if name in self.boolean_blocks:
            color = "gold1"
        return color

    @contextlib.contextmanager
    def subsegment(self, name, element=None, **metadata):
        self.stack.append(Bag({"name": name, "metadata": metadata, "element": element}))
        segment_type = self.get_segment_type(name)
        color = self.get_color(name, segment_type)
        pre_msg = self.get_pre_message(name, segment_type, color, element, metadata)
        if pre_msg:
            self.console.print(pre_msg)
        try:
            yield self.stack[-1]
        finally:
            segment = self.stack[-1]
            post_message = self.get_post_message(name, segment_type, color, segment)
            self.console.print(
                f"{self.indent} [{color}]{self.policy_name}[/{color}] {post_message}"
            )
            self.stack.pop(-1)

    def __enter__(self):
        """Enter main segment for policy execution."""

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        """Exit main segment for policy execution."""
