package main

import (
	"encoding/json"
	"io/ioutil"
	"net/http"
	"os/exec"
	"strings"

	"github.com/rs/zerolog/log"
)

const (
	// DefaultLinuxSSMRegistrationPath Linux Path to Agent Registration State
	DefaultLinuxSSMRegistrationPath = "/var/lib/amazon/ssm/registration"

	// IdentityDocumentURL EC2 metadata server instance identity document
	IdentityDocumentURL = "http://169.254.169.254/latest/dynamic/instance-identity/document"

	// IdentitySignatureURL RSA SHA256 Signature of identity document
	IdentitySignatureURL = "http://169.254.169.254/latest/dynamic/instance-identity/signature"
)

// InstanceInfo contains information for instances registered with SSM.  This
// is collected from the output of the following command:
//    ssm-cli get-instance-information
type InstanceInfo struct {
	InstanceId     string `json:"instance-id"`
	Region         string `json:"region"`
	ReleaseVersion string `json:"release-version"`
}

func getInstanceInformation() (*InstanceInfo, error) {
	out, err := exec.Command(SSMCLI.Path(), "get-instance-information").Output()
	if err != nil {
		return nil, err
	}
	var info InstanceInfo
	if err := json.Unmarshal(out, &info); err != nil {
		return nil, err
	}
	return &info, nil
}

func readRegistrationFile(path string) (id string, err error) {
	data, err := ioutil.ReadFile(path)
	if err != nil {
		return
	}
	var s struct {
		ManagedInstanceID string
		Region            string
	}
	err = json.Unmarshal(data, &s)
	if err != nil {
		return
	}
	if strings.HasPrefix(s.ManagedInstanceID, "mi-") {
		return s.ManagedInstanceID, nil
	}
	return
}

type InstanceIdentity struct {
	Document  string
	Signature string
}

func getLocalInstanceIdentity() *InstanceIdentity {
	doc, err := fetchContent(IdentityDocumentURL)
	if err != nil {
		log.Debug().Err(err).Msg("cannot get instance document")
	}
	sig, err := fetchContent(IdentitySignatureURL)
	if err != nil {
		log.Debug().Err(err).Msg("cannot get instance signature")
	}
	return &InstanceIdentity{string(doc), string(sig)}
}

func fetchContent(uri string) ([]byte, error) {
	response, err := http.Get(uri)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	body, err := ioutil.ReadAll(response.Body)
	if err != nil {
		return nil, err
	}
	return body, nil
}
