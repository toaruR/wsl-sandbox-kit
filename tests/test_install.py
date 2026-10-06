"""install.py の配置・フック登録マージのテスト。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT_ROOT))

import install  # noqa: E402

ALL = list(install.CLIENTS)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class InstallTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.target = Path(tmp.name)

    def test_places_sandbox_files_without_destroy(self):
        install.install(self.target, ALL, dry_run=False)
        kit = self.target / ".sandbox-kit"
        self.assertTrue((kit / "open_in_sandbox.py").is_file())
        self.assertTrue((kit / "provision.sh").is_file())
        self.assertFalse((kit / "destroy_sandbox.py").exists())
        self.assertNotIn(b"\r\n", (kit / "provision.sh").read_bytes())

    def test_skills_per_client(self):
        install.install(self.target, ["claude"], dry_run=False)
        self.assertTrue((self.target / ".claude/skills/sandbox-open/SKILL.md").is_file())
        self.assertFalse((self.target / ".agents/skills").exists())

        install.install(self.target, ["cursor"], dry_run=False)
        self.assertTrue((self.target / ".agents/skills/sandbox-open/SKILL.md").is_file())

    def test_hook_files_use_client_adapter(self):
        install.install(self.target, ALL, dry_run=False)
        for client, hook_dir in install.HOOK_DIRS.items():
            placed = (self.target / hook_dir / "sandbox_guard.py").read_text(encoding="utf-8")
            source = (KIT_ROOT / "hooks" / f"{client}_sandbox_guard.py").read_text(encoding="utf-8")
            self.assertEqual(placed, source.replace("\r\n", "\n"), client)
            self.assertTrue((self.target / hook_dir / "_sandbox_guard_core.py").is_file())

    def test_claude_registration_keeps_other_hooks(self):
        settings = self.target / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        other = {"hooks": [{"type": "command", "command": "echo other"}]}
        settings.write_text(json.dumps({"model": "x", "hooks": {"UserPromptSubmit": [other]}}), encoding="utf-8")

        install.install(self.target, ["claude"], dry_run=False)
        data = load(settings)
        self.assertEqual(data["model"], "x")
        commands = [h["command"] for g in data["hooks"]["UserPromptSubmit"] for h in g["hooks"]]
        self.assertIn("echo other", commands)
        self.assertTrue(any("sandbox_guard.py" in c for c in commands))
        self.assertIn("SessionStart", data["hooks"])

    def test_codex_registration_schema(self):
        install.install(self.target, ["codex"], dry_run=False)
        data = load(self.target / ".codex/hooks.json")
        group = data["hooks"]["UserPromptSubmit"][0]
        handler = group["hooks"][0]
        self.assertEqual(handler["type"], "command")
        self.assertIn("--event UserPromptSubmit", handler["command"])
        self.assertIn((self.target / ".codex/hooks/sandbox_guard.py").resolve().as_posix(), handler["command"])

    def test_cursor_registration_schema(self):
        install.install(self.target, ["cursor"], dry_run=False)
        data = load(self.target / ".cursor/hooks.json")
        self.assertEqual(data["version"], 1)
        for event in ("sessionStart", "beforeSubmitPrompt"):
            self.assertIn(".cursor/hooks/sandbox_guard.py", data["hooks"][event][0]["command"])

    def test_antigravity_registration_schema(self):
        install.install(self.target, ["antigravity"], dry_run=False)
        entry = load(self.target / ".agents/hooks.json")[install.ANTIGRAVITY_HOOK_NAME]
        self.assertIn("--event PreInvocation", entry["PreInvocation"][0]["command"])
        self.assertEqual(entry["PreToolUse"][0]["matcher"], "*")
        self.assertIn("--event PreToolUse", entry["PreToolUse"][0]["hooks"][0]["command"])
        # Windows では " が \" にエスケープされて渡るためクォートしない
        self.assertNotIn('"', entry["PreInvocation"][0]["command"])

    def test_idempotent(self):
        install.install(self.target, ALL, dry_run=False)
        report = install.install(self.target, ALL, dry_run=False)
        self.assertEqual(report.placed, [])
        self.assertEqual(report.updated, [])

    def test_stale_command_is_updated(self):
        install.install(self.target, ["cursor"], dry_run=False)
        path = self.target / ".cursor/hooks.json"
        data = load(path)
        data["hooks"]["sessionStart"][0]["command"] = "python old/sandbox_guard.py"
        path.write_text(json.dumps(data), encoding="utf-8")

        report = install.install(self.target, ["cursor"], dry_run=False)
        self.assertTrue(any("sessionStart" in u for u in report.updated))
        self.assertEqual(len(load(path)["hooks"]["sessionStart"]), 1)

    def test_dry_run_writes_nothing(self):
        report = install.install(self.target, ALL, dry_run=True)
        self.assertTrue(report.placed)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_rejects_unknown_client(self):
        with self.assertRaises(install.InstallError):
            install.parse_clients("claude,vim")

    def test_broken_json_is_skipped_with_warning(self):
        path = self.target / ".cursor/hooks.json"
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        report = install.install(self.target, ["cursor"], dry_run=False)
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")
        self.assertTrue(any("hooks.json" in w for w in report.warnings))


if __name__ == "__main__":
    unittest.main()
