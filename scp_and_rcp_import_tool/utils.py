import json
import os
import sys
import time
import logging
import argparse
from datetime import timezone
from itertools import batched

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def get_policies_from_orgs(org_client, filter_name):
    all_policies = []
    next_token = None
    while True:
        if next_token is None:
            list_response = org_client.list_policies(Filter=filter_name)
        else:
            list_response = org_client.list_policies(Filter=filter_name, NextToken=next_token)
        all_policies.extend(list_response['Policies'])
        next_token = list_response.get("NextToken", None)
        if next_token is None:
            break
    return all_policies

def filter_policies_to_be_included(org_client, all_policies, starts_with, aws_policy_name, policy_type):
    # Separate policies with and without targets
    policies_without_targets = []
    control_tower_policies = []  # List to store Control Tower policies
    aws_managed_fullawsaccess_policy = []
    policies_to_be_included = []

    for policy in all_policies:
        # Get the policy ID
        policy_id = policy.get('Id')

        # Get the policy details
        policy_details = org_client.describe_policy(PolicyId=policy_id)['Policy']

        if policy_details['PolicySummary']['Name'].startswith(starts_with):
            control_tower_policies.append(policy_details)
        else:
            policies_to_be_included.append(policy_id)
        
        # Get the targets for the policies
        targets = org_client.list_targets_for_policy(PolicyId=policy_id)['Targets']

        if not targets:
            policies_without_targets.append(policy_details)

        if policy_details['PolicySummary']['Name'] == aws_policy_name:
            aws_managed_fullawsaccess_policy.append(policy_id)
            policies_to_be_included.remove(policy_id)

    # If there are Control Tower policies, print an INFO block
    if control_tower_policies:
        print(f"\033[35mINFO: Found Control Tower {policy_type}:\033[0m")
        for policy in control_tower_policies:
            print(f"\t - {policy['PolicySummary']['Name']}")

    # If there are policies without targets, print a warning
    if policies_without_targets:
        print(f"\n")
        print(f"\033[35mWARNING: Found {policy_type}s without targets\033[0m")
        for policy in policies_without_targets:
            print(f"\t - {policy['PolicySummary']['Name']}")
    else:
        logger.info(f"All {policy_type}s have targets or {policy_type}s are not enabled in the organization.")

    print(f"\n")
    print(f"\033[35mNumber of {policy_type}s excluding Control Tower {policy_type}s and {aws_policy_name} {policy_type} (If Any): {len(all_policies) - len(control_tower_policies)- len(aws_managed_fullawsaccess_policy)}\033[0m")
    print(f"\n")
    return policies_to_be_included

