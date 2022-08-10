.. _developer-documentation:

Documentation For Developers
============================

Cloud Custodian makes every effort to provide comprehensive documentation.
Any new features you add should be documented.

The documentation is built using `sphinx <http://www.sphinx-doc.org>`_.
The documentation is written using reStructured Text (``rst``).
The sphinx documentation contains `a useful introduction <https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html>`_ to ``rst`` syntax.

Find the Documentation
----------------------

The root of the documentation is located in the ``docs`` directory.
Within the documentation, topics are organized according to the following main areas:

* :doc:`Overview <../index>`
* :ref:`Quickstart <quickstart>`
* :ref:`AWS <aws-gettingstarted>`
* :ref:`Azure <azure_gettingstarted>`
* :ref:`GCP <gcp_gettingstarted>`
* :ref:`Developer <developer>`

In addition, the api documentation will be built from docstrings on classes and methods in source code.
The ``rst`` files for these may be found in the ``generated`` subdirectory.

Edit the Documentation
----------------------

In most cases, documentation edits will be made in docstrings on source code.
Docstrings should be written following the principles of `pep 257 <https://www.python.org/dev/peps/pep-0257/>`_.
Within docstrings, ``rst`` directives allow for highlighting code examples:

.. code-block:: python

    class AutoTagUser(EventAction):
        """Tag a resource with the user who created/modified it.

        .. code-block:: yaml

          policies:
            - name: ec2-auto-tag-ownercontact
              resource: ec2
              description: |
                Triggered when a new EC2 Instance is launched. Checks to see if
                it's missing the OwnerContact tag. If missing it gets created
                with the value of the ID of whomever called the RunInstances API
              mode:
                type: cloudtrail
                role: arn:aws:iam::123456789000:role/custodian-auto-tagger
                events:
                  - RunInstances
              filters:
               - tag:OwnerContact: absent
              actions:
               - type: auto-tag-user
                 tag: OwnerContact

        There's a number of caveats to usage. Resources which don't
        include tagging as part of their api may have some delay before
        automation kicks in to create a tag. Real world delay may be several
        minutes, with worst case into hours[0]. This creates a race condition
        between auto tagging and automation.

        In practice this window is on the order of a fraction of a second, as
        we fetch the resource and evaluate the presence of the tag before
        attempting to tag it.

        References

         CloudTrail User
         https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-user-identity.html
        """

Render the Documentation
------------------------

In general, you should use tox to build the documentation:

.. code-block::

    tox -e docs

This command will clean previously built files and rebuild the entire documentation tree.

When developing, you may prefer to build only those files you have edited.
To do so, use the following command:

.. code-block::

    make -f docs/Makefile.sphinx html


You can also build documentation via the provided tox dockerfile.  You will need to build and
run from the root of your source enlistment each time you edit documentation files:

.. code-block::

    docker build -t tox_linux --build-arg TOX_ENV=docs . -f tools/dev/docker_tox_linux/Dockerfile
    docker run -v 'pwd'/docs/build:/src/docs/build -it tox_linux
