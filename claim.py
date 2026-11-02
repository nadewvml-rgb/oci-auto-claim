import base64
import io
import os
import re
import sys
import time
import zipfile
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


def check_existing_jobs():
  """දැනටමත් සර්වර් එක හැදිලද නැත්නම් Job එකක් දුවනවද කියලා පරීක්ෂා කිරීම."""
  jobs = rm_client.list_jobs(stack_id=stack_id).data
  for job in jobs:
    if job.operation == "APPLY" and job.lifecycle_state == "SUCCEEDED":
      print(
          "🎉 සර්වර් එක දැනටමත් සාර්ථකව නිර්මාණය වී ඇත! නැවත ට්‍රයි කිරීම"
          " අවශ්‍ය නැත."
      )
      sys.exit(0)
    if job.lifecycle_state in ["ACCEPTED", "IN_PROGRESS"]:
      print("⏳ දැනටමත් Job එකක් ක්‍රියාත්මක වෙමින් පවතී.")
      sys.exit(0)


def update_stack_ad(target_ad):
  """Stack එකේ ඇති Terraform ගොනුව සහ Variables තුළ Availability Domain එක වෙනස් කිරීම."""
  stack = rm_client.get_stack(stack_id).data

  # 1. Stack Variables වල AD එක තිබේ නම් යාවත්කාලීන කිරීම
  updated_vars = dict(stack.variables) if stack.variables else {}
  for k, v in updated_vars.items():
    if isinstance(v, str) and re.search(r"AD-[123]", v):
      updated_vars[k] = re.sub(r"AD-[123]", target_ad, v)

  # 2. Stack එකේ Terraform (.zip) ගොනුව බාගත කර එහි ඇති AD එක වෙනස් කිරීම
  tf_resp = rm_client.get_stack_tf_config(stack_id)
  zip_bytes = (
      tf_resp.data.content
      if hasattr(tf_resp.data, "content")
      else tf_resp.data.read()
  )

  out_buffer = io.BytesIO()
  with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zin:
    with zipfile.ZipFile(out_buffer, "w", zipfile.ZIP_DEFLATED) as zout:
      for item in zin.infolist():
        content = zin.read(item.filename)
        if item.filename.endswith((".tf", ".tfvars", ".json")):
          text = content.decode("utf-8")
          text = re.sub(r"AD-[123]", target_ad, text)
          content = text.encode("utf-8")
        zout.writestr(item, content)

  b64_zip = base64.b64encode(out_buffer.getvalue()).decode("utf-8")

  update_details = oci.resource_manager.models.UpdateStackDetails(
      variables=updated_vars,
      config_source=oci.resource_manager.models.UpdateZipUploadConfigSourceDetails(
          zip_file_base64_encoded=b64_zip
      ),
  )
  rm_client.update_stack(stack_id, update_details)
  print(
      f"🔄 Stack එකේ Availability Domain එක {target_ad} ලෙස යාවත්කාලීන කරන"
      " ලදී."
  )


def run_apply_job(target_ad):
  """අදාළ AD එක සඳහා Apply Job එකක් ක්‍රියාත්මක කර ප්‍රතිඵලය පරීක්ෂා කිරීම."""
  print(f"🚀 [{target_ad}] සඳහා අලුත් Apply Job එකක් ආරම්භ කරමින්...")
  job_details = oci.resource_manager.models.CreateJobDetails(
      stack_id=stack_id,
      operation="APPLY",
      apply_job_plan_resolution=oci.resource_manager.models.ApplyJobPlanResolution(
          is_auto_approved=True
      ),
  )

  job = rm_client.create_job(job_details).data
  print(f"Job ID: {job.id} ({target_ad}) ආරම්භ වුණා. ප්‍රතිඵලය පරීක්ෂා කරමින්...")

  for _ in range(25):
    time.sleep(15)
    status = rm_client.get_job(job.id).data.lifecycle_state
    if status == "SUCCEEDED":
      print(
          f"🎉 සුබ පැතුම්! [{target_ad}] තුළ සර්වර් එක සාර්ථකව නිර්මාණය වුණා!"
      )
      sys.exit(0)
    elif status in ["FAILED", "CANCELED"]:
      print(f"❌ [{target_ad}] තුළ තවම ඉඩ නැහැ (Out of host capacity).")
      return False

  print(f"⚠️ [{target_ad}] Job එකට වැඩි කාලයක් ගතවන නිසා ඊළඟ වටයට යොමු වේ.")
  return False


if __name__ == "__main__":
  check_existing_jobs()

  # එකම Run එකකදී AD-1, AD-2, සහ AD-3 යන තුනම පිළිවෙළින් පරීක්ෂා කිරීම
  for ad in ["AD-1", "AD-2", "AD-3"]:
    try:
      update_stack_ad(ad)
      run_apply_job(ad)
      # ඊළඟ AD එකට යාමට පෙර තත්පර 5ක විරාමයක්
      time.sleep(5)
    except Exception as e:
      print(f"⚠️ {ad} පරීක්ෂා කිරීමේදී දෝෂයක් ඇතිවිය: {e}")

  print("🔄 AD තුනම පරීක්ෂා කර අවසන්. මීළඟ වටයේදී නැවත උත්සාහ කරයි.")
