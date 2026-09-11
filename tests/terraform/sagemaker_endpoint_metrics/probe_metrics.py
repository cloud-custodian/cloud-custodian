"""Check sagemaker_metrics.yaml against what these endpoints really publish.

Run against the endpoints this terraform module creates, with credentials
for the account they live in:

    terraform apply
    AWS_DEFAULT_REGION=us-east-1 uv run tests/terraform/sagemaker_endpoint_metrics/probe_metrics.py

Everything goes to standard output. Use --no-invoke to skip generating
traffic when the endpoints have been invoked within the metric window.

--- Updating c7n/data/sagemaker_metrics.yaml ---

For an agent asked to bring the catalogue up to date. Two sources, and
they answer different questions.

The documentation is the only source of metric *names* and namespaces:

    https://docs.aws.amazon.com/sagemaker/latest/dg/monitoring-cloudwatch.html

Fetch it as markdown -- the same URL with .md instead of .html serves the
tables without the page chrome. Each metric table becomes a section whose
`title` is the table's caption; the namespace is stated in the prose above
the table, not in it. Add metrics the page has gained, remove ones it has
dropped, and keep each section's metric list in the page's order so the two
can be read side by side.

This script is the only source of *dimension sets* and of `endpoint-kinds`.
Do not take the page's dimensions tables literally: they list the dimensions
a metric can be filtered by, and CloudWatch identifies a series by an exact
set of dimensions. Instance type, for example, is documented as
"EndpointName, VariantName, InstanceType" but is only ever published
alongside AvailabilityZone and Region, so a query on the documented three
returns nothing.

So, for dimensions:

  - List only sets this script reports as carrying data.
  - Never add a set because the page lists it.
  - Never add a set this script found but the page doesn't mention: those
    exist, but c7n has no way to supply an AvailabilityZone or a Region.

And for endpoint-kinds, `classic` means a model is attached to each
production variant, `inference-component` means the configuration carries an
execution role and models arrive as components. A section's metrics belong
to the kinds this script saw publishing them.

The script cannot see everything. It reports which catalogue entries it
could not check -- metrics no endpoint here publishes, such as the GPU
metrics with no GPU instance in the account, and the multi-model metrics
with no multi-model endpoint. Those entries stay as they are, and their
`endpoint-kinds` remain reasoning by analogy with the metrics that were
checked. Say so in a comment rather than implying they were measured.
"""

import argparse
import collections
import datetime
import time

import boto3

from c7n.resources.sagemaker import SAGEMAKER_METRICS_BY_KIND

PREFIX = 'c7n-endpoint-metrics-'

NAMESPACES = (
    'AWS/SageMaker',
    '/aws/sagemaker/Endpoints',
    '/aws/sagemaker/InferenceComponents',
    )


def endpoint_kind(sagemaker, endpoint: dict) -> str:
    """Which way this endpoint hosts its models.

    The rule the SageMaker SDK uses: an execution role on the
    configuration and no production variant naming a model.
    """
    config = sagemaker.describe_endpoint_config(
        EndpointConfigName=endpoint['EndpointConfigName'])
    if config.get('ExecutionRoleArn') and not any(
            'ModelName' in variant for variant in config['ProductionVariants']):
        return 'inference-component'
    return 'classic'


def find_endpoints(sagemaker) -> list[dict]:
    endpoints = []
    for page in sagemaker.get_paginator('list_endpoints').paginate():
        for summary in page['Endpoints']:
            if summary['EndpointName'].startswith(PREFIX):
                endpoint = sagemaker.describe_endpoint(
                    EndpointName=summary['EndpointName'])
                endpoint['kind'] = endpoint_kind(sagemaker, endpoint)
                endpoints.append(endpoint)
    return endpoints


def find_components(sagemaker) -> dict[str, list[str]]:
    components = collections.defaultdict(list)
    for page in sagemaker.get_paginator(
            'list_inference_components').paginate():
        for summary in page['InferenceComponents']:
            components[summary['EndpointName']].append(
                summary['InferenceComponentName'])
    return components


def invoke(runtime, endpoints, components, count: int) -> None:
    """Invoke one variant of each classic endpoint, and each component.

    A variant named "quiet" is left alone: a variant that is never invoked
    still publishes zeros, which is worth seeing.
    """
    for endpoint in endpoints:
        name = endpoint['EndpointName']
        targets = [
            dict(InferenceComponentName=component)
            for component in components.get(name, ())
            ] or [
            dict(TargetVariant=variant['VariantName'])
            for variant in endpoint['ProductionVariants']
            if variant['VariantName'] != 'quiet'
            ]
        for target in targets:
            for _ in range(count):
                runtime.invoke_endpoint(
                    EndpointName=name, ContentType='text/csv',
                    Body=b'0.5\n', **target)
            print(f"  invoked {name} {count}x {target}")


def observed(cloudwatch, names: set[str]) -> dict:
    """What CloudWatch reports for our resources.

    {(namespace, resource name): {metric name: {dimension name set}}},
    where the resource name is the endpoint or component named in the
    metric's dimensions.
    """
    seen: dict = collections.defaultdict(
        lambda: collections.defaultdict(set))
    for namespace in NAMESPACES:
        for page in cloudwatch.get_paginator('list_metrics').paginate(
                Namespace=namespace):
            for metric in page['Metrics']:
                name_set = tuple(sorted(d['Name'] for d in metric['Dimensions']))
                for dimension in metric['Dimensions']:
                    if dimension['Value'] in names:
                        seen[namespace, dimension['Value']][
                            metric['MetricName']].add(name_set)
    return seen


