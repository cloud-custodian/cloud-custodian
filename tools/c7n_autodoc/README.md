
# Automated Cloud Custodian Policy Documentation

## What is c7n-autodoc?

Automated Cloud Custodian policy documentation for your business partners.

## Why use c7n-autodoc?

Administrators of cloud platforms need provide their business partners
with clear and accurate documentation regarding the security, governance and
cost control policies.  The easiest way to stay on top of your documentation 
is to automate it.  This utility will create an HTML file with easy to read information
regarding your existing Cloud Custodian policies.  

Features include:
* Automatically writes to S3 bucket
* Groups policies by resource type
* Groups policies by category (i.e 'Security & Governance' vs 'Cost Controls')
* Provide links to underlying file in your versioning system of choice
* Uses policy tags to determine applicable environments

## Assumptions

* You have added any necessary security controls to the destination S3 bucket
* Local credentials exist for the boto3 module to push the file to S3

## Installation

  pip install pyyaml boto3 jinja2

## Configuration

Use your favorite editor to modify the c7n-autodoc.py script.  There is a section at the top
which needs to be customized for each implementation. There is documentation within the script to 
help you better understand how each variable should be set.  You can also customize the jinja2 template 
to further modify the HTML documentation which is created. 

The S3 bucket which will house the HTML file needs to have `Static website hosting` enabled.  The 
default (index.html, error.html) are fine because you will be directly targeting the c7n-autodoc.html
file.

## Run

For the best results this script should be run as a part of a CI/CD pipeline. 

  python c7n-autodoc.py

Assuming there aren't any issues you should see the HTML file in the S3 bucket.

## Example 

![alt text](images/c7n-autodoc_example1.png "Example c7n-autodoc")

## TODO

* Account for multiple cloud platforms 
* Move configuration from script into a configuration file, cli params, etc
* Account for different policies for proper rendering
