// Copyright 2018 Capital One Services, LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package omnissm

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/awserr"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/aws/aws-sdk-go/service/dynamodb/dynamodbattribute"
	"github.com/aws/aws-sdk-go/service/dynamodb/dynamodbiface"
	"github.com/pkg/errors"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ssm"
)

type RegistrationEntry struct {
	Id         string    `json:"id,omitempty"`
	CreatedAt  time.Time `json:"CreatedAt"`
	ManagedId  string    `json:"ManagedId"`
	AccountId  string    `json:"AccountId"`
	Region     string    `json:"Region"`
	InstanceId string    `json:"InstanceId"`

	// IsTagged and IsInventoried are logically bool types, but must be
	// represented as integers to allow for a LSI to be created in DynamoDB, as
	// DynamoDB disallows creating a LSI on a Bool type. The value is false
	// when equal to 0 and true when greater than 0.
	IsTagged      int `json:"IsTagged,omitempty"`
	IsInventoried int `json:"IsInventoried,omitempty"`

	ClientVersion string `json:"ClientVersion,omitempty"`

	// ActivationId/ActivationCode for registering with SSM
	ssm.Activation
}

type RegistrationsConfig struct {
	*aws.Config

	TableName string
}

type Registrations struct {
	dynamodbiface.DynamoDBAPI

	config *RegistrationsConfig
}

func NewRegistrations(config *RegistrationsConfig) *Registrations {
	r := &Registrations{
		DynamoDBAPI: dynamodb.New(session.New(config.Config)),
		config:      config,
	}
	return r
}

func (r *Registrations) queryIndex(ctx context.Context, indexName, attrName, value string) ([]*RegistrationEntry, error) {
	input := &dynamodb.QueryInput{
		ExpressionAttributeValues: map[string]*dynamodb.AttributeValue{":v1": {N: aws.String(value)}},
		IndexName:                 aws.String(indexName),
		KeyConditionExpression:    aws.String(fmt.Sprintf("%s = :v1", attrName)),
		TableName:                 aws.String(r.config.TableName),
	}
	items := make([]map[string]*dynamodb.AttributeValue, 0)
	err := r.DynamoDBAPI.QueryPagesWithContext(ctx, input, func(page *dynamodb.QueryOutput, lastPage bool) bool {
		items = append(items, page.Items...)
		return !lastPage
	})
	if err != nil {
		return nil, errors.Wrap(err, "dynamodb.Scan failed")
	}
	entries := make([]*RegistrationEntry, 0)
	for _, item := range items {
		var entry RegistrationEntry
		if err := dynamodbattribute.UnmarshalMap(item, &entry); err != nil {
			return nil, err
		}
		entries = append(entries, &entry)
	}
	return entries, nil
}

type QueryIndexInput struct {
	IndexName, AttrName, Value string
}

func (r *Registrations) QueryIndexes(ctx context.Context, inputs ...QueryIndexInput) ([]*RegistrationEntry, error) {
	m := make(map[string]bool)
	entries := make([]*RegistrationEntry, 0)
	for _, input := range inputs {
		resp, err := r.queryIndex(ctx, input.IndexName, input.AttrName, input.Value)
		if err != nil {
			return nil, err
		}
		// avoid duplicates
		for _, entry := range resp {
			if !m[entry.Id] {
				entries = append(entries, entry)
				m[entry.Id] = true
			}
		}
	}
	return entries, nil
}

func (r *Registrations) Scan(ctx context.Context) ([]*RegistrationEntry, error) {
	input := &dynamodb.ScanInput{
		ExpressionAttributeValues: map[string]*dynamodb.AttributeValue{
			":v1": {BOOL: aws.Bool(false)},
			":v2": {BOOL: aws.Bool(false)},
		},
		ConsistentRead:   aws.Bool(true),
		FilterExpression: aws.String("IsTagged = :v1 or IsInventoried = :v2"),
		TableName:        aws.String(r.config.TableName),
	}
	items := make([]map[string]*dynamodb.AttributeValue, 0)
	err := r.DynamoDBAPI.ScanPagesWithContext(ctx, input, func(page *dynamodb.ScanOutput, lastPage bool) bool {
		items = append(items, page.Items...)
		return !lastPage
	})
	if err != nil {
		return nil, errors.Wrap(err, "dynamodb.Scan failed")
	}
	entries := make([]*RegistrationEntry, 0)
	for _, item := range items {
		var entry RegistrationEntry
		if err := dynamodbattribute.UnmarshalMap(item, &entry); err != nil {
			return nil, err
		}
		entries = append(entries, &entry)
	}
	return entries, nil
}

