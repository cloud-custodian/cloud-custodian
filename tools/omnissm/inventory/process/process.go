/*
Copyright 2018 Capital One Services, LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.

You may obtain a copy of the License at
	http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/
package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"os/exec"
	"strconv"
	"time"

	"github.com/shirou/gopsutil/process"
)

// SSMHostInfo output of ssm-cli get-instance-information
type SSMHostInfo struct {
	InstanceID     string `json:"instance-id"`
	Region         string `json:"region"`
	ReleaseVersion string `json:"release-version"`
}

func newSSMHost() (*SSMHostInfo, error) {
	ssmInfoCmd := exec.Command("/usr/bin/ssm-cli", "get-instance-information")
	ssmInfoOut, err := ssmInfoCmd.Output()
	if err != nil {
		return nil, err
	}

	ssmInfo := SSMHostInfo{}
	err = json.Unmarshal(ssmInfoOut, &ssmInfo)
	if err != nil {
		return nil, err
	}
	return &ssmInfo, nil
}

func getProcesses() []map[string]string {

	procs, _ := process.Pids()
	procInfos := make([]map[string]string, 0)

	for _, pid := range procs {
		procMap := map[string]string{}
		proc, err := process.NewProcess(int32(pid))
		if err != nil {
			continue
		}
		procMap["process_pid"] = strconv.Itoa(int(proc.Pid))

		name, err := proc.Name()
		if err == nil {
			procMap["process_name"] = name
		} else {
			fmt.Println("Error name", pid, err)
		}

		user, err := proc.Username()
		procMap["process_user"] = user

		cmdline, err := proc.Cmdline()
		if err == nil {
			procMap["process_cmdline"] = cmdline
		} else {
			fmt.Println("Error cmdline", pid, err)
		}

		iocounters, err := proc.IOCounters()
		if err == nil {
			procMap["stat_read_bytes"] = strconv.FormatInt(int64(iocounters.ReadBytes), 10)
			procMap["stat_write_bytes"] = strconv.FormatInt(int64(iocounters.WriteBytes), 10)
		}

		fdcount, err := proc.NumFDs()
		if err == nil {
			procMap["stats_fds"] = strconv.Itoa(int(fdcount))
		}

		created, err := proc.CreateTime()
		if err == nil {
			procMap["process_create_time"] = strconv.FormatInt(created, 10)
		}
		threadcount, err := proc.NumThreads()
		if err == nil {
			procMap["stats_thread_count"] = strconv.Itoa(int(threadcount))
		}

		memstat, err := proc.MemoryInfo()
		if err == nil {
			procMap["stat_rss"] = strconv.Itoa(int(memstat.RSS))
			procMap["stat_vms"] = strconv.Itoa(int(memstat.VMS))
		}
		if len(procMap) > 0 {
			procInfos = append(procInfos, procMap)
		}
	}
	return procInfos
}

func main() {

	log.Println("Process Inventory Starting")
	ssmInfo, err := newSSMHost()
	if err != nil {
		log.Fatalf("Unable to find ssm host information: %s", err)
	}

	now := time.Now().UTC()
	inventory := map[string]interface{}{
		"SchemaVersion": "1.0",
		"TypeName":      "Custom:ProcessInfo",
		"CaptureTime":   now.Format("2006-01-02T15:04:05Z"),
		"Content":       getProcesses(),
	}

	serialized, _ := json.MarshalIndent(inventory, "", "   ")
	err = ioutil.WriteFile(
		fmt.Sprintf("/var/lib/amazon/ssm/%s/inventory/custom/ProcessInfo.json", ssmInfo.InstanceID),
		serialized, 0644)

	if err != nil {
		log.Fatalf("Error writing inventory %s", err)
	}
	log.Println("Process Inventory Complete")

}
