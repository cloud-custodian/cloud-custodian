# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import json
import time

from c7n.output import OutputRegistry

from rich.console import Console
from rich.syntax import Syntax


report_outputs = OutputRegistry("left")


def get_reporter(config):
    for k, v in report_outputs.items():
        if k == config.output:
            return v(None, config)


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
        return self.policy.name

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
class RichCli(Output):
    def __init__(self, ctx, config):
        super().__init__(ctx, config)
        self.console = Console(file=config.output_file)
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


@report_outputs.register("github")
class Github(Output):

    # https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions#setting-an-error-message

    "::error file={name},line={line},endLine={endLine},title={title}::{message}"

    def on_results(self, results):
        for r in results:
            print(self.format_result(r), file=self.config.output_file)

    def format_result(self, result):
        resource = result.resource

        md = PolicyMetadata(result.policy)
        filename = resource.src_dir / resource.filename
        title = md.title
        message = md.description or ""

        return f"::error file={filename} line={resource.line_start} lineEnd={resource.line_end} title={title}::{message}"  # noqa


@report_outputs.register("json")
class Json(Output):
    def __init__(self, ctx, config):
        super().__init__(ctx, config)
        self.results = []

    def on_results(self, results):
        self.results.extend(results)

    def on_execution_ended(self):
        formatted_results = [self.format_result(r) for r in self.results]
        self.config.output_file.write(
            json.dumps({"results": formatted_results}, indent=2)
        )

    def format_result(self, result):
        resource = result.resource

        lines = resource.get_source_lines()
        line_pairs = []
        index = resource.line_start
        for l in lines:
            line_pairs.append((index, l))
            index += 1

        return {
            "policy": dict(result.policy.data),
            "file_path": str(resource.src_dir / resource.filename),
            "file_line_start": resource.line_start,
            "file_line_end": resource.line_end,
            "code_block": line_pairs,
        }
