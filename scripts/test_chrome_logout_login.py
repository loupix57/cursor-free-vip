"""Test : profil Chrome loic5488@gmail.com + logout/login compte récent."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from account_manager import AccountManager
from chrome_gmail_scan import find_chrome_profile_for_email, get_browser_user_data_dir
from agent_cli_helper import (
    _get_chrome_preferred_profile_email,
    _resolve_chrome_profile_dir,
    automate_cursor_web_email_password_login,
    chrome_profile_logout_cursor_session,
)


def _pick_test_account(max_age_days: int = 2):
    from datetime import datetime

    am = AccountManager()
    now = datetime.now()
    candidates = []
    for a in am.get_saved_accounts():
        ca = a.get("created_at")
        if not ca:
            continue
        age = (now - ca).days
        pw = (a.get("password") or "").strip()
        if pw and 1 <= age <= max_age_days:
            candidates.append((age, a))
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1] if candidates else None


def main():
    chrome_email = _get_chrome_preferred_profile_email()
    ud = get_browser_user_data_dir(None, "chrome")
    found = find_chrome_profile_for_email(ud, chrome_email) if ud else None
    profile = _resolve_chrome_profile_dir(None, chrome_email)
    print("=== Chrome profile ===")
    print("target email:", chrome_email)
    print("resolved profile:", profile)
    print("find_chrome_profile_for_email:", found)

    acc = _pick_test_account(2)
    if not acc:
        print("No account 1-2 days old with password in cursor_accounts.txt")
        return 1
    email = acc["email"]
    password = acc["password"]
    print("=== Test account ===")
    print("email:", email)

    print("\n=== Step 1: logout on Chrome profile ===")
    if not chrome_profile_logout_cursor_session():
        print("LOGOUT FAILED")
        return 2

    print("\n=== Step 2: login target account ===")
    ok = automate_cursor_web_email_password_login(
        email,
        password,
        translator=None,
        update_existing=True,
        use_chrome_public_profile=True,
    )
    print("LOGIN OK" if ok else "LOGIN FAILED")
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
