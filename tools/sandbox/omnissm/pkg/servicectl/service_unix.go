// +build !windows

package servicectl

import (
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/pkg/errors"
)

func newService(name string) (Service, error) {
	switch {
	case isSystemd():
		cmd, err := exec.LookPath("systemctl")
		if err != nil {
			return nil, errors.WithStack(err)
		}
		return &systemd{cmd, name}, nil
	case isUpstart():
		cmd, err := exec.LookPath("initctl")
		if err != nil {
			return nil, errors.WithStack(err)
		}
		return &upstart{cmd, name}, nil
	case isSysV():
		cmd, err := exec.LookPath("service")
		if err != nil {
			return nil, errors.WithStack(err)
		}
		return &sysV{cmd, name}, nil
	}
	return nil, errors.Errorf("cannot detect service manager")
}

type upstart struct {
	cmd, name string
}

func (u *upstart) Start() error {
	_, err := run(u.cmd, "start", u.name)
	return err
}
func (u *upstart) Stop() error {
	_, err := run(u.cmd, "stop", u.name)
	return err
}

func (u *upstart) Restart() error {
	// ignoring error for cases where Stop is called and the service is not
	// already running
	_ = u.Stop()
	time.Sleep(50 * time.Millisecond)
	return u.Start()
}

type systemd struct {
	cmd, name string
}

func (s *systemd) Start() error {
	_, err := run(s.cmd, "start", s.name)
	return err
}
func (s *systemd) Stop() error {
	_, err := run(s.cmd, "stop", s.name)
	return err
}

func (s *systemd) Restart() error {
	_, err := run(s.cmd, "restart", s.name)
	return err
}

type sysV struct {
	cmd, name string
}

func (s *sysV) Start() error {
	_, err := run(s.cmd, s.name, "start")
	return err
}
func (s *sysV) Stop() error {
	_, err := run(s.cmd, s.name, "stop")
	return err
}

func (s *sysV) Restart() error {
	err := s.Stop()
	if err != nil {
		return err
	}
	time.Sleep(50 * time.Millisecond)
	return s.Start()
}

func isSystemd() bool {
	if _, err := os.Stat("/run/systemd/system"); err == nil {
		return true
	}
	return false
}

func isSysV() bool {
	if _, err := os.Stat("/usr/sbin/service"); err == nil {
		return true
	}
	return false
}

func isUpstart() bool {
	if _, err := os.Stat("/sbin/upstart-udev-bridge"); err == nil {
		return true
	}
	if _, err := os.Stat("/sbin/init"); err == nil {
		if out, err := exec.Command("/sbin/init", "--version").Output(); err == nil {
			if strings.Contains(string(out), "init (upstart") {
				return true
			}
		}
	}
	return false
}
