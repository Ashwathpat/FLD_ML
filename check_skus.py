import subprocess
import json
import urllib.request

# Get access token from az cli
token_out = subprocess.check_output("az account get-access-token --query accessToken -o tsv", shell=True, text=True).strip()
sub_id = "20837fd4-e028-435c-b829-3ab17096eb52"

import urllib.parse

filter_q = urllib.parse.quote("location eq 'eastasia'")
url = f"https://management.azure.com/subscriptions/{sub_id}/providers/Microsoft.Compute/skus?api-version=2021-07-01&$filter={filter_q}"

req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token_out}"})
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        items = data.get("value", [])
        vms = [x for x in items if x.get("resourceType") == "virtualMachines"]
        available = [x["name"] for x in vms if not x.get("restrictions")]
        print(f"Total VMs in eastasia: {len(vms)}")
        print(f"Available VMs without restrictions: {len(available)}")
        print("First 20 available:", available[:20])
except Exception as e:
    print("Error:", e)
