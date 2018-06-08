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

package store

import (
	"context"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/awserr"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/aws/aws-sdk-go/service/dynamodb/dynamodbattribute"
	"github.com/aws/aws-sdk-go/service/dynamodb/dynamodbiface"
	"github.com/pkg/errors"
)

type RegistrationEntry struct {
	Id             string    `json:"id,omitempty"`
	CreatedAt      time.Time `json:"CreatedAt"`
	ActivationId   string    `json:"ActivationId"`
	ActivationCode string    `json:"ActivationCode"`
	ManagedId      string    `json:"ManagedId"`
	AccountId      string    `json:"AccountId"`
	Region         string    `json:"Region"`
	InstanceId     string    `json:"InstanceId"`
	Enriched       bool      `json:"Enriched"`
}

type Registrations struct {
	dynamodbiface.DynamoDBAPI

	tableName string
}

func NewRegistrations(cfg *aws.Config, tableName string) *Registrations {
	return &Registrations{dynamodb.New(session.New(cfg)), tableName}
}

func (r *Registrations) Scan() ([]*RegistrationEntry, error) {
	input := &dynamodb.ScanInput{
		ExpressionAttributeValues: map[string]*dynamodb.AttributeValue{
			":v1": {BOOL: aws.Bool(false)},
		},
		ConsistentRead:   aws.Bool(true),
		FilterExpression: aws.String("Enriched = :v1"),
		//ProjectionExpression:   aws.String("id,ManagedId"),
		TableName: aws.String(r.tableName),
	}
	items := make([]map[string]*dynamodb.AttributeValue, 0)
	err := r.DynamoDBAPI.ScanPagesWithContext(context.Background(), input, func(page *dynamodb.ScanOutput, lastPage bool) bool {
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

func (r *Registrations) Get(id string) (*RegistrationEntry, error, bool) {
	resp, err := r.DynamoDBAPI.GetItem(&dynamodb.GetItemInput{
		TableName:       aws.String(r.tableName),
		AttributesToGet: aws.StringSlice([]string{"id", "ActivationId", "ActivationCode", "ManagedId"}),
		Key:             map[string]*dynamodb.AttributeValue{"id": {S: aws.String(id)}},
	})
	if err != nil {
		if aerr, ok := err.(awserr.Error); ok {
			if aerr.Code() == dynamodb.ErrCodeResourceNotFoundException {
				return nil, nil, false
			}
		}
		return nil, err, false
	}
	if resp.Item == nil {
		return nil, nil, false
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
	_, err = r.DynamoDBAPI.PutItem(&dynamodb.PutItemInput{
		TableName: aws.String(r.tableName),
		Item:      item,
	})
	return err
}

func (r *Registrations) Update(entry *RegistrationEntry) error {
	_, err := r.DynamoDBAPI.UpdateItem(&dynamodb.UpdateItemInput{
		TableName:        aws.String(r.tableName),
		Key:              map[string]*dynamodb.AttributeValue{"id": {S: aws.String(entry.Id)}},
		UpdateExpression: aws.String("SET ManagedId=:v1, Enriched=:v2"),
		ExpressionAttributeValues: map[string]*dynamodb.AttributeValue{
			":v1": {S: aws.String(entry.ManagedId)},
			":v2": {BOOL: aws.Bool(entry.Enriched)},
		},
	})
	return err
}

type RegistrationEntryIndex int

const (
	IndexInstanceId RegistrationEntryIndex = iota
	IndexManagedid
)

type RegistrationEntries struct {
	entries []*RegistrationEntry
	indexes map[RegistrationEntryIndex]map[string]int
}

func NewRegistrationEntries(entries []*RegistrationEntry) *RegistrationEntries {
	r := &RegistrationEntries{
		entries: entries,
		indexes: map[RegistrationEntryIndex]map[string]int{
			IndexInstanceId: make(map[string]int),
			IndexManagedid:  make(map[string]int),
		},
	}
	for i, entry := range entries {
		r.indexes[IndexInstanceId][entry.InstanceId] = i
		r.indexes[IndexManagedid][entry.ManagedId] = i
	}
	return r
}

func (r *RegistrationEntries) All() []*RegistrationEntry { return r.entries }

func (r *RegistrationEntries) First() RegistrationEntry {
	if len(r.entries) == 0 {
		return RegistrationEntry{}
	}
	return *r.entries[0]
}

func (r *RegistrationEntries) Lookup(index RegistrationEntryIndex, value string) (*RegistrationEntry, bool) {
	i, ok := r.indexes[index][value]
	if !ok {
		return nil, false
	}
	entry := r.entries[i]
	return entry, true
}
