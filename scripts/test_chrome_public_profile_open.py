"""Test : ouverture du profil Chrome public (miroir CDP + compte loic5488@gmail.com)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chrome_gmail_scan import find_chrome_profile_for_email, get_browser_user_data_dir
from agent_cli_helper import (
    _get_chrome_preferred_profile_email,
    open_chrome_public_profile_page,
    sync_chrome_public_session_from_page,
)


def main():
    email = _get_chrome_preferred_profile_email()
    ud = get_browser_user_data_dir(None, "chrome")
    found = find_chrome_profile_for_email(ud, email) if ud else None
    print("target:", email)
    print("found:", found)

    page = None
    try:
        page, _config = open_chrome_public_profile_page(None)
        page.get("chrome://version")
        import time

        time.sleep(0.6)
        text = page.run_js("return document.body ? document.body.innerText : ''") or ""
        profile_line = next(
            (ln for ln in text.splitlines() if "profil" in ln.lower() or "profile path" in ln.lower()),
            "?",
        )
        print("profile_line:", profile_line.strip())
        meta = getattr(page, "_cursor_chrome_session", {})
        print("session_meta:", meta)
        ok = bool(meta.get("cdp_ud") and meta.get("real_ud") and meta.get("profile_dir") == "Default")
        print("OPEN OK" if ok else "OPEN FAILED")
        return 0 if ok else 1
    except Exception as e:
        print("ERROR:", e)
        return 2
    finally:
        if page:
            sync_chrome_public_session_from_page(page, None)


if __name__ == "__main__":
    raise SystemExit(main())
