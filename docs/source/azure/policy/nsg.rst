Network Security Groups
=======================

Available Types:
----------------
    - ingress - Inbound Security Rules
    - egress - Outbound Security Rules

Available Filters:
------------------
    - FromPort
        - Lower bound of port range (inclusive)
        - Can be used alone to indicate all ports at or above number
        - Can be used with ToPort to create range
    - ToPort
        - Upper bound of port range (inclusive)
        - Can be used alone to indicate all ports at or below number
        - Can be used with FromPort to create range
    - Ports
        - Filter on ports contained in list.
        - Ex: Ports: [8080,8081]
    - OnlyPorts
        - Filter on ports NOT contained in list.
        - Ex: OnlyPorts: [22]
    - IpProtocol
        - Specify for rules with indicated protocol (TCP,UDP)
        - Can be used with any other filter
        - Ex: IpProtocol: TCP

Available Actions
-----------------
    - open - Allow access to security rules
    - close - Deny access to security rules

Example Policies
----------------

This policy will deny access to all security rules with Inbound SSH ports in the range [8080,8090]

.. code-block:: yaml

     policies:
       - name: close-ingress-8080-8090
         resource: azure.networksecuritygroup
         filters:
          - type: ingress
            FromPort: 8080
            ToPort: 8090
         actions:
          - type: close

This policy will deny access to all security rules with any Inbound SSH ports that are NOT 22, 23 or 24

.. code-block:: yaml

     policies:
       - name: close-ingress-except-22-24
         resource: azure.networksecuritygroup
         filters:
          - type: ingress
            OnlyPorts: [22,23,24]
         actions:
          - type: close

This policy will deny access to all security rules with any Outbound SSH ports with a TCP Protocol

.. code-block:: yaml

     policies:
       - name: close-egress-except-TCP
         resource: azure.networksecuritygroup
         filters:
          - type: egress
            IpProtocol: TCP
         actions:
          - type: close