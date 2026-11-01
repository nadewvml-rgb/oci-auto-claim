import os
import sys
import time
import oci

config = {
    "user": os.environ["OCI_USER_OCID"],
    "key_content": os.environ["OCI_PRIVATE_KEY"],
    "fingerprint": os.environ["OCI_FINGERPRINT"],
    "tenancy": os.environ["OCI_TENANCY_OCID"],
    "region": os.environ["OCI_REGION"],
}

stack_id = os.environ["OCI_STACK_OCID"]
rm_client = oci.resource_manager.ResourceManagerClient(config)

# දැනටමත් සර්වර් එක හැදිලද නැත්නම් Job එකක් දුවනවද කියලා බැලීම
jobs = rm_client.list_jobs(stack_id=stack_id).data
for job in jobs:
  if job.operation == "APPLY" and job.lifecycle_state == "SUCCEEDED":
    print("🎉 සර්වර් එක දැනටමත් සාර්ථකව නිර්මාණය වී ඇත! නැවත ට්‍රයි කිරීම අවශ්‍ය නැත.")
    sys.exit(0)
  if job.lifecycle_state in ["ACCEPTED", "IN_PROGRESS"]:
    print("⏳ දැනටමත් Job එකක් ක්‍රියාත්මක වෙමින් පවතී.")
    sys.exit(0)

print("🚀 අලුත් Apply Job එකක් ආරම්භ කරමින්...")
job_details = oci.resource_manager.models.CreateJobDetails(
    stack_id=stack_id,
    operation="APPLY",
    apply_job_plan_resolution=oci.resource_manager.models.ApplyJobPlanResolution(
        is_auto_approved=True
    ),
)

job = rm_client.create_job(job_details).data
print(f"Job ID: {job.id} ආරම්භ වුණා. ප්‍රතිඵලය පරීක්ෂා කරමින්...")

for _ in range(20):
  time.sleep(15)
  status = rm_client.get_job(job.id).data.lifecycle_state
  if status == "SUCCEEDED":
    print("🎉 සුබ පැතුම්! සර්වර් එක සාර්ථකව නිර්මාණය වුණා!")
    sys.exit(0)
  elif status in ["FAILED", "CANCELED"]:
    print("❌ තවම ඉඩ නැහැ (Out of host capacity). ඊළඟ වටයේදී නැවත උත්සාහ කරයි.")
    sys.exit(0)
