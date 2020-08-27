Policy Testing tool
===================

The `tools/util/policy_test` tool can be used to record and replay API calls
against a given policy. It allows you to validate changes and to potentially
speed up policy development by eliminating API calls.

First, run the tool in record mode against a policy::

   $ tools/util/policy_test record output_dir policies.yaml --name policy_name

This will record API calls as well as any findings to the specified `output_dir`.

Next, make any desired changes to your policy.

When you're ready to test those changes, run the tool in replay mode::

   $ tools/util/policy_test replay output_dir policies.yaml --name policy_name
   ✅ policy_name, OK

If the policy output matches, you should get a ✅. Otherwise, an error message
will be displayed with additional information.
