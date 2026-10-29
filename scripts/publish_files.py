"""Publish a checked release to the football-only directory on the files host.

Never run this directly from unreviewed pull-request code. The workflow invokes
it after successful checks from main or a manually dispatched release job.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

from scripts.build_release import COMMIT_PATTERN, sha256_file, validate_version


PUBLIC_BASE = "https://files.shenqianqian.com/football"
SSH_HOST = "files.shenqianqian.com"
SSH_PORT = "37767"
REMOTE_BASE = "/srv/files/public/football"
USER_PATTERN = re.compile(r"[a-z_][a-z0-9_-]*\Z")
RUN_PATTERN = re.compile(r"[0-9]+\Z")
SHA_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


PREPARE_REMOTE = r"""
set -eu
version=$1
run=$2
base=/srv/files/public/football
stage="$base/.staging/$version-$run"
release="$base/releases/$version"
mkdir -p "$base/releases" "$base/channels" "$base/.staging"
if [ -e "$release" ] || [ -L "$release" ] || [ -e "$stage" ] || [ -L "$stage" ]; then
    echo 'Release or staging path already exists; refusing overwrite' >&2
    exit 1
fi
mkdir "$stage"
"""

FINALIZE_REMOTE = r"""
set -eu
version=$1
run=$2
base=/srv/files/public/football
stage="$base/.staging/$version-$run"
release="$base/releases/$version"
test -d "$stage" && test ! -L "$stage"
test ! -e "$release" && test ! -L "$release"
cd "$stage"
test -f release.json && test -f SHA256SUMS && test -f channel-pointer.json
sha256sum -c SHA256SUMS
mv "$stage" "$release"
"""

ACTIVATE_CHANNEL = r"""
set -eu
version=$1
channel=$2
base=/srv/files/public/football
pointer="$base/releases/$version/channel-pointer.json"
destination="$base/channels/$channel.json"
test -f "$pointer" && test ! -L "$pointer"
test -d "$base/channels" && test ! -L "$base/channels"
mv -f "$pointer" "$destination"
"""

PREPARE_PROMOTION = r"""
set -eu
version=$1
channel=$2
run=$3
base=/srv/files/public/football
temporary="$base/.staging/channel-$channel-$run.json"
test -d "$base/releases/$version" && test ! -L "$base/releases/$version"
test -d "$base/.staging" && test ! -L "$base/.staging"
test ! -e "$temporary" && test ! -L "$temporary"
cd "$base/releases/$version"
sha256sum -c SHA256SUMS
"""

ACTIVATE_PROMOTION = r"""
set -eu
version=$1
channel=$2
run=$3
base=/srv/files/public/football
temporary="$base/.staging/channel-$channel-$run.json"
destination="$base/channels/$channel.json"
test -f "$temporary" && test ! -L "$temporary"
test -d "$base/channels" && test ! -L "$base/channels"
cd "$base/releases/$version"
sha256sum -c SHA256SUMS
mv -f "$temporary" "$destination"
"""


def validate_bundle(dist: Path, version: str) -> dict:
    validate_version(version)
    record = json.loads((dist / "release.json").read_text(encoding="utf-8"))
    archive = f"football-{version}.tar.gz"
    if record.get("project") != "football" or record.get("version") != version:
        raise ValueError("Release metadata does not match the requested project/version")
    if record.get("archive") != archive or not COMMIT_PATTERN.fullmatch(record.get("commit", "")):
        raise ValueError("Invalid release filename or commit")
    if not SHA_PATTERN.fullmatch(record.get("sha256", "")):
        raise ValueError("Invalid SHA256 metadata")
    if (dist / "SHA256SUMS").read_text(encoding="utf-8") != f"{record['sha256']}  {archive}\n":
        raise ValueError("SHA256SUMS disagrees with metadata")
    if sha256_file(dist / archive) != record["sha256"]:
        raise ValueError("Release archive checksum mismatch")
    return record


def channel_pointer(record: dict, channel: str) -> dict:
    if channel not in {"test", "stable"}:
        raise ValueError("Channel must be test or stable")
    version = validate_version(record["version"])
    return {
        "schema": 1,
        "channel": channel,
        "version": version,
        "commit": record["commit"],
        "url": f"{PUBLIC_BASE}/releases/{version}/{record['archive']}",
        "sha256": record["sha256"],
    }


def validate_ref(ref: str, version: str, channel: str) -> None:
    if ref not in {"refs/heads/main", f"refs/tags/{version}"}:
        raise ValueError("Publishing requires main or an exact version tag")
    if channel == "stable" and ref != f"refs/tags/{version}":
        raise ValueError("Stable releases require a matching vX.Y.Z Git tag")


def verify_public_archive(url: str, checksum: str) -> None:
    import hashlib

    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=30) as reply:
        if reply.status != 200:
            raise RuntimeError(f"Unexpected public download status: {reply.status}")
        for block in iter(lambda: reply.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != checksum:
        raise RuntimeError("HTTPS download SHA256 mismatch; channel pointer was not updated")


def verify_public_metadata(record: dict) -> None:
    """Promotion may only target the exact already-published, matching package."""
    url = f"{PUBLIC_BASE}/releases/{record['version']}/release.json"
    with urllib.request.urlopen(url, timeout=30) as reply:
        if reply.status != 200:
            raise RuntimeError(f"Unexpected public metadata status: {reply.status}")
        remote = json.load(reply)
    for name in ("project", "version", "commit", "archive", "sha256"):
        if remote.get(name) != record.get(name):
            raise RuntimeError(f"Existing public release differs in {name}; refusing promotion")


def publish(dist: Path, version: str, channel: str, ref: str, ssh_user: str,
            key_file: Path, known_hosts: Path, run_id: str, attempt: str,
            operation: str = "publish-new") -> dict:
    record = validate_bundle(dist, version)
    pointer = channel_pointer(record, channel)
    validate_ref(ref, version, channel)
    if not USER_PATTERN.fullmatch(ssh_user):
        raise ValueError("Invalid SSH user")
    if not RUN_PATTERN.fullmatch(run_id) or not RUN_PATTERN.fullmatch(attempt):
        raise ValueError("Invalid GitHub workflow run identifier")
    if operation not in {"publish-new", "promote-existing"}:
        raise ValueError("Unsupported publication operation")
    if not key_file.is_file() or not known_hosts.is_file() or not known_hosts.stat().st_size:
        raise ValueError("SSH private key and trusted known_hosts files are required")
    run_token = f"{run_id}-{attempt}"
    stage = f"{REMOTE_BASE}/.staging/{version}-{run_token}"
    pointer_file = dist / "channel-pointer.json"
    if pointer_file.exists():
        raise FileExistsError("Channel pointer staging file already exists")
    pointer_file.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")

    options = [
        "-i", str(key_file), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "ConnectTimeout=10",
    ]
    destination = f"{ssh_user}@{SSH_HOST}"

    def remote(script: str, *args: str) -> None:
        # Every argument is validated as a plain token, never injected from PR input.
        command = "sh -s -- " + " ".join(args)
        subprocess.run(["ssh", "-p", SSH_PORT, *options, destination, command],
                       input=script, text=True, check=True)

    if operation == "publish-new":
        remote(PREPARE_REMOTE, version, run_token)
        subprocess.run([
            "scp", "-P", SSH_PORT, *options,
            str(dist / record["archive"]), str(dist / "SHA256SUMS"),
            str(dist / "release.json"), str(pointer_file), f"{destination}:{stage}/",
        ], check=True)
        remote(FINALIZE_REMOTE, version, run_token)
        # A failed public GET cannot silently activate an unverified channel.
        verify_public_archive(pointer["url"], record["sha256"])
        remote(ACTIVATE_CHANNEL, version, channel)
    else:
        verify_public_metadata(record)
        verify_public_archive(pointer["url"], record["sha256"])
        remote(PREPARE_PROMOTION, version, channel, run_token)
        temporary = f"{REMOTE_BASE}/.staging/channel-{channel}-{run_token}.json"
        subprocess.run([
            "scp", "-P", SSH_PORT, *options, str(pointer_file),
            f"{destination}:{temporary}",
        ], check=True)
        remote(ACTIVATE_PROMOTION, version, channel, run_token)
    return pointer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", choices=("test", "stable"), required=True)
    parser.add_argument("--operation", choices=("publish-new", "promote-existing"), required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    args = parser.parse_args()
    result = publish(
        args.dist, args.version, args.channel, args.ref,
        os.environ.get("FILES_SSH_USER", ""), args.key_file, args.known_hosts,
        os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        args.operation,
    )
    print(f"Published {result['version']} to {result['channel']}: {result['url']}")


if __name__ == "__main__":
    main()
