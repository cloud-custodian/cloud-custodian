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
	"bytes"
	"context"
	"errors"
	"log"
	"os"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/credentials"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/aws/signer/v4"
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/olivere/elastic"
	"github.com/sha1sum/aws_signing_client"
)

var (
	esClient      = os.Getenv("OMNISSM_ELASTIC_SEARCH_HTTP")
	indexName     = os.Getenv("OMNISSM_INDEX_NAME")
	typeName      = os.Getenv("OMNISSM_TYPE_NAME")
	mappingBucket = os.Getenv("OMNISSM_MAPPING_BUCKET")
	mappingKey    = os.Getenv("OMNISSM_MAPPING_KEY")
	s3Svc         = s3.New(session.New())
)

func main() {
	lambda.Start(func(ctx context.Context) {
		if esClient == "" || indexName == "" || typeName == "" {
			log.Fatal("Missing required env variables OMNISSM_ELASTIC_SEARCH_HTTP, OMNISSM_INDEX_NAME, OMNISSM_TYPE_NAME")
		}
		client, err := newElasticClient(esClient)
		if err != nil {
			log.Fatal(err)
		}
		exists, err := client.IndexExists(indexName).Do(context.Background())
		if err != nil {
			log.Fatal(err)
		}
		if !exists {
			err := createIndex(client)
			if err != nil {
				log.Fatal(err)
			}
		}
	})
}

func createIndex(client *elastic.Client) error {
	if mappingBucket == "" || mappingKey == "" {
		return errors.New("Missing mapping bucket or key, unable to create new ES index")
	}

	result, err := s3Svc.GetObject(&s3.GetObjectInput{
		Bucket: aws.String(mappingBucket),
		Key:    aws.String(mappingKey),
	})
	if err != nil {
		return err
	}
	buf := new(bytes.Buffer)
	buf.ReadFrom(result.Body)
	mapping := buf.String()

	createIndex, err := client.CreateIndex(indexName).BodyString(mapping).Do(context.Background())
	if err != nil {
		return errors.New(err.Error())
	}

	if !createIndex.Acknowledged {
		return errors.New("Create Index not Acknowledged")
	}
	return nil
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
