"""各クライアント用 sandbox_guard アダプタの stdin → stdout 契約のテスト。

サンドボックス判定は .agent-sandbox マーカーを置いた一時ディレクトリで再現する。
アダプタはホスト Windows でのみ動作する(os.name != "nt" では何も出力しない)ため、
Windows 以外ではスキップする。
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"


def run_adapter(client: str, payload, *args, cwd=None):
    proc = subprocess.run(
        [sys.executable, str(HOOKS / f"{client}_sandbox_guard.py"), *args],
        input=json.dumps(payload), capture_output=True, text=True, cwd=cwd, check=True)
    out = proc.stdout.strip()
    return json.loads(out) if out else None


@unittest.skipUnless(os.name == "nt", "ガードはホスト Windows でのみ動作する")
class AdapterTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.sandbox = Path(tmp.name) / "inside"
        self.sandbox.mkdir()
        (self.sandbox / ".agent-sandbox").write_text("")
        self.host = Path(tmp.name) / "outside"
        self.host.mkdir()

    # Claude Code
    def test_claude_blocks_prompt(self):
        out = run_adapter("claude", {"hook_event_name": "UserPromptSubmit", "cwd": str(self.sandbox)})
        self.assertEqual(out["decision"], "block")
        self.assertIn("agent-sandbox", out["reason"])

    def test_claude_warns_on_session_start(self):
        out = run_adapter("claude", {"hook_event_name": "SessionStart", "cwd": str(self.sandbox)})
        self.assertEqual(set(out), {"systemMessage"})

    def test_claude_silent_outside(self):
        self.assertIsNone(run_adapter("claude", {"hook_event_name": "UserPromptSubmit", "cwd": str(self.host)}))

    # Codex CLI
    def test_codex_blocks_prompt(self):
        out = run_adapter("codex", {"hook_event_name": "UserPromptSubmit", "cwd": str(self.sandbox)})
        self.assertEqual(out["decision"], "block")
        self.assertIn("systemMessage", out)

    def test_codex_event_from_argument(self):
        out = run_adapter("codex", {"cwd": str(self.sandbox)}, "--event", "UserPromptSubmit")
        self.assertEqual(out["decision"], "block")

    def test_codex_warns_on_session_start(self):
        out = run_adapter("codex", {"hook_event_name": "SessionStart", "cwd": str(self.sandbox)})
        self.assertEqual(set(out), {"systemMessage"})

    # Cursor
    def test_cursor_blocks_prompt(self):
        out = run_adapter("cursor", {"hook_event_name": "beforeSubmitPrompt",
                                     "workspace_roots": [str(self.host), str(self.sandbox)]})
        self.assertIs(out["continue"], False)
        self.assertIn(str(self.sandbox), out["user_message"])

    def test_cursor_accepts_uri_style_root(self):
        root = "/" + self.sandbox.as_posix()
        out = run_adapter("cursor", {"hook_event_name": "beforeSubmitPrompt", "workspace_roots": [root]})
        self.assertIs(out["continue"], False)

    def test_cursor_session_start_adds_context(self):
        out = run_adapter("cursor", {"hook_event_name": "sessionStart", "workspace_roots": [str(self.sandbox)]})
        self.assertIn("additional_context", out)
        self.assertNotIn("continue", out)

    def test_cursor_falls_back_to_cwd(self):
        out = run_adapter("cursor", {"hook_event_name": "beforeSubmitPrompt"}, cwd=self.sandbox)
        self.assertIs(out["continue"], False)

    def test_cursor_silent_outside(self):
        self.assertIsNone(run_adapter("cursor", {"hook_event_name": "beforeSubmitPrompt",
                                                 "workspace_roots": [str(self.host)]}))

    # Antigravity
    def test_antigravity_denies_tools(self):
        out = run_adapter("antigravity", {"workspacePaths": [str(self.sandbox)],
                                          "toolCall": {"name": "run_command"}}, "--event", "PreToolUse")
        self.assertEqual(out["decision"], "deny")

    def test_antigravity_injects_warning(self):
        out = run_adapter("antigravity", {"workspacePaths": [str(self.sandbox)]}, "--event", "PreInvocation")
        self.assertIn("ephemeralMessage", out["injectSteps"][0])

    def test_antigravity_event_inferred_from_payload(self):
        out = run_adapter("antigravity", {"workspacePaths": [str(self.sandbox)], "toolCall": {}})
        self.assertEqual(out["decision"], "deny")

    def test_antigravity_silent_outside(self):
        self.assertIsNone(run_adapter("antigravity", {"workspacePaths": [str(self.host)]}, "--event", "PreToolUse"))


if __name__ == "__main__":
    unittest.main()
