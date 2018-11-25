.. _mu:

Mu - Lambda Lifecycle Management
--------------------------------

For full Lambda lifecycle management we built Mu. We needed the
ability to create all the resources associated with a given Custodian
policy. These resources can include event sources for Lambda
functions such as Cloud Watch Events and Scheduled Events. We also
needed the ability to manage different versions of the policy and
did not want to update the Lambda functions during every Custodian
run.

Mu will evaluate if a policy has changed by comparing the
compiled Lambda function to the current Lambda function. Mu will also
update the event sources if the policy has been updated.
