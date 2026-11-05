"""IPC regressions using private local sockets, without a running daemon."""

import socket
import sys
import threading
import time
from multiprocessing.connection import Listener
from unittest.mock import Mock

import pytest

from siada.foundation import ipc_client
from siada.foundation.ipc import IPC_AUTHKEY


@pytest.fixture
def address(monkeypatch):
    # macOS limits AF_UNIX paths to 104 bytes.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="siada-ipc-") as directory:
        path = directory + "/test.sock"
        monkeypatch.setattr(ipc_client, "get_ipc_address", lambda: path)
        yield path


@pytest.mark.skipif(sys.platform == "win32", reason="Unix socket regression")
@pytest.mark.parametrize("partial_header", [False, True])
def test_unresponsive_authentication_is_bounded(address, partial_header):
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(address)
        listener.listen(1)
        stop = threading.Event()
        def serve():
            connection, _ = listener.accept()
            with connection:
                if partial_header:
                    connection.sendall(b"\x00")
                stop.wait(3)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            client = ipc_client.DaemonIPCClient(timeout=0.1)
            start = time.monotonic()
            assert not client.connect()
            assert time.monotonic() - start < 1
            assert not client.is_connected
        finally:
            stop.set()
            thread.join(1)


@pytest.mark.skipif(sys.platform == "win32", reason="Unix socket regression")
def test_full_accept_queue_is_bounded(address):
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(address)
        listener.listen(1)
        queued = []
        try:
            for _ in range(10):
                connection = socket.socket(socket.AF_UNIX)
                connection.setblocking(False)
                queued.append(connection)
                try:
                    connection.connect(address)
                except (BlockingIOError, ConnectionRefusedError):
                    break
            else:
                pytest.fail("Could not fill accept queue")
            client = ipc_client.DaemonIPCClient(timeout=0.1)
            start = time.monotonic()
            assert not client.connect()
            assert time.monotonic() - start < 1
        finally:
            for connection in queued:
                connection.close()


@pytest.mark.skipif(sys.platform == "win32", reason="Unix socket regression")
def test_authenticated_rpc_remains_compatible(address):
    with Listener(address, authkey=IPC_AUTHKEY) as listener:
        def serve():
            with listener.accept() as connection:
                request = connection.recv()
                connection.send({"result": "ok", "id": request["id"]})
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        client = ipc_client.DaemonIPCClient(timeout=1)
        try:
            assert client.connect()
            assert client.call("test")["result"] == "ok"
        finally:
            client.disconnect()
            thread.join(2)
        assert not thread.is_alive()


def test_rpc_failure_closes_connection():
    client = ipc_client.DaemonIPCClient()
    connection = Mock()
    connection.send.side_effect = BrokenPipeError("peer closed")
    client._conn = connection
    with pytest.raises(ConnectionError):
        client.call("test")
    connection.close.assert_called_once()
    assert not client.is_connected


def test_rpc_timeout_discards_late_response_connection():
    client = ipc_client.DaemonIPCClient()
    connection = Mock()
    connection.poll.return_value = False
    client._conn = connection
    assert "timeout" in client.call("test")["error"]
    connection.close.assert_called_once()
    assert not client.is_connected


@pytest.mark.skipif(sys.platform == "win32", reason="Unix socket regression")
def test_partial_rpc_frame_times_out_and_closes_connection(address):
    with Listener(address, authkey=IPC_AUTHKEY) as listener:
        stop = threading.Event()
        def serve():
            with listener.accept() as connection:
                connection.recv()
                # One byte makes poll() true but cannot complete a frame.
                import os
                os.write(connection.fileno(), b"\x00")
                stop.wait(3)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        client = ipc_client.DaemonIPCClient(timeout=0.1)
        try:
            assert client.connect()
            start = time.monotonic()
            with pytest.raises(ConnectionError):
                client.call("test")
            assert time.monotonic() - start < 1
            assert not client.is_connected
        finally:
            client.disconnect()
            stop.set()
            thread.join(1)


@pytest.mark.skipif(sys.platform == "win32", reason="Unix socket regression")
def test_rejected_authentication_closes_socket(address, monkeypatch):
    opened = []
    original = ipc_client.socket.socket
    def tracked_socket(*args, **kwargs):
        sock = original(*args, **kwargs)
        opened.append(sock)
        return sock
    with Listener(address, authkey=b"wrong-key") as listener:
        from multiprocessing import AuthenticationError
        def serve():
            with pytest.raises(AuthenticationError):
                listener.accept()
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        monkeypatch.setattr(ipc_client.socket, "socket", tracked_socket)
        client = ipc_client.DaemonIPCClient(timeout=1)
        assert not client.connect()
        thread.join(2)
        assert not thread.is_alive()
        assert opened
        assert all(sock.fileno() == -1 for sock in opened)