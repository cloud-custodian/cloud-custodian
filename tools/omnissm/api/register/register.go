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
	"os"
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

	// RegistrationTable DynamodDb Table for storing instance regisrations
	RegistrationTable = os.Getenv("REGISTRATION_TABLE")

	// Only allow instance registrations from these accounts, read from
	// $ACCOUNT_WHITELIST (comma-separated)
	accountWhitelist = make(map[string]bool)
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

	w := os.Getenv("ACCOUNT_WHITELIST")
	for _, a := range strings.Split(w, ",") {
		accountWhitelist[a] = true
	}
}

// RegistrationRequest structure of instance registration request
type RegistrationRequest struct {
	Identity  string `json:"identity"`
	Signature string `json:"signature"`
	Provider  string `json:"provider"`
	ManagedID string `json:"managed-id"`
}

// InstanceIdentity provides for ec2 metadata instance information
type InstanceIdentity struct {
	ManagedID        string `json:"managedId"`
	AvailabilityZone string `json:"availabilityZone"`
	Region           string `json:"region"`
	InstanceID       string `json:"instanceId"`
	AccountID        string `json:"accountId"`
	InstanceType     string `json:"instanceType"`
}

// GetIdentifier Get a unique identifier for an instance
func (i *InstanceIdentity) GetIdentifier() string {
	ident := strings.Join([]string{i.AccountID, i.InstanceID}, "-")
	h := sha1.New()
	h.Write([]byte(ident))
	bid := h.Sum(nil)
	return fmt.Sprintf("%x", bid)
}

// GetRegistration fetch instance registration from db
func (i *InstanceIdentity) GetRegistration() (*InstanceRegistration, error) {
	registration := &InstanceRegistration{}

	params := &dynamodb.GetItemInput{
		TableName: aws.String(RegistrationTable),
		AttributesToGet: []string{
			"id", "ActivationId", "ActivationCode", "ManagedID",
		},
		Key: map[string]dynamodb.AttributeValue{
			"id": {
				S: aws.String(i.GetIdentifier()),
			},
		},
	}

	getRequest := dbClient.GetItemRequest(params)
	getResult, err := getRequest.Send()
	if err != nil {
		return nil, err
	}
	err = dynamodbattribute.UnmarshalMap(getResult.Item, registration)
	if err != nil {
		return nil, err
	}
	return registration, nil
}

// UpdateManagedID Record SSM Managed ID for an Instance
func (r *InstanceRegistration) UpdateManagedID(identity InstanceIdentity) error {

	params := &dynamodb.UpdateItemInput{
		TableName: aws.String(RegistrationTable),
		Key: map[string]dynamodb.AttributeValue{
			"id": dynamodb.AttributeValue{
				S: aws.String(identity.GetIdentifier())}},
		UpdateExpression: aws.String("SET ManagedId = :mid"),
		ExpressionAttributeValues: map[string]dynamodb.AttributeValue{
			":mid": {
				S: aws.String(identity.ManagedID),
			},
		},
	}

	updateReq := dbClient.UpdateItemRequest(params)
	_, err := updateReq.Send()

	if err != nil {
		return err
	}
	return nil
}

// RegisterInstance Create SSM activation for instance and store
func (i *InstanceIdentity) RegisterInstance() (*InstanceRegistration, error) {

	registration := &InstanceRegistration{}

	activateParams := &ssm.CreateActivationInput{
		DefaultInstanceName: aws.String(strings.Join([]string{i.AccountID, i.InstanceID}, "-")),
		IamRole:             aws.String(SSMInstanceRole),
		Description: aws.String(
			strings.Join([]string{i.AccountID, i.InstanceID}, "-")),
	}

	activateReq := ssmClient.CreateActivationRequest(activateParams)
	activateResult, err := activateReq.Send()

	if err != nil {
		return nil, err
	}
	registration.ActivationCode = *activateResult.ActivationCode
	registration.ActivationID = *activateResult.ActivationId
	registration.ID = i.GetIdentifier()

	regRecord, err := dynamodbattribute.MarshalMap(registration)
	insertParams := &dynamodb.PutItemInput{
		Item:      regRecord,
		TableName: aws.String(RegistrationTable),
	}

	insertRequest := dbClient.PutItemRequest(insertParams)
	insertResult, err := insertRequest.Send()

	if err != nil {
		return nil, fmt.Errorf("Put Registration Error %s %s", insertResult, err)
	}
	return registration, nil
}

