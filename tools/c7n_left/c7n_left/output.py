import time

from c7n.output import OutputRegistry

from rich.console import Console
from rich.syntax import Syntax


report_outputs = OutputRegistry("left")
report_outputs.default_protocol = "cli"


def get_reporter(config):
    return report_outputs.select(None, None)


class PolicyMetadata:
    def __init__(self, policy):
        self.policy = policy

    @property
    def resource_type(self):
        return self.policy.resource_type

    @property
    def provider(self):
        return self.policy.provider_name

    @property
    def name(self):
        return self.policy

    @property
    def description(self):
        return self.policy.data.get("description")

    @property
    def category(self):
        return " ".join(self.policy.data.get("metadata", {}).get("category", []))

    @property
    def severity(self):
        return self.policy.data.get("metadata", {}).get("severity", "")

    @property
    def title(self):
        title = self.policy.data.get("metadata", {}).get("title", "")
        if title:
            return title
        title = f"{self.resource_type} - policy:{self.name}"
        if self.category:
            title += f"category:{self.category}"
        if self.severity:
            title += f"severity:{self.severity}"
        return title


class Output:
    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config

    def on_execution_started(self, policies):
        pass

    def on_execution_ended(self):
        pass

    def on_results(self, results):
        pass


@report_outputs.register("cli")
@report_outputs.register("default")
class RichCli(Output):
    def __init__(self, ctx, config):
        super().__init__(ctx, config)
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


class Github(Output):

    # https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions#setting-an-error-message

    "::error file={name},line={line},endLine={endLine},title={title}::{message}"

    def on_results(self):
        resource = self.policy_resource.resource

        md = PolicyMetadata(self.policy)
        filename = resource.src_dir / resource.filename
        title = md.title
        message = md.description

        print(
            f"::error file={filename} line={resource.line_start} lineEnd={resource.line_end} title={title}::{message}"  # noqa
        )
