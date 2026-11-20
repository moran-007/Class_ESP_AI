"""Local USB control for the AI Maker teaching firmware."""

from .client import Robot
from .errors import (
    ConnectionLostError,
    DeviceError,
    ProtocolError,
    RequestTimeout,
    RobotError,
    UnsupportedCapability,
)
from .transport import SerialTransport, Transport
from .pages import validate_project, load_project
from .audio import AudioClip, load_audio_url
from .program import Program

__all__ = [
    "Robot", "RobotError", "DeviceError", "ProtocolError", "RequestTimeout",
    "ConnectionLostError", "UnsupportedCapability", "SerialTransport", "Transport",
    "validate_project", "load_project", "AudioClip", "load_audio_url", "Program",
]
__version__ = "0.8.3"
