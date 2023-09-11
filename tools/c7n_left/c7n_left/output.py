# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from importlib.metadata import version as pkg_version
import sys
import time
import uuid
import xml.etree.ElementTree as etree

from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .core import CollectionRunner, PolicyMetadata
from .utils import SEVERITY_LEVELS
from c7n.output import OutputRegistry
from c7n.utils import jmespath_search, filter_empty


report_outputs = OutputRegistry("left")


def get_reporter(config):
    for k, v in report_outputs.items():
        if k == config.output:
            return v(None, config)


class Output:
    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config

    def on_execution_started(self, policies, graph):
        pass

    def on_execution_ended(self):
        pass

    def on_results(self, results):
        pass


class RichCli(Output):
    def __init__(self, ctx, config):
        super().__init__(ctx, config)
        self.console = Console(file=config.output_file)
        self.started = None
        self.matches = 0

    def on_execution_started(self, policies, graph):
        self.console.print("Running %d policies on %d resources" % (len(policies), len(graph)))
        self.started = time.time()

    def on_execution_ended(self):
        message = "[green]Success[green]"
        if self.matches:
            message = "[red]%d Failures[/red]" % self.matches
        self.console.print(
            "Evaluation complete %0.2f seconds -> %s" % (time.time() - self.started, message)
        )

    def on_results(self, results):
        for r in results:
            self.console.print(RichResult(r))
        self.matches += len(results)


class RichResult:
    def __init__(self, policy_resource):
        self.policy_resource = policy_resource

    def __rich_console__(self, console, options):
        policy = self.policy_resource.policy
        resource = self.policy_resource.resource

        yield f"[bold]{policy.name}[/bold] - {policy.resource_type}"
        yield "  [red]Failed[/red]"
        if policy.data.get("description"):
            yield f"  [red]Reason: {policy.data['description']}[/red]"
        yield f"  [purple]File: {resource.filename}:{resource.line_start}-{resource.line_end}"

        lines = resource.get_source_lines()
        yield Syntax(
            "\n".join(lines),
            start_line=resource.line_start,
            line_numbers=True,
            lexer=resource.format,
        )
        refs = self.policy_resource.resource.get_references()
        if refs:
            yield "  [yellow]References:"
            for r in refs:
                yield f"   - {r}"
        yield ""


class Summary(Output):
    def __init__(self, ctx, config):
        super().__init__(ctx, config)
        self.console = Console(file=config.output_file)
        self.counter_unevaluated_by_type = {}
        self.counter_resources_by_type = {}
        self.counter_resources_by_policy = {}
        self.counter_policies_by_type = {}
        self.count_policy_matches = 0
        self.count_total_resources = 0
        self.resource_name_matches = set()

    def on_execution_started(self, policies, graph):
        unevaluated = Counter()
        policy_resources = Counter()
        type_counts = Counter()
        type_policies = Counter()

        resource_count = 0

        for rtype, resources in graph.get_resources_by_type():
            resources = self.config.exec_filter.filter_resources(rtype, resources)
            if "_" not in rtype:
                continue
            if not resources:
                continue

            resource_count += len(resources)
            type_counts[rtype] = len(resources)
            for p in policies:
                if not CollectionRunner.match_type(rtype, p):
                    unevaluated[rtype] = len(resources)
                else:
                    type_policies[rtype] += 1
                    policy_resources[p.name] = len(resources)

        self.counter_unevaluated_by_type = unevaluated
        self.counter_resources_by_type = type_counts
        self.counter_resources_by_policy = policy_resources
        self.counter_policies_by_type = type_policies
        self.count_total_resources = resource_count

    def on_results(self, results):
        for r in results:
            self.count_policy_matches += 1
            self.resource_name_matches.add(r.resource.name)

    def on_execution_ended(self):
        unevaluated = sum(
            [
                v
                for k, v in self.counter_unevaluated_by_type.items()
                if k not in set(self.counter_policies_by_type)
            ]
        )
        compliant = self.count_total_resources - len(self.resource_name_matches) - unevaluated
        msg = "%d compliant of %d total" % (compliant, self.count_total_resources)
        if self.resource_name_matches:
            msg += ", %d resources have %d policy violations" % (
                len(self.resource_name_matches),
                self.count_policy_matches,
            )

        if unevaluated:
            msg += ", %d resources unevaluated" % (unevaluated)
        self.console.print(msg)


severity_colors = {
    "critical": "red",
    "high": "yellow",
    "medium": "green_yellow",
    "low": "violet",
    "unknown": "grey42",
}


def severity_key(a):
    return SEVERITY_LEVELS.get(a.severity.lower(), SEVERITY_LEVELS["unknown"])