def create_template_from_scanned_resources(cfn_client, policies_to_be_included):    
    try:
        # List all resource scans
        response = cfn_client.list_resource_scans()

        # Check if the response contains the 'ResourceScanSummaries' key
        if 'ResourceScanSummaries' in response:
            resource_scan_summaries = response['ResourceScanSummaries']

            # Get the most recent scan summary
            most_recent_scan_summary = max(resource_scan_summaries, key=lambda x: x['StartTime'])

            # Format the start and end timestamps as ISO strings
            start_timestamp = most_recent_scan_summary['StartTime'].astimezone(timezone.utc).isoformat()
            end_timestamp = most_recent_scan_summary['EndTime'].astimezone(timezone.utc).isoformat()

            # Prepare the response for the most recent scan details
            recent_scan_details = {
                'ScanId': most_recent_scan_summary['ResourceScanId'],
                'Status': most_recent_scan_summary['Status'],
                'StartTimestamp': start_timestamp,
                'EndTimestamp': end_timestamp,
                'PercentageCompleted': most_recent_scan_summary['PercentageCompleted']
            }
            print("\033[35m" + "Recent scan details:" + "\033[0m")
            print(recent_scan_details)

            # List resources from the most recent scan
            all_resources = []
            next_token = None
            while True:
                kwargs = {
                    'ResourceScanId': most_recent_scan_summary['ResourceScanId'],
                    'ResourceTypePrefix': 'AWS::Organizations::Policy'  # Filter resources by type
                }
                if next_token:
                    kwargs['NextToken'] = next_token

                response = cfn_client.list_resource_scan_resources(**kwargs)
                all_resources.extend(response['Resources'])
                next_token = response.get('NextToken')
                if not next_token:
                    break

            all_organizations_policies = [r for r in all_resources if r["ResourceType"] == "AWS::Organizations::Policy"]
            policies = [r for r in all_organizations_policies if r["ResourceIdentifier"]["Id"] in policies_to_be_included]
            _resources = [{
                'ResourceType': 'AWS::Organizations::Policy',
                'ResourceIdentifier': i["ResourceIdentifier"]
            } for i in policies]
            
            if len(_resources) == 0:
                print("\033[35mError: No policies were detected by the Cloudformation IaC scan. Either there are no organizations policies or you do not have enough permissions or a delegated administrator is setup.\033[0m")
            
            if len(policies_to_be_included) != len(policies):
                print(f"Error: CloudFormation IaC Generator failed to detect all AWS Organizations policies")
                return 1  # Return non-zero value to indicate failure
            
            def create_tmplt_batch(batchsize=100, _resources=[], recc_id=""):
                if len(_resources) == 0:
                    print("\033[35mError: No policies were detected by the Cloudformation IaC scan.\033[0m")

                if batchsize == 0:
                    raise RuntimeError("Batch size is 0")

                b_id = 0
                for batch in batched(_resources, batchsize):
                    print("Batching policy resources in batch of: ", len(batch))
                    b_id += 1
                    id = recc_id if recc_id else b_id
                    # Call the CreateGeneratedTemplate API if there are resources
                    template_name = f'OrganizationsPolicies-{id}'
                    create_template_response = cfn_client.create_generated_template(
                        Resources=batch,
                        GeneratedTemplateName=template_name,
                        TemplateConfiguration={
                            'DeletionPolicy': 'RETAIN',
                            'UpdateReplacePolicy': 'DELETE'
                        }
                    )
                    time.sleep(10)

                    resp = cfn_client.describe_generated_template(
                        GeneratedTemplateName=template_name,
                    )
                    status = resp["Status"]
                    progress = resp["Progress"]
                    print(f"Progress - Succeeded: {progress['ResourcesSucceeded']}, Failed: {progress['ResourcesFailed']}, Processing: {progress['ResourcesProcessing']}, Pending: {progress['ResourcesPending']}")


                    check = 1
                    while status not in ("COMPLETE", "FAILED"):
                        print("waiting")
                        time.sleep(10)
                        resp = cfn_client.describe_generated_template(
                            GeneratedTemplateName=template_name
                        )
                        status = resp["Status"]
                        progress = resp["Progress"]
                        print(f"Progress - Succeeded: {progress['ResourcesSucceeded']}, Failed: {progress['ResourcesFailed']}, Processing: {progress['ResourcesProcessing']}, Pending: {progress['ResourcesPending']}")
                        print("retry: ", check)
                        check += 1

                    if status == "COMPLETE":
                        print("\033[32m" + "completed status for template: " + "\033[0m", template_name)
                        gen_template = cfn_client.get_generated_template(Format="JSON", GeneratedTemplateName=template_name)
                        content_len = float(gen_template["ResponseMetadata"]["HTTPHeaders"]["content-length"])
                        if content_len>1000000:

                            print(f"\033[31m Template: {template_name} exceeds 1000000 bytes in size. \033[0m")
                            print("\033[31m" + "Deleting template splitting the resources into 2 different templates" + "\033[0m")

                            response = cfn_client.delete_generated_template(GeneratedTemplateName=template_name)

                            if batchsize == 1:
                                raise RuntimeError("batch size 1 and yet it failed. No way to split any further")
                            newsize = batchsize // 2
                            newsize2 = batchsize - newsize
                            create_tmplt_batch(newsize, batch[:newsize], f"{id}-a")
                            create_tmplt_batch(newsize2, batch[-newsize2:], f"{id}-b")
                        else:
                            template_body_json = json.loads(gen_template["TemplateBody"])

                            if not os.path.exists("policies"):
                                os.makedirs("policies")
                                
                            with open(f"policies/{template_name}.json", 'w', encoding ='utf8') as json_file:
                                json.dump(template_body_json, json_file, allow_nan=True)


                    elif status == "FAILED":
                        print(f"\033[31mFailed creating template: {template_name}. Reason: {resp['StatusReason']}\033[0m")
                        print("\033[31m" + "Deleting template & splitting the resources into 2 different templates" + "\033[0m")

                        response = cfn_client.delete_generated_template(
                            GeneratedTemplateName=template_name
                        )

                        if batchsize == 1:
                            raise RuntimeError("There is only one policy resource in the template yet template exceeded the permited template size . There is no way to split resources in multiple templates")
                        newsize = batchsize // 2
                        newsize2 = batchsize - newsize
                        create_tmplt_batch(newsize, batch[:newsize], f"{id}-1")
                        create_tmplt_batch(newsize2, batch[-newsize2:], f"{id}-2")

                    else:
                        raise RuntimeError("exited something went wrong")

            # Call the create_tmplt_batch function
            create_tmplt_batch(100, _resources)
            print("\033[32m" + "Template creation is complete, please login to AWS Cloudformation IaC console and check the templates created" + "\033[0m")

    except Exception as e:
        logger.error(f"Error retrieving recent scan details: {e}")
        # Exit with a non-zero code to indicate failure
        os._exit(1)
