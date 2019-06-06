.. _dmsenforcessl:

DMS - DB Migration Service Endpoint - Enforce SSL 
=====================================================

The following example policies will allow you to enforce SSL connectivity on any new
or modified DMS Endpoints.  The supported SSL methods vary based on the database engine.
See https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Security.SSL.html for more info.
There are 2 policies to handle the different types of SSL.  With sqlserver, mongodb, and
postgres you can turn on the SSL mode to require without having to pass in a certificate.
Most other database engines would require you to pass in the ARN of the CA certificate
to use which is why automating those in a c7n policy is difficult and this example policy will
just delete them instead.  DMS certificate ARNS are unique per account and region which
is why multi-account policy runs wouldn't work.  Both policies trigger off the creation or
modification of any DMS endpoints so if a user tries to disable the SSL it would re-enable the
SSL or delete the users endpoint and then email them depending on SSL modes supported.
For the notify action in the second policy to work you must have setup the c7n_mailer tool:
https://github.com/cloud-custodian/cloud-custodian/tree/master/tools/c7n_mailer



.. code-block:: yaml

   policies:

 
    - name: dms-endpoint-enable-ssl-require-realtime
      resource: dms-endpoint
      description: |
        If the SSL Mode is none for a DMS Endpoint with engine of sql, mongo, or postgres
        it gets turned on to Require SSL setting
      mode:
          type: cloudtrail
          events:
            - source: dms.amazonaws.com
              event: CreateEndpoint
              ids: "responseElements.endpoint.endpointArn"
            - source: dms.amazonaws.com
              event: ModifyEndpoint
              ids: "responseElements.endpoint.endpointArn"
      filters:
        - or:
            - SslMode: none
            - type: event
              key: "detail.requestParameters.sslMode"
              op: eq
              value: "none"
        - or:
          - EngineName: sqlserver
          - EngineName: mongodb
          - EngineName: postgres
      actions:
        - type: modify-endpoint
          SslMode: require
    
    
    - name: dms-delete-endpoint-missing-ssl-ca-cert-realtime
      resource: dms-endpoint
      description: |
        If the SSL Mode is none for a DMS Endpoint with engine that is not one of sql, mongo, or postgres
        the endpoint is deleted and an email is sent stating that CA Certificates need to be used as a requirement
      mode:
          type: cloudtrail
          events:
            - source: dms.amazonaws.com
              event: CreateEndpoint
              ids: "responseElements.endpoint.endpointArn"
            - source: dms.amazonaws.com
              event: ModifyEndpoint
              ids: "responseElements.endpoint.endpointArn"
      filters:
        - or:
            - SslMode: none
            - type: event
              key: "detail.requestParameters.sslMode"
              op: eq
              value: "none"
        - or:
            - EngineName: aurora
            - EngineName: mariadb
            - EngineName: mysql
            - EngineName: sybase
            - EngineName: oracle
      actions:
        - delete
        - type: notify
          template: default.html
          priority_header: 1
          subject: DMS Endpoint Deleted As It's Non-Compliant! - [custodian {{ account }} - {{ region }}]
          violation_desc: |
              Per regulations all DMS Endpoints have to use SSL connections and your endpoint was setup as 'none' for SSL mode!
          action_desc: |
              Actions Taken:  You are required to enable SSL on your endpoint for a secure transmission of data.
              This incident has been reported and the invalid endpoint has been deleted.  Please launch a new endpoint using SSL
          to:
            - CloudCustodian@Company.com
            - resource-owner
            - event-owner
          transport:
            type: sqs
            queue: https://sqs.us-east-1.amazonaws.com/123456789012/cloud-custodian-mailer
            region: us-east-1
    
    
    