def fill(name_set: list[str], endpoint: dict, component: str | None) -> list[list[dict]]:
    """The dimensions to query for one resource, or [] if we can't supply them."""
    if name_set == ['EndpointName', 'VariantName']:
        return [
            [{'Name': 'EndpointName', 'Value': endpoint['EndpointName']},
             {'Name': 'VariantName', 'Value': variant['VariantName']}]
            for variant in endpoint['ProductionVariants']
            ]
    if name_set == ['InferenceComponentName'] and component:
        return [[{'Name': 'InferenceComponentName', 'Value': component}]]
    return []


def has_points(cloudwatch, namespace: str, metric: str, dimensions,
               window) -> bool:
    start, end = window
    return bool(cloudwatch.get_metric_statistics(
        Namespace=namespace, MetricName=metric, StartTime=start, EndTime=end,
        Period=300, Statistics=['Sum'], Dimensions=dimensions)['Datapoints'])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--no-invoke', action='store_true',
                        help="don't generate traffic first")
    parser.add_argument('--count', type=int, default=30,
                        help='invocations per target (default 30)')
    parser.add_argument('--wait', type=int, default=300,
                        help='seconds to wait for publication (default 300)')
    parser.add_argument('--minutes', type=int, default=60,
                        help='metric window in minutes (default 60)')
    args = parser.parse_args()

    sagemaker = boto3.client('sagemaker')
    cloudwatch = boto3.client('cloudwatch')

    endpoints = find_endpoints(sagemaker)
    if not endpoints:
        raise SystemExit(f"no endpoints named {PREFIX}* -- run terraform apply")
    components = find_components(sagemaker)

    print('Endpoints')
    for endpoint in endpoints:
        variants = ', '.join(v['VariantName']
                             for v in endpoint['ProductionVariants'])
        print(f"  {endpoint['EndpointName']}  {endpoint['kind']}"
              f"  variants: {variants}"
              f"  components: {components.get(endpoint['EndpointName'], [])}")

    if not args.no_invoke:
        print('\nInvoking')
        invoke(boto3.client('sagemaker-runtime'), endpoints, components,
               args.count)
        print(f"  waiting {args.wait}s for publication")
        time.sleep(args.wait)

    end = datetime.datetime.now(datetime.timezone.utc)
    window = (end - datetime.timedelta(minutes=args.minutes), end)
    names = {e['EndpointName'] for e in endpoints}
    names.update(c for cs in components.values() for c in cs)

    print('\nDimension sets CloudWatch reports for these resources')
    seen = observed(cloudwatch, names)
    by_namespace: dict = collections.defaultdict(
        lambda: collections.defaultdict(set))
    for (namespace, resource), metrics in seen.items():
        for metric, name_sets in metrics.items():
            for name_set in name_sets:
                by_namespace[namespace][name_set].add(metric)
    for namespace in NAMESPACES:
        print(f"  {namespace}")
        for name_set, metrics in sorted(by_namespace[namespace].items()):
            print(f"    {list(name_set)}: {len(metrics)} metrics")

    print('\nCatalogue entries')
    unexercised: list[str] = []
    mismatched: list[str] = []
    for resource, by_kind in SAGEMAKER_METRICS_BY_KIND.items():
        for entry_kind, table in by_kind.items():
            # an entry under no kind claims every kind publishes it, so
            # check them one at a time rather than together
            kinds = ([entry_kind] if entry_kind
                     else sorted({endpoint['kind'] for endpoint in endpoints}))
            for kind in kinds:
                targets = [
                    (endpoint, component)
                    for endpoint in endpoints if endpoint['kind'] == kind
                    for component in (components.get(endpoint['EndpointName'])
                                      or [None])
                    ]
                if resource == 'sagemaker-inference-component':
                    targets = [(e, c) for e, c in targets if c]

                for metric, entry in table.items():
                    namespace = entry['namespace']
                    name_sets = [tuple(sorted(names))
                                 for names in entry['dimension_sets']]
                    published = {
                        name_set
                        for endpoint, component in targets
                        for named in (endpoint['EndpointName'], component)
                        if named
                        for name_set in seen[namespace, named].get(metric, ())
                        }
                    if not published:
                        unexercised.append(f"{metric:32} {kind}")
                        continue

                    matching = [s for s in name_sets if s in published]
                    if not matching:
                        mismatched.append(
                            f"{metric:32} {kind:20} catalogue"
                            f" {[list(s) for s in name_sets]},"
                            f" published {[list(s) for s in sorted(published)]}")
                        continue

                    queried = [
                        has_points(cloudwatch, namespace, metric, filled, window)
                        for name_set in matching
                        for endpoint, component in targets
                        for filled in fill(list(name_set), endpoint, component)
                        ]
                    verdict = 'ok      ' if any(queried) else 'no points'
                    print(f"  {verdict} {metric:32} {kind:20}"
                          f" {[list(s) for s in matching]}")

    if mismatched:
        print('\nWrong dimensions -- the catalogue names a set that is not'
              ' published')
        for line in mismatched:
            print(f"  {line}")

    if unexercised:
        print('\nNot exercised by these endpoints -- left as they are,'
              ' not measured')
        for line in unexercised:
            print(f"  {line}")

    print('\nPublished for our resources but not in the catalogue'
          ' -- do not add these')
    catalogued = {
        tuple(sorted(names))
        for by_kind in SAGEMAKER_METRICS_BY_KIND.values()
        for table in by_kind.values()
        for entry in table.values()
        for names in entry['dimension_sets']
        }
    for namespace in NAMESPACES:
        for name_set in sorted(by_namespace[namespace]):
            if name_set not in catalogued:
                print(f"  {namespace} {list(name_set)}")


if __name__ == '__main__':
    main()
