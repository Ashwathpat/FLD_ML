import boto3
from pathlib import Path
import subprocess

pub_key = Path(r"C:\Users\Ashwath\.ssh\fld_key.pub").read_text().strip()
client = boto3.client("ec2-instance-connect", region_name="ap-southeast-2")
resp = client.send_ssh_public_key(
    InstanceId="i-0f88e5b5593e8f1d1",
    InstanceOSUser="ubuntu",
    SSHPublicKey=pub_key,
    AvailabilityZone="ap-southeast-2a"
)
print("EC2 Instance Connect:", resp.get("Success"))

cmd = [
    "ssh",
    "-o", "StrictHostKeyChecking=no",
    "-o", "BatchMode=yes",
    "-i", r"C:\Users\Ashwath\.ssh\fld_key",
    "ubuntu@54.66.222.189",
    f"echo '{pub_key}' >> ~/.ssh/authorized_keys && echo PERMANENT_KEY_INSTALLED && uname -a && docker --version"
]
res = subprocess.run(cmd, capture_output=True, text=True)
print("STDOUT:", res.stdout)
print("STDERR:", res.stderr)
