"""Kanały wysyłki alertów (mail, SMS, telefon). Szczegóły: base.py i registry.py."""
from services.channels.base import Channel, ChannelError, Message
from services.channels.registry import available_channels, get_channel

__all__ = ["Channel", "ChannelError", "Message", "available_channels", "get_channel"]
