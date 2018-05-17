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

// Package awsutil provides helpers for interacting with aws-sdk-go
package awsutil

import (
	"os"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/ec2metadata"
	"github.com/aws/aws-sdk-go/aws/session"
)

// LoadDefaultAWSConfig returns a new aws.Config with a region picked
// automatically. If the environment variable AWS_REGION was not specified, an
// attempt to use ec2metadata will be made to discern the region.
func LoadDefaultAWSConfig() (*aws.Config, error) {
	region := os.Getenv("AWS_REGION")
	if region == "" {
		var err error
		region, err = getCurrentRegion()
		if err != nil {
			return nil, err
		}
	}
	return aws.NewConfig().WithRegion(region), nil

}

func getCurrentRegion() (string, error) {
	svc := ec2metadata.New(session.New(aws.NewConfig()))
	resp, err := svc.GetInstanceIdentityDocument()
	if err != nil {
		return "", err
	}
	return resp.Region, nil
}
