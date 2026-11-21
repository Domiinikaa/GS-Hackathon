"""
Kanał e-mail przez SMTP – standardowy "język" poczty, wbudowany w Pythona (smtplib).

Lokalnie wysyłamy do Mailpit (łapka na maile, http://localhost:8025) – prawdziwy protokół SMTP,
tylko że listy zostają w testowej skrzynce zamiast iść do ludzi.
Przejście na prawdziwą pocztę = zmiana zmiennych środowiskowych, bez zmian w kodzie:

    SMTP_HOST=smtp.firma.com  SMTP_PORT=587  SMTP_STARTTLS=1  SMTP_USER=...  SMTP_PASSWORD=...
    MAIL_FROM=alerts@firma.com
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from services.channels.base import Channel, ChannelError, Message


class SmtpEmail(Channel):
    name = "email"

    def __init__(self) -> None:
        self.host = (os.getenv("SMTP_HOST") or "localhost").strip()
        port_raw = (os.getenv("SMTP_PORT") or "1025").strip()
        self.port = int(port_raw) if port_raw.isdigit() else 1025
        self.user = (os.getenv("SMTP_USER") or "").strip() or None
        # Remove any extra spaces often introduced when copy-pasting Google App Passwords
        raw_password = (os.getenv("SMTP_PASSWORD") or "").strip()
        self.password = raw_password or None
        self.ssl = (os.getenv("SMTP_SSL") or "0").strip() == "1" or self.port == 465
        self.starttls = (
            ((os.getenv("SMTP_STARTTLS") or "0").strip() == "1" or self.port == 587)
            and not self.ssl
        )
        default_sender = f"GS Alerting <{self.user}>" if self.user else "GS Alerting <alerts@gs-alerting.local>"
        self.sender = (os.getenv("MAIL_FROM") or default_sender).strip()

    def send(self, message: Message) -> None:
        email = EmailMessage()
        email["From"] = self.sender
        email["To"] = message.to
        email["Subject"] = message.subject
        email.set_content(message.body)
        if message.html:
            email.add_alternative(message.html, subtype="html")

        try:
            if self.ssl:
                with smtplib.SMTP_SSL(self.host, self.port, timeout=15) as smtp:
                    if self.user:
                        smtp.login(self.user, self.password or "")
                    smtp.send_message(email)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                    if self.starttls:
                        smtp.starttls()
                    if self.user:
                        smtp.login(self.user, self.password or "")
                    smtp.send_message(email)
        except (OSError, smtplib.SMTPException) as exc:
            # OSError = serwer nie odpowiada / odrzuca połączenie; SMTPException = serwer odmówił
            raise ChannelError(f"SMTP {self.host}:{self.port} – {exc}") from exc
