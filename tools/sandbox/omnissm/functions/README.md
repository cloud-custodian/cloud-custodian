# lambda functions

OmniSSM depends upon several lambda functions to manage hybrid mode functionality:

 * `enrich-registrations` - Periodically scans the registrations table for any entries where the managed instance has not yet being tagged or inventoried in SSM.
 * `handle-registrations` - The API Gateway handler for the registrations API.
 * `process-config-events` - Receives ConfigurationItemChange events from CloudWatch Events and will either enrich the managed instance (tags/inventory) or deregister the managed instance from SSM (depending upon the ConfigurationItemStatus).
 * `process-deferred-actions`- Periodically starts and consumes from SQS until all messages are exhausted. The messages contain deferred actions that should be performed by the function. These actions were either API calls that could not be completed normally (timeout, throttled, etc) or were better performed asynchronously.

# configuration

A `config.yaml` must be provided alongside the lambda functions to configure any of the following values:

| Name | Description |
| -------- | ------ |
| AccountWhitelist | A whitelist of accounts allowed to register with SSM. |
| AssumeRoleName | The IAM role name to assume for using AWS ConfigService. If this is provided then the full arn will be built based upon this name and the target account, otherwise AssumeRoles is used. This or AssumeRoles must be specified. |
| AssumeRoles | A mapping of IAM roles to assume with the provided accounts. |
| InstanceRole | The IAM role used when the SSM agent registers with the SSM service. |
| MaxRetries | Sets the number of retries attempted for AWS API calls. Defaults to 0 if not specified. |
| QueueName | If provided, SSM API requests that are throttled will be sent to this queue. Should be used in conjunction with MaxRetries since the throttling that takes place should retry several times before attempting to queue the request. |
| RegistrationsTable | The DynamoDb table used for storing instance registrations. |
| ResourceDeletedSNSTopic | The SNS topic published to when resources are deleted. |
| ResourceTags | The name of tags that should be added to SSM tags if they are tagged on the EC2 instance. |
| S3DownloadRole | The IAM role used for downloading OversizedConfigurationItems from S3. |
| SNSPublishRole | The IAM role used for publishing to the Resource Deleted SNS topic. |
