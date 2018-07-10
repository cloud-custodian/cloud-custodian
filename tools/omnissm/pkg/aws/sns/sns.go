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

package sns

import (
	"context"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/credentials/stscreds"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/sns"
	"github.com/aws/aws-sdk-go/service/sns/snsiface"
	"github.com/golang/time/rate"
	"github.com/pkg/errors"
)

type Config struct {
	*aws.Config

	AssumeRole string
}

type SNS struct {
	snsiface.SNSAPI

	config  *Config
	snsRate *rate.Limiter
}

func New(config *Config) *SNS {
	sess := session.New(config.Config)
	if config.AssumeRole != "" {
		config.Config.WithCredentials(stscreds.NewCredentials(sess, config.AssumeRole))
	}
	s := &SNS{
		SNSAPI:  sns.New(session.New(config.Config)),
		config:  config,
		snsRate: rate.NewLimiter(300, 300),
	}
	return s
}

func (s *SNS) Publish(topicArn string, msg []byte) error {
	_, err := s.SNSAPI.PublishWithContext(context.TODO(), &sns.PublishInput{
		Message:  aws.String(string(msg)),
		TopicArn: aws.String(topicArn),
	})
	return errors.Wrap(err, "sns.Publish")

}