// InstanceRegistration Minimal
type InstanceRegistration struct {
	ID             string `json:"id"`
	ActivationCode string
	ActivationID   string `json:"ActivationId"`
	ManagedID      string `json:"ManagedId"`
}

func validateRequest(requestBody string) (InstanceIdentity, events.APIGatewayProxyResponse) {

	var regRequest RegistrationRequest
	var identity InstanceIdentity

	err := json.Unmarshal([]byte(requestBody), &regRequest)
	if err != nil {
		return identity, newErrorResponse("invalid-request", "malformed json", 400)
	}

	// TODO: At the moment this is AWS Specific, support GCP & Azure to the extant possible.
	switch regRequest.Provider {
	case "aws":
	default:
		return identity, newErrorResponse("invalid-request", "unknown provider", 400)
	}

	signature, err := base64.StdEncoding.DecodeString(string(regRequest.Signature))
	if err != nil {
		return identity, newErrorResponse("invalid-request", "malformed rsa signature", 400)
	}
	err = RSACert.CheckSignature(x509.SHA256WithRSA, []byte(regRequest.Identity), signature)
	if err != nil {
		return identity, newErrorResponse("invalid-signature", "invalid identity", 400)
	}

	// We verified the signature, so malformed here would more than odd.
	_ = json.Unmarshal([]byte(regRequest.Identity), &identity)

	// Capture request variable into identity
	identity.ManagedID = regRequest.ManagedID

	return identity, events.APIGatewayProxyResponse{}
}

func handleUpdateManagedID(identity InstanceIdentity) events.APIGatewayProxyResponse {
	fmt.Println("Instance Update SSMID Request", identity.InstanceID, identity.Region, identity.AccountID, identity.GetIdentifier())

	registration, err := identity.GetRegistration()
	if err != nil {
		panic(err)
	}
	fmt.Println("Queried Instance", registration)

	if identity.ManagedID != "" {
		registration.UpdateManagedID(identity)
	}

	response := map[string]interface{}{
		"instance-id": identity.InstanceID,
		"account-id":  identity.AccountID,
		"managed-id":  identity.ManagedID,
	}
	serialized, err := json.Marshal(response)
	if err != nil {
		panic(err)
	}
	fmt.Println("Update ssmid response", string(serialized))
	return events.APIGatewayProxyResponse{Body: string(serialized), StatusCode: 200}
}

func handleRegistrationRequest(identity InstanceIdentity) events.APIGatewayProxyResponse {
	fmt.Println("Instance Registration Request", identity.InstanceID, identity.Region, identity.AccountID, identity.GetIdentifier())
	registration, err := identity.GetRegistration()
	if err != nil {
		panic(err)
	}

	fmt.Println("Queried Instance", registration)
	if len(registration.ActivationCode) < 1 {
		registration, err = identity.RegisterInstance()
		if err != nil {
			panic(err)
		}
	}

	response := map[string]interface{}{
		"instance-id":     identity.InstanceID,
		"account-id":      identity.AccountID,
		"region":          identity.Region,
		"activation-id":   registration.ActivationID,
		"activation-code": registration.ActivationCode,
	}

	serialized, err := json.Marshal(response)
	if err != nil {
		panic(err)
	}
	fmt.Println("Register Response", string(serialized))
	return events.APIGatewayProxyResponse{Body: string(serialized), StatusCode: 200}
}

func newErrorResponse(name, msg string, statusCode int) events.APIGatewayProxyResponse {
	response := map[string]string{
		"error":   name,
		"message": msg,
	}
	body, _ := json.Marshal(response)
	return events.APIGatewayProxyResponse{Body: string(body), StatusCode: statusCode}
}

func handleRequest(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {

	fmt.Printf("Processing request data for request %s.\n", request.RequestContext.RequestID)
	fmt.Printf("Body size = %d.\n", len(request.Body))

	identity, errorResponse := validateRequest(request.Body)

	if len(identity.InstanceID) < 1 {
		return errorResponse, nil
	}

	if !accountWhitelist[identity.AccountID] {
		// Account is not whitelisted, deny request
		fmt.Printf("Request from account '%s' is not whitelisted.\n", identity.AccountID)
		return newErrorResponse("invalid-request", "invalid account", 401), nil
	}

	if request.HTTPMethod == "POST" {
		return handleRegistrationRequest(identity), nil
	}
	return handleUpdateManagedID(identity), nil
}

func main() {
	lambda.Start(handleRequest)
}
