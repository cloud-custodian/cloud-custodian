from pathlib import Path
import sys

import click

from c7n.config import Config
from c7n.data import Data as DataMatcher
from c7n.utils import load_file
from c7n.output import NullTracer

from .core import CollectionRunner
from .output import RichCli, Output
from .utils import load_policies


class TestRunner:
    def __init__(self, policies, options, reporter):
        self.policies = policies
        self.options = options
        self.reporter = reporter
        self.unmatched_policies = set()
        self.unmatched_tests = set()

    def run(self) -> bool:
        policy_tests = self.get_policy_tests()
        for test in policy_tests:
            self.run_test(test)

    def run_test(self, test) -> bool:
        checker = TestChecker(test, self.options)
        runner = CollectionRunner(
            [test.policy],
            self.options.copy(exec_filter=None, source_dir=test.test_dir),
            checker,
        )
        runner.run()

    def get_policy_tests(self):
        policy_map = {p.name: p for p in self.policies}
        test_map = {t.name: t for t in self.get_tests(self.options.source_dir)}

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
        except Exception as e:
            self.reporter.console.print(f"plan file {plan_path} has errors")
            self.reporter.console.print(e)
            raise
        return Test(plan, test_dir)


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

    def check_result(self, result):
        self.plan.match(result)


class TestPlan:
    def __init__(self, plan_data):
        self.data = plan_data
        self.used = set()
        self.initialize_matchers()

    def initialize_matchers(self):
        cfg = Config.empty(session_factory=None, tracer=NullTracer(None), options=None)
        matchers = []
        for match_block in self.data:
            matcher = DataMatcher(cfg, match_block)
            for i in matcher.iter_filters():
                i.annotate = False
            matchers.append(matcher)
        self.matchers = matchers

    def match(self, result):
        for idx, matcher in enumerate(self.matchers):
            if idx in self.used:
                continue
            if matcher.filter_resources([result]):
                self.used.add(idx)


class TestReporter(RichCli):
    pass


class TestChecker(Output):
    def on_execution_started(self, policies, graph):
        print("running tests %d" % len(policies))

    def on_execution_ended(self):
        print("done")

    def on_results(self, results):
        print("results %s" % results)


@click.command()
@click.option("-p", "--policy-dir", type=click.Path(), required=True)
def main(policy_dir):
    policy_dir = Path(policy_dir)
    source_dir = policy_dir / "tests"
    config = Config.empty(
        source_dir=source_dir,
        policy_dir=policy_dir,
        output_file=sys.stdout,
        # output=output,
        # output_file=output_file,
        # output_query=output_query,
        # summary=summary,
        # filters=filters,
    )

    reporter = TestReporter(None, config)
    policies = load_policies(policy_dir, config)
    runner = TestRunner(policies, config, reporter)
    runner.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import pdb
        import traceback

        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
