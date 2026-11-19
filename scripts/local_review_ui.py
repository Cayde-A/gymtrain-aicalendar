#!/usr/bin/env python3
"""Local-only workout correction UI for TrainingOS."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from . import (
        trainingos_dashboard,
        trainingos_db,
        trainingos_observability,
        trainingos_voice_input,
    )
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_dashboard  # type: ignore
    import trainingos_db  # type: ignore
    import trainingos_observability  # type: ignore
    import trainingos_voice_input  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
APP_ICON_PATH = ROOT / "artifacts" / "trainingos-app-icon.svg"
GARMIN_IMPORT_SCRIPT = ROOT / "scripts" / "garmin_import.py"
PWA_MANIFEST = {
    "id": "/",
    "name": "TrainingOS",
    "short_name": "TrainingOS",
    "description": "Local-first training review and planning",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#f8fafc",
    "theme_color": "#111827",
    "icons": [
        {
            "src": "/app-icon.svg",
            "sizes": "any",
            "type": "image/svg+xml",
            "purpose": "any maskable",
        }
    ],
}
SERVICE_WORKER = """const CACHE_NAME = 'trainingos-shell-v1';
const STATIC_ASSETS = ['/offline', '/manifest.webmanifest', '/app-icon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.match('/offline')));
    return;
  }
  if (url.origin === self.location.origin && STATIC_ASSETS.includes(url.pathname)) {
    event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
  }
});
"""


def page(title: str, body: str, language: str = "zh-CN") -> str:
    return f"""<!doctype html>