func (r *Registrations) Get(ctx context.Context, id string) (*RegistrationEntry, error, bool) {
	resp, err := r.DynamoDBAPI.GetItemWithContext(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(r.config.TableName),
		//AttributesToGet: aws.StringSlice([]string{"id", "ActivationId", "ActivationCode", "ManagedId"}),
		Key: map[string]*dynamodb.AttributeValue{"id": {S: aws.String(id)}},
	})
	if err != nil {
		if aerr, ok := err.(awserr.Error); ok {
			if aerr.Code() == dynamodb.ErrCodeResourceNotFoundException {
				return nil, nil, false
			}
		}
		return nil, errors.Wrap(err, "dynamodb.Get failed"), false
	}
	if resp.Item == nil {
		return nil, nil, false
	}
	var entry RegistrationEntry
	if err := dynamodbattribute.UnmarshalMap(resp.Item, &entry); err != nil {
		return nil, errors.Wrap(err, "cannot unmarshal dynamodbattribute map"), false
	}
	return &entry, nil, true
}

func (r *Registrations) GetByManagedId(ctx context.Context, managedId string) (*RegistrationEntry, error, bool) {
	resp, err := r.DynamoDBAPI.QueryWithContext(ctx, &dynamodb.QueryInput{
		TableName: aws.String(r.config.TableName),
		ExpressionAttributeValues: map[string]*dynamodb.AttributeValue{
			":v1": {S: aws.String(managedId)},
		},
		IndexName:              aws.String("ManagedId-index"),
		KeyConditionExpression: aws.String("ManagedId = :v1"),
	})
	if err != nil {
		if aerr, ok := err.(awserr.Error); ok {
			if aerr.Code() == dynamodb.ErrCodeResourceNotFoundException {
				return nil, nil, false
			}
		}
		return nil, errors.Wrap(err, "dynamodb.Get failed"), false
	}
	if len(resp.Items) == 0 {
		return nil, nil, false
	}
	var entry RegistrationEntry
	if err := dynamodbattribute.UnmarshalMap(resp.Items[0], &entry); err != nil {
		return nil, errors.Wrap(err, "cannot unmarshal dynamodbattribute map"), false
	}
	return &entry, nil, true
}

func (r *Registrations) Put(ctx context.Context, entry *RegistrationEntry) error {
	item, err := dynamodbattribute.MarshalMap(entry)
	if err != nil {
		return err
	}
	_, err = r.DynamoDBAPI.PutItemWithContext(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(r.config.TableName),
		Item:      item,
	})
	return err
}

func (r *Registrations) Update(ctx context.Context, entry *RegistrationEntry) error {
	_, err := r.DynamoDBAPI.UpdateItemWithContext(ctx, &dynamodb.UpdateItemInput{
		TableName:        aws.String(r.config.TableName),
		Key:              map[string]*dynamodb.AttributeValue{"id": {S: aws.String(entry.Id)}},
		UpdateExpression: aws.String("SET ManagedId=:v1, IsTagged=:v2, IsInventoried=:v3"),
		ExpressionAttributeValues: map[string]*dynamodb.AttributeValue{
			":v1": {S: aws.String(entry.ManagedId)},
			":v2": {N: aws.String(strconv.Itoa(entry.IsTagged))},
			":v3": {N: aws.String(strconv.Itoa(entry.IsInventoried))},
		},
	})
	return errors.Wrapf(err, "unable to update entry: %#v", entry.Id)
}

func (r *Registrations) Delete(ctx context.Context, id string) error {
	_, err := r.DynamoDBAPI.DeleteItemWithContext(ctx, &dynamodb.DeleteItemInput{
		TableName: aws.String(r.config.TableName),
		Key:       map[string]*dynamodb.AttributeValue{"id": {S: aws.String(id)}},
	})
	return errors.Wrapf(err, "unable to delete entry: %#v", id)
}
