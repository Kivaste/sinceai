"""Interpreter start-up hook: blocks sockets when PETS_OFFLINE=1. Self-contained."""
import os

if os.environ.get("PETS_OFFLINE") == "1":
    import _socket
    import socket as _s

    def _deny(*a, **k):
        raise OSError("pets-release: network access is disabled (offline guard)")

    class _Blocked(_s.socket):
        def __init__(self, *a, **k):
            _deny()

    _s.socket = _s.SocketType = _Blocked
    _socket.socket = _socket.SocketType = _Blocked
    for _n in ("create_connection", "create_server", "getaddrinfo", "gethostbyname", "gethostbyname_ex",
               "socketpair", "fromfd", "gethostbyaddr", "getnameinfo"):
        setattr(_s, _n, _deny)
        if hasattr(_socket, _n):
            setattr(_socket, _n, _deny)