def get_severity_color(policy):
    severity = policy.severity.lower()
    if severity not in severity_colors:
        severity = "unknown"
    style = severity_colors.get(severity)
    return severity, style


class SummaryPolicy(Summary):
    def __init__(self, ctx, config):
        super().__init__(ctx, config)
        self.counter_policy_matches = Counter()
        self.policies = []

    def on_execution_started(self, policies, graph):
        super().on_execution_started(policies, graph)
        self.policies = sorted(map(PolicyMetadata, policies), key=severity_key)

    def on_results(self, results):
        super().on_results(results)
        for r in results:
            self.counter_policy_matches[r.policy.name] += 1

    def on_execution_ended(self):
        table = Table(title="Summary - By Policy")
        table.add_column("Severity")
        table.add_column("Policy")
        table.add_column("Result")

        for p in self.policies:
            severity, style = get_severity_color(p)
            total = self.counter_resources_by_policy[p.name]
            failed = self.counter_policy_matches.get(p.name, 0)
            passed = total - failed

            if failed:
                msg_result = "[red]%d[/red] failed [green]%d[/green] passed" % (
                    failed,
                    passed,
                )
            elif not passed:
                continue
            else:
                msg_result = "[green]%d[/green] passed" % passed

            table.add_row(Text(severity, style=style), Text(p.name), msg_result)
        self.console.print(table)
        super().on_execution_ended()


class SummaryResource(Summary):
    def __init__(self, ctx, config):
        super().__init__(ctx, config)
        self.policies = {}
        self.resource_policy_matches = {}

    def on_execution_started(self, policies, graph):
        super().on_execution_started(policies, graph)
        self.policies = {p.name: p for p in sorted(map(PolicyMetadata, policies), key=severity_key)}

    def on_results(self, results):
        super().on_results(results)
        for r in results:
            self.resource_policy_matches.setdefault(r.resource.name, []).append(r)

    def on_execution_ended(self):
        table = Table(title="Summary - By Resource")
        table.add_column("type")
        table.add_column("count")
        table.add_column("policies")
        table.add_column("evaluations")

        rtypes = {n.split(".", 1)[0] for n in self.counter_resources_by_type}

        for rtype in sorted(rtypes):
            if "_" not in rtype:
                continue
            prefix = "%s." % rtype
            rmatches = [r for r in self.resource_policy_matches if r.startswith(prefix)]

            pcount = self.counter_policies_by_type[rtype]
            pcount_style = pcount and "gray" or "red"

            eval_ok = self.counter_resources_by_type[rtype] - len(rmatches)
            eval_fail = len(rmatches)

            if pcount and eval_fail:
                eval_msg = "[red]%d[/red] failed [green]%d[/green] passed" % (
                    eval_fail,
                    eval_ok,
                )
            elif pcount:
                eval_msg = "[green]%d[/green] passed" % eval_ok
            else:
                eval_msg = "na"
            table.add_row(
                rtype,
                "%s" % self.counter_resources_by_type[rtype],
                Text(str(pcount), style=pcount_style),
                eval_msg,
            )
        self.console.print(table)
        super().on_execution_ended()


summary_options = {"policy": SummaryPolicy, "resource": SummaryResource}


class MultiOutput:
    def __init__(self, outputs):
        self.outputs = outputs

    def on_execution_started(self, policies, graph):
        for o in self.outputs:
            o.on_execution_started(policies, graph)

    def on_execution_ended(self):
        for o in self.outputs:
            o.on_execution_ended()

    def on_results(self, results):
        for o in self.outputs:
            o.on_results(results)


class GithubFormat(Output):
    # https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions#setting-an-error-message

    def on_results(self, results):
        for r in results:
            print(self.format_result(r), file=self.config.output_file)

    def format_result(self, result):
        resource = result.resource

        md = PolicyMetadata(result.policy)
        filename = resource.src_dir / resource.filename
        title = md.title
        message = md.description or md.title

        return f"::error file={filename},line={resource.line_start},lineEnd={resource.line_end},title={title}::{message}"  # noqa


@report_outputs.register("cli")
class RichMulti(MultiOutput):
    def __init__(self, ctx, config):
        summary = summary_options[config.summary](ctx, config)
        super().__init__([RichCli(ctx, config), summary])


@report_outputs.register("github")
class GithubOutput(MultiOutput):
    "For github action execution we want both line annotation and cli outputs"

    def __init__(self, ctx, config):
        super().__init__([GithubFormat(ctx, config), RichMulti(ctx, config)])


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        # Match all the types you want to handle in your converter
        if isinstance(obj, Path):
            return str(obj)
        return super().default(obj)


