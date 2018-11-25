package omnissm

import (
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/aws/aws-sdk-go/service/sns"
	"github.com/aws/aws-sdk-go/service/sqs"
	"github.com/aws/aws-sdk-go/service/ssm"
	"github.com/aws/aws-xray-sdk-go/xray"
)

func SetupTracing(o *OmniSSM) {
	if svc, ok := o.S3API.(*s3.S3); ok {
		xray.AWS(svc.Client)
	}
	if svc, ok := o.SNSAPI.(*sns.SNS); ok {
		xray.AWS(svc.Client)
	}
	if svc, ok := o.SSMAPI.(*ssm.SSM); ok {
		xray.AWS(svc.Client)
	}
	if o.SQS != nil {
		if svc, ok := o.SQSAPI.(*sqs.SQS); ok {
			xray.AWS(svc.Client)
		}
	}
	if d, ok := o.Registrations.DynamoDBAPI.(*dynamodb.DynamoDB); ok {
		xray.AWS(d.Client)
	}
}
