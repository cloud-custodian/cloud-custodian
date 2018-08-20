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
	"io"
	"io/ioutil"
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
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/aws/aws-xray-sdk-go/xray"
	"github.com/olivere/elastic"
	"github.com/sha1sum/aws_signing_client"
)

type myOutput struct {
	requiredTags
	processObj
	resourceObj
}
type tagObj struct {
	Key   string `json:"Key"`
	Value string `json:"Value"`
}

type requiredTags struct {
	ASV             string
	CMDBEnvironment string
	OwnerContact    string
}

type processObj struct {
	Cmdline       string `json:"cmdline"`
	Rss           string `json:"rss"`
	CreateTime    string `json:"create_time"`
	WriteBytes    string `json:"write_bytes"`
	Name          string `json:"name"`
	Pid           string `json:"pid"`
	ThreadCount   string `json:"thread_count"`
	NumFds        string `json:"num_fds"`
	ReadBytes     string `json:"read_bytes"`
	User          string `json:"user"`
	Vms           string `json:"vms"`
	ResourceId    string `json:"resourceId"`
	captureTime   string `json:"captureTime"`
	schemaVersion string `json:"schemaVersion"`
}

type resourceObj struct {
	KeyName      string `json:"KeyName"`
	AccountId    string `json:"AccountId"`
	Platform     string `json:"Platform"`
	InstanceId   string `json:"InstanceId"`
	VPCId        string `json:"VPCId"`
	State        string `json:"State"`
	ImageId      string `json:"ImageId"`
	InstanceRole string `json:"InstanceRole"`
	Region       string `json:"Region"`
	SubnetId     string `json:"SubnetId"`
	InstanceType string `json:"InstanceType"`
	Created      string `json:"Created"`
}

var (
	xRayTracingEnabled = os.Getenv("_X_AMZN_TRACE_ID")
	esClient           = os.Getenv("OMNISSM_ELASTIC_SEARCH_HTTP")
	indexName          = os.Getenv("OMNISSM_INDEX_NAME")
	typeName           = os.Getenv("OMNISSM_TYPE_NAME")
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
	var bucketName = record.S3.Bucket.Name
	//url encoded in response so we need to parse it
	bucketKey, err := url.QueryUnescape(record.S3.Object.Key)
	if err != nil {
		return err
	}

	tags, err := getTags(ctx, bucketName, bucketKey)
	if err != nil {
		return err
	}

	resource, err := getResourceInfo(ctx, bucketName, bucketKey)
	if err != nil {
		return err
	}

	//get process file
	processFile, err := s3Svc.GetObjectWithContext(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucketName),
		Key:    aws.String(bucketKey),
	})
	if err != nil {
		return err
	}
	defer processFile.Body.Close()
	dec := json.NewDecoder(processFile.Body)

	for {
		var process processObj
		if err := dec.Decode(&process); err == io.EOF {
			break
		} else if err != nil {
			return err
		}

		output := myOutput{
			requiredTags: tags,
			resourceObj:  resource,
			processObj:   process,
		}
		_, error := client.Index().
			Index(indexName).
			Type(typeName).
			BodyJson(output).
			Do(ctx)
		if err != nil {
			return error
		}
	}

	return nil
}

//Attempt to pull file from s3 with the same manager id, iterate over returned tags
func getTags(ctx context.Context, bucketName string, bucketKey string) (requiredTags, error) {
	var tags requiredTags
	//get tags file from s3
	tagsRes, err := s3Svc.GetObjectWithContext(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucketName),
		Key:    aws.String(strings.Replace(bucketKey, "Custom:ProcessInfo", "AWS:Tag", 1)),
	})
	if err != nil {
		return tags, err
	}
	defer tagsRes.Body.Close()
	//setup decoder to iterate over individual tag objects
	dec := json.NewDecoder(tagsRes.Body)
	if err != nil {
		return tags, err
	}

	for {
		var aTagObj tagObj
		if err := dec.Decode(&aTagObj); err == io.EOF {
			break
		} else if err != nil {
			return tags, err
		}
		//search for specific tags
		switch aTagObj.Key {
		case "ASV":
			tags.ASV = aTagObj.Value
		case "CMDBEnvironment":
			tags.CMDBEnvironment = aTagObj.Value
		case "OwnerContact":
			tags.OwnerContact = aTagObj.Value
		}
	}
	return tags, nil
}

func getResourceInfo(ctx context.Context, bucketName string, bucketKey string) (resourceObj, error) {
	var resource resourceObj
	//get resource file
	resourceFile, err := s3Svc.GetObjectWithContext(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucketName),
		Key:    aws.String(strings.Replace(bucketKey, "Custom:ProcessInfo", "Custom:CloudInfo", 1)),
	})

	if err != nil {
		return resource, err
	}
	defer resourceFile.Body.Close()

	resourceByteArray, err := ioutil.ReadAll(resourceFile.Body)
	if err != nil {
		return resource, err
	}

	err = json.Unmarshal(resourceByteArray, resource)
	if err != nil {
		return resource, err
	}

	return resource, nil
}
