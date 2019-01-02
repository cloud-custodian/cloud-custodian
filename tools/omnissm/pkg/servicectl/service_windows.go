// +build windows

package servicectl

import (
	"context"
	"time"

	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/mgr"

	"github.com/pkg/errors"
)

func openService(name string) (*mgr.Service, error) {
	m, err := mgr.Connect()
	if err != nil {
		return nil, errors.Wrap(err, "unable to open windows service manager")
	}
	svc, err := m.OpenService(name)
	if err != nil {
		return nil, errors.Wrapf(err, "unable to open windows service %s", name)
	}
	return svc, nil
}

// NOTE: on windows this will only control existing services
func newService(name string) (Service, error) {
	svc, err := openService(name)
	if err != nil {
		return nil, err
	}
	// close service handle until we need it later
	svc.Close()
	return &windows{name}, nil
}

type windows struct {
	name string
}

func (w *windows) wait(s *mgr.Service, timeout time.Duration, desired svc.State) error {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	for {
		st, err := s.Query()
		if err != nil {
			return errors.Wrapf(err, "unable to query status of service %s", w.name)
		}
		if st.State == desired {
			return nil
		}
		d := st.WaitHint
		if d == 0 {
			d = 10
		}
		select {
		case <-time.After(time.Duration(d) * time.Millisecond):
			// try again
		case <-ctx.Done():
			return ctx.Err()
		}
	}
}

func (w *windows) Start() error {
	s, err := openService(w.name)
	if err != nil {
		return err
	}
	defer s.Close()
	return w.start(s)
}

func (w *windows) start(s *mgr.Service) error {
	if err := s.Start(); err != nil {
		return errors.Wrapf(err, "unable to start service %s", w.name)
	}
	return w.wait(s, 30*time.Second, svc.Running)
}

func (w *windows) Stop() error {
	s, err := openService(w.name)
	if err != nil {
		return err
	}
	defer s.Close()
	return w.stop(s)
}

func (w *windows) stop(s *mgr.Service) error {
	st, err := s.Query()
	if err != nil {
		return errors.Wrapf(err, "error stopping service: unable to query status of service %s", w.name)
	}
	if st.State == svc.Stopped {
		return nil
	}
	if st, err := s.Control(svc.Stop); err != nil {
		return errors.Wrapf(err, "unable to stop service %s", w.name)
	} else if st.State == svc.Stopped {
		return nil
	}
	return w.wait(s, 30*time.Second, svc.Stopped)
}

func (w *windows) Restart() error {
	s, err := openService(w.name)
	if err != nil {
		return err
	}
	defer s.Close()

	if err := w.stop(s); err != nil {
		return err
	}
	return w.start(s)
}
