.. _mu:

Mu - Lambda Lifecycle Management
--------------------------------

For full Lambda lifecycle management we built Mu. We needed the
ability to create all the resources associated to a given Custodian
policy. These resources can include the event sources for the Lambda
functions, such as, Cloud Watch Events, Scheduled Events. We also
needed the ability to manage the different versions of the policy and
to not keep updating the lambda functions during every Custodian
run. Mu will evaluate if a policy has changed by comparing the
compiled lambda function to the current Lambda function. Mu will also
update the event sources if the policy has been updated. Mu can also
be used independently for managing lambda functions with event
sources.
