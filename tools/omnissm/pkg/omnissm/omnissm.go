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

package omnissm

import (
	"github.com/pkg/errors"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/s3"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/sns"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/sqs"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ssm"
)

type OmniSSM struct {
	*Config
	*Registrations
	*s3.S3
	*sns.SNS
	*sqs.SQS
	*ssm.SSM
}

func New(config *Config) (*OmniSSM, error) {
	o := &OmniSSM{
		Config: config,
		Registrations: NewRegistrations(&RegistrationsConfig{
			Config:    config.Config,
			TableName: config.RegistrationsTable,
		}),
		SNS: sns.New(&sns.Config{
			Config:     config.Config,
			AssumeRole: config.S3DownloadRole,
		}),
		SSM: ssm.New(&ssm.Config{
			Config:       config.Config,
			InstanceRole: config.InstanceRole,
		}),
		S3: s3.New(&s3.Config{
			Config:     config.Config,
			AssumeRole: config.S3DownloadRole,
		}),
	}
	if config.QueueName != "" {
		var err error
		o.SQS, err = sqs.New(&sqs.Config{
			Config:         config.Config,
			MessageGroupId: "omnissm-event-stream",
			QueueName:      config.QueueName,
		})

		if err != nil {
			return nil, errors.Wrap(err, "cannot initialize SQS")
		}
	}

	if config.XRayTracingEnabled != "" {
		SetupTracing(o)
	}

	return o, nil
}
