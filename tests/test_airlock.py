"""Real local sockets and denied public addresses; no external DNS or packet is sent."""

import errno
import socket
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.security.airlock import OfflineBlocked, airlock_status, install_airlock, loopback


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "127.0.0.2", "::1", "::ffff:127.0.0.1", "localhost", "LOCALHOST."]
)
def test_loopback_address_forms(host):
    assert loopback(host)


@pytest.mark.parametrize(
    "host",
    [
        "example.com",
        "localhost.evil",
        "0.0.0.0",
        "::",
        "192.168.1.1",
        "::ffff:8.8.8.8",
        "2130706433",
        "127.1",
        b"\xff",
    ],
)
def test_nonloopback_and_ambiguous_forms_are_refused(host):
    assert not loopback(host)


def test_example_com_connect_is_blocked_and_counted():
    install_airlock()
    before = airlock_status()[1]
    with socket.socket() as client, pytest.raises(OfflineBlocked):
        client.connect(("example.com", 443))
    assert airlock_status()[1] == before + 1


@pytest.mark.parametrize(
    "operation",
    [
        lambda: socket.create_connection(("example.com", 443), timeout=1),
        lambda: socket.getaddrinfo("example.com", 443),
        lambda: socket.gethostbyname("example.com"),
        lambda: socket.gethostbyname_ex("example.com"),
        lambda: socket.gethostbyaddr("8.8.8.8"),
    ],
)
def test_outbound_helpers_fail_before_dns(operation):
    install_airlock()
    before = airlock_status()[1]
    with pytest.raises(OfflineBlocked):
        operation()
    assert airlock_status()[1] == before + 1


def test_connect_ex_udp_and_wildcard_bind_are_blocked():
    install_airlock()
    before = airlock_status()[1]
    with socket.socket() as client:
        assert client.connect_ex(("198.51.100.1", 443)) == errno.EACCES
        with pytest.raises(OfflineBlocked):
            client.bind(("0.0.0.0", 0))
    with socket.socket(type=socket.SOCK_DGRAM) as client, pytest.raises(OfflineBlocked):
        client.sendto(b"contract", ("198.51.100.1", 53))
    assert airlock_status()[1] == before + 3


def test_real_loopback_tcp_and_localhost_resolution_work():
    install_airlock()
    before = airlock_status()[1]
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()

        def echo():
            client, _ = server.accept()
            with client:
                client.sendall(client.recv(16))

        with ThreadPoolExecutor(max_workers=1) as pool:
            job = pool.submit(echo)
            with socket.create_connection(
                ("LOCALHOST", server.getsockname()[1]), timeout=2
            ) as client:
                client.sendall(b"contract")
                assert client.recv(16) == b"contract"
            job.result(timeout=2)
    assert airlock_status()[1] == before
    assert socket.getaddrinfo("localhost", 80, socket.AF_INET6)[0][4][0] == "::1"


def test_loopback_udp_and_unix_ipc_remain_available():
    install_airlock()
    with (
        socket.socket(type=socket.SOCK_DGRAM) as server,
        socket.socket(type=socket.SOCK_DGRAM) as client,
    ):
        server.bind(("127.0.0.1", 0))
        server.settimeout(2)
        client.sendto(b"contract", server.getsockname())
        assert server.recv(16) == b"contract"
    left, right = socket.socketpair()
    with left, right:
        left.sendall(b"ipc")
        assert right.recv(16) == b"ipc"


def blocked_worker(counter):
    from backend.security.airlock import install_airlock

    install_airlock(counter)
    try:
        socket.create_connection(("example.com", 443))
    except OfflineBlocked:
        pass


def test_spawned_worker_blocks_and_updates_parent_counter():
    import multiprocessing

    from backend.security.airlock import shared_counter

    install_airlock()
    before = airlock_status()[1]
    process = multiprocessing.get_context("spawn").Process(
        target=blocked_worker, args=(shared_counter(),)
    )
    process.start()
    process.join(timeout=10)
    if process.is_alive():
        process.terminate()
        process.join()
        pytest.fail("Guarded worker did not stop")
    assert process.exitcode == 0
    assert airlock_status()[1] == before + 1


def test_reverse_lookup_alias_is_numeric_before_native_resolver(monkeypatch):
    import backend.security.airlock as guard

    install_airlock()

    def numeric_only(address, flags):
        assert address == ("127.0.0.1", 80)
        assert flags & socket.NI_NUMERICHOST and flags & socket.NI_NUMERICSERV
        return "127.0.0.1", "80"

    monkeypatch.setitem(guard._ORIGINALS, "getnameinfo", numeric_only)
    assert socket.getnameinfo(("LOCALHOST.", 80), 0) == ("127.0.0.1", "80")
