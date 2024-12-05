# Custodian OpenStack Support

Work in Progress - Not Ready For Use.

## Quick Start

### Installation

```
pip install c7n-openstack
```

### OpenStack Environment Configration

C7N will find cloud config for as few as 1 cloud and as many as you want to put in a config file.
It will read environment variables and config files, and it also contains some vendor specific default
values so that you don't have to know extra info to use OpenStack:

* If you have a config file, you will get the clouds listed in it
* If you have environment variables, you will get a cloud named envvars
* If you have neither, you will get a cloud named defaults with base defaults

Create a clouds.yml file:

```yaml
clouds:
 demo:
   region_name: RegionOne
   auth:
     username: 'admin'
     password: XXXXXXX
     project_name: 'admin'
     domain_name: 'Default'
     auth_url: 'https://montytaylor-sjc.openstack.blueboxgrid.com:5001/v2.0'
```

Please note: c7n will look for a file called `clouds.yaml` in the following locations:

* Current Directory
* ~/.config/openstack
* /etc/openstack

More information at [https://pypi.org/project/os-client-config](https://pypi.org/project/os-client-config)

### Create a c7n policy yaml file as follows:

```yaml
policies:
- name: demo
  resource: openstack.flavor
  filters:
  - type: value
    key: vcpus
    value: 1
    op: gt
```

### Run c7n and report the matched resources:

```sh
mkdir -p output
custodian run demo.yaml -s output
custodian report demo.yaml -s output --format grid
```

## Examples

filter examples:

```yaml
policies:
- name: test-flavor
  resource: openstack.flavor
  filters:
  - type: value
    key: vcpus
    value: 1
    op: gt
- name: test-project
  resource: openstack.project
  filters: []
- name: test-server-image
  resource: openstack.server
  filters:
  - type: image
    image_name: cirros-0.5.1
- name: test-user
  resource: openstack.user
  filters:
  - type: role
    project_name: demo
    role_name: _member_
    system_scope: false
- name: test-server-flavor
  resource: openstack.server
  filters:
  - type: flavor
    vcpus: 1
- name: test-server-age
  resource: openstack.server
  filters:
  - type: age
    op: lt
    days: 1
- name: test-server-tags
  resource: openstack.server
  filters:
  - type: tags
    tags:
    - key: a
      value: a
    - key: b
      value: c
    op: any
```
