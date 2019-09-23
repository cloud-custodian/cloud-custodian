# Cloud Custodian Workbook
This folder contains the json definition for an [Azure Workbook](https://docs.microsoft.com/en-us/azure/azure-monitor/app/usage-workbooks) that visualizes the execution of your policies. The folder structure is based on [Application-Insights-Workbooks](https://github.com/microsoft/Application-Insights-Workbooks) to make publishing of the workbooks easier in the future.

## Deploying
These steps assume that you have an Application Insights instance created in Azure and a running set of policies (either container host or function host) that are logging to the Application Insights instance.

1. Go to Application Insights in the portal
1. On the left hand side, select Workbooks
1. Under quickstarts, select "Empty" to get a new workbook. Any workbook will work becasue the next step will overwrite the existing information.
1. On the top bar, the one with "Done Editing" and save, the advanced editor is the button with `</>`, click it
1. Copy the cotents of `CopyCustodian/Overview/Overview.workbook` and paste them in the advanced editor page
1. Click "Apply"
1. You should now see the workbook full of data. If there are no logs in Application Insights yet, there will be no avaialable Subscription Ids to filter the data and you will get the message "This query could not run because some parameters are not set". This will correct itself once logs become available
1. Save the new dashboard by clicking the save icon in the top bar. If you want the workbook to be visible to everyone with access to the Application Insights instance make sure to change "Save To" to "Shared Reports"
1. Edit the workbook to your needs

## Description
This workbook gives a high level overview of the policies being executed in Azure by querying the logs in Application Insights. It is split into the following sections:
1. Policy Executions: Bar chart displaying which policies were executed when.
1. Acted on Resources: Gives a view of which policy executions acted on your resources in Azure. By clicking on a policy in the table, a second query will appear showing the execution id's and logs for the runs where actions were taken.
1. Failed Policy Execution: Errors when executing policies against the resources. Failed actions and issues with permissions will be raised here. Again, if you select a policy in the table the execution ids and logs will be displayed
1. Python Exceptions: Uncaught python exceptions that are raised during the execution. These things should be filed as Issues in the Cloud Custodian repository

In order to control which information is being displayed, the workbook has two parameters:
* Timespan: The time period used to query data. This also sets the granularity of the time bin used in time resolved queries
* SubscriptionId: When policies running against multiple subscriptions are logged to the same Application Insights instance, this parameter can be used to filter to one or more of the subscriptions