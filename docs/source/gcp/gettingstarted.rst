.. _gcp_gettingstarted:

Getting Started
===========================

The GCP provider plugin is an additional package which can optionally be installed to
the base Cloud Custodian application. It provides the ability to write policies which
interact with GCP related resources.

.. _gcp_install-cc:

Install GCP Plugin
------------------

First ensure you have installed the base Cloud Custodian application :ref:`install-cc`. 
Cloud Custodian is a Python application that supports Python 2 and 3 on Linux and Windows. 
We recommend using Python 3.6 or higher.

Once the base install is complete, you are now ready to install the GCP provider package
using one of the following options:

Option 1: Install released packages to local Python Environment
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

.. code-block:: bash

    $ pip install c7n
    $ pip install c7n_gcp


Option 2: Install latest from the repository
"""""""""""""""""""""""""""""""""""""""""""""

.. code-block:: bash

    $ git clone https://github.com/cloud-custodian/cloud-custodian.git
    $ cd cloud-custodian
    $ pip install -e ./cloud-custodian
    $ pip install -e ./cloud-custodian/tools/c7n_gcp

.. _gcp_authenticate:
Connect Your Authentication Credentials
---------------------------------------

In order for Custodian to be able to interact with your GCP resources, you will need to 
configure your GCP authentication credentials on your system in a way in which the 
application the application is able to retrieve them.

Choose from one of the following methods to figure your credentials, depending on your 
use case. In either option, after the configuration is complete Custodian will implicitly
pick up your credentials when it runs.

GCP CLI:
""""""""
If you are a general user accessing a single account, then you can use the GCP CLI to
configure your credentials.

First install ``glcoud`` (the GCP Command Line Interface). 
`Fix this link <https://cloud.google.com/sdk/install>`

Run the command ``gcloud auth login <your_user_name>`` and follow the prompts in the browser window that
opens to configure your credentials. For more information on this command, 
view its `documentation <https://cloud.google.com/sdk/gcloud/reference/auth/login>`.

Environment Variables:
""""""""""""""""""""""
If you are planning to run Custodian using a service account, then configure your credentials
using environment variables.

Follow the steps outlined in the 
`GCP documentation to configure credentials this way. <https://cloud.google.com/docs/authentication/getting-started>`

.. _gcp_write-policy:

Write Your First Policy
-----------------------


.. _gcp_run-policy:

Run Your Policy
---------------