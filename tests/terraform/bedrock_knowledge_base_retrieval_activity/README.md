# Bedrock knowledge base retrieval activity recording

This fixture creates three knowledge bases and a trail that sends their data
events to a CloudWatch Logs log group. Searching a knowledge base is an
ephemeral operation that Terraform cannot represent, so `setup.py` searches the
`used` knowledge base once each with `Retrieve`, `RetrieveAndGenerate` and
`RetrieveAndGenerateStream`, then waits for the events to reach the log group.
The `idle` knowledge base is never searched.

A new trail drops events for a while after it starts logging, so `setup.py`
first searches the `canary` knowledge base once a minute until one of those
searches reaches the log group. The tests count searches over the last 30
minutes, and the filter rejects a trail newer than that window, so `setup.py`
then waits until the trail is 30 minutes old. Only then does it search `used`,
and `canary` once more.

Recording needs access to `amazon.titan-embed-text-v2:0` and
`amazon.nova-lite-v1:0` in us-east-1. The
`test_bedrock_knowledge_base_retrieval_activity_*` tests share this fixture
with `scope="session"`, so they must be recorded together:

1. Temporarily add `replay=False` to each test's `@terraform(...)` decorator, and
   change `replay_flight_data` to `record_flight_data` in
   `retrieval_activity_flight_data`, which all four tests use.
2. Put a breakpoint at the start of
   `test_bedrock_knowledge_base_retrieval_activity_idle`, the first of them,
   after pytest-terraform applies this fixture. From the repository root, run
   `pytest -s -p no:env tests/test_bedrock.py -k bedrock_knowledge_base_retrieval_activity`.
3. At the breakpoint, run `python setup.py` from this directory, using the
   repository's Python environment and the same AWS credentials. It reads the
   knowledge base IDs and log group name from the sibling `tf_resources.json`.
   Expect it to take 35 to 45 minutes. Wait for it to print the five `used`
   events, then continue the tests within the time it prints.
4. Restore `replay_flight_data`, remove `replay=False` and the breakpoint. Set
   `YOUNG_RECORDED_AT` in `tests/test_bedrock.py` to the `creationTime` in
   `bedrock_knowledge_base_retrieval_activity_young/logs.DescribeLogGroups_1.json`,
   divided by 1000, plus 3600. Then rerun the tests in replay mode.
5. Remove identifiers the account ID scrub misses. In `tf_resources.json`,
   replace each IAM role `unique_id`, which encodes the account ID, and the S3
   bucket `grant` id. In each `cloudtrail.DescribeTrails_1.json`, replace the
   names and buckets of trails that aren't this fixture's.

pytest-terraform manages Terraform teardown. Replay runs never execute the
setup script, and the searches create no resource requiring teardown.
