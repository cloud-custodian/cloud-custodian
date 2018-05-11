package main

import (
	"crypto/sha1"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// cloudWatchEvent is only needed to unmarshal specific fields of a
// CloudWatch event, therefore is not exported.
type cloudWatchEvent struct {
	Version    string                `json:"version"`
	ID         string                `json:"id"`
	DetailType string                `json:"detail-type"`
	Source     string                `json:"source"`
	AccountId  string                `json:"account"`
	Time       time.Time             `json:"time"`
	Region     string                `json:"region"`
	Resources  []string              `json:"resources"`
	Detail     cloudWatchEventDetail `json:"detail"`
}

type cloudWatchEventDetail struct {
	RecordVersion            string                 `json:"recordVersion"`
	MessageType              string                 `json:"messageType"`
	ConfigurationItemDiff    map[string]interface{} `json:"configurationItemDiff"`
	NotificationCreationTime string                 `json:"notificationCreationTime"`
	ConfigurationItem        configurationItem      `json:"configurationItem"`
}

type configurationItem struct {
	Configuration struct {
		ImageId            string             `json:"imageId"`
		KeyName            string             `json:"keyName"`
		Platform           string             `json:"platform"`
		SubnetId           string             `json:"subnetId"`
		State              configurationState `json:"state"`
		InstanceType       string             `json:"instanceType"`
		IAMInstanceProfile struct {
			ARN string `json:"arn"`
			Id  string `json:"id"`
		} `json:"iamInstanceProfile"`
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

func (c *configurationItem) getIdentity() string {
	return strings.ToUpper(fmt.Sprintf("%x", sha1.Sum([]byte(fmt.Sprintf("%s-%s", c.AWSAccountId, c.ResourceId)))))
}

// configurationState can be a string or object
type configurationState string

func (s *configurationState) UnmarshalJSON(b []byte) (err error) {
	var st struct {
		Code int    `json:"code"`
		Name string `json:"name"`
	}
	err = json.Unmarshal(b, &st)
	if err == nil {
		*s = configurationState(st.Name)
		return
	}
	return json.Unmarshal(b, (*string)(s))
}
