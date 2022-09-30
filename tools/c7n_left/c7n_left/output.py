import time

from c7n.output import OutputRegistry

from rich.console import Console
from rich.syntax import Syntax


report_outputs = OutputRegistry("left")
report_outputs.default_protocol = "rich"


def get_reporter(config):
    return report_outputs.select(None, None)


@report_outputs.register("rich")
@report_outputs.register("default")
class RichCli:
    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config
        self.console = Console()
        self.started = None

    def on_execution_started(self, policies):
        self.console.print("Running %d policies" % (len(policies),))
        self.started = time.time()

    def on_execution_ended(self):
        self.console.print(
            "Execution complete %0.2f seconds" % (time.time() - self.started)
        )

    def on_results(self, results):
        for r in results:
            self.console.print(RichResult(r))

    def report(self, results):
        self.console.print(results)


class RichResult:
    def __init__(self, policy_resource):
        self.policy_resource = policy_resource

    def __rich_console__(self, console, options):
        policy = self.policy_resource.policy
        resource = self.policy_resource.resource

        yield f"[bold]{policy.name}[/bold] - {policy.resource_type}"
        yield "  [red]Failed[/red]"
        yield f"  [purple]File: {resource.filename}:{resource.line_start}-{resource.line_end}"

        lines = resource.get_source_lines()
        yield Syntax(
            "\n".join(lines),
            start_line=resource.line_start,
            line_numbers=True,
            lexer=resource.format,
        )
        yield ""
