/*
Copyright 2018 Capital One Services, LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.

You may obtain a copy of the License at
	http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/
package main

import (
	"context"
	"crypto/sha1"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"strings"

	"fmt"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/aws/external"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/dynamodbattribute"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
)

const (
	// SSMInstanceRole IAM Role to associate to instance registration
	SSMInstanceRole = "service-role/AmazonEC2RunCommandRoleForManagedInstances"

	// RegistrationTable DynamodDb Table for storing instance regisrations
	RegistrationTable = "omnissm-registrations"

	// AWSRSAIdentityCert is the RSA public certificate
	AWSRSAIdentityCert = `-----BEGIN CERTIFICATE-----
MIIDIjCCAougAwIBAgIJAKnL4UEDMN/FMA0GCSqGSIb3DQEBBQUAMGoxCzAJBgNV
BAYTAlVTMRMwEQYDVQQIEwpXYXNoaW5ndG9uMRAwDgYDVQQHEwdTZWF0dGxlMRgw
FgYDVQQKEw9BbWF6b24uY29tIEluYy4xGjAYBgNVBAMTEWVjMi5hbWF6b25hd3Mu
Y29tMB4XDTE0MDYwNTE0MjgwMloXDTI0MDYwNTE0MjgwMlowajELMAkGA1UEBhMC
VVMxEzARBgNVBAgTCldhc2hpbmd0b24xEDAOBgNVBAcTB1NlYXR0bGUxGDAWBgNV
BAoTD0FtYXpvbi5jb20gSW5jLjEaMBgGA1UEAxMRZWMyLmFtYXpvbmF3cy5jb20w
gZ8wDQYJKoZIhvcNAQEBBQADgY0AMIGJAoGBAIe9GN//SRK2knbjySG0ho3yqQM3
e2TDhWO8D2e8+XZqck754gFSo99AbT2RmXClambI7xsYHZFapbELC4H91ycihvrD
jbST1ZjkLQgga0NE1q43eS68ZeTDccScXQSNivSlzJZS8HJZjgqzBlXjZftjtdJL
XeE4hwvo0sD4f3j9AgMBAAGjgc8wgcwwHQYDVR0OBBYEFCXWzAgVyrbwnFncFFIs
77VBdlE4MIGcBgNVHSMEgZQwgZGAFCXWzAgVyrbwnFncFFIs77VBdlE4oW6kbDBq
MQswCQYDVQQGEwJVUzETMBEGA1UECBMKV2FzaGluZ3RvbjEQMA4GA1UEBxMHU2Vh
dHRsZTEYMBYGA1UEChMPQW1hem9uLmNvbSBJbmMuMRowGAYDVQQDExFlYzIuYW1h
em9uYXdzLmNvbYIJAKnL4UEDMN/FMAwGA1UdEwQFMAMBAf8wDQYJKoZIhvcNAQEF
BQADgYEAFYcz1OgEhQBXIwIdsgCOS8vEtiJYF+j9uO6jz7VOmJqO+pRlAbRlvY8T
C1haGgSI/A1uZUKs/Zfnph0oEI0/hu1IIJ/SKBDtN5lvmZ/IzbOPIJWirlsllQIQ
7zvWbGd9c9+Rm3p04oTvhup99la7kZqevJK0QRdD/6NpCKsqP/0=
-----END CERTIFICATE-----`
)

var (
	// RSACert AWS Public Certificate
	RSACert *x509.Certificate
	// RSACertPEM Decoded pem signature
	RSACertPEM, _ = pem.Decode([]byte(AWSRSAIdentityCert))

	dbClient  *dynamodb.DynamoDB
	ssmClient *ssm.SSM
)

func init() {
	var err error

	if RSACert, err = x509.ParseCertificate(RSACertPEM.Bytes); err != nil {
		panic(err)
	}

	cfg, err := external.LoadDefaultAWSConfig()
	if err != nil {
		panic("unable to load SDK config, " + err.Error())
	}

	dbClient = dynamodb.New(cfg)
	ssmClient = ssm.New(cfg)

}

// RegistrationRequest structure of instance registration request
type RegistrationRequest struct {
	Identity  string `json:"identity"`
	Signature string `json:"signature"`
	Provider  string `json:"provider"`
}

// InstanceIdentity provides for ec2 metadata instance information
type InstanceIdentity struct {
	AvailabilityZone string `json:"availabilityZone"`
	Region           string `json:"region"`
	InstanceID       string `json:"instanceId"`
	AccountID        string `json:"accountId"`
	InstanceType     string `json:"instanceType"`
}

// GetManagedID Retrieve instance ssm managed instance id
func (i *InstanceIdentity) GetManagedID() string {
	// Not Intended to be cryptographically secure, just a partition / lookup key
	// we only get s
	ident := strings.Join([]string{i.AccountID, i.InstanceID}, "-")
	h := sha1.New()
	h.Write([]byte(ident))
	bid := h.Sum(nil)
	return fmt.Sprintf("%x", bid)[0:17]
}

// GetRegistration fetch instance registration from db
func (i *InstanceIdentity) GetRegistration() (*InstanceRegistration, error) {
	registration := &InstanceRegistration{}

	params := &dynamodb.GetItemInput{
		TableName: aws.String(RegistrationTable),
		AttributesToGet: []string{
			"mid", "ActivationId", "ActivationCode",
		},
		Key: map[string]dynamodb.AttributeValue{
			"mid": {
				S: aws.String(i.GetManagedID()),
			},
		},
	}

	getRequest := dbClient.GetItemRequest(params)
	getResult, err := getRequest.Send()
	if err != nil {
		return registration, err
	}
	err = dynamodbattribute.UnmarshalMap(getResult.Item, registration)
	if err != nil {
		return registration, err
	}
	return registration, nil
}

// RegisterInstance Create SSM activation for instance and store
func (i *InstanceIdentity) RegisterInstance() (*InstanceRegistration, error) {

	registration := &InstanceRegistration{}

	activateParams := &ssm.CreateActivationInput{
		IamRole: aws.String(SSMInstanceRole),
		Description: aws.String(
			strings.Join([]string{i.AccountID, i.InstanceID}, "-")),
	}
	activateReq := ssmClient.CreateActivationRequest(activateParams)
	activateResult, err := activateReq.Send()

	if err != nil {
		return registration, err
	}
	registration.ActivationCode = *activateResult.ActivationCode
	registration.ActivationID = *activateResult.ActivationId
	registration.ManagedID = i.GetManagedID()

	regRecord, err := dynamodbattribute.MarshalMap(registration)
	insertParams := &dynamodb.PutItemInput{
		Item:      regRecord,
		TableName: aws.String(RegistrationTable),
	}

	insertRequest := dbClient.PutItemRequest(insertParams)
	insertResult, err := insertRequest.Send()

	if err != nil {
		fmt.Println("Put Registration Error", insertResult, err)
		return registration, err
	}
	return registration, nil
}

// InstanceRegistration Minimal
type InstanceRegistration struct {
	ActivationCode string
	ActivationID   string `json:"ActivationId"`
	ManagedID      string `json:"mid"`
}

func validateRequest(requestBody string) (InstanceIdentity, events.APIGatewayProxyResponse) {

	var regRequest RegistrationRequest
	var identity InstanceIdentity

	err := json.Unmarshal([]byte(requestBody), &regRequest)
	if err != nil {
		response := map[string]string{
			"error":   "invalid-request",
			"message": "malformed json",
		}
		body, _ := json.Marshal(response)
		return identity, events.APIGatewayProxyResponse{Body: string(body), StatusCode: 400}
	}

	// TODO: At the moment this is AWS Specific, support GCP & Azure to the extant possible.
	switch regRequest.Provider {
	case "aws":
	default:
		response := map[string]string{
			"error":   "invalid-request",
			"message": "unknown provider",
		}

		body, _ := json.Marshal(response)
		return identity, events.APIGatewayProxyResponse{Body: string(body), StatusCode: 400}
	}

	signature, err := base64.StdEncoding.DecodeString(string(regRequest.Signature))
	if err != nil {
		response := map[string]string{
			"error":   "invalid-request",
			"message": "malformed rsa signature",
		}
		body, _ := json.Marshal(response)
		return identity, events.APIGatewayProxyResponse{Body: string(body), StatusCode: 400}
	}
	err = RSACert.CheckSignature(x509.SHA256WithRSA, []byte(regRequest.Identity), signature)
	if err != nil {
		response := map[string]string{
			"error":   "invalid-signature",
			"message": "invalid identity",
		}
		body, _ := json.Marshal(response)
		return identity, events.APIGatewayProxyResponse{Body: string(body), StatusCode: 400}
	}

	// We verified the signature, so malformed here would more than odd.
	_ = json.Unmarshal([]byte(regRequest.Identity), &identity)

	return identity, events.APIGatewayProxyResponse{}
}

func handleRequest(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {

	fmt.Printf("Processing request data for request %s.\n", request.RequestContext.RequestID)
	fmt.Printf("Body size = %d.\n", len(request.Body))

	identity, errorResponse := validateRequest(request.Body)

	if len(identity.InstanceID) < 1 {
		return errorResponse, nil
	}

	fmt.Println("Instance Registration Request", identity.InstanceID, identity.Region, identity.AccountID, identity.GetManagedID())

	registration, err := identity.GetRegistration()
	if err != nil {
		panic(err)
	}
	fmt.Println("Queryed Instance", registration, err)

	if len(registration.ActivationCode) < 1 {
		registration, err = identity.RegisterInstance()
		fmt.Println("Registered Instance", registration, err)
		if err != nil {
			panic(err)
		}
	}

	response := map[string]interface{}{
		"instance-id":     identity.InstanceID,
		"account-id":      identity.AccountID,
		"managed-id":      identity.GetManagedID(),
		"region":          identity.Region,
		"activation-id":   registration.ActivationID,
		"activation-code": registration.ActivationCode,
	}

	serialized, err := json.Marshal(response)
	fmt.Println("response", string(serialized))
	if err != nil {
		panic(err)
	}

	return events.APIGatewayProxyResponse{Body: string(serialized), StatusCode: 200}, nil
}

func main() {
	lambda.Start(handleRequest)
}
