import base64
import json
import os
import time

import requests
from colorama import Fore, Style

from config import get_config

# Client OAuth Cursor (documenté / reverse-engineering public)
CURSOR_OAUTH_CLIENT_ID = "KbZUR41cY7W6zRSdpSUJ7I7mLYBKOCmB"
CURSOR_OAUTH_TOKEN_URL = "https://api2.cursor.sh/oauth/token"

# Define emoji constants
EMOJI = {
    "START": "🚀",
    "OAUTH": "🔑",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WAIT": "⏳",
    "INFO": "ℹ️",
    "WARNING": "⚠️",
}


def extract_jwt_token(value: str) -> str:
    """Retire le préfixe user_01…:: du cookie WorkOS ; ne garde que le JWT."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if "%3A%3A" in raw:
        return raw.split("%3A%3A", 1)[-1].strip()
    if "::" in raw:
        return raw.split("::", 1)[-1].strip()
    return raw


def _same_jwt_token(a: str, b: str) -> bool:
    left = extract_jwt_token(a or "")
    right = extract_jwt_token(b or "")
    return bool(left and right and left == right)


def _jwt_exp_unix(token: str):
    """Retourne l’expiration JWT (unix) ou None."""
    jwt = extract_jwt_token(token)
    parts = jwt.split(".")
    if len(parts) < 2:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        exp = data.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def verify_cursor_session_active(access_token: str, translator=None, strict: bool = False) -> bool:
    """Vérifie que le JWT fonctionne via l'API Cursor (profil / usage)."""
    jwt = extract_jwt_token(access_token)
    if not jwt or len(jwt) < 20:
        return False
    try:
        from cursor_acc_info import UsageManager

        if UsageManager.get_stripe_profile(jwt):
            return True
        if UsageManager.get_usage(jwt) is not None:
            return True
    except Exception:
        pass
    if strict:
        return False
    # Fallback souple : uniquement pour un jeton fraîchement lu depuis le navigateur (inscription).
    return jwt.startswith("eyJ") and jwt.count(".") >= 2 and len(jwt) > 80


def parse_workos_session_cookie(cookie_value: str, translator=None, allow_cn_refresh: bool = False) -> dict:
    """
    Parse WorkosCursorSessionToken → user_id + JWT.
    Cursor stocke dans state.vscdb uniquement le JWT (pas le cookie complet).
    """
    raw = (cookie_value or "").strip()
    user_id = ""
    jwt = raw
    if "%3A%3A" in raw:
        user_id, jwt = raw.split("%3A%3A", 1)
    elif "::" in raw:
        user_id, jwt = raw.split("::", 1)
    jwt = extract_jwt_token(jwt)
    if allow_cn_refresh and _token_refresh_enabled(translator):
        jwt = refresh_token_via_cn_proxy(raw, translator) or jwt
    return {
        "user_id": user_id.strip(),
        "access_token": jwt,
        "refresh_token": jwt,
        "session_cookie": raw,
    }


def _oauth_refresh_candidates(refresh_token: str, access_token: str = None, session_cookie: str = None) -> list:
    """Ordre d’essai pour l’API oauth/token (refresh_token distinct de l’access en priorité)."""
    seen = set()
    candidates = []

    def _add(value: str):
        v = (value or "").strip()
        if not v or v in seen:
            return
        seen.add(v)
        candidates.append(v)

    refresh_jwt = extract_jwt_token(refresh_token)
    access_jwt = extract_jwt_token(access_token or "")
    if refresh_jwt and refresh_jwt != access_jwt:
        _add(refresh_jwt)
    if access_jwt:
        _add(access_jwt)
    if refresh_jwt:
        _add(refresh_jwt)
    if session_cookie:
        _add(session_cookie)
        _add(extract_jwt_token(session_cookie))
    return candidates