@report_outputs.register("json")
class Json(Output):
    def __init__(self, ctx, config):
        super().__init__(ctx, config)
        self.results = []

    def on_results(self, results):
        self.results.extend(results)

    def on_execution_ended(self):
        formatted_results = [self.format_result(r) for r in self.results]
        if self.config.output_query:
            formatted_results = jmespath_search(self.config.output_query, formatted_results)
        self.config.output_file.write(
            json.dumps({"results": formatted_results}, cls=JSONEncoder, indent=2)
        )

    def format_result(self, result):
        resource = result.resource

        lines = resource.get_source_lines()
        line_pairs = []
        index = resource.line_start
        for l in lines:
            line_pairs.append((index, l))
            index += 1

        formatted = result.as_dict()
        formatted["code_block"] = line_pairs
        return formatted


class JunitReport(Output):
    suite_name = "c7n-left"

    SCHEMA_FILE = (
        "https://raw.githubusercontent.com/windyroad/JUnit-Schema/master/JUnit.xsd"  # noqa
    )

    def __init__(self, ctx, config):
        super().__init__(ctx, config)
        self.results = []
        self.start_time = None

    def on_results(self, results):
        self.results.extend(results)

    def on_execution_started(self, policies, graph):
        self.start_time = datetime.utcnow()
        self.policies = {p.name: p for p in sorted(map(PolicyMetadata, policies), key=severity_key)}

    def on_execution_ended(self):
        builder = etree.TreeBuilder()
        builder.start("testsuites", {})
        builder.start(
            "testsuite",
            {
                "name": self.suite_name,
                "tests": str(len(self.policies)),
                "time": "%0.2f" % (datetime.utcnow() - self.start_time).total_seconds(),
                "failures": str(len(self.results)),
            },
        )
        [self.format_result(r, builder) for r in self.results]
        doc = builder.close()
        self.config.output_file.write(etree.tostring(doc).decode("utf8"))

    def format_result(self, result, builder):
        md = self.policies[result.policy.name]
        resource = result.resource
        file_path = resource.src_dir / resource.filename
        builder.start(
            "testcase",
            {
                "name": md.title,
                "classname": "%s.%s" % (str(file_path), resource.id),
                "file": str(file_path),
            },
        )
        text_data = []
        lines = resource.get_source_lines()
        line_idx = resource.line_start
        for l in lines:
            text_data.append("%d | %s" % (line_idx, l))
            line_idx += 1
        builder.data("\n".join(text_data))
        builder.end("testcase")


@report_outputs.register("junit")
class Junit(MultiOutput):
    def __init__(self, ctx, config):
        if config.output_file.isatty() is False:
            parts = [RichCli(ctx, config.copy(output_file=sys.stdout)), JunitReport(ctx, config)]
        else:
            parts = [JunitReport(ctx, config)]
        super().__init__(parts)


@report_outputs.register("gitlab_sast")
class GitlabSAST(Output):
    SCHEMA_FILE = "https://gitlab.com/gitlab-org/security-products/security-report-schemas/-/raw/v15.0.6/dist/sast-report-format.json"  # noqa

    def __init__(self, ctx, config):
        super().__init__(ctx, config)
        self.results = []
        self.start_time = None

    def on_results(self, results):
        self.results.extend(results)

    def on_execution_started(self, *args):
        self.start_time = datetime.utcnow().replace(microsecond=0)

    def on_execution_ended(self):
        formatted_results = [self.format_result(r) for r in self.results]

        self.config.output_file.write(
            json.dumps(
                {
                    "schema": self.SCHEMA_FILE,
                    "version": "15.0.6",
                    "scan": {
                        "type": "sast",
                        "status": "success",
                        "start_time": self.start_time.isoformat(),
                        "end_time": datetime.utcnow().replace(microsecond=0).isoformat(),
                        "analyzer": self.get_analyzer(),
                        "scanner": self.get_scanner(),
                    },
                    "vulnerabilities": formatted_results,
                },
                cls=JSONEncoder,
                indent=2,
            )
        )

    def format_result(self, result):
        md = PolicyMetadata(result.policy)
        info = result.as_dict()
        return dict(
            id=str(uuid.uuid4()),
            name=md.name,
            description=md.description,
            severity=md.severity.title(),
            identifiers=[
                filter_empty(dict(name=md.name, type="sinistral", value=md.name, url=md.url))
            ],
            location={
                "file": info["file_path"],
                "start": info["file_line_start"],
                "end": info["file_line_end"],
            },
        )

    def get_scanner(self):
        info = self.get_analyzer()
        info["url"] = "https://cloudcustodian.io"
        return info

    def get_analyzer(self):
        return {
            "id": "c7n-left",
            "name": "c7n-left",
            "version": pkg_version("c7n-left"),
            "vendor": {"name": "Cloud Custodian"},
        }