<html lang="{safe(language)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#111827">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="default">
  <link rel="manifest" href="/manifest.webmanifest">
  <link rel="icon" href="/app-icon.svg" type="image/svg+xml">
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
    input, textarea, select {{ box-sizing: border-box; width: 100%; padding: 9px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 15px; background: white; }}
    input[type="checkbox"] {{ width: auto; }}
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
    .section-heading {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 26px; }}
    .section-heading h2 {{ margin: 0; }}
    .notice {{ margin: 12px 0; padding: 12px 14px; border: 1px solid #86efac; border-radius: 6px; background: #f0fdf4; color: #166534; }}
    .notice.error {{ border-color: #fca5a5; background: #fef2f2; color: #991b1b; }}
    .chart-panel {{ background: white; border: 1px solid #d1d5db; border-radius: 8px; padding: 16px; overflow: hidden; }}
    .chart-legend {{ display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 14px; font-size: 13px; }}
    .legend-key {{ display: inline-flex; align-items: center; gap: 6px; }}
    .legend-swatch {{ width: 12px; height: 12px; border-radius: 2px; }}
    .trend-chart {{ display: grid; grid-template-columns: repeat(14, minmax(0, 1fr)); gap: 4px; min-height: 186px; align-items: end; }}
    .trend-day {{ min-width: 0; text-align: center; }}
    .trend-bars {{ height: 148px; display: flex; gap: 2px; align-items: end; justify-content: center; border-bottom: 1px solid #cbd5e1; }}
    .trend-bar {{ width: 28%; min-width: 3px; position: relative; border-radius: 2px 2px 0 0; }}
    .trend-bar.sleep {{ background: #2563eb; }}
    .trend-bar.battery {{ background: #16a34a; }}
    .trend-bar.readiness {{ background: #d97706; }}
    .trend-value {{ position: absolute; left: 50%; top: -16px; transform: translateX(-50%); font-size: 9px; color: #374151; }}
    .trend-date {{ display: block; margin-top: 6px; font-size: 9px; color: #6b7280; overflow: hidden; }}
    .sleep-stack {{ display: flex; width: 100%; height: 34px; border-radius: 4px; overflow: hidden; background: #e5e7eb; }}
    .sleep-segment {{ min-width: 2px; }}
    .sleep-segment.deep {{ background: #1d4ed8; }}
    .sleep-segment.light {{ background: #60a5fa; }}
    .sleep-segment.rem {{ background: #7c3aed; }}
    .sleep-segment.awake {{ background: #dc2626; }}
    details {{ margin-top: 14px; }}
    summary {{ cursor: pointer; color: #1d4ed8; font-weight: 700; }}
    @media (max-width: 760px) {{
      main {{ padding: 14px; }}
      nav {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 8px; }}
      nav a {{ white-space: nowrap; text-align: center; font-size: 14px; }}
      .summary {{ grid-template-columns: 1fr; }}
      .section-heading {{ align-items: stretch; flex-direction: column; }}
      .trend-value {{ display: none; }}
      .trend-date {{ writing-mode: vertical-rl; height: 34px; }}
      table, thead, tbody, th, td, tr {{ display: block; }}
      thead {{ display: none; }}
      tr {{ border-bottom: 1px solid #d1d5db; padding: 8px; }}
      td {{ border: 0; padding: 6px 0; }}
      td::before {{ content: attr(data-label); display: block; font-size: 12px; color: #6b7280; margin-bottom: 3px; }}
    }}
  </style>
</head>
<body><main>{body}</main>
<script>
  if ('serviceWorker' in navigator) {{
    window.addEventListener('load', () => navigator.serviceWorker.register('/service-worker.js'));
  }}
  document.querySelectorAll('[data-speech-target]').forEach((button) => {{
    button.addEventListener('click', () => {{
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      const target = document.getElementById(button.dataset.speechTarget);
      if (!SpeechRecognition || !target) {{
        button.disabled = true;
        button.title = '当前浏览器不支持语音转写';
        return;
      }}
      const recognition = new SpeechRecognition();
      recognition.lang = 'zh-CN';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      button.disabled = true;
      recognition.onresult = (event) => {{
        target.value = event.results[0][0].transcript;
        const submitId = button.dataset.submitTarget;
        if (submitId) document.getElementById(submitId)?.click();
      }};
      recognition.onerror = () => {{ button.disabled = false; }};
      recognition.onend = () => {{ button.disabled = false; }};
      recognition.start();
    }});
  }});
  document.querySelectorAll('[data-disable-on-submit]').forEach((form) => {{
    form.addEventListener('submit', () => {{
      const button = form.querySelector('button[type="submit"]');
      if (!button) return;
      button.disabled = true;
      button.textContent = button.dataset.loadingText || '处理中...';
    }});
  }});
</script>
</body></html>"""


def safe(value: object) -> str:
    return html.escape("" if value is None else str(value))


def numeric(value: object) -> str:
    return "" if value is None else html.escape(str(value))


def value_or(value: object, fallback: str = "无") -> object:
    return fallback if value is None else value


def format_sleep_duration(value: object, locale: str = "zh") -> str:
    if value is None:
        return dashboard_text(locale, "无")
    try:
        minutes = max(0, int(value))
    except (TypeError, ValueError):
        return dashboard_text(locale, "无")
    hours, remainder = divmod(minutes, 60)
    return (
        f"{hours} 小时 {remainder} 分"
        if locale == "zh"
        else f"{hours} hr {remainder} min"
    )


DASHBOARD_EN = {
    "总览": "Overview", "训练日": "Training Days", "录入": "Entry", "身体指标": "Body Metrics",
    "触发设置": "Triggers", "调试观测": "Debug", "无": "None", "查看": "View",
    "尚未找到可作为分析锚点的历史训练。恢复指标会继续同步，TrainingOS 将等待你完成第一次训练后再进行解析、AI 复盘和次日计划。": "No usable training history was found. Recovery metrics will keep syncing, and TrainingOS will wait for your first completed workout before analysis, AI review, or next-day planning.",
    "已找到训练活动，但没有有效训练组。请先重新同步或校正第一次训练记录，系统暂不进行 AI 解析。": "A training activity was found, but it has no active sets. Resync or correct the first workout before AI analysis.",
    "TrainingOS 总览": "TrainingOS Overview", "近 30 天训练日": "Training days (30d)",
    "训练次数": "Sessions", "有效组": "Active sets", "训练量 kg": "Volume kg",
    "PR 记录": "PR records", "数据缺失": "Missing fields", "今日状态": "Today's status",
    "立即读取 Garmin": "Sync Garmin now", "读取中...": "Syncing...", "恢复日期": "Recovery date",
    "睡眠分数": "Sleep score", "睡眠时长": "Sleep duration", "HRV 状态": "HRV status",
    "训练准备度": "Training readiness", "体重 kg": "Body weight kg", "周期": "Cycle",
    "未开始": "Not started", "14 天恢复趋势": "14-day recovery trend", "睡眠构成": "Sleep stages",
    "详细健康指标": "Detailed health metrics", "最近训练日": "Recent training days",
    "日期": "Date", "活动数": "Activities", "训练内容": "Training", "暂无训练记录。": "No training records.",
    "当前 PR": "Current PRs", "动作": "Exercise", "最佳组": "Best set", "暂无 PR 状态。": "No PR state.",
    "最近计划流程": "Recent planning runs", "目标日期": "Target date", "状态": "Status",
    "主肌群": "Primary group", "恢复调整": "Recovery adjustment", "暂无计划流程记录。": "No planning runs.",
    "暂无 14 天恢复趋势数据。": "No 14-day recovery trend data.", "睡眠": "Sleep", "准备度": "Readiness",
    "查看趋势数据": "View trend data", "最近十四天睡眠分数、Body Battery 和训练准备度趋势": "Sleep score, Body Battery, and training readiness over the last 14 days",
    "深睡": "Deep", "浅睡": "Light", "清醒": "Awake", "分": "min",
    "暂无睡眠阶段明细。": "No sleep-stage details.", "睡眠阶段构成": "Sleep-stage composition",
    "夜间 HRV 均值 ms": "Overnight HRV average ms", "静息心率": "Resting heart rate",
    "平均压力": "Average stress", "平均呼吸 次/分": "Average respiration /min", "平均血氧 %": "Average pulse ox %",
    "步数": "Steps", "活动热量 kcal": "Active calories kcal", "Body Battery 充/耗": "Body Battery charged/drained",
    "准备度级别": "Readiness level", "暂无分类健康明细。": "No categorized health details.",
    "Garmin 读取超时，请稍后重试或查看调试观测。": "Garmin sync timed out. Retry later or check Debug.",
    "无法启动 Garmin 读取进程，请查看调试观测。": "Could not start Garmin sync. Check Debug.",
    "Garmin 读取失败，请查看调试观测后重试。": "Garmin sync failed. Check Debug before retrying.",
    "Garmin 已响应，但今天尚无可显示的恢复指标。": "Garmin responded, but no recovery metrics are available for today.",
}


def resolve_locale(accept_language: str | None = None, override: str | None = None) -> str:
    requested = (override or "").strip().lower()
    if requested in {"zh", "zh-cn", "zh-hans", "zh-tw", "zh-hant"}:
        return "zh"
    if requested in {"en", "en-us", "en-au", "en-gb"}:
        return "en"
    first = (accept_language or "").split(",", 1)[0].strip().lower()
    return "zh" if first.startswith("zh") else "en"


def dashboard_text(locale: str, source: str) -> str:
    return DASHBOARD_EN.get(source, source) if locale == "en" else source


def nav(locale: str = "zh") -> str:
    t = lambda value: dashboard_text(locale, value)
    suffix = "?lang=en" if locale == "en" else "?lang=zh"
    return (
        f'<nav><a href="/{suffix}">{t("总览")}</a><a href="/training">{t("训练日")}</a>'
        f'<a href="/entry">{t("录入")}</a><a href="/body">{t("身体指标")}</a>'
        f'<a href="/settings">{t("触发设置")}</a><a href="/debug">{t("调试观测")}</a></nav>'
    )


def option(value: str, current: object, label: str) -> str:
    selected = " selected" if value == str(current) else ""
    return f'<option value="{safe(value)}"{selected}>{safe(label)}</option>'


def recovery_trend_chart(rows: list[dict[str, object]], locale: str = "zh") -> str:
    t = lambda value: dashboard_text(locale, value)
    if not rows:
        return f'<div class="empty">{t("暂无 14 天恢复趋势数据。")}</div>'
    days = []
    table_rows = []
    for row in rows:
        bars = []
        for field, class_name, label in (
            ("sleep_score", "sleep", t("睡眠")),
            ("body_battery", "battery", "Body Battery"),
            ("training_readiness", "readiness", t("准备度")),
        ):
            value = row.get(field)
            height = min(100.0, max(0.0, float(value))) if value is not None else 0
            bars.append(
                f'<div class="trend-bar {class_name}" style="height:{height}%" '
                f'title="{safe(label)} {safe(value_or(value))}">'
                f'<span class="trend-value">{safe(value_or(value, ""))}</span></div>'
            )
        date = str(row.get("metric_date") or "")
        days.append(
            f'<div class="trend-day"><div class="trend-bars">{"".join(bars)}</div>'
            f'<span class="trend-date">{safe(date[5:])}</span></div>'
        )
        table_rows.append(
            f'<tr><td data-label="{t("日期")}">{safe(date)}</td>'
            f'<td data-label="{t("睡眠分数")}">{safe(value_or(row.get("sleep_score"), t("无")))}</td>'
            f'<td data-label="Body Battery">{safe(value_or(row.get("body_battery"), t("无")))}</td>'
            f'<td data-label="{t("训练准备度")}">{safe(value_or(row.get("training_readiness"), t("无")))}</td></tr>'
        )
    return f'''<div class="chart-panel" role="img" aria-label="{t("最近十四天睡眠分数、Body Battery 和训练准备度趋势")}">
      <div class="chart-legend">
        <span class="legend-key"><span class="legend-swatch" style="background:#2563eb"></span>{t("睡眠分数")}</span>
        <span class="legend-key"><span class="legend-swatch" style="background:#16a34a"></span>Body Battery</span>
        <span class="legend-key"><span class="legend-swatch" style="background:#d97706"></span>{t("训练准备度")}</span>
      </div>
      <div class="trend-chart">{"".join(days)}</div>
      <details><summary>{t("查看趋势数据")}</summary><table><thead><tr><th>{t("日期")}</th><th>{t("睡眠分数")}</th><th>Body Battery</th><th>{t("训练准备度")}</th></tr></thead><tbody>{"".join(table_rows)}</tbody></table></details>
    </div>'''


def sleep_stage_chart(record: dict[str, object] | None, locale: str = "zh") -> str:
    t = lambda value: dashboard_text(locale, value)
    record = record or {}
    stages = [
        ("deep_sleep_minutes", "deep", "深睡"),
        ("light_sleep_minutes", "light", "浅睡"),
        ("rem_sleep_minutes", "rem", "REM"),
        ("awake_minutes", "awake", "清醒"),
    ]
    values = [max(0, int(record.get(field) or 0)) for field, _, _ in stages]
    total = sum(values)
    if total == 0:
        return f'<div class="empty">{t("暂无睡眠阶段明细。")}</div>'
    segments = []
    legend = []
    for (field, class_name, label), value in zip(stages, values):
        percent = value / total * 100
        segments.append(
            f'<span class="sleep-segment {class_name}" style="width:{percent:.2f}%" title="{safe(t(label))} {value} {t("分")}"></span>'
        )
        legend.append(f'<span class="legend-key">{safe(t(label))} {value} {t("分")}</span>')
    return f'<div class="chart-panel"><div class="sleep-stack" aria-label="{t("睡眠阶段构成")}">{"".join(segments)}</div><div class="chart-legend" style="margin:12px 0 0">{"".join(legend)}</div></div>'


def health_detail_cards(details: dict[str, dict[str, object] | None], locale: str = "zh") -> str:
    t = lambda value: dashboard_text(locale, value)
    hrv = details.get("hrv") or {}
    energy = details.get("energy") or {}
    vitals = details.get("vitals") or {}
    readiness = details.get("readiness") or {}
    charged = energy.get("body_battery_charged")
    drained = energy.get("body_battery_drained")
    charge_drain = None if charged is None and drained is None else f"{value_or(charged)} / {value_or(drained)}"
    items = (
        ("夜间 HRV 均值 ms", hrv.get("last_night_average_ms")),
        ("静息心率", vitals.get("heart_rate_resting")),
        ("平均压力", vitals.get("stress_average")),
        ("平均呼吸 次/分", vitals.get("respiration_average")),
        ("平均血氧 %", vitals.get("pulse_ox_average")),
        ("步数", energy.get("steps")),
        ("活动热量 kcal", energy.get("active_calories")),
        ("Body Battery 充/耗", charge_drain),
        ("准备度级别", readiness.get("level")),
    )
    if not any(value is not None for _, value in items):
        return f'<div class="empty">{t("暂无分类健康明细。")}</div>'
    return '<div class="summary">' + ''.join(
        f'<div class="field"><label>{safe(t(label))}</label><strong>{safe(value_or(value, t("无")))}</strong></div>'
        for label, value in items
    ) + '</div>'


class ReviewServer:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        trainingos_db.init_db(db_path)

    def connection(self):
        return trainingos_db.connect(self.db_path)

    def offline_page(self) -> str:
        return page(
            "TrainingOS Offline",
            "<h1>TrainingOS</h1><div class='empty'>当前无法连接本地服务。恢复连接后重新打开页面。</div>",
        )

    def dashboard_page(self, notice: str = "", notice_error: bool = False, locale: str = "zh") -> str:
        locale = resolve_locale(override=locale)
        t = lambda value: dashboard_text(locale, value)
        with self.connection() as connection:
            snapshot = trainingos_dashboard.dashboard_snapshot(connection)
        training = snapshot["training"]
        recovery = snapshot["latest_recovery"] or {}
        body_context = snapshot["body_metrics"]
        body_values = body_context.get("values") or {}
        cycle = snapshot["program_cycle"] or {}
        health_details = snapshot["health_details"]
        anchor = snapshot["training_anchor"]
        day_rows = "".join(
            f"<tr><td>{safe(item.get('training_date'))}</td>"
            f"<td>{safe(item.get('session_count'))}</td>"
            f"<td>{safe(item.get('activity_names'))}</td>"
            f"<td><a href='/day?date={safe(item.get('training_date'))}'>{t('查看')}</a></td></tr>"
            for item in snapshot["recent_training_days"]
        )
        pipeline_rows = "".join(
            f"<tr><td>{safe(item.get('target_date'))}</td>"
            f"<td>{safe(item.get('status'))}</td>"
            f"<td>{safe(item.get('primary_group'))}</td>"
            f"<td>{safe(item.get('recovery_adjustment'))}</td></tr>"
            for item in snapshot["recent_pipeline_runs"]
        )
        pr_rows = "".join(
            f"<tr><td>{safe(item.get('exercise'))}</td>"
            f"<td>{safe(round(float(item.get('best_value') or 0), 1))}</td>"
            f"<td>{safe(item.get('weight_kg'))} x {safe(item.get('reps'))}</td>"
            f"<td>{safe(str(item.get('achieved_at') or '')[:10])}</td></tr>"
            for item in snapshot["estimated_1rm_prs"]
        )
        notice_html = (
            f'<div class="notice{" error" if notice_error else ""}">{safe(notice)}</div>'
            if notice
            else ""
        )
        anchor_notice = ""
        if anchor["status"] == "waiting_for_first_training":
            anchor_notice = (
                '<div class="notice">尚未找到可作为分析锚点的历史训练。恢复指标会继续同步，'
                'TrainingOS 将等待你完成第一次训练后再进行解析、AI 复盘和次日计划。</div>'
            )
        elif anchor["status"] == "first_training_needs_data":
            anchor_notice = (
                '<div class="notice error">已找到训练活动，但没有有效训练组。请先重新同步或校正第一次训练记录，'
                '系统暂不进行 AI 解析。</div>'
            )
        if anchor_notice:
            for source in (
                "尚未找到可作为分析锚点的历史训练。恢复指标会继续同步，TrainingOS 将等待你完成第一次训练后再进行解析、AI 复盘和次日计划。",
                "已找到训练活动，但没有有效训练组。请先重新同步或校正第一次训练记录，系统暂不进行 AI 解析。",
            ):
                anchor_notice = anchor_notice.replace(source, t(source))
        lang_query = "en" if locale == "en" else "zh"
        body = f"""{nav(locale)}
        <h1>{t('TrainingOS 总览')}</h1>
        {notice_html}
        {anchor_notice}
        <div class="summary">
          <div class="field"><label>{t('近 30 天训练日')}</label><strong>{safe(training['training_days'])}</strong></div>
          <div class="field"><label>{t('训练次数')}</label><strong>{safe(training['session_count'])}</strong></div>
          <div class="field"><label>{t('有效组')}</label><strong>{safe(training['set_count'])}</strong></div>
          <div class="field"><label>{t('训练量 kg')}</label><strong>{safe(training['volume_kg'])}</strong></div>
          <div class="field"><label>{t('PR 记录')}</label><strong>{safe(training['pr_record_count'])}</strong></div>
          <div class="field"><label>{t('数据缺失')}</label><strong>{safe(training['missing_reps'] + training['missing_weight'])}</strong></div>
        </div>
        <div class="section-heading">
          <h2>{t('今日状态')}</h2>
          <form method="post" action="/garmin/sync?lang={lang_query}" data-disable-on-submit>
            <button type="submit" data-loading-text="{t('读取中...')}">{t('立即读取 Garmin')}</button>
          </form>
        </div>
        <div class="summary">
          <div class="field"><label>{t('恢复日期')}</label><strong>{safe(value_or(recovery.get('metric_date'), t('无')))}</strong></div>
          <div class="field"><label>{t('睡眠分数')}</label><strong>{safe(value_or(recovery.get('sleep_score'), t('无')))}</strong></div>
          <div class="field"><label>{t('睡眠时长')}</label><strong>{safe(format_sleep_duration(recovery.get('sleep_duration_minutes'), locale))}</strong></div>
          <div class="field"><label>{t('HRV 状态')}</label><strong>{safe(value_or(recovery.get('hrv_status'), t('无')))}</strong></div>
          <div class="field"><label>Body Battery</label><strong>{safe(value_or(recovery.get('body_battery'), t('无')))}</strong></div>
          <div class="field"><label>{t('训练准备度')}</label><strong>{safe(value_or(recovery.get('training_readiness'), t('无')))}</strong></div>
          <div class="field"><label>{t('体重 kg')}</label><strong>{safe(value_or(body_values.get('body_weight_kg'), t('无')))}</strong></div>
          <div class="field"><label>{t('周期')}</label><strong>{safe(('W' + str(cycle.get('week')) + ' ' + str(cycle.get('phase'))) if cycle else t('未开始'))}</strong></div>
        </div>
        <h2>{t('14 天恢复趋势')}</h2>
        {recovery_trend_chart(snapshot['recovery_trends'], locale)}
        <h2>{t('睡眠构成')}</h2>
        {sleep_stage_chart(health_details.get('sleep'), locale)}
        <h2>{t('详细健康指标')}</h2>
        {health_detail_cards(health_details, locale)}
        <h2>{t('最近训练日')}</h2>
        {('<table><thead><tr><th>' + t('日期') + '</th><th>' + t('活动数') + '</th><th>' + t('训练内容') + '</th><th></th></tr></thead><tbody>' + day_rows + '</tbody></table>') if day_rows else '<div class="empty">' + t('暂无训练记录。') + '</div>'}
        <h2>{t('当前 PR')}</h2>
        {('<table><thead><tr><th>' + t('动作') + '</th><th>e1RM kg</th><th>' + t('最佳组') + '</th><th>' + t('日期') + '</th></tr></thead><tbody>' + pr_rows + '</tbody></table>') if pr_rows else '<div class="empty">' + t('暂无 PR 状态。') + '</div>'}
        <h2>{t('最近计划流程')}</h2>
        {('<table><thead><tr><th>' + t('目标日期') + '</th><th>' + t('状态') + '</th><th>' + t('主肌群') + '</th><th>' + t('恢复调整') + '</th></tr></thead><tbody>' + pipeline_rows + '</tbody></table>') if pipeline_rows else '<div class="empty">' + t('暂无计划流程记录。') + '</div>'}
        """
        return page("TrainingOS Dashboard", body, "zh-CN" if locale == "zh" else "en")

    def sync_garmin_today(self, runner=subprocess.run, today: str | None = None, locale: str = "zh") -> str:
        locale = resolve_locale(override=locale)
        t = lambda value: dashboard_text(locale, value)
        target_date = today or dt.date.today().isoformat()
        command = [
            sys.executable,
            str(GARMIN_IMPORT_SCRIPT),
            "--days",
            "1",
            "--end-date",
            target_date,
            "--read-provider",
            "personal",
            "--write-db",
            "--db",
            str(self.db_path),
        ]
        trainingos_observability.record_event(
            "garmin_manual_sync_started",
            details={"metric_date": target_date, "provider": "personal"},
        )
        try:
            completed = runner(
                command,
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                timeout=90,
                check=False,
            )
        except subprocess.TimeoutExpired:
            trainingos_observability.record_event(
                "garmin_manual_sync_finished",
                status="error",
                details={"metric_date": target_date, "reason": "timeout"},
            )
            return self.dashboard_page(t("Garmin 读取超时，请稍后重试或查看调试观测。"), True, locale)
        except OSError as exc:
            trainingos_observability.record_event(
                "garmin_manual_sync_finished",
                status="error",
                details={"metric_date": target_date, "reason": type(exc).__name__},
            )
            return self.dashboard_page(t("无法启动 Garmin 读取进程，请查看调试观测。"), True, locale)

        if completed.returncode != 0:
            trainingos_observability.record_event(
                "garmin_manual_sync_finished",
                status="error",
                details={"metric_date": target_date, "returncode": completed.returncode},
            )
            return self.dashboard_page(t("Garmin 读取失败，请查看调试观测后重试。"), True, locale)

        with self.connection() as connection:
            row = connection.execute(
                """
                select sleep_score, sleep_duration_minutes, hrv_status,
                       resting_heart_rate, body_battery, stress_score,
                       training_readiness, recovery_time_hours
                from daily_recovery_metrics
                where athlete_id = ? and metric_date = ?
                order by created_at desc limit 1
                """,
                (trainingos_db.DEFAULT_ATHLETE_ID, target_date),
            ).fetchone()
        available = sum(value is not None for value in row) if row else 0
        if available == 0:
            trainingos_observability.record_event(
                "garmin_manual_sync_finished",
                status="warning",
                details={"metric_date": target_date, "available_fields": 0},
            )
            return self.dashboard_page(t("Garmin 已响应，但今天尚无可显示的恢复指标。"), True, locale)

        trainingos_observability.record_event(
            "garmin_manual_sync_finished",
            details={"metric_date": target_date, "available_fields": available},
        )
        message = (
            f"Garmin 今日状态同步成功，更新了 {available} 个恢复指标。"
            if locale == "zh"
            else f"Garmin status synced. Updated {available} recovery metrics."
        )
        return self.dashboard_page(message, locale=locale)

    def list_page(self) -> str:
        with self.connection() as connection:
            training_days = trainingos_db.get_recent_training_days(connection, 20)
        rows = []
        for training_day in training_days:
            rows.append(
                f"""<tr>
                  <td>{safe(training_day.get("training_date"))}</td>
                  <td>{safe(training_day.get("session_count"))}</td>
                  <td>{safe(training_day.get("activity_names"))}</td>
                  <td><a href="/day?date={safe(training_day.get("training_date"))}">查看当天</a></td>
                </tr>"""
            )
        body = f"""{nav()}<h1>TrainingOS 训练日</h1>"""
        if rows:
            body += f"""<table>
              <thead><tr><th>日期</th><th>活动数</th><th>训练内容</th><th></th></tr></thead>
              <tbody>{''.join(rows)}</tbody>
            </table>"""
        else:
            body += """<div class="empty">还没有已导入的训练。先运行 Garmin 完成活动导入，或稍后添加手动录入入口。</div>"""
        return page("TrainingOS Review", body)

    def manual_entry_page(
        self,
        draft: dict[str, object] | None = None,
        error: str | None = None,
    ) -> str:
        draft = draft or {}
        sets = list(draft.get("sets") or [])
        row_count = min(12, max(6, len(sets) + 1))
        rows = []
        for index in range(row_count):
            item = sets[index] if index < len(sets) else {}
            rows.append(
                f"""<tr>
                  <td data-label="动作"><input name="exercise_name_{index}" value="{safe(item.get('exercise_name'))}"></td>
                  <td data-label="组序"><input name="set_order_{index}" type="number" min="1" value="{numeric(item.get('set_order') or index + 1)}"></td>
                  <td data-label="重量 kg"><input name="weight_kg_{index}" inputmode="decimal" value="{numeric(item.get('weight_kg'))}"></td>
                  <td data-label="次数"><input name="reps_{index}" type="number" min="0" value="{numeric(item.get('reps'))}"></td>
                  <td data-label="RPE"><input name="rpe_{index}" inputmode="decimal" value="{numeric(item.get('rpe'))}"></td>
                </tr>"""
            )
        completed_at = draft.get("completed_at") or dt.datetime.now().strftime("%Y-%m-%dT%H:%M")
        error_block = f"<div class='empty'>{safe(error)}</div>" if error else ""
        body = f"""{nav()}
        <h1>手动训练录入</h1>
        {error_block}
        <form method="post" action="/entry/save">
          <input type="hidden" name="set_count" value="{row_count}">
          <div class="summary">
            <div class="field"><label>训练名称</label><input name="activity_name" required value="{safe(draft.get('activity_name') or '')}"></div>
            <div class="field"><label>完成时间</label><input name="completed_at" type="datetime-local" required value="{safe(completed_at)}"></div>
            <div class="field"><label>整体 RPE</label><input name="overall_rpe" inputmode="decimal" value="{numeric(draft.get('overall_rpe'))}"></div>
            <div class="field"><label>疲劳 1-10</label><input name="fatigue_rating" type="number" min="1" max="10" value="{numeric(draft.get('fatigue_rating'))}"></div>
          </div>
          <div class="row-actions">
            <input id="entry-transcript" name="voice_transcript" autocomplete="off" placeholder="卧推 80公斤 8次 RPE8">
            <button type="button" data-speech-target="entry-transcript" data-submit-target="entry-parse" title="语音输入" aria-label="语音输入">&#127908;</button>
            <button id="entry-parse" class="secondary" type="submit" formaction="/entry/voice">解析</button>
          </div>
          <h2>组记录</h2>
          <table>
            <thead><tr><th>动作</th><th>组序</th><th>重量 kg</th><th>次数</th><th>RPE</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
          <h2>主观记录</h2>
          <label>疼痛 / 技术备注</label>
          <textarea name="pain_notes">{safe(draft.get('pain_notes'))}</textarea>
          <label>恢复 / 状态备注</label>
          <textarea name="readiness_notes">{safe(draft.get('readiness_notes'))}</textarea>
          <div class="row-actions"><button type="submit">保存训练</button></div>
        </form>"""
        return page("TrainingOS Manual Entry", body)

    def parse_manual_voice(self, form_data: dict[str, list[str]]) -> str:
        draft = draft_from_form(form_data)
        transcript = form_data.get("voice_transcript", [""])[0]
        sets = list(draft["sets"])
        result = trainingos_voice_input.parse_voice_entry(
            transcript,
            previous_set=sets[-1] if sets else None,
            next_order=len(sets) + 1,
        )
        if result["status"] != "parsed":
            return self.manual_entry_page(draft, ", ".join(result["issues"]))
        if len(sets) + len(result["sets"]) > 12:
            return self.manual_entry_page(draft, "set_count_out_of_range")
        draft["sets"] = sets + result["sets"]
        return self.manual_entry_page(draft)

    def save_manual_entry(self, form_data: dict[str, list[str]]) -> str:
        draft = draft_from_form(form_data)
        try:
            if not str(draft["activity_name"]).strip():
                raise ValueError("activity_name_required")
            completed_at = dt.datetime.fromisoformat(str(draft["completed_at"]))
            if not draft["sets"]:
                raise ValueError("at_least_one_set_required")
        except ValueError as exc:
            return self.manual_entry_page(draft, str(exc))
        workout = {
            "provider": "local",
            "source_tool": "local_manual_entry",
            "completed_at": completed_at.strftime("%Y-%m-%d %H:%M:%S"),
            "session_type": "strength_training",
            "activity_name": draft["activity_name"],
            "overall_rpe": draft["overall_rpe"],
            "fatigue_rating": draft["fatigue_rating"],
            "pain_notes": draft["pain_notes"],
            "readiness_notes": draft["readiness_notes"],
            "sets": draft["sets"],
        }
        with self.connection() as connection:
            session_id = trainingos_db.save_imported_workout(connection, workout)
        return self.session_page(session_id, saved=True)

    def day_page(self, training_date: str) -> str:
        with self.connection() as connection:
            sessions = trainingos_db.get_sessions_for_day(connection, training_date)
        if not sessions:
            return page("Not found", "<h1>找不到训练日</h1><p><a href='/'>返回</a></p>")
        rows = []
        for session in sessions:
            rows.append(
                f"""<tr>
                  <td>{safe(session.get("completed_at"))}</td>
                  <td>{safe(session.get("activity_name") or session.get("session_type"))}</td>
                  <td>{safe(len(session.get("sets", [])))}</td>
                  <td><a href="/session?id={safe(session.get("id"))}">校正单条</a></td>
                </tr>"""
            )
        body = f"""{nav()}
        <p><a href="/">返回训练日</a></p>
        <h1>{safe(training_date)} 训练</h1>
        <p class="muted">同一天的 Garmin 活动会作为同一组训练进入 AI 复盘。</p>
        <table>
          <thead><tr><th>时间</th><th>活动</th><th>组数</th><th></th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        <div class="row-actions">
          <a href="/day/analysis?date={safe(training_date)}">进入当天 AI 复盘与初版计划</a>
        </div>"""
        return page("TrainingOS Day Review", body)

    def session_page(
        self,
        session_id: str,
        saved: bool = False,
        draft_sets: list[dict[str, object]] | None = None,
        voice_error: str | None = None,
    ) -> str:
        with self.connection() as connection:
            session = trainingos_db.get_session_for_review(connection, session_id)
        if session is None:
            return page("Not found", "<h1>找不到训练记录</h1><p><a href='/'>返回</a></p>")
        sets = draft_sets if draft_sets is not None else session.get("sets", [])
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
        pr_rows = []
        for pr_record in session.get("pr_records", []):
            pr_rows.append(
                f"""<tr>
                  <td>{safe(pr_record.get("exercise_name"))}</td>
                  <td>{safe(pr_record.get("pr_type"))}</td>
                  <td>{numeric(pr_record.get("best_value"))}</td>
                  <td>{numeric(pr_record.get("weight_kg"))}</td>
                  <td>{numeric(pr_record.get("reps"))}</td>
                </tr>"""
            )
        pr_block = "<div class='empty'>本次没有新 PR。</div>"
        if pr_rows:
            pr_block = f"""<table>
              <thead><tr><th>动作</th><th>PR 类型</th><th>PR 数值</th><th>重量 kg</th><th>次数</th></tr></thead>
              <tbody>{''.join(pr_rows)}</tbody>
            </table>"""
        saved_notice = "<p class='muted'>已保存校正。</p>" if saved else ""
        voice_notice = f"<div class='empty'>{safe(voice_error)}</div>" if voice_error else ""
        target_options = "".join(
            f'<option value="{index + 1}">第 {index + 1} 组</option>' for index in range(len(sets))
        )
        body = f"""{nav()}
        <p><a href="/">返回列表</a></p>
        <h1>{safe(session.get("activity_name") or "Completed Workout")}</h1>
        {saved_notice}
        {voice_notice}
        <h2>本次 PR</h2>
        {pr_block}
        <form method="post" action="/session/voice">
          <input type="hidden" name="session_id" value="{safe(session_id)}">
          <div class="row-actions">
            <select name="target_set">{target_options}</select>
            <input id="session-transcript" name="voice_transcript" autocomplete="off" placeholder="卧推 80公斤 8次 RPE8">
            <button type="button" data-speech-target="session-transcript" data-submit-target="session-parse" title="语音输入" aria-label="语音输入">&#127908;</button>
            <button id="session-parse" class="secondary" type="submit">填入</button>
          </div>
        </form>
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
            <button class="secondary" type="submit" name="next" value="analysis">保存并进入 AI 复盘与初版计划</button>
            <a href="/summary?id={safe(session_id)}">查看 AI 输入摘要</a>
          </div>
        </form>"""
        return page("TrainingOS Review", body)

    def parse_session_voice(self, form_data: dict[str, list[str]]) -> str:
        session_id = form_data.get("session_id", [""])[0]
        with self.connection() as connection:
            session = trainingos_db.get_session_for_review(connection, session_id)
        if session is None:
            return page("Not found", "<h1>找不到训练记录</h1><p><a href='/'>返回</a></p>")
        sets = [dict(item) for item in session.get("sets", [])]
        if not sets:
            sets = [{"set_order": 1, "set_type": "working"}]
        target = parse_int(form_data.get("target_set", ["1"])[0]) or 1
        target = max(1, min(target, len(sets)))
        previous = sets[target - 2] if target > 1 else None
        result = trainingos_voice_input.parse_voice_entry(
            form_data.get("voice_transcript", [""])[0],
            previous_set=previous,
            next_order=target,
        )
        if result["status"] != "parsed":
            return self.session_page(
                session_id,
                draft_sets=sets,
                voice_error=", ".join(result["issues"]),
            )
        sets[target - 1 : target] = result["sets"]
        for index, item in enumerate(sets):
            item["set_order"] = index + 1
        return self.session_page(session_id, draft_sets=sets)

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
        body = f"""{nav()}
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
            f"{nav()}<p><a href='/session?id={safe(session_id)}'>返回校正</a></p><h1>AI 输入摘要</h1><pre>{payload}</pre>",
        )

    def analysis_page(self, session_id: str) -> str:
        with self.connection() as connection:
            try:
                prompt = trainingos_db.build_post_workout_analysis_prompt(connection, session_id)
                packet = trainingos_db.build_ai_review_packet(connection, session_id)
                reviews = trainingos_db.get_ai_reviews_for_session(connection, session_id)
            except ValueError:
                return page("Not found", "<h1>找不到训练记录</h1><p><a href='/'>返回</a></p>")
        trainingos_observability.record_event(
            "manual_ai_analysis_opened",
            details={"session_id": session_id},
        )
        packet_text = json.dumps(packet, indent=2, ensure_ascii=False)
        review_rows = ""
        if reviews:
            review_rows = "<h2>已保存复盘</h2><table><thead><tr><th>时间</th><th>决策</th><th>摘要</th></tr></thead><tbody>"
            for review in reviews:
                review_rows += (
                    f"<tr><td>{safe(review.get('created_at'))}</td>"
                    f"<td>{safe(review.get('decision'))}</td>"
                    f"<td>{safe(review.get('summary'))}</td></tr>"
                )
            review_rows += "</tbody></table>"
        body = f"""{nav()}
        <p><a href="/session?id={safe(session_id)}">返回校正</a></p>
        <h1>AI 复盘与初版计划</h1>
        <p class="muted">这是低算力手动流程。复制标准输入到 ChatGPT，要求返回 JSON，然后把结果粘贴回来保存。初版计划会在第二天恢复指标同步后再微调。</p>
        {review_rows}
        <h2>标准 AI 输入</h2>
        <textarea readonly style="min-height: 300px">{safe(packet_text)}</textarea>
        <h2>简短指令</h2>
        <textarea readonly style="min-height: 220px">{safe(prompt)}</textarea>
        <h2>粘贴 AI 输出</h2>
        <form method="post" action="/analysis/save">
          <input type="hidden" name="session_id" value="{safe(session_id)}">
          <textarea name="ai_response" style="min-height: 260px" placeholder="在这里粘贴 ChatGPT 返回的 JSON"></textarea>
          <div class="row-actions">
            <button type="submit">保存 AI 复盘</button>
          </div>
        </form>"""
        return page("TrainingOS AI Analysis", body)

    def day_analysis_page(self, training_date: str) -> str:
        with self.connection() as connection:
            try:
                prompt = trainingos_db.build_day_post_workout_analysis_prompt(connection, training_date)
                packet = trainingos_db.build_day_ai_review_packet(connection, training_date)
                reviews = trainingos_db.get_ai_reviews_for_day(connection, training_date)
            except ValueError:
                return page("Not found", "<h1>找不到训练日</h1><p><a href='/'>返回</a></p>")
        trainingos_observability.record_event(
            "manual_ai_day_analysis_opened",
            details={"training_date": training_date},
        )
        packet_text = json.dumps(packet, indent=2, ensure_ascii=False)
        review_rows = ""
        if reviews:
            review_rows = "<h2>已保存当天复盘</h2><table><thead><tr><th>时间</th><th>决策</th><th>摘要</th></tr></thead><tbody>"
            for review in reviews:
                review_rows += (
                    f"<tr><td>{safe(review.get('created_at'))}</td>"
                    f"<td>{safe(review.get('decision'))}</td>"
                    f"<td>{safe(review.get('summary'))}</td></tr>"
                )
            review_rows += "</tbody></table>"
        body = f"""{nav()}
        <p><a href="/day?date={safe(training_date)}">返回当天训练</a></p>
        <h1>{safe(training_date)} AI 复盘与初版计划</h1>
        <p class="muted">这是当天聚合复盘。同一天的多条 Garmin 活动会作为一个训练整体进入标准 AI 输入包。</p>
        {review_rows}
        <h2>标准 AI 输入</h2>
        <textarea readonly style="min-height: 300px">{safe(packet_text)}</textarea>
        <h2>简短指令</h2>
        <textarea readonly style="min-height: 220px">{safe(prompt)}</textarea>
        <h2>粘贴 AI 输出</h2>
        <form method="post" action="/day/analysis/save">
          <input type="hidden" name="training_date" value="{safe(training_date)}">
          <textarea name="ai_response" style="min-height: 260px" placeholder="在这里粘贴 ChatGPT 返回的 JSON"></textarea>
          <div class="row-actions">
            <button type="submit">保存当天 AI 复盘</button>
          </div>
        </form>"""
        return page("TrainingOS Day AI Analysis", body)

    def save_ai_analysis(self, form_data: dict[str, list[str]]) -> str:
        session_id = form_data.get("session_id", [""])[0]
        response_text = form_data.get("ai_response", [""])[0]
        if not session_id or not response_text.strip():
            return page("Missing AI response", "<h1>缺少 AI 输出</h1><p><a href='/'>返回</a></p>")
        with self.connection() as connection:
            trainingos_db.save_ai_review_response(connection, session_id, response_text)
        return self.analysis_page(session_id)

    def save_day_ai_analysis(self, form_data: dict[str, list[str]]) -> str:
        training_date = form_data.get("training_date", [""])[0]
        response_text = form_data.get("ai_response", [""])[0]
        if not training_date or not response_text.strip():
            return page("Missing AI response", "<h1>缺少 AI 输出</h1><p><a href='/'>返回</a></p>")
        with self.connection() as connection:
            trainingos_db.save_day_ai_review_response(connection, training_date, response_text)
        return self.day_analysis_page(training_date)

    def settings_page(self, saved: bool = False, trigger_decision: dict[str, object] | None = None) -> str:
        with self.connection() as connection:
            policy = trainingos_db.get_ai_trigger_policy(connection)
            ai_calls_today = trainingos_db.count_ai_calls_for_date(connection)
            trigger_logs = trainingos_db.get_recent_api_trigger_logs(connection, 8)
        checked = " checked" if policy.get("auto_api_enabled") else ""
        saved_notice = "<p class='muted'>触发设置已保存。</p>" if saved else ""
        decision_notice = ""
        if trigger_decision:
            decision_notice = (
                "<div class='empty'>"
                f"触发检查：{safe(trigger_decision.get('trigger_name'))} / "
                f"{safe(trigger_decision.get('status'))} / "
                f"{safe(trigger_decision.get('reason'))}"
                "</div>"
            )
        log_rows = ""
        if trigger_logs:
            log_rows = "<h2>最近触发判定</h2><table><thead><tr><th>时间</th><th>触发</th><th>状态</th><th>原因</th></tr></thead><tbody>"
            for log in trigger_logs:
                log_rows += (
                    f"<tr><td>{safe(log.get('created_at'))}</td>"
                    f"<td>{safe(log.get('trigger_name'))}</td>"
                    f"<td>{safe(log.get('status'))}</td>"
                    f"<td>{safe(log.get('reason'))}</td></tr>"
                )
            log_rows += "</tbody></table>"
        body = f"""{nav()}
        <h1>AI / API 触发设置</h1>
        {saved_notice}
        {decision_notice}
        <p class="muted">当前版本默认不直接调用 API。这里先定义未来自动化的触发规则，用来节省算力并降低误触发风险。</p>
        <div class="summary">
          <div class="field"><label>今日 AI 调用计数</label><input value="{safe(ai_calls_today)} / {safe(policy.get("max_ai_calls_per_day"))}" disabled></div>
          <div class="field"><label>自动 API 总开关</label><input value="{safe("已开启" if policy.get("auto_api_enabled") else "已关闭")}" disabled></div>
          <div class="field"><label>训练后复盘模式</label><input value="{safe(policy.get("post_workout_ai_mode"))}" disabled></div>
          <div class="field"><label>次日微调模式</label><input value="{safe(policy.get("next_morning_adjustment_mode"))}" disabled></div>
        </div>
        <form method="post" action="/settings/save">
          <div class="summary">
            <div class="field">
              <label>训练后复盘</label>
              <select name="post_workout_ai_mode">
                {option("manual_copy_paste", policy.get("post_workout_ai_mode"), "手动复制粘贴")}
                {option("user_confirmed_api", policy.get("post_workout_ai_mode"), "点击确认后调用 API")}
                {option("auto_api_after_correction", policy.get("post_workout_ai_mode"), "保存校正后自动调用 API")}
              </select>
            </div>
            <div class="field">
              <label>次日恢复微调</label>
              <select name="next_morning_adjustment_mode">
                {option("manual_copy_paste", policy.get("next_morning_adjustment_mode"), "手动复制粘贴")}
                {option("user_confirmed_api", policy.get("next_morning_adjustment_mode"), "点击确认后调用 API")}
                {option("auto_api_after_recovery_sync", policy.get("next_morning_adjustment_mode"), "恢复数据同步后自动调用 API")}
              </select>
            </div>
            <div class="field">
              <label>推送 Garmin</label>
              <select name="garmin_push_mode">
                {option("manual_only", policy.get("garmin_push_mode"), "仅手动")}
                {option("user_confirmed", policy.get("garmin_push_mode"), "点击确认后推送")}
                {option("auto_after_final_plan", policy.get("garmin_push_mode"), "最终计划生成后自动推送")}
              </select>
            </div>
            <div class="field">
              <label>每日 AI 调用上限</label>
              <input name="max_ai_calls_per_day" type="number" min="0" max="20" value="{numeric(policy.get("max_ai_calls_per_day"))}">
            </div>
          </div>
          <div class="field">
            <label><input name="auto_api_enabled" type="checkbox" value="1"{checked}> 允许自动 API 调用</label>
            <p class="muted">关闭时，即使某个步骤选了自动模式，也只显示手动确认入口，不会自动调用。</p>
          </div>
          <div class="row-actions">
            <button type="submit">保存触发设置</button>
          </div>
        </form>
        <h2>推荐默认值</h2>
        <p class="muted">训练后复盘：手动复制粘贴。次日恢复微调：点击确认后调用 API。推送 Garmin：点击确认后推送。</p>
        <h2>触发检查</h2>
        <p class="muted">这些按钮只检查并记录闸门判定，不会调用外部 API。</p>
        <div class="row-actions">
          <form method="post" action="/settings/check"><input type="hidden" name="trigger_name" value="post_workout_ai"><button type="submit">检查训练后复盘</button></form>
          <form method="post" action="/settings/check"><input type="hidden" name="trigger_name" value="next_morning_adjustment"><button type="submit">检查次日微调</button></form>
          <form method="post" action="/settings/check"><input type="hidden" name="trigger_name" value="garmin_push"><button type="submit">检查 Garmin 推送</button></form>
        </div>
        {log_rows}"""
        return page("TrainingOS Trigger Settings", body)

    def save_settings(self, form_data: dict[str, list[str]]) -> str:
        payload = {
            "post_workout_ai_mode": form_data.get("post_workout_ai_mode", [""])[0],
            "next_morning_adjustment_mode": form_data.get("next_morning_adjustment_mode", [""])[0],
            "garmin_push_mode": form_data.get("garmin_push_mode", [""])[0],
            "auto_api_enabled": form_data.get("auto_api_enabled", [""])[0] == "1",
            "max_ai_calls_per_day": form_data.get("max_ai_calls_per_day", [""])[0],
        }
        with self.connection() as connection:
            trainingos_db.update_ai_trigger_policy(connection, payload)
        return self.settings_page(saved=True)

    def check_trigger(self, form_data: dict[str, list[str]]) -> str:
        trigger_name = form_data.get("trigger_name", [""])[0]
        user_confirmed = form_data.get("user_confirmed", [""])[0] == "1"
        with self.connection() as connection:
            decision = trainingos_db.evaluate_api_trigger(connection, trigger_name, user_confirmed=user_confirmed)
            trainingos_db.record_api_trigger_decision(
                connection,
                decision,
                context={"source": "settings_page_check", "user_confirmed": user_confirmed},
            )
        return self.settings_page(trigger_decision=decision)

    def body_metrics_page(self, saved: bool = False, error: str | None = None) -> str:
        with self.connection() as connection:
            records = trainingos_db.get_recent_body_metrics(connection, 20)
        notice = "<p class='muted'>身体指标已保存在本机 SQLite。</p>" if saved else ""
        error_notice = f"<div class='empty'>{safe(error)}</div>" if error else ""
        rows = ""
        for record in records:
            rows += (
                f"<tr><td>{safe(record.get('metric_date'))}</td>"
                f"<td>{safe(record.get('body_weight_kg'))}</td>"
                f"<td>{safe(record.get('body_fat_percent'))}</td>"
                f"<td>{safe(record.get('waist_cm'))}</td>"
                f"<td>{safe(record.get('chest_cm'))}</td>"
                f"<td>{safe(record.get('hip_cm'))}</td>"
                f"<td>{safe(record.get('arm_cm'))}</td>"
                f"<td>{safe(record.get('leg_cm'))}</td></tr>"
            )
        history = (
            "<table><thead><tr><th>日期</th><th>体重 kg</th><th>体脂 %</th>"
            "<th>腰围 cm</th><th>胸围 cm</th><th>臀围 cm</th><th>臂围 cm</th><th>腿围 cm</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
            if rows
            else "<div class='empty'>暂无身体指标记录。</div>"
        )
        body = f"""{nav()}
        <h1>身体指标</h1>
        {notice}{error_notice}
        <p class="muted">数据仅写入本机 SQLite。同一天再次保存会更新原记录；至少填写一个数值。</p>
        <form method="post" action="/body/save">
          <div class="summary">
            <div class="field"><label>日期</label><input name="metric_date" type="date" required value="{dt.date.today().isoformat()}"></div>
            <div class="field"><label>体重 kg</label><input name="body_weight_kg" type="number" min="20" max="400" step="0.1"></div>
            <div class="field"><label>体脂 %</label><input name="body_fat_percent" type="number" min="2" max="75" step="0.1"></div>
            <div class="field"><label>腰围 cm</label><input name="waist_cm" type="number" min="30" max="250" step="0.1"></div>
            <div class="field"><label>胸围 cm</label><input name="chest_cm" type="number" min="30" max="250" step="0.1"></div>
            <div class="field"><label>臀围 cm</label><input name="hip_cm" type="number" min="30" max="250" step="0.1"></div>
            <div class="field"><label>臂围 cm</label><input name="arm_cm" type="number" min="10" max="100" step="0.1"></div>
            <div class="field"><label>腿围 cm</label><input name="leg_cm" type="number" min="15" max="150" step="0.1"></div>
          </div>
          <div class="field"><label>备注</label><textarea name="notes"></textarea></div>
          <div class="row-actions"><button type="submit">保存身体指标</button></div>
        </form>
        <h2>最近记录</h2>{history}"""
        return page("TrainingOS Body Metrics", body)

    def save_body_metrics(self, form_data: dict[str, list[str]]) -> str:
        payload = {
            "metric_date": form_data.get("metric_date", [""])[0],
            "notes": form_data.get("notes", [""])[0],
        }
        for field_name in trainingos_db.BODY_METRIC_RANGES:
            payload[field_name] = parse_float(form_data.get(field_name, [""])[0])
        try:
            dt.date.fromisoformat(str(payload["metric_date"]))
            with self.connection() as connection:
                trainingos_db.upsert_body_metric(connection, payload)
        except ValueError as exc:
            return self.body_metrics_page(error=str(exc))
        return self.body_metrics_page(saved=True)

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


def draft_from_form(form_data: dict[str, list[str]]) -> dict[str, object]:
    set_count = min(12, max(0, parse_int(form_data.get("set_count", ["0"])[0]) or 0))
    sets = []
    for index in range(set_count):
        exercise_name = form_data.get(f"exercise_name_{index}", [""])[0].strip()
        if not exercise_name:
            continue
        sets.append(
            {
                "exercise_name": exercise_name,
                "set_order": parse_int(form_data.get(f"set_order_{index}", [""])[0]) or len(sets) + 1,
                "set_type": form_data.get(f"set_type_{index}", ["working"])[0].strip() or "working",
                "weight_kg": parse_float(form_data.get(f"weight_kg_{index}", [""])[0]),
                "reps": parse_int(form_data.get(f"reps_{index}", [""])[0]),
                "rpe": parse_float(form_data.get(f"rpe_{index}", [""])[0]),
                "notes": form_data.get(f"notes_{index}", [""])[0].strip() or None,
            }
        )
    return {
        "activity_name": form_data.get("activity_name", [""])[0].strip(),
        "completed_at": form_data.get("completed_at", [""])[0],
        "overall_rpe": parse_float(form_data.get("overall_rpe", [""])[0]),
        "fatigue_rating": parse_int(form_data.get("fatigue_rating", [""])[0]),
        "pain_notes": form_data.get("pain_notes", [""])[0].strip() or None,
        "readiness_notes": form_data.get("readiness_notes", [""])[0].strip() or None,
        "sets": sets,
    }


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

        def request_locale(self, override: str | None = None) -> str:
            return resolve_locale(self.headers.get("Accept-Language"), override)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/manifest.webmanifest":
                self.respond(
                    json.dumps(PWA_MANIFEST, ensure_ascii=False),
                    content_type="application/manifest+json; charset=utf-8",
                )
                return
            if parsed.path == "/service-worker.js":
                self.respond(
                    SERVICE_WORKER,
                    content_type="application/javascript; charset=utf-8",
                    extra_headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
                )
                return
            if parsed.path == "/app-icon.svg":
                self.respond(
                    APP_ICON_PATH.read_text(encoding="utf-8"),
                    content_type="image/svg+xml; charset=utf-8",
                    extra_headers={"Cache-Control": "public, max-age=86400"},
                )
                return
            if parsed.path == "/offline":
                self.respond(app.offline_page())
                return
            if parsed.path == "/":
                self.respond(app.dashboard_page(locale=self.request_locale(query.get("lang", [None])[0])))
                return
            if parsed.path == "/training":
                self.respond(app.list_page())
                return
            if parsed.path == "/entry":
                self.respond(app.manual_entry_page())
                return
            if parsed.path == "/session":
                self.respond(app.session_page(query.get("id", [""])[0]))
                return
            if parsed.path == "/day":
                self.respond(app.day_page(query.get("date", [""])[0]))
                return
            if parsed.path == "/summary":
                self.respond(app.summary_page(query.get("id", [""])[0]))
                return
            if parsed.path == "/analysis":
                self.respond(app.analysis_page(query.get("id", [""])[0]))
                return
            if parsed.path == "/day/analysis":
                self.respond(app.day_analysis_page(query.get("date", [""])[0]))
                return
            if parsed.path == "/debug":
                self.respond(app.debug_page())
                return
            if parsed.path == "/settings":
                self.respond(app.settings_page())
                return
            if parsed.path == "/body":
                self.respond(app.body_metrics_page())
                return
            self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/garmin/sync":
                self.respond(
                    app.sync_garmin_today(
                        locale=self.request_locale(query.get("lang", [None])[0])
                    )
                )
                return
            if self.path == "/debug/clear":
                trainingos_observability.clear_events()
                self.respond(app.debug_page())
                return
            if self.path == "/analysis/save":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                self.respond(app.save_ai_analysis(parse_qs(body)))
                return
            if self.path == "/day/analysis/save":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                self.respond(app.save_day_ai_analysis(parse_qs(body)))
                return
            if self.path == "/settings/save":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                self.respond(app.save_settings(parse_qs(body)))
                return
            if self.path == "/settings/check":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                self.respond(app.check_trigger(parse_qs(body)))
                return
            if self.path == "/body/save":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                self.respond(app.save_body_metrics(parse_qs(body)))
                return
            if self.path == "/entry/voice":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                self.respond(app.parse_manual_voice(parse_qs(body)))
                return
            if self.path == "/entry/save":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                self.respond(app.save_manual_entry(parse_qs(body)))
                return
            if self.path == "/session/voice":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                self.respond(app.parse_session_voice(parse_qs(body)))
                return
            if self.path != "/save":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            self.respond(app.save(parse_qs(body)))

        def respond(
            self,
            content: str,
            content_type: str = "text/html; charset=utf-8",
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            payload = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
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
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(f"TrainingOS review UI: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
