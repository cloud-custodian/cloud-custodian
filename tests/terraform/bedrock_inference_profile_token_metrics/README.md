# Bedrock inference profile token metrics recording

This fixture creates the application inference profile. The runtime invocation
is an ephemeral operation that Terraform cannot represent, so `setup.py` emits
real input and output token metrics before flight data is recorded.

To re-record:

1. Temporarily add `replay=False` to the
   `@terraform("bedrock_inference_profile_token_metrics")` decorator and use
   `record_flight_data("bedrock_inference_profile_token_metrics")`.
2. Put a breakpoint at the start of the test, after pytest-terraform applies
   this fixture. Run the focused test with `-s -p no:env`.
3. At the breakpoint, run `./setup.py` from this directory. It reads the
   Terraform-created profile name and region from the sibling
   `tf_resources.json`, resolves the live ARN and ID through Bedrock, passes the
   ARN to Bedrock Runtime, and uses the ID for the CloudWatch `ModelId`
   dimension. Wait for it to report that both metrics are available, then
   continue the test.
4. Restore `replay_flight_data`, remove `replay=False` and the breakpoint, and
   rerun the focused test in replay mode.

pytest-terraform manages Terraform teardown. Replay runs never execute the
setup script, and the invocation creates no resource requiring teardown.
