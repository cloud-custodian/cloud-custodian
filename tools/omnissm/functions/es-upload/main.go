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

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/url"
	"os"
	"strings"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/credentials"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/aws/signer/v4"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/aws/aws-sdk-go/service/dynamodb/dynamodbattribute"
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/aws/aws-xray-sdk-go/xray"
	"github.com/olivere/elastic"
	"github.com/pkg/errors"
	"github.com/sha1sum/aws_signing_client"
)

var (
	xRayTracingEnabled = os.Getenv("_X_AMZN_TRACE_ID")
	esClient           = os.Getenv("OMNISSM_ELASTIC_SEARCH_HTTP")
	indexName          = os.Getenv("OMNISSM_INDEX_NAME")
	tableName          = os.Getenv("OMNISSM_REGISTRATIONS_TABLE")
	typeName           = os.Getenv("OMNISSM_TYPE_NAME")
	s3Svc              = s3.New(session.New())
	dynamoSvc          = dynamodb.New(session.New())
)

func main() {
	lambda.Start(func(ctx context.Context, event events.S3Event) {
		if xRayTracingEnabled != "" {
			xray.AWS(s3Svc.Client)
			xray.AWS(dynamoSvc.Client)
		}
		if esClient == "" || indexName == "" || typeName == "" {
			log.Fatal("Missing required env variables OMNISSM_ELASTIC_SEARCH_HTTP, OMNISSM_INDEX_NAME, OMNISSM_TYPE_NAME")
		}
		client, err := newElasticClient(esClient)
		if err != nil {
			log.Fatal(err)
		}

		for _, record := range event.Records {
			err = processEventRecord(ctx, record, client)
			if err != nil {
				log.Fatal(err)
			}
		}
	})
}

//get elastic client
func newElasticClient(url string) (*elastic.Client, error) {
	creds := credentials.NewEnvCredentials()
	signer := v4.NewSigner(creds)
	awsClient, err := aws_signing_client.New(signer, nil, "es", os.Getenv("AWS_REGION"))
	if err != nil {
		return nil, err
	}
	return elastic.NewClient(
		elastic.SetURL(url),
		elastic.SetScheme("https"),
		elastic.SetHttpClient(awsClient),
		elastic.SetSniff(false),
	)
}

func processEventRecord(ctx context.Context, record events.S3EventRecord, client *elastic.Client) error {
	//url encoded in response so we need to parse it
	key, err := url.QueryUnescape(record.S3.Object.Key)
	if err != nil {
		return err
	}
	result, err := s3Svc.GetObjectWithContext(ctx, &s3.GetObjectInput{
		Bucket: aws.String(record.S3.Bucket.Name),
		Key:    aws.String(key),
	})
	if err != nil {
		return err
	}
	keyParams := strings.Split(key, "/")
	//get m-id from key in filename
	id := strings.Split(keyParams[len(keyParams)-1], ".")[0]
	fmt.Println(id)
	fmt.Println("initializing session")
	fmt.Println("about to get item")
	fmt.Printf("tablename: %s\n", tableName)
	resp, err := dynamoSvc.GetItemWithContext(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(tableName),
		Key: map[string]*dynamodb.AttributeValue{
			"ManagedId": {
				S: aws.String(id),
			},
		},
	})

	fmt.Println(resp)
	fmt.Println(err)
	if err != nil {
		return err
	}

	if resp.Item == nil {
		return errors.New("Item not found with id: " + id)
	}

	fmt.Println("attempting to unmarshal")
	var entry map[string]interface{}
	if err := dynamodbattribute.UnmarshalMap(resp.Item, &entry); err != nil {
		return err
	}
	fmt.Println(entry)
	account := entry["AccountId"]
	region := entry["Region"]

	fmt.Println(account)
	fmt.Println(region)

	dec := json.NewDecoder(result.Body)
	defer result.Body.Close()
	for {
		var m map[string]interface{}
		if err := dec.Decode(&m); err == io.EOF {
			break
		} else if err != nil {
			return err
		}
		m["region"] = region
		m["accountId"] = account
		fmt.Println(m)
		_, err := client.Index().
			Index(indexName).
			Type(typeName).
			BodyJson(m).
			Do(ctx)
		if err != nil {
			return err
		}
	}

	return nil
}
