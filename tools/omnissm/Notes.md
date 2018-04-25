

# Registering an instance

apigw (regional) -> golang lambda -> dynamodb

Verify cryptographic signature on

```
/register

{'provider': 'aws',
 'signature': '',
 'signature_type': '',
 'identity': ''}

```

Returns a registration nonce (configurable).

On rate error return try again.


# Mapping instance id

Character limit 17 (note windows needs extra char consumption)

- instance-id (17) + account (12)->


# Enriching an instance

config -> sns -> sqs (cross) -> lambda

http://boto3.readthedocs.io/en/latest/reference/services/ssm.html#SSM.Client.put_inventory

Custom:CloudInfo

```
{
'Tags': {},
'InstanceId': '',
'SubnetId': '',
'Zone': '',
'InstanceType': '',
'AccountId': '',
'AccountName': ''
}

```

# Deleting an instance

Also off the

# Google Verification

https://cloud.google.com/compute/docs/instances/verifying-instance-identity#token_format
