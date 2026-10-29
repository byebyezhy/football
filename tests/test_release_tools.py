import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_release import build_release, sha256_file
from scripts.publish_files import (
    ACTIVATE_CHANNEL, ACTIVATE_PROMOTION, FINALIZE_REMOTE, PREPARE_PROMOTION,
    PREPARE_REMOTE, channel_pointer, publish, validate_bundle, validate_ref,
)


class ReleaseToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative, body in {
            "README.md": "Football\n",
            "pyproject.toml": "[project]\nname='football'\n",
            "Dockerfile": "FROM python:3.11-slim\n",
            ".dockerignore": ".env\n",
            "compose.yaml": "services: {}\n",
            ".env.example": "POSTGRES_PASSWORD=\n",
            "deploy/Caddyfile": "fb.linmeng.ai { respond OK }\n",
            "src/football_predictor/__init__.py": "__version__ = 'test'\n",
            "src/football_predictor/web/static/index.html": "<h1>test</h1>\n",
            "docs/RELEASES.md": "Public docs\n",
            "tests/test_sample.py": "assert True\n",
            "data/raw/private.csv": "Sensitive data\n",
            ".env": "PASSWORD=do-not-package\n",
            ".github/workflows/secret.yml": "secrets\n",
        }.items():
            file = self.root / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(body, encoding="utf-8")
        self.version = "v0.1.0"
        self.commit = "a" * 40
        self.output = self.root / "dist"

    def test_allowlist_checksum_and_reproducible_tar(self):
        record = build_release(self.root, self.output, self.version, self.commit)
        self.assertEqual(validate_bundle(self.output, self.version), record)
        with tarfile.open(self.output / record["archive"]) as archive:
            names = archive.getnames()
            self.assertTrue(any(item.endswith("/src/football_predictor/__init__.py") for item in names))
            self.assertTrue(any(item.endswith("/src/football_predictor/web/static/index.html") for item in names))
            self.assertTrue(any(item.endswith("/compose.yaml") for item in names))
            self.assertTrue(any(item.endswith("/.env.example") for item in names))
            self.assertFalse(any("private.csv" in item or item.endswith("/.env") or ".github" in item for item in names))
        other = self.root / "dist2"
        record2 = build_release(self.root, other, self.version, self.commit)
        self.assertEqual(record["sha256"], record2["sha256"])
        self.assertEqual(sha256_file(self.output / record["archive"]), record["sha256"])
        with self.assertRaises(FileExistsError):
            build_release(self.root, self.output, self.version, self.commit)

    def test_bad_version_and_tampered_package_rejected(self):
        with self.assertRaises(ValueError):
            build_release(self.root, self.output, "../../oops", self.commit)
        record = build_release(self.root, self.output, self.version, self.commit)
        (self.output / record["archive"]).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            validate_bundle(self.output, self.version)

    def test_channel_and_tag_policy(self):
        record = build_release(self.root, self.output, self.version, self.commit)
        pointer = channel_pointer(record, "test")
        self.assertEqual(pointer["channel"], "test")
        self.assertEqual(pointer["sha256"], record["sha256"])
        with self.assertRaises(ValueError):
            channel_pointer(record, "other")
        validate_ref("refs/heads/main", self.version, "test")
        validate_ref("refs/tags/v0.1.0", self.version, "stable")
        with self.assertRaises(ValueError):
            validate_ref("refs/heads/main", self.version, "stable")
        with self.assertRaises(ValueError):
            validate_ref("refs/heads/unreviewed", self.version, "test")

    def test_channel_is_activated_only_after_http_verification(self):
        build_release(self.root, self.output, self.version, self.commit)
        key = self.root / "key"
        known = self.root / "hosts"
        key.write_text("fake key")
        known.write_text("[files.shenqianqian.com]:37767 ssh-ed25519 example")
        events = []

        def fake_run(command, **kwargs):
            if command[0] == "ssh":
                events.append(kwargs["input"])
            else:
                events.append("scp")

        def fake_get(url, checksum):
            events.append("https verified")

        with patch("scripts.publish_files.subprocess.run", side_effect=fake_run), patch(
            "scripts.publish_files.verify_public_archive", side_effect=fake_get
        ):
            publish(self.output, self.version, "test", "refs/heads/main", "root", key, known, "123", "1")
        self.assertEqual(events, [PREPARE_REMOTE, "scp", FINALIZE_REMOTE, "https verified", ACTIVATE_CHANNEL])
        data = json.loads((self.output / "channel-pointer.json").read_text())
        self.assertEqual(data["channel"], "test")

    def test_failed_public_check_preserves_channel_pointer(self):
        build_release(self.root, self.output, self.version, self.commit)
        key = self.root / "key"
        known = self.root / "hosts"
        key.write_text("fake key")
        known.write_text("pinned key")
        remote_scripts = []

        def capture_run(command, **kwargs):
            if command[0] == "ssh":
                remote_scripts.append(kwargs["input"])

        with patch("scripts.publish_files.subprocess.run", side_effect=capture_run), patch(
            "scripts.publish_files.verify_public_archive", side_effect=RuntimeError("public mirror missing")
        ):
            with self.assertRaisesRegex(RuntimeError, "public mirror missing"):
                publish(self.output, self.version, "test", "refs/heads/main", "root", key, known, "123", "1")
        self.assertNotIn(ACTIVATE_CHANNEL, remote_scripts)

    def test_promotion_validates_existing_release_before_channel_switch(self):
        build_release(self.root, self.output, self.version, self.commit)
        key = self.root / "key"
        known = self.root / "hosts"
        key.write_text("fake key")
        known.write_text("pinned key")
        events = []

        def fake_run(command, **kwargs):
            events.append(kwargs.get("input", "scp"))

        with patch("scripts.publish_files.subprocess.run", side_effect=fake_run), patch(
            "scripts.publish_files.verify_public_metadata", side_effect=lambda record: events.append("metadata verified")
        ), patch("scripts.publish_files.verify_public_archive", side_effect=lambda *args: events.append("archive verified")):
            publish(self.output, self.version, "stable", f"refs/tags/{self.version}",
                    "root", key, known, "124", "1", "promote-existing")
        self.assertEqual(events, ["metadata verified", "archive verified", PREPARE_PROMOTION,
                                  "scp", ACTIVATE_PROMOTION])

    def test_failed_promotion_verification_never_uses_ssh(self):
        build_release(self.root, self.output, self.version, self.commit)
        key = self.root / "key"
        known = self.root / "hosts"
        key.write_text("fake key")
        known.write_text("pinned key")
        with patch("scripts.publish_files.subprocess.run") as runner, patch(
            "scripts.publish_files.verify_public_metadata", side_effect=RuntimeError("wrong commit")
        ):
            with self.assertRaisesRegex(RuntimeError, "wrong commit"):
                publish(self.output, self.version, "stable", f"refs/tags/{self.version}",
                        "root", key, known, "124", "1", "promote-existing")
            runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
