import boto3
import json
import os
import sys
import time
import logging
import argparse
from datetime import timezone
from itertools import batched
from scp_and_rcp_import_tool.utils import *

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)


def validate_policies_from_organizations(args=None):
    if args is None:
        args = sys.argv[1:]
        
    parser = argparse.ArgumentParser(add_help=False)

    parser.add_argument('--profile', default="default", help='The profile name to be used (default is "default")')
    args = parser.parse_args()
    
    # Get the profile name from the environment variable
    profile_name = args.profile
    print(f"Selected profile: {profile_name}")

    # Initialize the Organizations and cloudformation client
    session = boto3.Session(profile_name=profile_name)
    org_client = session.client('organizations')
    cfn_client = session.client('cloudformation')

    # Get all policies in the organization

    all_scps = get_policies_from_orgs(org_client, "SERVICE_CONTROL_POLICY")
    all_rcps = get_policies_from_orgs(org_client, "RESOURCE_CONTROL_POLICY")

    print(f"\n")
    print(f"\033[35mTotal number of SCPs found from AWS Organizations: {len(all_scps)}\033[0m \n")
    print(f"\033[35mTotal number of RCPs found from AWS Organizations: {len(all_rcps)}\033[0m \n")
    if len(all_scps) >= 50:
        print("Checking for SCPs without targets and Control Tower SCPs")
    if len(all_rcps) >= 50:
        print("Checking for RCPs without targets and Control Tower RCPs")

    scps_to_be_included = filter_policies_to_be_included(org_client, all_scps, 
                                                        starts_with='aws-guardrails-', 
                                                        aws_policy_name='FullAWSAccess',
                                                        policy_type="SCP")
    rcps_to_be_included = filter_policies_to_be_included(org_client, all_rcps, 
                                                        starts_with='AWSControlTower-Controls-', 
                                                        aws_policy_name='RCPFullAWSAccess',
                                                        policy_type="RCP")
    
    print(f"\033[35mSCPs to be included: {len(scps_to_be_included)}\033[35m")
    print(f"\033[35mRCPs to be included: {len(rcps_to_be_included)}\033[35m")
    all_policies_included = scps_to_be_included + rcps_to_be_included
    print(f"\033[35mTotal policies to be included: {len(all_policies_included)}\033[35m")

    print("\033[35mDo you want to continue with Cloudformation IaC resource scan?\033[35m (yes/no): ", end="")
    user_input = input().strip().lower()
    while user_input not in ["yes", "no"]:  # Validate user input
        print("Invalid input. Please enter 'yes' or 'no'.")
        user_input = input().strip().lower()

    if user_input == "yes":
        start_resource_scan(cfn_client)  # Call the function to start the resource scan
        create_template_from_scanned_resources(cfn_client, all_policies_included)  # Call the function to get recent scan details, passing policies_to_be_included
        return 0  # Return 0 to indicate success
    else:
        print("User chose not to continue. Exiting...")
        return 1  # Return non-zero value to indicate failure

    
def start_resource_scan(cfn_client):
    try:
        response = cfn_client.start_resource_scan(
                ScanFilters=[
                    {
                        'Types': ['AWS::Organizations::Policy']
                    }
                ]
        )
        resource_scan_id = response['ResourceScanId']
        logger.info(f"Resource scan started with ID: {resource_scan_id}")
        print("IaCToolScan initiated. Checking for scan completion...")

        # Checking every 5 seconds to check for scan completion
        while True:
            # Describe the resource scan to get the current status
            status_response = cfn_client.describe_resource_scan(ResourceScanId=resource_scan_id)
            status = status_response['Status']  # Assuming the status field gives scan completion status

            # Check if the scan has completed
            if status == 'COMPLETE':  # Replace with actual status value for completion
                print("Resource scan completed successfully.")
                break
            elif status == 'FAILED':  # Handle failure case
                print("Resource scan failed.")
                break
            # If not completed, wait 5 seconds before checking again
            time.sleep(5)

    except Exception as e:
        logger.error(f"Error starting resource scan: {e}")
        # Exit with a non-zero code to indicate failure
        os._exit(1)

# Call the validate_policies_from_organizations() function
if __name__ == "__main__":
    result = validate_policies_from_organizations()
    sys.exit(result)