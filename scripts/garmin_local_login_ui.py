#!/usr/bin/env python3
"""Local-only Garmin credential form for TrainingOS testing.

Runs on 127.0.0.1 and writes .env.local with file mode 0600. This helper is for
local MVP testing when the Codex terminal cannot accept interactive input.
"""

from __future__ import annotations

import html
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.local"
IMPORT_SCRIPT = ROOT / "scripts" / "garmin_import.py"
PYTHON = ROOT / ".venv" / "bin" / "python"


FORM = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TrainingOS Garmin Login</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #0f172a; color: #e5e7eb; }
    main { max-width: 560px; margin: 7vh auto; padding: 28px; background: #111827; border: 1px solid #374151; border-radius: 8px; }
    h1 { font-size: 22px; margin: 0 0 8px; }
    p { color: #9ca3af; line-height: 1.5; }
    label { display: block; margin-top: 18px; font-weight: 600; }
    input { width: 100%; box-sizing: border-box; margin-top: 8px; padding: 12px; border-radius: 6px; border: 1px solid #4b5563; background: #030712; color: #f9fafb; font-size: 16px; }
    button { margin-top: 22px; padding: 12px 14px; border: 0; border-radius: 6px; background: #2563eb; color: white; font-weight: 700; cursor: pointer; }
    button:disabled { opacity: .65; cursor: wait; }
    .secondary { background: #374151; margin-left: 8px; }
    .note { font-size: 13px; }
    .status { display: none; margin-top: 18px; padding: 12px; border: 1px solid #334155; background: #0b1220; border-radius: 6px; color: #cbd5e1; }
  </style>
</head>
<body>
  <main>
    <h1>TrainingOS Garmin Login</h1>
    <p>本页只在本机 127.0.0.1 运行。提交后会创建 <code>.env.local</code>，该文件已被 Git 忽略。</p>
    <form method="post" action="/save">
      <label>Garmin 邮箱</label>
      <input name="email" type="email" autocomplete="username" required>
      <label>Garmin 密码</label>
      <input name="password" type="password" autocomplete="current-password" required>
      <button name="action" value="save" type="submit">保存凭据</button>
      <button class="secondary" name="action" value="run" type="submit">保存并测试 3 天导入</button>
    </form>
    <div id="status" class="status">已提交，正在处理。导入测试通常需要几秒到一分钟，请不要重复点击。</div>
    <p class="note">测试完成后，你可以删除 <code>.env.local</code>。不要把 Garmin 密码发到聊天里。</p>
  </main>
  <script>
    const form = document.querySelector("form");
    const status = document.getElementById("status");
    form.addEventListener("submit", () => {
      status.style.display = "block";
      for (const button of form.querySelectorAll("button")) button.disabled = true;
    });
  </script>
</body>
</html>
"""


def write_env(email: str, password: str) -> None:
    ENV_PATH.write_text(f"GARMIN_EMAIL={email}\nGARMIN_PASSWORD={password}\n", encoding="utf-8")
    os.chmod(ENV_PATH, 0o600)


def run_import() -> tuple[int, str]:
    if not PYTHON.exists():
        return 1, f"Missing virtualenv Python: {PYTHON}"
    process = subprocess.run(
        [str(PYTHON), str(IMPORT_SCRIPT), "--days", "3"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    output = (process.stdout + "\n" + process.stderr).strip()
    return process.returncode, output


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return
        self.respond_html(FORM)

    def do_POST(self) -> None:
        if self.path != "/save":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        data = parse_qs(body)
        email = data.get("email", [""])[0].strip()
        password = data.get("password", [""])[0]
        action = data.get("action", ["save"])[0]
        if not email or not password:
            self.send_error(400, "Missing email or password")
            return
        write_env(email, password)
        if action == "run":
            code, output = run_import()
            status = "导入测试完成" if code == 0 else "导入测试失败"
            safe_output = html.escape(output)
            self.respond_html(
                f"""<!doctype html><meta charset="utf-8"><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:32px;background:#0f172a;color:#e5e7eb">
                <h1>{status}</h1>
                <p><code>.env.local</code> 已保存。</p>
                <pre style="white-space:pre-wrap;background:#030712;border:1px solid #374151;padding:16px;border-radius:8px">{safe_output}</pre>
                <p>可以关闭此页面，回到 Codex 让我检查结果。</p>
                </body>"""
            )
            return
        self.respond_html(
            """<!doctype html><meta charset="utf-8"><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:32px;background:#0f172a;color:#e5e7eb">
            <h1>已保存</h1><p><code>.env.local</code> 已创建。可以关闭此页面，回到 Codex 继续测试。</p></body>"""
        )

    def respond_html(self, content: str) -> None:
        payload = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    server = HTTPServer(("127.0.0.1", 8765), Handler)
    print("TrainingOS Garmin login UI: http://127.0.0.1:8765")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
