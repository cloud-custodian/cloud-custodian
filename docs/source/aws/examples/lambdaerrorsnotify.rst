.. _lambdaerrorsnotify:

Lambda - Notify On Lambda Errors 
=====================================================

The following example policy will run hourly as a CloudWatch Scheduled Event triggered Lambda function.
The policies filters will check each Lambdas CloudWatch Metrics for errors.  If there are any errors
in an hour period and the Lambda function is not tagged with **Custodian_Lambda_Error_Exclude**
then the policy will take the action of notifying the Lambda function owner and the cloud team.  These
notifications can help developers by informing them if unexpected errors occur so they can be quickly
addressed.

For the notify action in the policy to work you must have setup the c7n_mailer tool:
https://github.com/cloud-custodian/cloud-custodian/tree/master/tools/c7n_mailer

Mailer Setup Guide:
https://cloudcustodian.io/docs/tools/c7n-mailer.html



.. code-block:: yaml

   policies:

 
     - name: lambda-invocation-errors
       resource: lambda
       description: |
          Hourly check that finds any Lambda functions that have any
          errors within the last hour and notifies the customer and Cloud Team.
       mode:
         type: periodic
         schedule: "rate(1 hour)"
         timeout: 300
         tags:
               ResourceContact: "cloudteam@company.com"
               ResourcePurpose: "Created by Cloud Custodian Automated Fleet Management"
               Environment: prd
       filters:
         - type: metrics
           name: Errors
           days: 0.068
           period: 3600
           statistics: Sum
           op: greater-than
           value: 0
         - not:
             - "tag:Custodian_Lambda_Error_Exclude": present      
       actions:
         - type: notify
           template: default.html
           priority_header: 1
           subject: "Lambda Function Errors Occurring! - [custodian {{ account }} - {{ region }}]"
           violation_desc: |
              "There has been one or more code errors occurring on this lambda function in the last hour:"
           action_desc: |
              "Actions Taken:  Please investigate this lambda function as errors reported.
              To exclude the below function from this scan please add a tag with a Key called
              Custodian_Lambda_Error_Exclude with any value to the lambda function.
           to:
             - CloudCustodian@Company.com
             - resource-owner
           transport:
             type: sqs
             queue: https://sqs.us-east-1.amazonaws.com/1234567890/cloud-custodian-mailer
             region: us-east-1

    
    
