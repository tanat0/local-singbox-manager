from __future__ import annotations

from urllib.parse import quote

from fastapi.responses import RedirectResponse


def redirect(path: str, msg: str = "", msg_type: str = "info") -> RedirectResponse:
    url = path
    if msg:
        url += f"?msg={quote(msg)}&msg_type={msg_type}"
    return RedirectResponse(url=url, status_code=303)
