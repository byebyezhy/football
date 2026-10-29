"""Build an allow-listed, immutable source release without private data."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile


VERSION_PATTERN = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+\Z")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
ALLOWED_DIRECTORIES = {
    "src": (".py", ".html"),
    "docs": (".md",),
    "tests": (".py",),
}
DEPLOYMENT_FILES = (
    "Dockerfile", ".dockerignore", "compose.yaml", ".env.example", "deploy/Caddyfile",
)


def validate_version(version: str) -> str:
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("Release version must look like v0.1.0")
    return version


def release_files(root: Path) -> list[Path]:
    """Only approved project files may enter a public release archive."""
    selected = [Path("README.md"), Path("pyproject.toml")]
    selected += [Path(file) for file in DEPLOYMENT_FILES]
    for directory, suffixes in ALLOWED_DIRECTORIES.items():
        base = root / directory
        if not base.is_dir() or base.is_symlink():
            raise ValueError(f"Missing or unsafe release directory: {directory}")
        for path in sorted(base.rglob("*")):
            if path.suffix not in suffixes or "__pycache__" in path.parts:
                continue
            selected.append(path.relative_to(root))

    if not any(str(path).startswith("src/") for path in selected):
        raise ValueError("No Python source files found")
    for relative in selected:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Unsafe release entry: {relative}")
        if any((root / parent).is_symlink() for parent in relative.parents if parent != Path(".")):
            raise ValueError(f"Symlinked release parent: {relative}")
    return sorted(selected, key=lambda item: item.as_posix())


def _write_tar(archive: Path, root: Path, version: str, files: list[Path]) -> None:
    # Normalize timestamps/ownership and gzip header to make repeat builds stable.
    with archive.open("xb") as target:
        with gzip.GzipFile(fileobj=target, mode="wb", filename="", mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as bundle:
                for relative in files:
                    data = (root / relative).read_bytes()
                    info = tarfile.TarInfo(f"football-{version}/{relative.as_posix()}")
                    info.size = len(data)
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mode = 0o644
                    bundle.addfile(info, io.BytesIO(data))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_release(root: Path, output_dir: Path, version: str, commit: str) -> dict:
    validate_version(version)
    if not COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("Commit must be a full 40-character lowercase Git SHA")
    files = release_files(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"football-{version}.tar.gz"
    archive = output_dir / archive_name
    metadata = output_dir / "release.json"
    sums = output_dir / "SHA256SUMS"
    if any(path.exists() for path in (archive, metadata, sums)):
        raise FileExistsError("Release output already exists; use a clean directory")

    _write_tar(archive, root, version, files)
    digest = sha256_file(archive)
    record = {
        "schema": 1,
        "project": "football",
        "version": version,
        "commit": commit,
        "archive": archive_name,
        "sha256": digest,
        "file_count": len(files),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    metadata.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sums.write_text(f"{digest}  {archive_name}\n", encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    record = build_release(args.root.resolve(), args.output, args.version, args.commit)
    print(f"Built {record['archive']} ({record['sha256']}); {record['file_count']} approved files")


if __name__ == "__main__":
    main()
