"""Bounded byte transports. No ports are opened until explicitly constructed."""

from typing import Protocol

from .errors import RobotError


class Transport(Protocol):
    def write(self, data: bytes) -> None: ...

    def read(self, size: int, timeout: float) -> bytes: ...

    def close(self) -> None: ...


class SerialTransport:
    """One serial connection, owned and serialized by Robot.

    AUTO only accepts a single USB serial candidate; it never probes every port.
    A matching protocol handshake is still mandatory after selection.
    """

    def __init__(self, port: str, baudrate: int = 115200, write_timeout: float = 2.0):
        import serial
        from serial.tools import list_ports

        if port.upper() == "AUTO":
            candidates = [p.device for p in list_ports.comports() if p.vid is not None]
            if len(candidates) != 1:
                names = ", ".join(candidates) or "没有 USB 串口候选"
                raise RobotError(f"无法唯一确定设备，请显式指定 port：{names}")
            port = candidates[0]
        self.port = port
        self._serial = serial.Serial(
            port=None, baudrate=baudrate, timeout=0, write_timeout=write_timeout
        )
        # Avoid deliberately pulsing reset lines. Some boards may still reset
        # when their driver opens a port; their recovery path must be verified.
        self._serial.dtr = False
        self._serial.rts = False
        self._serial.port = port
        try:
            self._serial.open()
        except BaseException:
            self._serial.close()
            raise

    def write(self, data: bytes) -> None:
        count = self._serial.write(data)
        if count != len(data):
            raise OSError("串口未完整写入请求；执行结果未知")

    def read(self, size: int, timeout: float) -> bytes:
        self._serial.timeout = max(0.0, timeout)
        # Wait for one byte, then drain available bytes, rather than waiting
        # for a full 256-byte response until the timeout on every command.
        first = self._serial.read(1)
        if not first or size <= 1:
            return first
        return first + self._serial.read(min(size - 1, self._serial.in_waiting))

    def close(self) -> None:
        self._serial.close()
