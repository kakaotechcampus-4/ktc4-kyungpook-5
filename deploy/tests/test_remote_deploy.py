"""Run the real deployment shell script against isolated, stateful CLI doubles.

No Docker daemon, AWS credentials, database, or third-party packages are needed.
"""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


REGISTRY = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com"
API = f"{REGISTRY}/unyounghae-api"
WEB = f"{REGISTRY}/unyounghae-web"
SCRIPT = Path(__file__).resolve().parents[1] / "remote-deploy.sh"

MOCK_CLI = r'''
import json
import os
from pathlib import Path
import sys

root = Path(os.environ["DEPLOY_TEST_ROOT"])
state_path = root / "state.json"
state = json.loads(state_path.read_text())
command = [Path(sys.argv[0]).name, *sys.argv[1:]]
args = command[1:]
with (root / "commands.jsonl").open("a") as log:
    log.write(json.dumps({
        "command": command,
        "committed": not (root / "compose.next.yml").exists(),
    }) + "\n")

def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)

def save():
    state_path.write_text(json.dumps(state))

def compose_images(env_file):
    values = dict(line.split("=", 1) for line in
                  (root / env_file).read_text().splitlines() if "=" in line)
    # Reproduce Compose's shell-over-env-file precedence to catch rollback bugs.
    return [os.environ.get(key, values[key])
            for key in ("BACKEND_IMAGE", "FRONTEND_IMAGE")]

if command[0] == "df":
    if state.get("df_failure"):
        fail("df failed")
    assert args == ["-Pk", str(root / "docker data")], args
    print("Filesystem 1024-blocks Used Available Capacity Mounted on")
    print(f"/dev/test 50000000 1000000 {state['available_kb']} 2% /docker")
elif command[0] == "aws":
    assert args[:2] == ["ecr", "get-login-password"], args
    print("test-password")
elif command[0] == "curl":
    if state.get("health_failure"):
        fail("health check failed")
elif command[0] == "sleep":
    pass
elif command[0] == "docker":
    if args == ["info", "--format", "{{.DockerRootDir}}"]:
        print(root / "docker data")
    elif args[:1] == ["login"]:
        assert sys.stdin.read().strip() == "test-password"
    elif args[:1] == ["compose"]:
        assert args[1] == "--env-file" and args[3] == "-f", args
        env_file = args[2]
        operation = args[5:]
        if operation == ["config", "--images", "api", "web"]:
            if state.get("config_failure"):
                fail("old compose config failed")
            if not state.get("empty_config"):
                print("\n".join(compose_images(env_file)))
        elif operation == ["pull"]:
            if state.get("pull_failure"):
                fail("pull failed")
            for image in compose_images(env_file):
                if image not in state["images"]:
                    state["images"].append(image)
            save()
        elif operation[:1] == ["run"]:
            if state.get("preflight_failure"):
                fail("preflight failed")
        elif operation == ["up", "-d", "--remove-orphans"]:
            state["running"] = compose_images(env_file)
            save()
        elif operation != ["logs", "--tail", "100", "web"]:
            fail(f"Unexpected compose operation: {operation}")
    elif args[:2] == ["image", "ls"]:
        assert args[2:4] == ["--format", "{{.Repository}} {{.Tag}}"], args
        repository = args[4]
        if repository == state.get("list_failure"):
            fail("image listing failed")
        for image in state["images"]:
            repo, tag = image.rsplit(":", 1)
            if repo == repository or state.get("unfiltered_listing"):
                print(repo, tag)
    elif args[:2] == ["image", "rm"]:
        assert args[2] == "--no-prune" and len(args) == 4, args
        image = args[3]
        if image in state.get("remove_failures", []):
            fail("image still in use")
        state["images"].remove(image)
        save()
    else:
        fail(f"Unexpected Docker command (possibly destructive): {args}")
else:
    fail(f"Unexpected command: {command}")
'''


class RemoteDeployTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        mock = self.bin / "mock"
        mock.write_text(f"#!{sys.executable}\n" + MOCK_CLI)
        mock.chmod(0o755)
        for name in ("docker", "aws", "df", "curl", "sleep"):
            (self.bin / name).symlink_to(mock)
        (self.root / "api.env").touch()
        (self.root / "api-storage").mkdir()
        (self.root / "api-storage" / "upload").write_text("preserve upload")
        (self.root / "backups").mkdir()
        (self.root / "backups" / "db.dump").write_text("preserve backup")
        (self.root / "compose.yml").write_text("previous compose")
        (self.root / ".env").write_text(self.env_text("previous"))
        self.write_state({
            "available_kb": 4 * 1024 * 1024,
            "images": self.images("old", "previous"),
            "running": self.images("previous"),
        })
        source = SCRIPT.read_text()
        self.assertEqual(source.count("cd /opt/unyounghae\n"), 1)
        self.script = self.root / "remote-deploy.sh"
        self.script.write_text(source.replace(
            "cd /opt/unyounghae\n", f"cd {shlex.quote(str(self.root))}\n"
        ))

    @staticmethod
    def images(*versions):
        return [f"{repo}:{version}" for version in versions for repo in (API, WEB)]

    @staticmethod
    def env_text(version):
        return (f"BACKEND_IMAGE={API}:{version}\nFRONTEND_IMAGE={WEB}:{version}\n"
                "SITE_ADDRESS=:80\nACME_EMAIL=old@example.com\n")

    def state(self):
        return json.loads((self.root / "state.json").read_text())

    def write_state(self, state):
        (self.root / "state.json").write_text(json.dumps(state))

    def configure(self, **settings):
        self.write_state(self.state() | settings)

    def commands(self):
        return [json.loads(line) for line in
                (self.root / "commands.jsonl").read_text().splitlines()]

    def removals(self):
        return [entry for entry in self.commands()
                if entry["command"][:3] == ["docker", "image", "rm"]]

    def deploy(self, version="current", **environment):
        (self.root / "compose.next.yml").write_text(f"compose {version}")
        env = os.environ | {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "DEPLOY_TEST_ROOT": str(self.root),
            "AWS_REGION": "ap-northeast-2",
            "BACKEND_IMAGE": f"{API}:{version}",
            "FRONTEND_IMAGE": f"{WEB}:{version}",
            "SITE_ADDRESS": ":80",
            "ACME_EMAIL": "new@example.com",
        } | environment
        return subprocess.run(["bash", str(self.script)], env=env,
                              capture_output=True, text=True, timeout=30)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_no_cleanup(self):
        self.assertFalse(any(entry["command"][:2] == ["docker", "image"]
                             for entry in self.commands()))

    def test_two_deployments_keep_only_current_and_previous(self):
        # An unrelated tag can share layers or an image ID with an app image.
        unrelated = ["pgvector/pgvector:pg16", f"{REGISTRY}/other:old",
                     f"{REGISTRY}/unyounghae-api-extra:old",
                     "other-registry/unyounghae-api:old", "<none>:<none>"]
        self.configure(images=self.images("old", "previous", "future") + unrelated,
                       unfiltered_listing=True)
        self.assert_success(self.deploy())
        self.assertCountEqual(self.state()["images"],
                              self.images("current", "previous") + unrelated)
        self.assert_success(self.deploy("next"))
        self.assertCountEqual(self.state()["images"],
                              self.images("next", "current") + unrelated)
        self.assertEqual(self.state()["running"], self.images("next"))
        self.assertTrue(all(entry["committed"] for entry in self.removals()))
        self.assertEqual((self.root / "api-storage" / "upload").read_text(),
                         "preserve upload")
        self.assertEqual((self.root / "backups" / "db.dump").read_text(),
                         "preserve backup")

    def test_first_deployment_keeps_only_current(self):
        (self.root / ".env").unlink()
        (self.root / "compose.yml").unlink()
        self.assert_success(self.deploy())
        self.assertCountEqual(self.state()["images"], self.images("current"))

    def test_redeploy_same_release_preserves_rollback_images(self):
        self.assert_success(self.deploy())
        self.assert_success(self.deploy())
        self.assertCountEqual(self.state()["images"],
                              self.images("current", "previous"))
        self.assertCountEqual((self.root / ".previous-images").read_text().splitlines(),
                              self.images("previous"))

    def test_redeploy_without_rollback_history_skips_cleanup(self):
        result = self.deploy("previous")
        self.assert_success(result)
        self.assertIn("rollback image history is unavailable", result.stderr)
        self.assert_no_cleanup()

    def test_manifest_write_failure_does_not_fail_deployment(self):
        (self.root / ".previous-images.next").mkdir()
        result = self.deploy()
        self.assert_success(result)
        self.assertIn("deployment remains successful", result.stderr)
        self.assert_no_cleanup()
        self.assertEqual(self.state()["running"], self.images("current"))

    def test_low_space_stops_before_login_pull_or_switch(self):
        self.configure(available_kb=2 * 1024 * 1024 - 1)
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Insufficient disk space", result.stderr)
        self.assertIn("2097151 KiB", result.stderr)
        self.assertIn("2 GiB", result.stderr)
        self.assertFalse((self.root / ".env.next").exists())
        self.assertEqual([entry["command"][0] for entry in self.commands()],
                         ["docker", "df"])
        self.assertEqual(self.state()["running"], self.images("previous"))

    def test_exact_space_threshold_allows_deployment(self):
        self.configure(available_kb=2 * 1024 * 1024)
        self.assert_success(self.deploy())

    def test_invalid_disk_reading_stops_deployment(self):
        self.configure(available_kb="unknown")
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot determine available disk space", result.stderr)
        self.assert_no_cleanup()

    def test_failed_disk_check_stops_deployment(self):
        self.configure(df_failure=True)
        self.assertNotEqual(self.deploy().returncode, 0)
        self.assert_no_cleanup()

    def test_cleanup_removal_failure_does_not_rollback(self):
        self.configure(remove_failures=[f"{API}:old"])
        result = self.deploy()
        self.assert_success(result)
        self.assertIn("deployment remains successful", result.stderr)
        self.assertIn(f"{API}:old", self.state()["images"])
        self.assertNotIn(f"{WEB}:old", self.state()["images"])
        self.assertEqual(self.state()["running"], self.images("current"))
        self.assertEqual((self.root / "compose.yml").read_text(), "compose current")
        self.assertIn(f"{API}:current", (self.root / ".env").read_text())

    def test_cleanup_listing_failure_still_cleans_other_repository(self):
        self.configure(list_failure=API)
        result = self.deploy()
        self.assert_success(result)
        self.assertIn("deployment remains successful", result.stderr)
        self.assertIn(f"{API}:old", self.state()["images"])
        self.assertNotIn(f"{WEB}:old", self.state()["images"])

    def test_unreadable_previous_config_skips_cleanup(self):
        self.configure(config_failure=True)
        result = self.deploy()
        self.assert_success(result)
        self.assertIn("image cleanup will be skipped", result.stderr)
        self.assert_no_cleanup()

    def test_empty_previous_config_skips_cleanup(self):
        self.configure(empty_config=True)
        self.assert_success(self.deploy())
        self.assert_no_cleanup()

    def test_incomplete_previous_config_skips_cleanup(self):
        (self.root / "compose.yml").unlink()
        self.assert_success(self.deploy())
        self.assert_no_cleanup()

    def test_failed_health_check_restores_previous_images_without_cleanup(self):
        self.configure(health_failure=True)
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("previous image configuration restored", result.stderr)
        self.assertEqual(self.state()["running"], self.images("previous"))
        self.assertEqual((self.root / ".env").read_text(), self.env_text("previous"))
        self.assertEqual((self.root / "compose.yml").read_text(), "previous compose")
        self.assert_no_cleanup()

    def test_pull_or_preflight_failure_preserves_previous_configuration(self):
        for failure in ("pull_failure", "preflight_failure"):
            with self.subTest(failure=failure):
                self.configure(pull_failure=False, preflight_failure=False)
                self.configure(**{failure: True})
                self.assertNotEqual(self.deploy().returncode, 0)
                self.assertEqual(self.state()["running"], self.images("previous"))
                self.assertEqual((self.root / "compose.yml").read_text(),
                                 "previous compose")
                self.assert_no_cleanup()


if __name__ == "__main__":
    unittest.main()
