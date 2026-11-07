"""The one process allowed to open a socket: reads a request body on stdin, POSTs it, writes the reply.

Started only by `transport.subprocess_transport`, and only after `--allow-network`. Standard library only.
URL and API key arrive in the environment (never argv). Redirects are not followed, so a key cannot be
forwarded to a host the user did not name. Error text goes to stderr without the URL, key or body.
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main() -> int:
    url = os.environ.get("PETS_LLM_SEND_URL", "")
    timeout = float(os.environ.get("PETS_LLM_SEND_TIMEOUT", "120"))
    key = os.environ.get("PETS_LLM_API_KEY", "")
    if not url.startswith(("http://", "https://")):
        print("sender: bad URL", file=sys.stderr)
        return 2
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=sys.stdin.buffer.read(), headers=headers, method="POST")
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as resp:
            sys.stdout.buffer.write(resp.read())
    except urllib.error.HTTPError as e:
        print(f"sender: HTTP status {e.code}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"sender: {type(e).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
