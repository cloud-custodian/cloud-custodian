import contextlib

from c7n.output import tracer_outputs
from rich.console import Console


@tracer_outputs.register("console")
class ConsoleTracer:
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

    @contextlib.contextmanager
    def subsegment(self, name):
        self.stack.append(name)
        try:
            self.console.print(
                f"{self.indent}Begin {self.policy_name} {self.stack[-1]}"
            )
            yield self
        finally:
            self.console.print(
                f"{self.indent}End {self.policy_name} {self.stack.pop(-1)}"
            )

    def __enter__(self):
        """Enter main segment for policy execution."""

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        """Exit main segment for policy execution."""