def refresh_cursor_oauth_tokens(
    refresh_token: str,
    translator=None,
    access_token: str = None,
    session_cookie: str = None,
) -> dict:
    """
    Rafraîchit access_token via l'API officielle Cursor (évite shouldLogout au démarrage IDE).
    N'appelle pas l'API si access == refresh et que la session est déjà valide via l'API Cursor.
    """
    access = extract_jwt_token(access_token or refresh_token)
    refresh = extract_jwt_token(refresh_token or access_token or access)
    if not refresh or len(refresh) < 20:
        return {"ok": False, "should_logout": True, "error": "invalid_refresh"}

    # Session cookie navigateur : access et refresh identiques — oauth/token refuse le JWT d'accès.
    if _same_jwt_token(access, refresh) and verify_cursor_session_active(access, translator, strict=True):
        print(
            f"{Fore.GREEN}{EMOJI['SUCCESS']} "
            f"{translator.get('token.oauth_session_api_ok') if translator else 'Session validated via Cursor API (cookie token; OAuth refresh not required).'}"
            f"{Style.RESET_ALL}"
        )
        return {
            "ok": True,
            "access_token": access,
            "refresh_token": refresh,
            "should_logout": False,
            "via": "api",
        }

    candidates = _oauth_refresh_candidates(refresh, access_token=access, session_cookie=session_cookie)
    if not candidates:
        return {"ok": False, "should_logout": True, "error": "invalid_refresh"}

    print(
        f"{Fore.CYAN}{EMOJI['INFO']} "
        f"{translator.get('token.oauth_refreshing') if translator else 'Validating session with Cursor OAuth API…'}"
        f"{Style.RESET_ALL}"
    )

    last_error = "http_unknown"
    should_logout = False
    for candidate in candidates:
        try:
            response = requests.post(
                CURSOR_OAUTH_TOKEN_URL,
                json={
                    "grant_type": "refresh_token",
                    "client_id": CURSOR_OAUTH_CLIENT_ID,
                    "refresh_token": candidate,
                },
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            data = {}
            try:
                data = response.json() if response.text else {}
            except json.JSONDecodeError:
                data = {}

            if data.get("shouldLogout") is True:
                should_logout = True
                last_error = "shouldLogout"
                continue

            new_access = (data.get("access_token") or "").strip()
            if not new_access:
                last_error = f"http_{response.status_code}"
                should_logout = should_logout or response.status_code in (401, 403)
                if response.status_code in (500, 502, 503, 504):
                    time.sleep(0.8)
                continue

            new_refresh = (data.get("refresh_token") or candidate).strip()
            print(
                f"{Fore.GREEN}{EMOJI['SUCCESS']} "
                f"{translator.get('token.oauth_refresh_ok') if translator else 'Cursor OAuth session validated.'}"
                f"{Style.RESET_ALL}"
            )
            return {
                "ok": True,
                "access_token": new_access,
                "refresh_token": new_refresh or refresh,
                "should_logout": False,
                "via": "oauth",
            }
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            print(
                f"{Fore.YELLOW}{EMOJI['WARNING']} "
                f"{translator.get('token.oauth_refresh_failed', error=str(e)) if translator else f'OAuth refresh failed: {e}'}"
                f"{Style.RESET_ALL}"
            )
            time.sleep(0.5)
            continue

    return {"ok": False, "should_logout": should_logout, "error": last_error}


def prepare_tokens_for_storage(
    access_token: str,
    refresh_token: str = None,
    translator=None,
    oauth_refresh: bool = None,
    strict: bool = False,
    session_cookie: str = None,
) -> dict:
    """
    Normalise JWT + rafraîchissement OAuth optionnel avant écriture dans state.vscdb / storage.json.
    """
    access = extract_jwt_token(access_token)
    refresh = extract_jwt_token(refresh_token or access_token or access)
    if not access:
        return {"ok": False, "should_logout": True}

    cfg = get_config(translator)
    do_oauth = oauth_refresh
    if do_oauth is None and cfg and cfg.has_section("Auth"):
        do_oauth = cfg.get("Auth", "oauth_refresh_on_save", fallback="false").strip().lower() in (
            "true",
            "1",
            "yes",
            "on",
        )
    elif do_oauth is None:
        do_oauth = False

    oauth_ok = False
    if do_oauth:
        result = refresh_cursor_oauth_tokens(
            refresh,
            translator,
            access_token=access,
            session_cookie=session_cookie,
        )
        if result.get("ok") and result.get("access_token"):
            access = result["access_token"]
            refresh = result.get("refresh_token") or refresh
            oauth_ok = True
        elif strict:
            if result.get("should_logout") or not verify_cursor_session_active(
                access, translator, strict=True
            ):
                return {
                    "ok": False,
                    "should_logout": True,
                    "error": "reuse_token_expired",
                }
            print(
                f"{Fore.YELLOW}{EMOJI['WARNING']} "
                f"{translator.get('token.oauth_using_saved_token') if translator else 'OAuth refresh failed; saved token still valid via Cursor API.'}"
                f"{Style.RESET_ALL}"
            )
        elif verify_cursor_session_active(access, translator, strict=False):
            print(
                f"{Fore.YELLOW}{EMOJI['WARNING']} "
                f"{translator.get('token.oauth_using_cookie_session') if translator else 'OAuth refresh unavailable; using valid session token from browser cookie.'}"
                f"{Style.RESET_ALL}"
            )
        elif result.get("should_logout"):
            return {"ok": False, "should_logout": True}
        else:
            print(
                f"{Fore.YELLOW}{EMOJI['WARNING']} "
                f"{translator.get('token.oauth_using_cookie_session') if translator else 'OAuth refresh skipped; using session token from cookie.'}"
                f"{Style.RESET_ALL}"
            )

    if not verify_cursor_session_active(access, translator, strict=strict or (do_oauth and not oauth_ok)):
        return {"ok": False, "should_logout": True, "error": "invalid_token"}

    return {
        "ok": True,
        "access_token": access,
        "refresh_token": refresh,
        "should_logout": False,
    }


def _token_refresh_enabled(translator=None) -> bool:
    """Lit Token.enable_refresh dans config.ini (chaîne : true/false)."""
    cfg = get_config(translator)
    if not cfg or not cfg.has_section("Token"):
        return False
    raw = str(cfg.get("Token", "enable_refresh", fallback="false")).strip().lower()
    return raw in ("true", "1", "yes", "on")


def refresh_token_via_cn_proxy(token, translator=None):
    """Refresh the token using the Chinese server API (optionnel, souvent indisponible)."""
    if not _token_refresh_enabled(translator):
        return None
    try:
        start_time = time.time()
        config = get_config(translator)
        refresh_server = config.get("Token", "refresh_server", fallback="https://token.cursorpro.com.cn")

        if "%3A%3A" not in token and "::" in token:
            token = token.replace("::", "%3A%3A")

        url = f"{refresh_server}/reftoken?token={token}"

        print(
            f"{Fore.CYAN}{EMOJI['INFO']} "
            f"{translator.get('token.refreshing') if translator else 'Refreshing token...'}"
            f"{Style.RESET_ALL}"
        )

        response = requests.get(url, timeout=15)

        if response.status_code == 200:
            try:
                data = response.json()

                if data.get("code") == 0 and data.get("msg") == "获取成功":
                    access_token = data.get("data", {}).get("accessToken")
                    days_left = data.get("data", {}).get("days_left", 0)
                    expire_time = data.get("data", {}).get("expire_time", "Unknown")

                    if access_token:
                        elapsed = time.time() - start_time
                        print(
                            f"{Fore.GREEN}{EMOJI['SUCCESS']} "
                            f"{translator.get('token.refresh_success', days=days_left, expire=expire_time) if translator else f'Token refreshed successfully! Valid for {days_left} days (expires: {expire_time})'} (HTTP {elapsed:.1f}s)"
                            f"{Style.RESET_ALL}"
                        )
                        return access_token
                    print(
                        f"{Fore.YELLOW}{EMOJI['WARNING']} "
                        f"{translator.get('token.no_access_token') if translator else 'No access token in response'}"
                        f"{Style.RESET_ALL}"
                    )
                else:
                    error_msg = data.get("msg", "Unknown error")
                    print(
                        f"{Fore.YELLOW}{EMOJI['WARNING']} "
                        f"{translator.get('token.refresh_failed', error=error_msg) if translator else f'Token refresh failed: {error_msg}'}"
                        f"{Style.RESET_ALL}"
                    )
            except json.JSONDecodeError:
                print(
                    f"{Fore.YELLOW}{EMOJI['WARNING']} "
                    f"{translator.get('token.invalid_response') if translator else 'Invalid JSON response from refresh server'}"
                    f"{Style.RESET_ALL}"
                )
        else:
            warn = (
                translator.get("token.server_unavailable", status=response.status_code)
                if translator
                else f"Refresh server returned HTTP {response.status_code}; using token from cookie."
            )
            print(f"{Fore.YELLOW}{EMOJI['WARNING']} {warn}{Style.RESET_ALL}")

    except requests.exceptions.Timeout:
        print(
            f"{Fore.YELLOW}{EMOJI['WARNING']} "
            f"{translator.get('token.request_timeout') if translator else 'Request to refresh server timed out'}"
            f"{Style.RESET_ALL}"
        )
    except requests.exceptions.ConnectionError:
        print(
            f"{Fore.YELLOW}{EMOJI['WARNING']} "
            f"{translator.get('token.connection_error') if translator else 'Connection error to refresh server'}"
            f"{Style.RESET_ALL}"
        )
    except Exception as e:
        print(
            f"{Fore.YELLOW}{EMOJI['WARNING']} "
            f"{translator.get('token.unexpected_error', error=str(e)) if translator else f'Unexpected error during token refresh: {e}'}"
            f"{Style.RESET_ALL}"
        )

    return None


def get_token_from_cookie(cookie_value, translator=None, allow_cn_refresh: bool = False):
    """Extrait le JWT depuis WorkosCursorSessionToken."""
    try:
        return parse_workos_session_cookie(cookie_value, translator, allow_cn_refresh=allow_cn_refresh)[
            "access_token"
        ]
    except Exception as e:
        print(
            f"{Fore.RED}{EMOJI['ERROR']} "
            f"{translator.get('token.extraction_error', error=str(e)) if translator else f'Error extracting token: {str(e)}'}"
            f"{Style.RESET_ALL}"
        )
        return extract_jwt_token(cookie_value)
