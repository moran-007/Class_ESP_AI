"""Errors keep the firmware code and request ID for classroom diagnostics."""


class RobotError(Exception):
    """Base SDK error."""


class ProtocolError(RobotError):
    """The connected endpoint does not satisfy USB protocol v1."""


class RequestTimeout(RobotError):
    """No matching response arrived; an action might already have executed."""


class ConnectionLostError(RobotError):
    """The transport or heartbeat failed. Reconnect explicitly."""


class UnsupportedCapability(RobotError):
    """A feature is not implemented by this local firmware."""


class DeviceError(RobotError):
    """A structured firmware rejection."""

    def __init__(self, code: str, message: str, request_id: str):
        self.code = code
        self.message = message
        self.request_id = request_id
        super().__init__(f"{message} [{code}; request_id={request_id}]")
