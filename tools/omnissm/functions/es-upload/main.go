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
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"os"

	"github.com/aws/aws-xray-sdk-go/xray"

	"github.com/aws/aws-lambda-go/events"
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
	xRayTracingEnabled = os.Getenv("_X_AMZN_TRACE_ID")
	esClient           = os.Getenv("OMNISSM_ELASTIC_SEARCH_HTTP")
	indexName          = os.Getenv("OMNISSM_INDEX_NAME")
	typeName           = os.Getenv("OMNISSM_TYPE_NAME")
	mappingBucket      = os.Getenv("OMNISSM_MAPPING_BUCKET")
	mappingKey         = os.Getenv("OMNISSM_MAPPING_KEY")
	s3Svc              = s3.New(session.New())
)

func main() {
	lambda.Start(func(ctx context.Context, event events.S3Event) {
		if xRayTracingEnabled != "" {
			xray.AWS(s3Svc.Client)
		}
		if esClient == "" || indexName == "" || typeName == "" {
			log.Fatal("Missing required env variables OMNISSM_ELASTIC_SEARCH_HTTP, OMNISSM_INDEX_NAME, OMNISSM_TYPE_NAME")
		}
		fmt.Printf("%s %s %s %s %s\n", esClient, indexName, typeName, mappingBucket, mappingKey)
		client, err := newElasticClient(esClient)
		if err != nil {
			log.Fatal(err)
		}
		exists, err := client.IndexExists(indexName).Do(context.Background())
		if err != nil {
			log.Fatal(err)
		}
		if !exists {
			err := createIndex(ctx, client)
			if err != nil {
				log.Fatal(err)
			}
		}

		for _, record := range event.Records {
			err = processEventRecord(ctx, record, client)
			if err != nil {
				log.Fatal(err)
			}
		}
	})
}

func createIndex(ctx context.Context, client *elastic.Client) error {
	if mappingBucket == "" || mappingKey == "" {
		return errors.New("Missing mapping bucket or key, unable to create new ES index")
	}

	input := &s3.GetObjectInput{
		Bucket: aws.String(mappingBucket),
		Key:    aws.String(mappingKey),
	}

	result, err := s3Svc.GetObject(input)
	if err != nil {
		return err
	}
	buf := new(bytes.Buffer)
	buf.ReadFrom(result.Body)
	mapping := buf.String()

	createIndex, err := client.CreateIndex(indexName).BodyString(mapping).Do(ctx)
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
	awsClient, err := aws_signing_client.New(signer, nil, "es", "us-east-1")
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

func getObjFromS3(record events.S3EventRecord) (*s3.GetObjectOutput, error) {
	s3Record := record.S3
	input := &s3.GetObjectInput{
		Bucket: aws.String(s3Record.Bucket.Name),
		Key:    aws.String(s3Record.Object.Key),
	}

	result, err := s3Svc.GetObject(input)
	if err != nil {
		return nil, err
	}

	return result, nil
}

func processEventRecord(ctx context.Context, record events.S3EventRecord, client *elastic.Client) error {
	result, err := getObjFromS3(record)
	if err != nil {
		return err
	}

	body, err := ioutil.ReadAll(result.Body)
	if err != nil {
		return err
	}

	dec := json.NewDecoder(bytes.NewReader(body))
	for {
		var m map[string]interface{}
		if err := dec.Decode(&m); err == io.EOF {
			break
		} else if err != nil {
			return err
		}
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
