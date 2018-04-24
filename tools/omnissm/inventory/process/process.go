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

	"github.com/shirou/gopsutil/process"
)

func main() {

	procs, _ := process.Pids()
	procInfos := make([]map[string]interface{}, 0)

	for _, pid := range procs {
		procMap := map[string]interface{}{}
		proc, err := process.NewProcess(int32(pid))
		if err != nil {
			continue
		}
		procMap["process_pid"] = int32(proc.Pid)

		name, err := proc.Name()
		if err == nil {
			procMap["process_name"] = name
		} else {
			fmt.Println("Error name", pid, err)
		}

		user, err := proc.Username()
		procMap["process_user"] = user

		/* A bit expensive for busy systems.

		// ipv4 only, capture listen ports, requires all conn enum.
			conns, err := proc.Connections()
			if err == nil {
				ports := make([]uint32, 0)

				for _, conn := range conns {
					if conn.Status != "LISTEN" {
						continue
					}
					ports = append(ports, conn.Laddr.Port)
				}
				if len(ports) > 0 {
					procMap["listen_ports"] = ports
				}
			}
		*/

		cmdline, err := proc.Cmdline()
		if err == nil {
			procMap["process_cmdline"] = cmdline
		} else {
			fmt.Println("Error cmdline", pid, err)
		}

		iocounters, err := proc.IOCounters()
		if err == nil {
			procMap["stat_read_bytes"] = iocounters.ReadBytes
			procMap["stat_write_bytes"] = iocounters.WriteBytes
		}

		fdcount, err := proc.NumFDs()
		if err == nil {
			procMap["stats_fds"] = fdcount
		}

		created, err := proc.CreateTime()
		if err == nil {
			procMap["process_create_time"] = created
		}
		threadcount, err := proc.NumThreads()
		if err == nil {
			procMap["stats_thread_count"] = threadcount
		}

		memstat, err := proc.MemoryInfo()
		if err == nil {
			procMap["stat_rss"] = memstat.RSS
			procMap["stat_vms"] = memstat.VMS
		}
		if len(procMap) > 0 {
			procInfos = append(procInfos, procMap)
		}
	}

	inventory := map[string]interface{}{}
	processes := map[string]interface{}{}
	inventory["SchemaVersion"] = "1.0"
	inventory["TypeName"] = "Custom:ProcessInfo"
	processes["Processes"] = procInfos
	inventory["Content"] = processes
	serialized, _ := json.MarshalIndent(inventory, "", "   ")
	fmt.Println(string(serialized))
}
