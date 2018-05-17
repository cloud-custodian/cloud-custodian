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

package identity

import (
	"crypto/sha1"
	"fmt"
	"io/ioutil"
	"net/http"
	"strings"

	"github.com/rs/zerolog/log"
)

func Hash(parts ...string) string {
	return strings.ToUpper(fmt.Sprintf("%x", sha1.Sum([]byte(strings.Join(parts, "-")))))
}

// A Document provides a struct for EC2 instance identity documents to be
// unmarshaled.
type Document struct {
	AvailabilityZone string `json:"availabilityZone"`
	Region           string `json:"region"`
	InstanceId       string `json:"instanceId"`
	AccountId        string `json:"accountId"`
	InstanceType     string `json:"instanceType"`
}

// Name returns the logical name for the instance described in the identity
// document and is the value used when deriving the unique identifier hash.
func (d *Document) Name() string {
	return fmt.Sprintf("%s-%s", d.AccountId, d.InstanceId)
}

const (
	// The EC2 metadata service URL for the instance identity document.
	IdentityDocumentURL = "http://169.254.169.254/latest/dynamic/instance-identity/document"

	// The EC2 metadata service URL for the instance identity document signature (RSA SHA256).
	IdentitySignatureURL = "http://169.254.169.254/latest/dynamic/instance-identity/signature"
)

// GetLocalInstanceDocument returns the instance identity document from the EC2
// metadata service.
func GetLocalInstanceDocument() []byte {
	resp, err := http.Get(IdentityDocumentURL)
	if err != nil {
		log.Debug().Err(err).Msg("cannot get instance document")
		return nil
	}
	defer resp.Body.Close()
	data, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		log.Debug().Err(err).Msg("cannot get instance document")
		return nil
	}
	return data
}

// GetLocalInstanceDocument returns the signature for the instance identity
// document from the EC2 metadata service.
func GetLocalInstanceSignature() []byte {
	resp, err := http.Get(IdentitySignatureURL)
	if err != nil {
		log.Debug().Err(err).Msg("cannot get instance document")
		return nil
	}
	defer resp.Body.Close()
	data, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		log.Debug().Err(err).Msg("cannot get instance document")
		return nil
	}
	return data
}
