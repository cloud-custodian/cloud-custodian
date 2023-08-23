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

package sysmon

import (
	"time"

	"github.com/rs/zerolog/log"
	"github.com/shirou/gopsutil/process"
)

type Process struct {
	Pid         int32     `json:"pid,string"`
	Name        string    `json:"name"`
	User        string    `json:"user"`
	Cmdline     string    `json:"cmdline"`
	ReadBytes   uint64    `json:"read_bytes,string"`
	WriteBytes  uint64    `json:"write_bytes,string"`
	NumFDs      int       `json:"num_fds,string"`
	CreateTime  time.Time `json:"create_time,string"`
	ThreadCount int       `json:"thread_count,string"`
	RSS         int       `json:"rss,string"`
	VMS         int       `json:"vms,string"`
}

func ListAllProcesses() ([]Process, error) {
	pids, err := process.Pids()
	if err != nil {
		return nil, err
	}
	processes := make([]Process, 0)
	for _, pid := range pids {
		p, err := process.NewProcess(pid)
		if err != nil {
			continue
		}
		process := Process{Pid: p.Pid}
		name, err := p.Name()
		if err != nil {
			// TODO(chris): replace with multi-error
			log.Info().Err(err).Msgf("cannot get process name: %v", pid)
		} else {
			process.Name = name
		}
		user, err := p.Username()
		if err != nil {
			log.Debug().Err(err).Msgf("cannot get process username: %v", pid)
		} else {
			process.User = user
		}
		cmdline, err := p.Cmdline()
		if err != nil {
			log.Info().Err(err).Msgf("cannot get process cmdline: %v", pid)
		} else {
			process.Cmdline = cmdline
		}
		iocounters, err := p.IOCounters()
		if err != nil {
			log.Debug().Err(err).Msgf("cannot get process i/o counters: %v", pid)
		} else {
			process.ReadBytes = iocounters.ReadBytes
			process.WriteBytes = iocounters.WriteBytes
		}
		fdcount, err := p.NumFDs()
		if err != nil {
			log.Debug().Err(err).Msgf("cannot get process file descriptor count: %v", pid)
		} else {
			process.NumFDs = int(fdcount)
		}
		created, err := p.CreateTime()
		if err != nil {
			log.Debug().Err(err).Msgf("cannot get process create time: %v", pid)
		} else {
			process.CreateTime = time.Unix(created/1000, 0)
		}
		threadcount, err := p.NumThreads()
		if err != nil {
			log.Debug().Err(err).Msgf("cannot get process thread count: %v", pid)
		} else {
			process.ThreadCount = int(threadcount)
		}
		memstat, err := p.MemoryInfo()
		if err != nil {
			log.Debug().Err(err).Msgf("cannot get process memory info: %v", pid)
		} else {
			process.RSS = int(memstat.RSS)
			process.VMS = int(memstat.VMS)
		}
		processes = append(processes, process)
	}
	return processes, nil
}
