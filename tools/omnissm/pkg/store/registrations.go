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

package store

import (
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/aws/awserr"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/dynamodbattribute"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/dynamodbiface"
)

type RegistrationEntry struct {
	Id             string `json:"Id,omitempty"`
	ActivationId   string `json:"ActivationId"`
	ActivationCode string `json:"ActivationCode"`
	ManagedId      string `json:"ManagedId"`
}

type Registrations struct {
	dynamodbiface.DynamoDBAPI

	tableName string
}

func NewRegistrations(cfg aws.Config, tableName string) *Registrations {
	return &Registrations{dynamodb.New(cfg), tableName}
}

func (r *Registrations) Get(id string) (*RegistrationEntry, error, bool) {
	req := r.DynamoDBAPI.GetItemRequest(&dynamodb.GetItemInput{
		TableName:       aws.String(r.tableName),
		AttributesToGet: []string{"id", "ActivationId", "ActivationCode", "ManagedId"},
		Key:             map[string]dynamodb.AttributeValue{"id": {S: aws.String(id)}},
	})
	resp, err := req.Send()
	if err != nil {
		if aerr, ok := err.(awserr.Error); ok {
			if aerr.Code() == dynamodb.ErrCodeResourceNotFoundException {
				return nil, nil, false
			}
		}
		return nil, err, false
	}
	var entry RegistrationEntry
	if err := dynamodbattribute.UnmarshalMap(resp.Item, &entry); err != nil {
		return nil, err, false
	}
	return &entry, nil, true
}

func (r *Registrations) Put(entry *RegistrationEntry) error {
	item, err := dynamodbattribute.MarshalMap(entry)
	if err != nil {
		return err
	}
	req := r.DynamoDBAPI.PutItemRequest(&dynamodb.PutItemInput{
		TableName: aws.String(r.tableName),
		Item:      item,
	})
	_, err = req.Send()
	return err
}

func (r *Registrations) Update(entry *RegistrationEntry) error {
	req := r.DynamoDBAPI.UpdateItemRequest(&dynamodb.UpdateItemInput{
		TableName:        aws.String(r.tableName),
		Key:              map[string]dynamodb.AttributeValue{"id": {S: aws.String(entry.Id)}},
		UpdateExpression: aws.String("SET ManagedId = :mid"),
		ExpressionAttributeValues: map[string]dynamodb.AttributeValue{
			":mid": {S: aws.String(entry.ManagedId)},
		},
	})
	_, err := req.Send()
	return err
}
