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

package configservice

import (
	"crypto/sha1"
	"encoding/json"
	"fmt"
	"strings"
)

type CloudWatchEventDetail struct {
	RecordVersion            string `json:"recordVersion"`
	MessageType              string `json:"messageType"`
	NotificationCreationTime string `json:"notificationCreationTime"`

	ConfigurationItemDetail
	OversizedConfigurationItemDetail
}

type ConfigurationItemDetail struct {
	ConfigurationItemDiff map[string]interface{} `json:"configurationItemDiff"`
	ConfigurationItem     ConfigurationItem      `json:"configurationItem"`
}

type ConfigurationItem struct {
	Configuration struct {
		ImageId            string             `json:"imageId"`
		KeyName            string             `json:"keyName"`
		Platform           string             `json:"platform"`
		SubnetId           string             `json:"subnetId"`
		State              ConfigurationState `json:"state"`
		InstanceType       string             `json:"instanceType"`
		IAMInstanceProfile struct {
			ARN string `json:"arn"`
			Id  string `json:"id"`
		} `json:"iamInstanceProfile"`
		Tags []struct {
			Key   string `json:"key"`
			Value string `json:"Value"`
		} `json:"tags"`
		VPCId string `json:"vpcId"`
	} `json:"configuration"`
	SupplementaryConfiguration   struct{}          `json:"supplementaryConfiguration"`
	Tags                         map[string]string `json:"tags"`
	ConfigurationItemVersion     string            `json:"configurationItemVersion"`
	ConfigurationItemCaptureTime string            `json:"configurationItemCaptureTime"`
	ConfigurationStateId         float64           `json:"configurationStateId"`
	AWSAccountId                 string            `json:"awsAccountId"`
	ConfigurationItemStatus      string            `json:"configurationItemStatus"`
	ResourceType                 string            `json:"resourceType"`
	ResourceId                   string            `json:"resourceId"`
	ARN                          string            `json:"arn"`
	AWSRegion                    string            `json:"awsRegion"`
	AvailabilityZone             string            `json:"availabilityZone"`
	ConfigurationStateMD5Hash    string            `json:"configurationStateMd5Hash"`
	ResourceCreationTime         string            `json:"resourceCreationTime"`
}

func (c *ConfigurationItem) Name() string {
	return fmt.Sprintf("%s-%s", c.AWSAccountId, c.ResourceId)
}

func (c *ConfigurationItem) Hash() string {
	return strings.ToUpper(fmt.Sprintf("%x", sha1.Sum([]byte(c.Name()))))
}

type OversizedConfigurationItemDetail struct {
	S3DeliverySummary struct {
		S3BucketLocation string `json:"s3BucketLocation"`
	} `json:"s3DeliverySummary"`
	ConfigurationItemSummary struct {
		ARN                          string `json:"ARN"`
		AWSAccountId                 string `json:"awsAccountId"`
		AWSRegion                    string `json:"awsRegion"`
		ChangeType                   string `json:"changeType"`
		ConfigurationItemCaptureTime string `json:"configurationItemCaptureTime"`
		ConfigurationItemStatus      string `json:"configurationItemStatus"`
		ConfigurationItemVersion     string `json:"configurationItemVersion"`
		ConfigurationStateId         int    `json:"configurationStateId"`
		ConfigurationStateMd5Hash    string `json:"configurationStateMd5Hash"`
		ResourceId                   string `json:"resourceId"`
		ResourceType                 string `json:"resourceType"`
	} `json:"configurationItemSummary"`
}

// ConfigurationState can be a string or object
type ConfigurationState string

func (s *ConfigurationState) UnmarshalJSON(b []byte) (err error) {
	var st struct {
		Name string `json:"name"`
	}
	err = json.Unmarshal(b, &st)
	if err == nil {
		*s = ConfigurationState(st.Name)
		return
	}
	return json.Unmarshal(b, (*string)(s))
}

func ConfigurationItemContentMap(ci ConfigurationItem) map[string]string {
	platform := "Linux"
	if ci.Configuration.Platform != "" {
		platform = ci.Configuration.Platform
	}
	content := map[string]string{
		"Region":       ci.AWSRegion,
		"AccountId":    ci.AWSAccountId,
		"Created":      ci.ResourceCreationTime,
		"InstanceId":   ci.ResourceId,
		"InstanceType": ci.Configuration.InstanceType,
		"InstanceRole": ci.Configuration.IAMInstanceProfile.ARN,
		"VPCId":        ci.Configuration.VPCId,
		"ImageId":      ci.Configuration.ImageId,
		"KeyName":      ci.Configuration.KeyName,
		"SubnetId":     ci.Configuration.SubnetId,
		"Platform":     platform,
		"State":        string(ci.Configuration.State),
	}
	return content
}
