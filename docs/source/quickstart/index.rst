.. _quickstart:

Getting Started
===============

To install Cloud Custodian, just run:

``pip install c7n``

Then:

* :ref:`write-policy`
* :ref:`run-policy`
* :ref:`monitoring-env`

.. _write-policy:

Write your first policy
-----------------------

A policy specifies the following items:

* The resource to run the policy against
* The resource state or states the policy checks (filters)
* The action or actions to take on the resource depending on the specified filters

For more information, see the following topics:

* :ref:`Basic concepts and terms <glossary>`
* :ref:`Example offhours policy <offhours>`
* :ref:`Example tag compliance policy <tagCompliance>`

TODO: content about ``custodian schema``? more detail about actually creating the policy, maybe more pointers to specific examples

.. _run-policy:

Run the policy
--------------

TODO: command ...

TODO: best practices for running with options specified in ``metrics and logs``.

.. _monitoring-env:

Monitor your environment
------------------------

TODO: figure out whether the content from ``metrics and logs`` belongs here, rewrite?
(still thinking about page organization -- more content for write, monitor, not so much for install, run)



