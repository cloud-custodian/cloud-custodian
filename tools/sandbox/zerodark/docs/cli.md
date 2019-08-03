
# Command Line Ui (Science Fiction):-)

`zerodark metrics load-app`

Query CMDB for all application resources, then query cloudwatch metrics for those resources.

`zerodark metrics load-account`

Query CMDB for all resources in the account.

`zerodark metrics server`

`zerodark cmdb load-resources`
`zerodark cmdb show-app-resources`
`zerodark cmdb server`

`zerodark flows load-account`
`zerodark flows load-app`

`zerodark flows ingest-enriched`

Load enriched flow log records from s3

`zerodark flows enrich-account`

Ingest flows and output enriched flows to s3

`zerodark flows enrich-app`


`zerodark flows server-enrich`

SQS Worker for flow log enrichment

`zerodark flows server-account`

SQS Worker for flow log loading for an account
