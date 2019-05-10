.. _sagemakernotebookdeletepublicorunencrypted:

SageMaker Notebook - Delete Public or Unencrypted 
=====================================================

The following example policy chain will detect if new SageMaker Notebooks are internet-facing
(public) or unencrypted (not using KMS) at launch and then tag, stop, and delete the notebook
and email the customer and cloud custodian admin.  SageMaker Notebooks cannot be deleted unless they
are in a Stopped status and they cannot be stopped until they are in a InService status which
is why this needs a chain of policies that will trigger in order using tags and scheduled Lambda
runs.



.. code-block:: yaml

    policies:
    
    
    - name: sagemaker-notebook-auto-tag-user
      resource: sagemaker-notebook
      description: |
        When a new Sagemaker notebook is created tag the creators ID to CreatorName tag
      mode:
          type: cloudtrail
          events:
            - source: sagemaker.amazonaws.com
              event: CreateNotebookInstance
              ids: "responseElements.notebookInstanceArn"
      actions:
        - type: auto-tag-user
          tag: CreatorName
    
    
    
    - name: sagemaker-notebook-tag-non-compliant
      resource: sagemaker-notebook
      description: |
        When a new Sagemaker Notebook is created that is public or not encrypted
        it will get tagged for stopping and then deletion
      mode:
          type: cloudtrail
          events:
            - source: sagemaker.amazonaws.com
              event: CreateNotebookInstance
              ids: "responseElements.notebookInstanceArn"
      filters:
        - or:
          - "DirectInternetAccess": "Enabled"
          - "KmsKeyId": absent
      actions:
        - type: tag
          key: NonCompliantTag
          value: "TRUE"
    
    
    
    - name: sagemaker-notebook-stop-non-compliant
      resource: sagemaker-notebook
      description: |
        If a SageMaker Notebook is tagged with NonCompliantTag then it gets stopped and tagged
        with NonCompliantTagStopped for deletion
      mode:
        type: periodic
        schedule: "rate(5 minutes)"
        timeout: 45
      filters:
        - "tag:NonCompliantTag": "TRUE"
        - "NotebookInstanceStatus": "InService"
      actions:
        - type: tag
          key: NonCompliantTagStopped
          value: "TRUE"
        - stop
    
    
    
    - name: sagemaker-notebook-delete-non-compliant
      resource: sagemaker-notebook
      description: |
        When a new Sagemaker notebook is tagged as non-compliant and in a stopped state, delete it
      mode:
        type: periodic
        schedule: "rate(5 minutes)"
        timeout: 45
      filters:
        - "tag:NonCompliantTagStopped": "TRUE"
        - "NotebookInstanceStatus": "Stopped"
      actions:
        - delete
        - type: notify
          template: default.html
          priority_header: 1
          subject: SageMaker Notebook - Deleted! - [custodian {{ account }} - {{ region }}]
          violation_desc: |
              Public facing (Non-VPC) OR Non-Encrypted Sagemaker Notebooks Are Prohibited!
              All Notebooks Must Be in VPC mode and encrypted!
          action_desc: |
              Actions Taken:  Your SageMaker Notebook Instance has been deleted due to being non-compliant.  Please create a new
              SageMaker notebook in VPC mode with KMS encryption enabled.
          to:
            - CloudCustodian@Company.com
            - resource-owner
          transport:
            type: sqs
            queue: https://sqs.us-east-1.amazonaws.com/123456789123/cloud-custodian-mailer
            region: us-east-1
