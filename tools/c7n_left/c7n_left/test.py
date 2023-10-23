# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import operator
import time

from c7n.config import Config
from c7n.data import Data as DataMatcher
from c7n.utils import load_file
from c7n.output import NullTracer

from .core import CollectionRunner
from .output import RichCli, Output


class TestRunner:
    def __init__(self, policies, options, reporter):
        self.policies = policies
        self.options = options
        self.reporter = reporter
        self.unmatched_policies = set()
        self.unmatched_tests = set()

    def run(self) -> bool:
        policy_tests = self.get_policy_tests()
        self.reporter.on_tests_discovered(self, policy_tests)
        for test in sorted(policy_tests, key=operator.attrgetter("name")):
            self.run_test(test)
            self.reporter.on_test_result(test)
        self.reporter.on_tests_complete()
        return bool(self.reporter.failures)

    def run_test(self, test) -> bool:
        checker = TestChecker(test, self.options)
        runner = CollectionRunner(
            [test.policy],
            self.options.copy(
                exec_filter=self.options.get("exec_filter"), source_dir=test.test_dir
            ),
            checker,
        )
        runner.run()

    def get_policy_tests(self):
        policy_map = {p.name: p for p in self.policies}
        test_map = {t.name: t for t in self.get_tests(self.options.source_dir) if t}

        self.unmatched_policies = set(policy_map).difference(test_map)
        self.unmatched_tests = set(test_map).difference(policy_map)

        matched = set(policy_map).intersection(test_map)
        for name in matched:
            test_map[name].set_policy(policy_map[name])
        return [test_map[name] for name in matched]

    def get_tests(self, source_dir):
        tests = []
        for test_dir in source_dir.iterdir():
            if not test_dir.is_dir():
                continue

            plan_candidates = [
                test_dir / "left.plan.json",
                test_dir / "left.plan.yaml",
                test_dir / "left.plan.yml",
            ]

            for c in plan_candidates:
                if not c.exists():
                    continue
                tests.append(self.load_plan(test_dir, c))

        return tests

    def load_plan(self, test_dir, plan_path):
        try:
            plan = load_file(plan_path)
            return Test(plan, test_dir)
        except Exception as e:
            self.reporter.on_test_load_error(plan_path, e)


class Test:
    def __init__(self, plan_data, test_dir):
        self.plan = TestPlan(plan_data)
        self.test_dir = test_dir
        self.policy = None

    @property
    def name(self):
        return self.test_dir.name

    def set_policy(self, policy):
        self.policy = policy

    def check_execution_result(self, result):
        self.plan.match(result)

    def get_test_result(self):
        result = self.plan.get_test_result()
        result["name"] = self.name
        return result


class TestPlan:
    def __init__(self, plan_data):
        self.data = plan_data
        self.used = set()
        self.matchers = []
        self.unmatched = []
        self.initialize_matchers()

    def get_test_result(self):
        return {
            "success": len(self.used) == len(self.matchers) and not self.unmatched,
            "stat_checks": len(self.matchers),
            "stat_used": len(self.used),
            "stat_unmatched": len(self.unmatched),
            "unmatched": self.unmatched,
            "unused": [t for idx, t in enumerate(self.data) if idx not in self.used],
        }

    def initialize_matchers(self):
        cfg = Config.empty(session_factory=None, tracer=NullTracer(None), options=None)
        matchers = []
        for match_block in self.data:
            matcher = DataMatcher(cfg, {"filters": [{k: v} for k, v in match_block.items()]})
            for i in matcher.iter_filters():
                i.annotate = False
            matchers.append(matcher)
        self.matchers = matchers

    def match(self, result):
        found = False
        for idx, matcher in enumerate(self.matchers):
            if idx in self.used:
                continue
            if matcher.filter_resources([result.as_dict()]):
                self.used.add(idx)
                found = True
                break
        if found is False:
            self.unmatched.append(result.as_dict())


class TestReporter(RichCli):
    def __init__(self, ctx, config):
        super().__init__(ctx, config)
        self.start_time = time.time()
        self.failures = 0
        self.total = 0

    def on_tests_discovered(self, runner, tests):
        header = f"Discovered {len(tests)} Tests"
        if runner.unmatched_policies:
            header += f" - {len(runner.unmatched_policies)}/{len(runner.policies)}"
            header += " Policies Untested"
        if runner.unmatched_tests and not self.config.get("filters"):
            header += f" - [red]{len(runner.unmatched_tests)} Unused Tests"
        self.console.print(header)
        if self.config.get("verbose", True) and not self.config.get("filters"):
            for p in runner.unmatched_policies:
                self.console.print(f"no test for {p}")
            for t in runner.unmatched_tests:
                self.console.print(f"no policy for {t}")

    def on_tests_complete(self):
        status = f"{self.total} "
        status += self.total > 1 and "Tests" or "Test"
        status += " Complete (%0.2fs)" % (time.time() - self.start_time)
        if self.failures:
            status += f" [red]{self.failures} "
            status += self.failures > 1 and "Failures" or "Failure"
            status += "[/red]"
        self.console.print(status)

    def on_test_load_error(self, test_path, error):
        self.console.print(f"[yellow]test load error[yellow] {test_path} - {error}")

    def on_test_result(self, test: Test):
        self.total += 1
        result = test.get_test_result()
        if result["success"]:
            status = f"[green]Success[/green] {result['name']}"
            status += f" - {result['stat_checks']} checks"
            self.console.print(status)
            return

        self.failures += 1
        status = f"[red]Failure[/red] {result['name']}"
        if result["stat_unmatched"]:
            status += f" - {result['stat_unmatched']} findings unmatched"
        if result["unused"]:
            status += f" - {len(result['unused'])} Checks not used"
        self.console.print(status)
        if result["unused"]:
            self.console.print("Unused Checks")
            for u in result["unused"]:
                self.console.print(u)

        if result["unmatched"]:
            self.console.print("Unmatched Findings")
            for unmatched in result["unmatched"]:
                unmatched = dict(unmatched)
                unmatched.pop("policy")
                self.console.print(unmatched)
        self.console.print("")


class TestChecker(Output):
    def on_results(self, policy, results):
        for r in results:
            self.ctx.check_execution_result(r)
