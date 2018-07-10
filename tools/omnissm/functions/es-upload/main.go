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
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"os"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/awserr"
	"github.com/aws/aws-sdk-go/aws/credentials"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/aws/signer/v4"
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/aws/aws-xray-sdk-go/xray"
	"github.com/olivere/elastic"
	"github.com/sha1sum/aws_signing_client"
)

var xRayTracingEnabled = os.Getenv("_X_AMZN_TRACE_ID")

func main() {
	lambda.Start(func(ctx context.Context, event events.S3Event) {
		fmt.Println("lambda start")

		client, err := newElasticClient("https://vpc-cof-omnissm-2t62qkcyjh6vbjadenyifuqfki.us-east-1.es.amazonaws.com")
		fmt.Println("got client")
		if err != nil {
			fmt.Println("error block 1")
			fmt.Println(err.Error())
		}
		exists, err := client.IndexExists("twitter").Do(context.Background())
		if err != nil {
			fmt.Println("error block 2")
			fmt.Println(err.Error())
		}
		if !exists {
			fmt.Println("no index exists")
		}
		fmt.Println("finished")
		svc := s3.New(session.New())
		if xRayTracingEnabled != "" {
			xray.AWS(svc.Client)
		}
		for _, record := range event.Records {
			s3Record := record.S3
			input := &s3.GetObjectInput{
				Bucket: aws.String(s3Record.Bucket.Name),
				Key:    aws.String(s3Record.Object.Key),
			}

			result, err := svc.GetObject(input)
			if err != nil {
				if aerr, ok := err.(awserr.Error); ok {
					switch aerr.Code() {
					case s3.ErrCodeNoSuchKey:
						fmt.Println(s3.ErrCodeNoSuchKey, aerr.Error())
					default:
						fmt.Println(aerr.Error())
					}
				} else {
					fmt.Println(err.Error())
				}
				return
			}

			fmt.Println(result)
			body, err := ioutil.ReadAll(result.Body)
			dec := json.NewDecoder(bytes.NewReader(body))
			for {
				var m map[string]interface{}
				if err := dec.Decode(&m); err == io.EOF {
					break
				} else if err != nil {
					log.Fatal(err)
				}
				fmt.Println(m["cmdline"])
			}
			fmt.Printf("[%s - %s] Bucket = %s, Key = %s \n", record.EventSource, record.EventTime, s3Record.Bucket.Name, s3Record.Object.Key)
			fmt.Println(s3Record)
		}
	})
}

//get elastic client
func newElasticClient(url string) (*elastic.Client, error) {
	creds := credentials.NewEnvCredentials()
	fmt.Println("creds")
	fmt.Println(creds)
	signer := v4.NewSigner(creds)
	fmt.Println("signer")
	fmt.Println(signer)
	awsClient, err := aws_signing_client.New(signer, nil, "es", "us-east-1")
	if err != nil {
		return nil, err
	}
	fmt.Println("awsClient")
	fmt.Println(awsClient)
	return elastic.NewClient(
		elastic.SetURL(url),
		elastic.SetScheme("https"),
		elastic.SetHttpClient(awsClient),
		elastic.SetSniff(false), // See note below
	)
}
