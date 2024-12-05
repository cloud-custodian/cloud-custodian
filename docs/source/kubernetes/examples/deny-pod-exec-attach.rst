Denying Pod Exec or Attach
==========================

Custodian can deny users from connecting to a pod based on the event which includes
metadata such as their groups:

.. code-block:: yaml

  policies:
    - name: test-deny-pod-exec-based-on-group
      resource: k8s.pod
      mode:
        type: k8s-admission
        subresource: ['exec', 'attach']
        on-match: deny
        operations:
        - CONNECT
      filters:
      - type: event
        key: request.userInfo.groups
        value: allow-exec
        op: not-in
        value_type: swap


Alternatively, you can also deny based on the namespace or pod name the user is trying
to attach or exec to:

.. code-block:: yaml

  policies:
    - name: test-deny-pod-exec-based-on-namespace
      resource: k8s.pod
      mode:
        type: k8s-admission
        subresource: ['exec', 'attach']
        on-match: deny
        operations:
        - CONNECT
      filters:
      - type: event
        key: request.namespace
        value: 
          - default
          - database
        op: in

    - name: test-deny-pod-exec-based-on-pod-name
      resource: k8s.pod
      mode:
        type: k8s-admission
        subresource: ['exec', 'attach']
        on-match: deny
        operations:
        - CONNECT
      filters:
      - type: event
        key: request.name
        value: .*production-db.*
        op: regex
