#!/usr/bin/env python3
"""Local-only workout correction UI for TrainingOS."""

from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from . import trainingos_db, trainingos_observability
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore
    import trainingos_observability  # type: ignore


ROOT = Path(__file__).resolve().parents[1]


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8fafc; color: #111827; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 24px; margin: 0 0 18px; }}
    h2 {{ font-size: 18px; margin: 26px 0 10px; }}
    a {{ color: #1d4ed8; text-decoration: none; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #d1d5db; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 10px; text-align: left; vertical-align: middle; }}
    th {{ background: #f3f4f6; font-size: 13px; }}
    input, textarea {{ box-sizing: border-box; width: 100%; padding: 9px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 15px; background: white; }}
    textarea {{ min-height: 70px; }}
    button {{ padding: 10px 14px; border: 0; border-radius: 6px; background: #2563eb; color: white; font-weight: 700; cursor: pointer; }}
    button.secondary {{ background: #374151; }}
    pre {{ white-space: pre-wrap; background: #111827; color: #e5e7eb; padding: 14px; border-radius: 8px; overflow-x: auto; }}
    nav {{ display: flex; gap: 14px; margin: 0 0 18px; }}
    nav a {{ font-weight: 700; }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 999px; background: #e5e7eb; color: #374151; font-size: 12px; }}
    .muted {{ color: #6b7280; }}
    .row-actions {{ display: flex; gap: 8px; align-items: center; margin-top: 16px; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 12px 0 22px; }}
    .field {{ background: white; border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; }}
    .field label {{ display: block; color: #6b7280; font-size: 12px; margin-bottom: 6px; }}
    .empty {{ background: white; border: 1px solid #d1d5db; border-radius: 8px; padding: 18px; }}
    @media (max-width: 760px) {{
      main {{ padding: 14px; }}
      .summary {{ grid-template-columns: 1fr; }}
      table, thead, tbody, th, td, tr {{ display: block; }}
      thead {{ display: none; }}
      tr {{ border-bottom: 1px solid #d1d5db; padding: 8px; }}
      td {{ border: 0; padding: 6px 0; }}
      td::before {{ content: attr(data-label); display: block; font-size: 12px; color: #6b7280; margin-bottom: 3px; }}
    }}
  </style>
</head>
<body><main>{body}</main></body></html>"""


def safe(value: object) -> str:
    return html.escape("" if value is None else str(value))


def numeric(value: object) -> str:
    return "" if value is None else html.escape(str(value))


class ReviewServer:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        trainingos_db.init_db(db_path)

    def connection(self):
        return trainingos_db.connect(self.db_path)

    def list_page(self) -> str:
        with self.connection() as connection:
            sessions = trainingos_db.get_recent_sessions(connection, 20)
        rows = []
        for session in sessions:
            rows.append(
                f"""<tr>
                  <td>{safe(session.get("completed_at"))}</td>
                  <td>{safe(session.get("activity_name") or session.get("session_type"))}</td>
                  <td>{safe(session.get("provider"))}</td>
                  <td><a href="/session?id={safe(session.get("id"))}">校正</a></td>
                </tr>"""
            )
        body = """<nav><a href="/">训练校正</a><a href="/debug">调试观测</a></nav><h1>TrainingOS 训练校正</h1>"""
        if rows:
            body += f"""<table>
              <thead><tr><th>完成时间</th><th>训练</th><th>来源</th><th></th></tr></thead>
              <tbody>{''.join(rows)}</tbody>
            </table>"""
        else:
            body += """<div class="empty">还没有已导入的训练。先运行 Garmin 完成活动导入，或稍后添加手动录入入口。</div>"""
        return page("TrainingOS Review", body)

    def session_page(self, session_id: str, saved: bool = False) -> str:
        with self.connection() as connection:
            session = trainingos_db.get_session_for_review(connection, session_id)
        if session is None:
            return page("Not found", "<h1>找不到训练记录</h1><p><a href='/'>返回</a></p>")
        sets = session.get("sets", [])
        if not sets:
            sets = [
                {
                    "exercise_name": "",
                    "set_order": 1,
                    "set_type": "working",
                    "weight_kg": None,
                    "reps": None,
                    "rpe": None,
                    "notes": "",
                }
            ]
        set_rows = []
        for index, set_log in enumerate(sets):
            set_rows.append(
                f"""<tr>
                  <td data-label="动作"><input name="exercise_name_{index}" value="{safe(set_log.get("exercise_name"))}"></td>
                  <td data-label="组序"><input name="set_order_{index}" type="number" min="1" value="{numeric(set_log.get("set_order") or index + 1)}"></td>
                  <td data-label="类型"><input name="set_type_{index}" value="{safe(set_log.get("set_type") or "working")}"></td>
                  <td data-label="重量 kg"><input name="weight_kg_{index}" inputmode="decimal" value="{numeric(set_log.get("weight_kg"))}"></td>
                  <td data-label="次数"><input name="reps_{index}" type="number" min="0" value="{numeric(set_log.get("reps"))}"></td>
                  <td data-label="RPE"><input name="rpe_{index}" inputmode="decimal" value="{numeric(set_log.get("rpe"))}"></td>
                  <td data-label="备注"><input name="notes_{index}" value="{safe(set_log.get("notes"))}"></td>
                </tr>"""
            )
        saved_notice = "<p class='muted'>已保存校正。</p>" if saved else ""
        body = f"""<nav><a href="/">训练校正</a><a href="/debug">调试观测</a></nav>
        <p><a href="/">返回列表</a></p>
        <h1>{safe(session.get("activity_name") or "Completed Workout")}</h1>
        {saved_notice}
        <form method="post" action="/save">
          <input type="hidden" name="session_id" value="{safe(session_id)}">
          <input type="hidden" name="set_count" value="{len(sets)}">
          <div class="summary">
            <div class="field"><label>整体 RPE</label><input name="overall_rpe" inputmode="decimal" value="{numeric(session.get("overall_rpe"))}"></div>
            <div class="field"><label>疲劳 1-10</label><input name="fatigue_rating" type="number" min="1" max="10" value="{numeric(session.get("fatigue_rating"))}"></div>
            <div class="field"><label>完成时间</label><input value="{safe(session.get("completed_at"))}" disabled></div>
            <div class="field"><label>来源</label><input value="{safe(session.get("provider"))}" disabled></div>
          </div>
          <h2>组记录</h2>
          <table>
            <thead><tr><th>动作</th><th>组序</th><th>类型</th><th>重量 kg</th><th>次数</th><th>RPE</th><th>备注</th></tr></thead>
            <tbody>{''.join(set_rows)}</tbody>
          </table>
          <h2>主观记录</h2>
          <label>疼痛 / 技术备注</label>
          <textarea name="pain_notes">{safe(session.get("pain_notes"))}</textarea>
          <label>恢复 / 状态备注</label>
          <textarea name="readiness_notes">{safe(session.get("readiness_notes"))}</textarea>
          <div class="row-actions">
            <button type="submit">保存校正</button>
            <button class="secondary" type="submit" name="next" value="analysis">保存并进入 AI 复盘</button>
            <a href="/summary?id={safe(session_id)}">查看 AI 输入摘要</a>
          </div>
        </form>"""
        return page("TrainingOS Review", body)

    def debug_page(self) -> str:
        events = trainingos_observability.read_events(100)
        rows = []
        for event in reversed(events):
            rows.append(
                f"""<tr>
                  <td>{safe(event.get("time"))}</td>
                  <td><span class="badge">{safe(event.get("status"))}</span></td>
                  <td>{safe(event.get("event"))}</td>
                  <td><pre>{safe(json.dumps(event.get("details", {}), ensure_ascii=False, indent=2))}</pre></td>
                </tr>"""
            )
        body = """<nav><a href="/">训练校正</a><a href="/debug">调试观测</a></nav>
        <h1>调试观测</h1>
        <p class="muted">这里显示本机调试事件：Garmin 导入、写入 SQLite、保存校正、生成 AI 摘要。日志位于本机 data/debug_events.jsonl，已被 Git 忽略。</p>
        <form method="post" action="/debug/clear"><button type="submit">清空调试日志</button></form>
        """
        if rows:
            body += f"""<table>
              <thead><tr><th>时间</th><th>状态</th><th>事件</th><th>细节</th></tr></thead>
              <tbody>{''.join(rows)}</tbody>
            </table>"""
        else:
            body += "<div class='empty'>暂无调试事件。运行导入或保存一次校正后会显示。</div>"
        return page("TrainingOS Debug", body)

    def summary_page(self, session_id: str) -> str:
        with self.connection() as connection:
            try:
                summary = trainingos_db.build_ai_review_summary(connection, session_id)
            except ValueError:
                return page("Not found", "<h1>找不到训练记录</h1><p><a href='/'>返回</a></p>")
        payload = html.escape(json.dumps(summary, indent=2, ensure_ascii=False))
        return page(
            "TrainingOS AI Summary",
            f"<nav><a href='/'>训练校正</a><a href='/debug'>调试观测</a></nav><p><a href='/session?id={safe(session_id)}'>返回校正</a></p><h1>AI 输入摘要</h1><pre>{payload}</pre>",
        )

    def analysis_page(self, session_id: str) -> str:
        with self.connection() as connection:
            try:
                prompt = trainingos_db.build_post_workout_analysis_prompt(connection, session_id)
            except ValueError:
                return page("Not found", "<h1>找不到训练记录</h1><p><a href='/'>返回</a></p>")
        trainingos_observability.record_event(
            "manual_ai_analysis_opened",
            details={"session_id": session_id},
        )
        body = f"""<nav><a href="/">训练校正</a><a href="/debug">调试观测</a></nav>
        <p><a href="/session?id={safe(session_id)}">返回校正</a></p>
        <h1>AI 复盘</h1>
        <p class="muted">这是手动复盘入口。它只分析本次训练；次日训练计划应等第二天 Garmin 睡眠和恢复指标同步后再生成。</p>
        <textarea readonly style="min-height: 520px">{safe(prompt)}</textarea>"""
        return page("TrainingOS AI Analysis", body)

    def save(self, form_data: dict[str, list[str]]) -> str:
        session_id = form_data.get("session_id", [""])[0]
        set_count = int(form_data.get("set_count", ["0"])[0] or 0)
        sets = []
        for index in range(set_count):
            exercise_name = form_data.get(f"exercise_name_{index}", [""])[0].strip()
            if not exercise_name:
                continue
            sets.append(
                {
                    "exercise_name": exercise_name,
                    "set_order": parse_int(form_data.get(f"set_order_{index}", [""])[0]),
                    "set_type": form_data.get(f"set_type_{index}", ["working"])[0].strip() or "working",
                    "weight_kg": parse_float(form_data.get(f"weight_kg_{index}", [""])[0]),
                    "reps": parse_int(form_data.get(f"reps_{index}", [""])[0]),
                    "rpe": parse_float(form_data.get(f"rpe_{index}", [""])[0]),
                    "notes": form_data.get(f"notes_{index}", [""])[0].strip() or None,
                }
            )
        payload = {
            "overall_rpe": parse_float(form_data.get("overall_rpe", [""])[0]),
            "fatigue_rating": parse_int(form_data.get("fatigue_rating", [""])[0]),
            "pain_notes": form_data.get("pain_notes", [""])[0].strip() or None,
            "readiness_notes": form_data.get("readiness_notes", [""])[0].strip() or None,
            "sets": sets,
        }
        with self.connection() as connection:
            trainingos_db.update_review_payload(connection, session_id, payload)
        if form_data.get("next", [""])[0] == "analysis":
            return self.analysis_page(session_id)
        return self.session_page(session_id, saved=True)


def parse_float(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_int(value: str) -> int | None:
    parsed = parse_float(value)
    return int(parsed) if parsed is not None else None


def make_handler(app: ReviewServer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/":
                self.respond(app.list_page())
                return
            if parsed.path == "/session":
                self.respond(app.session_page(query.get("id", [""])[0]))
                return
            if parsed.path == "/summary":
                self.respond(app.summary_page(query.get("id", [""])[0]))
                return
            if parsed.path == "/analysis":
                self.respond(app.analysis_page(query.get("id", [""])[0]))
                return
            if parsed.path == "/debug":
                self.respond(app.debug_page())
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if self.path == "/debug/clear":
                trainingos_observability.clear_events()
                self.respond(app.debug_page())
                return
            if self.path != "/save":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            self.respond(app.save(parse_qs(body)))

        def respond(self, content: str) -> None:
            payload = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start local TrainingOS workout review UI.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8787, help="Port to bind.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = ReviewServer(Path(args.db))
    server = HTTPServer((args.host, args.port), make_handler(app))
    print(f"TrainingOS review UI: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
