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
        self.host = os.getenv("SMTP_HOST", "localhost")
        self.port = int(os.getenv("SMTP_PORT", "1025"))      # 1025 = Mailpit
        self.user = os.getenv("SMTP_USER")
        self.password = os.getenv("SMTP_PASSWORD")
        self.starttls = os.getenv("SMTP_STARTTLS", "0") == "1"
        self.sender = os.getenv("MAIL_FROM", "GS Alerting <alerts@gs-alerting.local>")

    def send(self, message: Message) -> None:
        email = EmailMessage()
        email["From"] = self.sender
        email["To"] = message.to
        email["Subject"] = message.subject
        email.set_content(message.body)
        if message.html:
            email.add_alternative(message.html, subtype="html")

        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
                if self.starttls:
                    smtp.starttls()
                if self.user:
                    smtp.login(self.user, self.password or "")
                smtp.send_message(email)
        except (OSError, smtplib.SMTPException) as exc:
            # OSError = serwer nie odpowiada / odrzuca połączenie; SMTPException = serwer odmówił
            raise ChannelError(f"SMTP {self.host}:{self.port} – {exc}") from exc
