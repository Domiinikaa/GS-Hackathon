"""
Treść wiadomości o alercie – inna dla każdego kanału (wymaganie 2.6):
  e-mail  → pełna treść + wszystkie kroki runbooka + link
  SMS     → krótko (≤160 znaków) + link do alertu
  telefon → krótki tekst do przeczytania przez syntezator mowy

APP_URL = adres strony, z którego budujemy link do alertu (#alerts/<id>).
"""
from __future__ import annotations

import html
import os

from models import Alert
from services.channels.base import Message

APP_URL = os.getenv("APP_URL", "http://localhost:5173").rstrip("/")

SEVERITY_COLOR = {"critical": "#dc2626", "warning": "#d97706", "info": "#2563eb"}


def alert_link(alert: Alert) -> str:
    return f"{APP_URL}/#alerts/{alert.id}"


def build_message(alert: Alert, channel: str, to: str, name: str | None = None) -> Message:
    if channel == "email":
        return _email(alert, to, name)
    if channel == "sms":
        return _sms(alert, to)
    if channel == "phone":
        return _phone(alert, to)
    return Message(to=to, subject=alert.title, body=alert.title)


def _steps_lines(alert: Alert) -> list[str]:
    lines = []
    for i, step in enumerate(alert.steps or [], start=1):
        risky = "  (needs approval)" if step.get("approval") == "required" else ""
        lines.append(f"{i}. {step.get('text', '')}{risky}")
    return lines


def _email(alert: Alert, to: str, name: str | None) -> Message:
    sev = (alert.severity or "info").upper()
    times = f" (×{alert.count})" if (alert.count or 1) > 1 else ""
    subject = f"[{sev}] {alert.title}{times}"
    link = alert_link(alert)
    steps = _steps_lines(alert)

    text = [f"Hi {name}," if name else "Hi,", "",
            f"{sev} alert for team {alert.team}:", alert.title]
    if alert.body:
        text += ["", alert.body]
    if steps:
        text += ["", "What to do:", *steps]
    text += ["", f"Open the alert: {link}"]

    color = SEVERITY_COLOR.get((alert.severity or "").lower(), "#475569")
    e = html.escape
    steps_html = "".join(f"<li style='margin:4px 0'>{e(s.split('. ', 1)[1])}</li>" for s in steps)
    body_html = f"""\
<div style="font-family:Arial,sans-serif;max-width:560px;color:#0f172a">
  <div style="border-left:6px solid {color};padding:12px 16px;background:#f8fafc">
    <div style="font-size:12px;font-weight:bold;color:{color};letter-spacing:.05em">{e(sev)} · {e(alert.team)}{e(times)}</div>
    <div style="font-size:18px;font-weight:bold;margin-top:4px">{e(alert.title)}</div>
    {f'<p style="margin:8px 0 0;color:#334155">{e(alert.body)}</p>' if alert.body else ''}
  </div>
  {f'<h3 style="font-size:14px;margin:20px 0 6px">What to do</h3><ol style="padding-left:20px;margin:0">{steps_html}</ol>' if steps else ''}
  <p style="margin-top:24px"><a href="{e(link)}" style="background:#f59e0b;color:#0f172a;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:bold">Open alert</a></p>
</div>"""
    return Message(to=to, subject=subject, body="\n".join(text), html=body_html)


def _sms(alert: Alert, to: str) -> Message:
    sev = (alert.severity or "info").upper()[:4]       # CRIT / WARN / INFO
    link = alert_link(alert)
    room = 160 - len(f"[{sev}] ") - len(link) - 1
    title = alert.title if len(alert.title) <= room else alert.title[: room - 1] + "…"
    return Message(to=to, subject="", body=f"[{sev}] {title} {link}")


def _phone(alert: Alert, to: str) -> Message:
    sev = (alert.severity or "info").lower()
    body = f"This is a {sev} alert for team {alert.team}. {alert.title}. Please check the alerting app."
    return Message(to=to, subject="", body=body)
