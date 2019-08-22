Compute Engine - Enforce minimal CPU utilization target for autoscalers
=======================================================================

In the example below, the policy checks the CPU utilization target of newly added autoscalers and modifies it when needed
guaranteeing the target won't be less than 80%.

.. code-block:: yaml

    vars:
      min-utilization-target: &min-utilization-target 0.8
    policies:
      - name: gcp-autoscalers-enforced
        resource: gcp.autoscaler
        mode:
          type: gcp-audit
          methods:
            - v1.compute.autoscalers.insert
        filters:
          - type: value
            key: autoscalingPolicy.cpuUtilization.utilizationTarget
            op: less-than
            value: *min-utilization-target
        actions:
          - type: set
            cpuUtilization:
              utilizationTarget: 0.8
