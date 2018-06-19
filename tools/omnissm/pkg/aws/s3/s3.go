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

package s3

import (
	"io/ioutil"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/credentials/stscreds"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/aws/aws-sdk-go/service/s3/s3iface"
)

type Config struct {
	*aws.Config

	AssumeRole string
}
type S3 struct {
	s3iface.S3API

	config *Config
}

func New(config *Config) *S3 {
	sess := session.New(config.Config)
	if config.AssumeRole != "" {
		config.Config.WithCredentials(stscreds.NewCredentials(sess, config.AssumeRole))
	}
	s := &S3{
		S3API:  s3.New(session.New(config.Config)),
		config: config,
	}
	return s
}

func (s *S3) GetObject(path string) ([]byte, error) {
	u, err := ParseURL(path)
	if err != nil {
		return nil, err
	}
	resp, err := s.S3API.GetObject(&s3.GetObjectInput{
		Bucket: aws.String(u.Bucket),
		Key:    aws.String(u.Path),
	})
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	return data, nil
}
