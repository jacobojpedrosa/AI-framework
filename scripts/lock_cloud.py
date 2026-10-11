"""Explicitly format packaged Terraform templates and lock official provider hashes."""

import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--terraform", default="terraform")
parser.add_argument("--provider", choices=("gcp", "azure"), default="gcp")
args = parser.parse_args()
folder = "cloud_azure" if args.provider == "azure" else "cloud"
provider = "azurerm" if args.provider == "azure" else "google"
TEMPLATES = ROOT / f"src/harness/templates/{folder}/infra/{args.provider}"
terraform = str(Path(args.terraform).absolute()) if "/" in args.terraform else args.terraform
with tempfile.TemporaryDirectory(prefix="harness-cloud-lock-") as directory:
    temporary = Path(directory)
    for root in ("bootstrap", "service"):
        work = temporary / root
        for template in (TEMPLATES / root).rglob("*.tmpl"):
            destination = work / template.relative_to(TEMPLATES / root).as_posix().removesuffix(
                ".tmpl"
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(template.read_bytes())
        subprocess.run([terraform, "fmt", "-recursive"], cwd=work, check=True)
        for template in (TEMPLATES / root).rglob("*.tmpl"):
            source = work / template.relative_to(TEMPLATES / root).as_posix().removesuffix(".tmpl")
            template.write_bytes(source.read_bytes())
    work = temporary / "bootstrap"
    subprocess.run([terraform, "init", "-backend=false", "-input=false"], cwd=work, check=True)
    subprocess.run(
        [terraform, "providers", "lock", "-platform=darwin_arm64", "-platform=linux_amd64"],
        cwd=work,
        check=True,
    )
    (ROOT / f"src/harness/templates/cloud_locks/{provider}.lock.hcl.tmpl").write_bytes(
        (work / ".terraform.lock.hcl").read_bytes()
    )
