"""Process-wide Python socket guard. Permit local IPC/loopback; reject outbound DNS/IP."""

from __future__ import annotations

import errno
import ipaddress
import multiprocessing
import socket
from collections.abc import Callable
from functools import wraps
from threading import RLock
from typing import Any

_LOCK = RLock()
_INSTALLED = False
_COUNTER: Any = None
_ORIGINALS: dict[str, Any] = {}


class OfflineBlocked(PermissionError):
    def __init__(self) -> None:
        super().__init__(errno.EACCES, "Offline guard blocked a non-loopback network operation")


def shared_counter() -> Any:
    global _COUNTER
    with _LOCK:
        if _COUNTER is None:
            _COUNTER = multiprocessing.get_context("spawn").Value("Q", 0)
        return _COUNTER


def _deny() -> None:
    counter = shared_counter()
    with counter.get_lock():
        counter.value = min(counter.value + 1, 2**63 - 1)
    raise OfflineBlocked


def loopback(host: object) -> bool:
    if isinstance(host, bytes):
        try:
            host = host.decode("ascii")
        except UnicodeError:
            return False
    if not isinstance(host, str):
        return False
    if host.casefold() in {"localhost", "localhost."}:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped.is_loopback
    return address.is_loopback


def _address(value: object) -> None:
    if not isinstance(value, tuple) or not value or not loopback(value[0]):
        _deny()


def _numeric_address(value: Any, family: int) -> Any:
    _address(value)
    host = value[0].decode("ascii") if isinstance(value[0], bytes) else value[0]
    if host.casefold() in {"localhost", "localhost."}:
        return ("::1" if family == socket.AF_INET6 else "127.0.0.1", *value[1:])
    return value


def _socket_operation(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(original)
    def guarded(sock: socket.socket, *args: Any, **kwargs: Any) -> Any:
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            try:
                if name in {"connect", "connect_ex", "bind"}:
                    address = _numeric_address(
                        args[0] if args else kwargs.get("address"), sock.family
                    )
                    if args:
                        args = (address, *args[1:])
                    else:
                        kwargs["address"] = address
                elif name == "sendto":
                    address = _numeric_address(
                        args[-1] if args else kwargs.get("address"), sock.family
                    )
                    if args:
                        args = (*args[:-1], address)
                    else:
                        kwargs["address"] = address
                elif name == "sendmsg" and len(args) >= 4 and args[3] is not None:
                    args = (*args[:3], _numeric_address(args[3], sock.family), *args[4:])
                elif name == "sendmsg" and kwargs.get("address") is not None:
                    kwargs["address"] = _numeric_address(kwargs["address"], sock.family)
                else:
                    _address(sock.getpeername())
            except OfflineBlocked:
                if name == "connect_ex":
                    return errno.EACCES
                raise
        return original(sock, *args, **kwargs)

    return guarded


def _create_connection(*args: Any, **kwargs: Any) -> Any:
    _address(args[0] if args else kwargs.get("address"))
    return _ORIGINALS["create_connection"](*args, **kwargs)


def _getaddrinfo(
    host: Any, port: Any, family: int = 0, type: int = 0, proto: int = 0, flags: int = 0
) -> Any:
    if host is None:
        # Passive address construction has no DNS traffic. bind() still enforces loopback.
        return _ORIGINALS["getaddrinfo"](host, port, family, type, proto, flags)
    if not loopback(host):
        _deny()
    normalized = host.decode("ascii") if isinstance(host, bytes) else host
    if normalized.casefold() in {"localhost", "localhost."}:
        host = "::1" if family == socket.AF_INET6 else "127.0.0.1"
    return _ORIGINALS["getaddrinfo"](host, port, family, type, proto, flags | socket.AI_NUMERICHOST)


def _gethostbyname(host: Any) -> str:
    if not loopback(host):
        _deny()
    normalized = host.decode("ascii") if isinstance(host, bytes) else host
    if normalized.casefold() in {"localhost", "localhost."}:
        return "127.0.0.1"
    address = ipaddress.ip_address(normalized)
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        raise socket.gaierror(socket.EAI_ADDRFAMILY, "IPv4 address required")
    return str(address)


def _gethostbyname_ex(host: Any) -> tuple[str, list[str], list[str]]:
    return "localhost", [], [_gethostbyname(host)]


def _gethostbyaddr(host: Any) -> tuple[str, list[str], list[str]]:
    if not loopback(host):
        _deny()
    return "localhost", [], ["::1" if ":" in str(host) else "127.0.0.1"]


def _getnameinfo(address: Any, flags: int) -> Any:
    _address(address)
    address = _numeric_address(address, socket.AF_INET6 if len(address) > 2 else socket.AF_INET)
    return _ORIGINALS["getnameinfo"](address, flags | socket.NI_NUMERICHOST | socket.NI_NUMERICSERV)


def install_airlock(counter: Any = None) -> None:
    global _INSTALLED, _COUNTER
    with _LOCK:
        if counter is not None:
            _COUNTER = counter
        shared_counter()
        if _INSTALLED:
            return
        for name in ("connect", "connect_ex", "bind", "send", "sendall", "sendto", "sendmsg"):
            original = getattr(socket.socket, name, None)
            if original is not None:
                _ORIGINALS["socket." + name] = original
                setattr(socket.socket, name, _socket_operation(name, original))
        replacements = {
            "create_connection": _create_connection,
            "getaddrinfo": _getaddrinfo,
            "gethostbyname": _gethostbyname,
            "gethostbyname_ex": _gethostbyname_ex,
            "gethostbyaddr": _gethostbyaddr,
            "getnameinfo": _getnameinfo,
        }
        for name, replacement in replacements.items():
            _ORIGINALS[name] = getattr(socket, name)
            setattr(socket, name, replacement)
        _INSTALLED = True


def airlock_status() -> tuple[bool, int]:
    counter = shared_counter()
    with counter.get_lock():
        return _INSTALLED, int(counter.value)
