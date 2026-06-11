# agent_cli_helper.py — Option 16 : `agent login` + DrissionPage. Option 17 : connexion web Cursor (authenticator), sans agent.
# et optionnellement automatiser le flux (fenêtre réduite, clics, saisie e-mail / mot de passe).
import base64
import json
import os
import re
import sys
import time
import uuid
import shutil
import tempfile
import subprocess
import platform
import socket
from typing import List, Optional, Sequence, Tuple
from urllib.parse import quote

from get_user_token import extract_jwt_token

from colorama import Fore, Style

EMOJI = {"INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌"}

DEFAULT_CLI_LOGIN_EMAIL = "continuer"
DEFAULT_CLI_LOGIN_PASSWORD = "connecter"

# ``/sign-in`` renvoie souvent 404 — entrée web = même host avec client_id + redirect (flux dashboard).
CURSOR_AUTH_CLIENT_ID = "client_01GS6W3C96KW4WRS6Z93JCE2RJ"
CURSOR_AUTH_REDIRECT_URI = "https://cursor.com/api/auth/callback"
CURSOR_WEB_SIGN_UP = "https://authenticator.cursor.sh/sign-up"


def cursor_web_authenticator_entry_url() -> str:
    """URL d’entrée authenticator (équivalent « Sign in » depuis cursor.com), sans chemin ``/sign-in``."""
    state = {"returnTo": "/dashboard", "nonce": str(uuid.uuid4())}
    state_q = quote(json.dumps(state, separators=(",", ":")), safe="")
    redir_q = quote(CURSOR_AUTH_REDIRECT_URI, safe="")
    return (
        f"https://authenticator.cursor.sh/?client_id={CURSOR_AUTH_CLIENT_ID}"
        f"&redirect_uri={redir_q}&state={state_q}"
    )


def _authenticator_page_is_not_found(page) -> bool:
    try:
        t = (page.title or "").lower()
        if "404" in t or "not found" in t or "introuvable" in t:
            return True
        body = ""
        try:
            body = (page.html or "")[:12000].lower()
        except Exception:
            pass
        if (
            "cette page n'existe pas" in body
            or "page introuvable" in body
            or "this page doesn't exist" in body
            or "page not found" in body
        ):
            return True
    except Exception:
        pass
    return False


def _open_authenticator_for_web_password_login(page, translator) -> None:
    page.get(cursor_web_authenticator_entry_url())
    time.sleep(1.35)
    if not _authenticator_page_is_not_found(page):
        return
    msg = (
        translator.get("agent_cli.authenticator_signin_404_fallback")
        if translator
        else "Authenticator returned a not-found page; trying sign-up URL…"
    )
    print(f"{Fore.YELLOW}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")
    page.get(CURSOR_WEB_SIGN_UP)
    time.sleep(1.1)
    _try_click_xpaths(
        page,
        [
            '//a[contains(., "Sign in")]',
            '//a[contains(., "sign in")]',
            '//a[contains(., "Log in")]',
            '//a[contains(., "Se connecter")]',
            '//button[contains(., "Sign in")]',
        ],
        timeout_each=2.0,
    )
    time.sleep(0.75)

# Défauts mode 2 si [AgentCliLogin] absent du config.ini (voir aussi config.py)
_MODE2_DEFAULT_W, _MODE2_DEFAULT_H = 1040, 780
_MODE2_DEFAULT_X, _MODE2_DEFAULT_Y = 64, 40


def get_cli_login_mode2_window_rect(translator=None) -> Tuple[int, int, int, int]:
    """
    Mode menu **2** (automatisation DrissionPage / option 16) : largeur, hauteur, coin supérieur gauche (x, y).

    Valeurs lues dans ``[AgentCliLogin]`` du ``config.ini`` (``window_width``, ``window_height``,
    ``window_x``, ``window_y``), sinon constantes ci-dessus.
    """
    w, h, x, y = _MODE2_DEFAULT_W, _MODE2_DEFAULT_H, _MODE2_DEFAULT_X, _MODE2_DEFAULT_Y
    try:
        from config import get_config

        cfg = get_config(translator)
        if cfg and cfg.has_section("AgentCliLogin"):
            w = cfg.getint("AgentCliLogin", "window_width", fallback=w)
            h = cfg.getint("AgentCliLogin", "window_height", fallback=h)
            x = cfg.getint("AgentCliLogin", "window_x", fallback=x)
            y = cfg.getint("AgentCliLogin", "window_y", fallback=y)
    except (ValueError, TypeError, Exception):
        pass
    w = max(400, min(w, 3840))
    h = max(320, min(h, 2160))
    x = max(0, x)
    y = max(0, y)
    return w, h, x, y


def load_last_saved_login_credentials(translator=None) -> Optional[Tuple[str, str]]:
    """
    Dernier bloc valide de ``cursor_accounts.txt`` (e-mail + mot de passe non vides),
    relatif au répertoire du projet pour fonctionner quel que soit le CWD.
    """
    try:
        from account_manager import AccountManager

        proj = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(proj, "cursor_accounts.txt")
        am = AccountManager(translator, accounts_file=path)
        accounts = am.get_saved_accounts()
        for acc in reversed(accounts):
            em = (acc.get("email") or "").strip()
            pw = (acc.get("password") or "").strip()
            if em and pw:
                return em, pw
    except Exception:
        pass
    return None


def normalize_cli_login_url(url: str) -> str:
    """
    Réassemble une URL copiée depuis le terminal (retours à la ligne, espaces de césure).
    """
    if not url:
        return ""
    s = url.strip().replace("\r", "").replace("\n", "")
    s = re.sub(r"\s+", "", s)
    return s


def _resolve_agent_exe() -> Optional[str]:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        userprofile = os.environ.get("USERPROFILE", "")
        candidates = [
            # Chemins explicites Windows (prioritaires)
            os.path.join(userprofile, "AppData", "Local", "cursor-agent", "agent.exe"),
            os.path.join(userprofile, "AppData", "Local", "cursor-agent", "agent.cmd"),
            os.path.join(userprofile, "AppData", "Local", "cursor-agent", "agent"),
            # Chemins via variables d'environnement
            os.path.join(local, "cursor-agent", "agent.exe"),
            os.path.join(local, "cursor-agent", "agent.cmd"),
            os.path.join(local, "cursor-agent", "agent"),
            os.path.join(local, "Programs", "cursor-agent", "agent.exe"),
            os.path.join(local, "Programs", "cursor-agent", "agent.cmd"),
            os.path.join(local, "Programs", "cursor-agent", "agent"),
        ]
        for p in candidates:
            if p and os.path.isfile(p):
                return p
    found = shutil.which("agent")
    return found or None


def _extract_login_url_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(
        r"https://cursor\.com/loginDeepControl\?[\s\S]*?redirectTarget=cli",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    return normalize_cli_login_url(m.group(0))


def launch_agent_login_and_get_url(
    translator=None,
    timeout_sec: float = 25.0,
) -> Tuple[Optional[subprocess.Popen], str, str, Optional[object]]:
    """
    Lance `agent login` avec NO_OPEN_BROWSER=1 puis extrait l'URL loginDeepControl.
    Retourne (process, url, log_path, log_file_handle).
    """
    agent_exe = _resolve_agent_exe()
    if not agent_exe:
        return None, "", "", None

    fd, log_path = tempfile.mkstemp(prefix="agent-login-", suffix=".log")
    os.close(fd)
    log_fp = open(log_path, "w", encoding="utf-8", errors="ignore")
    env = os.environ.copy()
    env["NO_OPEN_BROWSER"] = "1"

    proc = subprocess.Popen(
        [agent_exe, "login"],
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    deadline = time.time() + timeout_sec
    url = ""
    while time.time() < deadline and proc.poll() is None:
        try:
            log_fp.flush()
        except Exception:
            pass
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as r:
                url = _extract_login_url_from_text(r.read()) or ""
        except Exception:
            url = ""
        if url:
            break
        time.sleep(0.25)

    return proc, url, log_path, log_fp


def _private_launch_args(browser_type: str, url: str) -> List[str]:
    b = (browser_type or "edge").lower()
    if b == "firefox":
        return ["-private-window", url]
    if b == "edge":
        return ["-inprivate", url]
    if b in ("opera", "operagx"):
        return ["--private", url]
    return ["--incognito", url]


def _resolve_browser_exe(browser_type: str, translator) -> Optional[str]:
    from utils import get_default_browser_path

    path = get_default_browser_path(browser_type)
    if path and os.path.isfile(path):
        return path
    if sys.platform == "win32":
        import shutil

        which_map = {
            "edge": "msedge",
            "chrome": "chrome",
            "firefox": "firefox",
            "brave": "brave",
        }
        w = which_map.get(browser_type.lower())
        if w:
            found = shutil.which(w)
            if found:
                return found
    return None


def open_url_in_private_browsing_window(
    url: str,
    browser_type: Optional[str] = None,
    translator=None,
) -> bool:
    """
    Ouvre une URL (ex. lien loginDeepControl affiché par `agent login`) dans une fenêtre privée.

    Utilise le navigateur défini dans la config [Browser] default_browser si browser_type est None.
    """
    url = normalize_cli_login_url(url)
    if not url.startswith(("https://", "http://")):
        msg = (
            translator.get("agent_cli.url_invalid")
            if translator
            else "URL must start with https:// or http://"
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {msg}{Style.RESET_ALL}")
        return False

    b = browser_type
    if not b:
        try:
            from config import get_config

            cfg = get_config(translator)
            if cfg and cfg.has_section("Browser") and cfg.has_option("Browser", "default_browser"):
                b = cfg.get("Browser", "default_browser", fallback="edge").strip()
        except Exception:
            b = "edge"
        if not b:
            b = "edge"

    exe = _resolve_browser_exe(b, translator)
    if not exe:
        msg = (
            translator.get("agent_cli.browser_not_found", browser=b)
            if translator
            else f"Browser executable not found for: {b}"
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {msg}{Style.RESET_ALL}")
        return False

    args = [exe] + _private_launch_args(b, url)
    try:
        if platform.system() == "Windows":
            subprocess.Popen(args, close_fds=True)
        else:
            subprocess.Popen(
                args,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        ok = (
            translator.get("agent_cli.private_open_ok", browser=b)
            if translator
            else f"Private window opened ({b})"
        )
        print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {ok}{Style.RESET_ALL}")
        return True
    except Exception as e:
        msg = (
            translator.get("agent_cli.private_open_failed", error=str(e))
            if translator
            else f"Failed to open browser: {e}"
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {msg}{Style.RESET_ALL}")
        return False


def _chromium_page_cli_login(translator) -> Tuple[object, object, str]:
    """
    DrissionPage Chromium incognito, taille / position du **mode 2**.

    Utilise un **répertoire de profil temporaire** dédié (évite l’erreur « connexion au navigateur »
    quand Chrome/Edge est déjà ouvert avec le profil par défaut).
    Retourne ``(page, config, session_user_data_dir)`` pour nettoyage après ``quit``.
    """
    from DrissionPage import ChromiumPage, ChromiumOptions
    from config import get_config
    from utils import get_default_browser_path

    config = get_config(translator)
    ww, hh, px, py = get_cli_login_mode2_window_rect(translator)
    geo = (
        translator.get("agent_cli.window_mode2", w=ww, h=hh, x=px, y=py)
        if translator
        else f"Mode 2 window: {ww}x{hh} @ ({px},{py})"
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {geo}{Style.RESET_ALL}")

    browser_type = config.get("Browser", "default_browser", fallback="chrome").strip().lower()
    path_key = f"{browser_type}_path"
    browser_path = config.get("Browser", path_key, fallback=get_default_browser_path(browser_type))
    if not browser_path or not os.path.isfile(browser_path):
        browser_path = get_default_browser_path(browser_type)

    session_dir = os.path.join(
        tempfile.gettempdir(),
        "cursor-free-vip-agent-cli",
        uuid.uuid4().hex,
    )
    os.makedirs(session_dir, exist_ok=True)

    co = ChromiumOptions()
    co.set_paths(browser_path=browser_path, user_data_path=session_dir)
    co.set_argument("--incognito")
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")
    co.set_argument(f"--window-size={ww},{hh}")
    co.set_argument(f"--window-position={px},{py}")
    if sys.platform == "linux":
        co.set_argument("--no-sandbox")
        co.set_argument("--disable-dev-shm-usage")
    elif os.name == "nt":
        co.set_argument("--disable-features=TranslateUI")
        co.set_argument("--disable-features=RendererCodeIntegrity")
    co.auto_port()
    co.headless(False)

    proj = os.path.dirname(os.path.abspath(__file__))
    extension_path = os.path.join(proj, "turnstilePatch")
    if os.path.isdir(extension_path):
        try:
            co.set_argument("--allow-extensions-in-incognito")
            co.add_extension(extension_path)
        except Exception:
            pass

    try:
        page = ChromiumPage(co)
    except Exception:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise
    time.sleep(0.95)
    return page, config, session_dir


def _get_chrome_debug_port(translator=None) -> int:
    try:
        from config import get_config

        cfg = get_config(translator)
        if cfg and cfg.has_section("Chrome"):
            return max(1024, int(str(cfg.get("Chrome", "debug_port", fallback="9222")).strip()))
    except Exception:
        pass
    return 9222


def _chrome_force_profile_relaunch(translator=None) -> bool:
    try:
        from config import get_config

        cfg = get_config(translator)
        if cfg and cfg.has_section("Chrome"):
            return str(cfg.get("Chrome", "force_profile_relaunch", fallback="true")).strip().lower() in (
                "true",
                "1",
                "yes",
                "on",
            )
    except Exception:
        pass
    return True


def _get_chrome_user_data_dir() -> str:
    if os.name == "nt":
        return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
    return ""


def _get_chrome_cdp_user_data_dir() -> str:
    """Copie miroir du User Data Chrome (chemin non standard → CDP autorisé depuis Chrome 136)."""
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "cursor-free-vip", "chrome-cdp-user-data")


_CHROME_MIRROR_IGNORE = shutil.ignore_patterns(
    "Cache",
    "Code Cache",
    "GPUCache",
    "GrShaderCache",
    "ShaderCache",
    "Service Worker",
    "BrowserMetrics*",
    "Crashpad",
    "SingletonLock",
    "SingletonCookie",
    "SingletonSocket",
)


def _chrome_profile_session_rel_paths() -> List[str]:
    """Chemins relatifs (sous le dossier profil) à synchroniser entre Chrome réel et miroir CDP."""
    return [
        "Preferences",
        os.path.join("Network", "Cookies"),
        os.path.join("Network", "Cookies-journal"),
        "Local Storage",
        "Session Storage",
        "IndexedDB",
        "Web Data",
        "Web Data-journal",
        "Login Data",
        "Login Data-journal",
    ]


def _copy_path_if_exists(src: str, dst: str) -> None:
    if not os.path.exists(src):
        return
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.isdir(src):
        if os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


def _sync_chrome_profile_session(src_ud: str, dst_ud: str, profile_dir: str) -> None:
    """Copie cookies / stockage local du profil src → dst (Chrome doit être fermé)."""
    for rel in _chrome_profile_session_rel_paths():
        src = os.path.join(src_ud, profile_dir, rel)
        dst = os.path.join(dst_ud, profile_dir, rel)
        _copy_path_if_exists(src, dst)
    _copy_path_if_exists(
        os.path.join(src_ud, "Local State"),
        os.path.join(dst_ud, "Local State"),
    )


def _ensure_chrome_cdp_mirror(real_ud: str, cdp_ud: str, profile_dir: str, translator=None) -> None:
    """
    Prépare le miroir CDP : copie complète au premier lancement, puis sync session depuis Chrome réel.
    Chrome 136+ ignore --remote-debugging-port sur le User Data par défaut.
    """
    if not real_ud or not os.path.isdir(real_ud):
        return
    if not os.path.isdir(cdp_ud):
        msg = (
            translator.get("agent_cli.chrome_cdp_mirror_init", path=cdp_ud)
            if translator
            else f"First-time Chrome CDP mirror copy → {cdp_ud} (one-time, may take a minute)…"
        )
        print(f"{Fore.CYAN}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")
        os.makedirs(os.path.dirname(cdp_ud), exist_ok=True)
        shutil.copytree(real_ud, cdp_ud, ignore=_CHROME_MIRROR_IGNORE)
    else:
        msg = (
            translator.get("agent_cli.chrome_cdp_sync_from_real", profile=profile_dir)
            if translator
            else f"Syncing Chrome profile {profile_dir} from real browser into CDP mirror…"
        )
        print(f"{Fore.CYAN}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")
        _sync_chrome_profile_session(real_ud, cdp_ud, profile_dir)


def _sync_chrome_cdp_back_to_real(
    real_ud: str, cdp_ud: str, profile_dir: str, translator=None
) -> None:
    """Après automation : réinjecte cookies/session Cursor dans le Chrome réel de l'utilisateur."""
    if not real_ud or not cdp_ud or not os.path.isdir(cdp_ud):
        return
    msg = (
        translator.get("agent_cli.chrome_cdp_sync_to_real", profile=profile_dir)
        if translator
        else f"Syncing Cursor session back to real Chrome profile {profile_dir}…"
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")
    _sync_chrome_profile_session(cdp_ud, real_ud, profile_dir)


def _kill_chrome_processes(translator=None) -> None:
    msg = (
        translator.get("agent_cli.chrome_kill_processes")
        if translator
        else "Closing all Chrome processes to attach the correct profile…"
    )
    print(f"{Fore.YELLOW}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")
    if os.name == "nt":
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    time.sleep(0.8)


def _resolve_chrome_profile_dir(translator=None, email: str = None) -> str:
    """Dossier profil Chrome (Default, Profile 1, …) pour l'e-mail configuré."""
    target = (email or _get_chrome_preferred_profile_email(translator)).strip().lower()
    ud = ""
    try:
        from chrome_gmail_scan import find_chrome_profile_for_email, get_browser_user_data_dir

        ud = get_browser_user_data_dir(translator, browser_type="chrome") or ""
        found = find_chrome_profile_for_email(ud, target) if ud else None
        if found and found.get("profile_dir"):
            return found["profile_dir"]
    except Exception:
        pass

    try:
        from chrome_gmail_scan import _read_profile_account_email
        from config import get_config

        cfg = get_config(translator)
        if cfg and cfg.has_section("Chrome"):
            forced = (cfg.get("Chrome", "profile_directory", fallback="") or "").strip()
            if forced and ud:
                forced_email = _read_profile_account_email(ud, forced)
                if forced_email == target:
                    return forced
                if forced_email:
                    print(
                        f"{Fore.YELLOW}{EMOJI['INFO']} "
                        f"[Chrome] profile_directory={forced} is {forced_email}, not {target} — ignored."
                        f"{Style.RESET_ALL}"
                    )
            elif forced:
                return forced
    except Exception:
        pass
    return "Default"


def _read_active_chrome_profile_path(page) -> str:
    """Lit le chemin profil depuis chrome://version (vérifie qu'on pilote le bon profil)."""
    try:
        page.get("chrome://version")
        time.sleep(0.55)
        text = ""
        try:
            text = page.run_js("return document.body ? document.body.innerText : ''") or ""
        except Exception:
            pass
        if not text:
            try:
                text = page.html or ""
            except Exception:
                text = ""
        for pattern in (
            r"Chemin d'accès au profil\s*([^\n\r]+)",
            r"Profile Path\s*([^\n\r]+)",
        ):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    except Exception:
        pass
    return ""


def _verify_chrome_profile_active(page, user_data_dir: str, profile_dir: str, translator=None) -> bool:
    """Vérifie que l'instance Chrome pilotée utilise bien profile_dir."""
    if not user_data_dir or not profile_dir:
        return True
    path = _read_active_chrome_profile_path(page).replace("/", os.sep)
    expected_suffix = os.path.join(user_data_dir, profile_dir).replace("/", os.sep)
    ok = expected_suffix.lower() in path.lower()
    if ok:
        msg = (
            translator.get("agent_cli.chrome_profile_verified", path=path)
            if translator
            else f"Chrome profile verified: {path}"
        )
        print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {msg}{Style.RESET_ALL}")
    else:
        msg = (
            translator.get(
                "agent_cli.chrome_profile_mismatch",
                expected=expected_suffix,
                actual=path or "?",
            )
            if translator
            else f"Chrome profile mismatch — expected {expected_suffix}, got {path or '?'}"
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {msg}{Style.RESET_ALL}")
    return ok


def _jwt_claim(token: str, claim: str):
    jwt = extract_jwt_token(token or "")
    parts = jwt.split(".")
    if len(parts) < 2:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        return data.get(claim)
    except Exception:
        return None


def _read_workos_session_cookie(page) -> str:
    try:
        for cookie in page.cookies() or []:
            if cookie.get("name") == "WorkosCursorSessionToken":
                val = (cookie.get("value") or "").strip()
                if val:
                    return val
    except Exception:
        pass
    return ""


def _cursor_session_cookie_present(page) -> bool:
    return bool(_read_workos_session_cookie(page))


def _delete_cursor_session_cookies_cdp(page) -> int:
    """Supprime les cookies HttpOnly Cursor/WorkOS via CDP (obligatoire pour un vrai logout)."""
    removed = 0
    try:
        page.run_cdp("Network.enable")
    except Exception:
        pass

    names = (
        "WorkosCursorSessionToken",
        "cursor-web-target-synced-user",
        "workos_id",
        "workos_session",
    )
    domains = (
        "cursor.com",
        ".cursor.com",
        "www.cursor.com",
        "authenticator.cursor.sh",
        ".authenticator.cursor.sh",
    )
    for domain in domains:
        for name in names:
            try:
                page.run_cdp("Network.deleteCookies", name=name, domain=domain)
                removed += 1
            except Exception:
                pass

    for url in (
        "https://www.cursor.com",
        "https://cursor.com",
        "https://authenticator.cursor.sh",
    ):
        try:
            res = page.run_cdp("Network.getCookies", urls=[url])
            cookies = []
            if isinstance(res, dict):
                cookies = res.get("cookies") or []
            elif isinstance(res, list):
                cookies = res
            for c in cookies:
                name = (c.get("name") or "").strip()
                domain = (c.get("domain") or "cursor.com").strip()
                low = name.lower()
                if not name:
                    continue
                if "workos" in low or "cursor" in low or name in names:
                    try:
                        page.run_cdp("Network.deleteCookies", name=name, domain=domain)
                        removed += 1
                    except Exception:
                        pass
        except Exception:
            pass
    return removed


def _workos_logout_navigation(page, session_token: str, translator=None) -> bool:
    """Logout WorkOS côté serveur (révoque la session liée au cookie HttpOnly)."""
    sid = _jwt_claim(session_token, "sid")
    if not sid:
        return False
    return_to = quote("https://www.cursor.com/", safe="")
    logout_url = (
        f"https://api.workos.com/user_management/sessions/logout"
        f"?session_id={quote(str(sid), safe='')}&return_to={return_to}"
    )
    msg = (
        translator.get("agent_cli.chrome_workos_logout")
        if translator
        else "WorkOS server logout (revokes Cursor web session)…"
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")
    try:
        page.get(logout_url)
        time.sleep(1.2)
        return True
    except Exception:
        return False


def _verify_cursor_web_logged_out(page, translator=None) -> bool:
    _delete_cursor_session_cookies_cdp(page)
    try:
        page.get("https://www.cursor.com/dashboard")
        time.sleep(1.0)
    except Exception:
        pass
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    if "authenticator.cursor.sh" in url:
        return True
    if _cursor_session_cookie_present(page):
        return False
    try:
        body = (page.html or "")[:8000].lower()
        if "sign in" in body or "se connecter" in body or "log in" in body:
            return True
    except Exception:
        pass
    return not _cursor_session_cookie_present(page)


def _get_chrome_preferred_profile_email(translator=None) -> str:
    """E-mail Chrome dont le profil est utilisé pour logout/login Cursor web."""
    fallback = "loic5488@gmail.com"
    try:
        from config import get_config

        cfg = get_config(translator)
        if cfg and cfg.has_section("Chrome"):
            raw = (cfg.get("Chrome", "preferred_profile_email", fallback=fallback) or "").strip()
            if raw and "@" in raw:
                return raw
    except Exception:
        pass
    return fallback


def _chromium_page_chrome_public_current_profile(translator) -> Tuple[object, object, str, str, str]:
    """
    DrissionPage Chromium sur le profil Chrome de l'utilisateur (loic5488@gmail.com / config).

    Chrome 136+ bloque le CDP sur le User Data par défaut : on utilise un miroir local
    (cursor-free-vip/chrome-cdp-user-data) synchronisé depuis le vrai profil avant lancement.
    Retourne (page, config, profile_dir, real_user_data, cdp_user_data).
    """
    from DrissionPage import ChromiumPage, ChromiumOptions
    from config import get_config
    from utils import get_default_browser_path

    config = get_config(translator)
    ww, hh, px, py = get_cli_login_mode2_window_rect(translator)
    geo = (
        translator.get("agent_cli.window_mode2", w=ww, h=hh, x=px, y=py)
        if translator
        else f"Mode 2 window: {ww}x{hh} @ ({px},{py})"
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {geo}{Style.RESET_ALL}")

    browser_path = ""
    try:
        browser_path = config.get("Browser", "chrome_path", fallback="").strip()
    except Exception:
        browser_path = ""
    if not browser_path or not os.path.isfile(browser_path):
        browser_path = get_default_browser_path("chrome")

    preferred_email = _get_chrome_preferred_profile_email(translator)
    real_user_data = _get_chrome_user_data_dir()
    cdp_user_data = _get_chrome_cdp_user_data_dir()
    chosen_profile_dir = _resolve_chrome_profile_dir(translator, preferred_email)
    debug_port = _get_chrome_debug_port(translator)

    try:
        from chrome_gmail_scan import find_chrome_profile_for_email

        found = find_chrome_profile_for_email(real_user_data, preferred_email) if real_user_data else None
        if found:
            chosen_profile_dir = found.get("profile_dir") or chosen_profile_dir
            detail = (
                translator.get(
                    "agent_cli.chrome_profile_resolved",
                    email=preferred_email,
                    profile=chosen_profile_dir,
                    label=found.get("profile_label") or chosen_profile_dir,
                )
                if translator
                else (
                    f"Chrome profile for {preferred_email}: {chosen_profile_dir} "
                    f"({found.get('profile_label') or chosen_profile_dir})"
                )
            )
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {detail}{Style.RESET_ALL}")
    except Exception:
        pass

    info_profile = (
        translator.get("agent_cli.chrome_public_profile_forced", profile=chosen_profile_dir, email=preferred_email)
        if translator
        else f"Chrome public profile forced: {chosen_profile_dir} ({preferred_email})"
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {info_profile}{Style.RESET_ALL}")

    # Chrome 136+ : CDP interdit sur le User Data par défaut → miroir + sync depuis le vrai profil.
    _kill_chrome_processes(translator)
    time.sleep(1.2)
    _ensure_chrome_cdp_mirror(real_user_data, cdp_user_data, chosen_profile_dir, translator)

    relaunch_msg = (
        translator.get("agent_cli.chrome_debug_relaunch_profile", profile=chosen_profile_dir, port=debug_port)
        if translator
        else f"Opening Chrome profile {chosen_profile_dir} ({preferred_email}) on CDP port {debug_port}…"
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {relaunch_msg}{Style.RESET_ALL}")

    co = ChromiumOptions()
    co.set_browser_path(browser_path)
    co.set_user_data_path(cdp_user_data)
    co.set_user(chosen_profile_dir)
    co.set_local_port(debug_port)
    co.headless(False)
    co.set_argument(f"--window-size={ww},{hh}")
    co.set_argument(f"--window-position={px},{py}")
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")
    if os.name == "nt":
        co.set_argument("--disable-features=TranslateUI")
        co.set_argument("--disable-features=RendererCodeIntegrity")

    proj = os.path.dirname(os.path.abspath(__file__))
    extension_path = os.path.join(proj, "turnstilePatch")
    if os.path.isdir(extension_path):
        try:
            co.set_argument("--allow-extensions-in-incognito")
            co.add_extension(extension_path)
        except Exception:
            pass

    page = ChromiumPage(co)
    time.sleep(1.0)

    if not _verify_chrome_profile_active(page, cdp_user_data, chosen_profile_dir, translator):
        raise RuntimeError(
            f"Chrome profile mismatch: expected {chosen_profile_dir} for {preferred_email}"
        )

    return page, config, chosen_profile_dir, real_user_data, cdp_user_data


def _safe_click_maybe_later(page, translator=None) -> bool:
    """
    Clic UNIQUEMENT sur un élément dont le texte est essentiellement "Maybe later" / "Plus tard".
    Évite les sélecteurs larges qui peuvent cliquer la carte et ouvrir GitHub/GitLab.
    """
    try:
        js_ok = page.run_js(
            """
            (() => {
              const candidates = [...document.querySelectorAll('a,button,[role="link"],[role="button"],span,div,p')];
              const normalize = (s) => (s || '').trim().toLowerCase().replace(/\\s+/g, ' ');
              const valid = new Set(['maybe later', 'plus tard', "i'll do this later", 'i’ll do this later', 'i will do this later', 'je le ferai plus tard']);
              const visible = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 2 && r.height > 2 && !!(el.offsetParent || getComputedStyle(el).position === 'fixed');
              };
              const clickableAncestor = (el) => {
                let cur = el;
                for (let i = 0; i < 6 && cur; i++) {
                  const tag = (cur.tagName || '').toLowerCase();
                  const role = (cur.getAttribute && cur.getAttribute('role')) || '';
                  if (tag === 'a' || tag === 'button' || role === 'link' || role === 'button') return cur;
                  cur = cur.parentElement;
                }
                return el;
              };
              for (const el of candidates) {
                const txt = normalize(el.innerText || el.textContent);
                if (!valid.has(txt)) continue;
                if (!visible(el)) continue;
                const target = clickableAncestor(el);
                const ttxt = normalize(target.innerText || target.textContent);
                if (ttxt.includes('connect github') || ttxt.includes('connect gitlab')) continue;
                target.scrollIntoView({ block: 'center', inline: 'center' });
                try { target.click(); } catch (_) {}
                try {
                  const r = target.getBoundingClientRect();
                  const x = r.left + r.width / 2;
                  const y = r.top + r.height / 2;
                  const opts = { bubbles: true, cancelable: true, clientX: x, clientY: y };
                  target.dispatchEvent(new MouseEvent('mousedown', opts));
                  target.dispatchEvent(new MouseEvent('mouseup', opts));
                  target.dispatchEvent(new MouseEvent('click', opts));
                } catch (_) {}
                return true;
              }
              return false;
            })();
            """
        )
        if js_ok:
            return True
    except Exception:
        pass

    xpaths = [
        'xpath://a[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "maybe later")]',
        'xpath://button[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "maybe later")]',
        'xpath://a[contains(., "Plus tard")]',
        'xpath://button[contains(., "Plus tard")]',
        'xpath://a[contains(., "I\'ll do this later")]',
        'xpath://button[contains(., "I\'ll do this later")]',
    ]
    for xp in xpaths:
        try:
            el = page.ele(xp, timeout=0.75)
            if not el:
                continue
            raw = ((getattr(el, "text", None) or "") or "").strip().lower()
            if "connect github" in raw or "connect gitlab" in raw:
                continue
            el.click()
            return True
        except Exception:
            continue
    return False


def _dismiss_setup_prompts(page, translator=None) -> bool:
    """
    Ferme les écrans setup qui ouvrent des onglets OAuth (start-download ou connect-provider sur dashboard/settings)
    en cliquant exclusivement sur "Maybe later" / "I'll do this later".
    """
    try:
        u = (page.url or "").lower()
    except Exception:
        u = ""
    is_start_download = "start-download" in u
    is_connect_provider = False
    try:
        if "cursor.com" in u and ("dashboard/settings" in u or "dashboard?tab=settings" in u or "/settings" in u):
            is_connect_provider = bool(
                page.ele('xpath://*[contains(., "Connect GitHub to finish setup")]', timeout=0.35)
                or page.ele('xpath://button[contains(., "Connect GitHub")]', timeout=0.25)
                or page.ele('xpath://button[contains(., "Connect GitLab")]', timeout=0.25)
            )
    except Exception:
        is_connect_provider = False

    if not (is_start_download or is_connect_provider):
        return False

    if _safe_click_maybe_later(page, translator):
        msg = (
            translator.get("agent_cli.dismiss_start_download")
            if translator
            else "Écran setup contourné (Maybe later / I'll do this later)."
        )
        print(f"{Fore.CYAN}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")
        return True
    return False


def _try_click_xpaths(page, xpaths: Sequence[str], timeout_each: float = 4.0) -> bool:
    for xp in xpaths:
        try:
            el = page.ele(f"xpath:{xp}", timeout=timeout_each)
            if el:
                el.click()
                time.sleep(0.5)
                return True
        except Exception:
            continue
    return False


def _try_fill_then_click(
    page,
    field_selectors: Sequence[str],
    value: str,
    button_xpaths: Sequence[str],
) -> bool:
    el = None
    for sel in field_selectors:
        try:
            if sel.startswith("xpath:"):
                el = page.ele(sel, timeout=3)
            else:
                el = page.ele(sel, timeout=3)
            if el:
                break
        except Exception:
            continue
    if not el:
        return False
    try:
        el.clear()
    except Exception:
        pass
    try:
        el.input(value)
    except Exception:
        return False
    time.sleep(0.32)
    return _try_click_xpaths(page, button_xpaths, timeout_each=3.5)


def _maybe_turnstile(page, config, translator) -> None:
    try:
        from new_signup import handle_turnstile

        handle_turnstile(page, config, translator)
    except Exception:
        time.sleep(0.9)


def _ele_ok(page, selector: str, timeout: float = 1.5) -> bool:
    try:
        return bool(page.ele(selector, timeout=timeout))
    except Exception:
        return False


def _try_click_google_on_authenticator(page, translator=None) -> bool:
    """Bouton « Continuer avec Google » / lien GoogleOAuth sur authenticator.cursor."""
    xpaths = [
        "//a[contains(@href,'GoogleOAuth')]",
        "//a[contains(@href,'googleoauth')]",
        "//a[contains(@class,'auth-method-button') and contains(@href,'Google')]",
        "//button[contains(., 'Google') and not(contains(., 'GitHub'))]",
        "//a[contains(., 'Google') and contains(@href,'OAuth')]",
    ]
    return _try_click_xpaths(page, xpaths, timeout_each=3.5)


def _google_identifier_next_buttons() -> List[str]:
    return [
        '//*[@id="identifierNext"]//button',
        '//button[.//span[contains(text(),"Next")]]',
        '//button[.//span[contains(text(),"Suivant")]]',
        '//button[contains(., "Next") and not(contains(., "Google"))]',
        '//button[contains(., "Suivant")]',
    ]


def _google_password_next_buttons() -> List[str]:
    return [
        '//*[@id="passwordNext"]//button',
        '//button[.//span[contains(text(),"Next")]]',
        '//button[.//span[contains(text(),"Suivant")]]',
        '//button[contains(., "Next")]',
        '//button[contains(., "Suivant")]',
    ]


def _try_click_google_account_tile(page, email: str) -> bool:
    """Sélecteur de compte Google (tuile) si une session existe déjà."""
    local = (email or "").strip().lower()
    if not local:
        return False
    xps = [
        f'//div[@data-identifier="{local}"]',
        f'//*[translate(@data-email,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz")="{local}"]',
        f'//li[@data-identifier and translate(@data-identifier,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz")="{local}"]',
    ]
    for xp in xps:
        try:
            el = page.ele(f"xpath:{xp}", timeout=1.2)
            if el:
                el.click()
                time.sleep(1.05)
                return True
        except Exception:
            continue
    return False


def _authenticator_login_via_google_oauth_after_page_load(
    page,
    config,
    email: str,
    password: str,
    translator,
    success_done_message: str,
    deadline_seconds: float = 240.0,
) -> bool:
    """
    Flux web : authenticator → clic « Google » → saisie e-mail + mot de passe sur accounts.google.com
    → consentement éventuel → retour Cursor + « Yes, Log In ».
    """
    msg = (
        translator.get("agent_cli.google_oauth_start")
        if translator
        else "Using Google sign-in, then Gmail credentials on accounts.google.com…"
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")

    done_google_click = False
    done_g_identifier = False
    done_g_password = False
    done_yes = False
    challenge_warned = False

    _try_click_xpaths(
        page,
        [
            '//button[contains(., "Continue to sign in")]',
            '//button[contains(., "continue to sign in")]',
            '//button[contains(., "Continuer pour vous connecter")]',
        ],
        timeout_each=3.0,
    )
    time.sleep(0.8)

    deadline = time.time() + deadline_seconds
    while time.time() < deadline and not done_yes:
        u = ""
        try:
            u = page.url or ""
        except Exception:
            pass
        ulo = u.lower()

        if "start-download" in ulo or ("cursor.com" in ulo and ("/settings" in ulo or "dashboard?tab=settings" in ulo)):
            _dismiss_setup_prompts(page, translator)
            time.sleep(0.85)
            continue

        if "accounts.google.com" in ulo:
            if "/signin/v2/speedbump" in ulo or "/speedbump" in ulo:
                _try_click_xpaths(
                    page,
                    [
                        '//button[contains(., "Continue")]',
                        '//button[contains(., "Continuer")]',
                    ],
                    timeout_each=2.0,
                )
                time.sleep(1.5)
                continue

            pwd_visible = _ele_ok(page, "@name=Passwd", 1.2) or _ele_ok(
                page, 'xpath://input[@type="password"]', 1.2
            )
            id_visible = _ele_ok(page, "@id=identifierId", 0.7) or _ele_ok(
                page, 'xpath://input[@type="email"]', 0.7
            )

            if pwd_visible and not done_g_password and (done_g_identifier or not id_visible):
                if _try_fill_then_click(
                    page,
                    ["@name=Passwd", 'xpath://input[@type="password"]'],
                    password,
                    _google_password_next_buttons(),
                ):
                    done_g_password = True
                    if not done_g_identifier:
                        done_g_identifier = True
                    time.sleep(2.5)
                    _maybe_turnstile(page, config, translator)
                continue

            if any(x in ulo for x in ("totp", "sms", "ipp/collect")) or (
                "selection" in ulo and not pwd_visible
            ):
                if not challenge_warned:
                    tw = (
                        translator.get("agent_cli.google_2fa_manual")
                        if translator
                        else "Complete the Google verification step in the browser (2FA / SMS), then wait…"
                    )
                    print(f"{Fore.YELLOW}{EMOJI['INFO']} {tw}{Style.RESET_ALL}")
                    challenge_warned = True
                time.sleep(2.5)
                continue

            if not done_g_identifier:
                if _try_click_google_account_tile(page, email):
                    done_g_identifier = True
                    time.sleep(2.0)
                    continue

            if not done_g_identifier:
                if _ele_ok(page, "@id=identifierId", 2) or _ele_ok(
                    page, 'xpath://input[@type="email"]', 1.5
                ):
                    if _try_fill_then_click(
                        page,
                        ["@id=identifierId", 'xpath://input[@type="email"]'],
                        email,
                        _google_identifier_next_buttons(),
                    ):
                        done_g_identifier = True
                        time.sleep(2.0)
                        continue

            if _try_click_xpaths(
                page,
                [
                    '//button[contains(., "Allow")]',
                    '//button[contains(., "Autoriser")]',
                    '//span[contains(., "Allow")]/ancestor::button[1]',
                ],
                timeout_each=2.0,
            ):
                time.sleep(2.0)
                continue

            time.sleep(0.65)
            continue

        if "authenticator.cursor" in u:
            if not done_google_click:
                if _try_click_google_on_authenticator(page, translator):
                    done_google_click = True
                    time.sleep(2.5)
                    continue
            _maybe_turnstile(page, config, translator)

        if ("logindeepcontrol" in ulo or "cursor.com" in ulo) and not done_yes:
            if _try_click_xpaths(
                page,
                [
                    '//button[contains(., "Yes, Log In")]',
                    '//button[contains(., "Yes, Log in")]',
                    '//button[contains(., "Log In") and contains(., "Yes")]',
                ],
                timeout_each=3.0,
            ):
                done_yes = True
                time.sleep(1.1)
                print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {success_done_message}{Style.RESET_ALL}")
                return True
            if "cursor.com" in ulo and (
                "/dashboard" in ulo or "tab=settings" in ulo or "/settings" in ulo
            ):
                try:
                    for c in page.cookies() or []:
                        if c.get("name") == "WorkosCursorSessionToken" and (c.get("value") or "").strip():
                            done_yes = True
                            time.sleep(0.55)
                            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {success_done_message}{Style.RESET_ALL}")
                            return True
                except Exception:
                    pass

        time.sleep(0.5)

    fail = translator.get("agent_cli.automate_timeout") if translator else "Timeout: could not complete all steps."
    print(f"{Fore.YELLOW}{EMOJI['INFO']} {fail}{Style.RESET_ALL}")
    return False


def _authenticator_login_steps_after_page_load(
    page,
    config,
    email: str,
    password: str,
    translator,
    success_done_message: str,
    deadline_seconds: float = 150.0,
) -> bool:
    """Après ``page.get`` sur loginDeepControl ou entrée authenticator : e-mail, mot de passe, « Yes, Log In »."""
    done_email = False
    done_password = False
    done_yes = False

    _try_click_xpaths(
        page,
        [
            '//button[contains(., "Continue to sign in")]',
            '//button[contains(., "continue to sign in")]',
            '//button[contains(., "Continuer pour vous connecter")]',
        ],
        timeout_each=2.5,
    )
    time.sleep(0.85)

    deadline = time.time() + deadline_seconds
    while time.time() < deadline and not done_yes:
        u = ""
        try:
            u = page.url or ""
        except Exception:
            pass
        ulo = u.lower()

        if "start-download" in ulo or ("cursor.com" in ulo and ("/settings" in ulo or "dashboard?tab=settings" in ulo)):
            _dismiss_setup_prompts(page, translator)
            time.sleep(0.85)
            continue

        if (
            "authenticator.cursor" in u
            and "/password" not in ulo
            and not done_email
            and (
                _ele_ok(page, "@name=email", 2)
                or _ele_ok(page, 'xpath://input[@type="email"]', 1.5)
            )
        ):
            ok = _try_fill_then_click(
                page,
                ["@name=email", 'xpath://input[@type="email"]'],
                email,
                [
                    '//button[normalize-space()="Continuer"]',
                    '//button[normalize-space()="Continue"]',
                    '//button[contains(@class,"rt-") and normalize-space()="Continuer"]',
                    '//button[contains(@class,"rt-") and normalize-space()="Continue"]',
                ],
            )
            if ok:
                done_email = True
                _maybe_turnstile(page, config, translator)
            time.sleep(0.85)
            continue

        if (
            "authenticator.cursor" in u
            and "password" in ulo
            and not done_password
            and (
                _ele_ok(page, "@name=password", 2)
                or _ele_ok(page, 'xpath://input[@name="password"]', 1.5)
            )
        ):
            ok = _try_fill_then_click(
                page,
                ["@name=password", 'xpath://input[@name="password"]'],
                password,
                [
                    '//button[normalize-space()="Se connecter"]',
                    '//button[normalize-space()="Sign in"]',
                    '//button[contains(., "Se connecter")]',
                    '//button[contains(., "Sign in") and not(contains(., "Google"))]',
                ],
            )
            if ok:
                done_password = True
                _maybe_turnstile(page, config, translator)
            time.sleep(1.1)
            continue

        if ("logindeepcontrol" in ulo or "cursor.com" in ulo) and not done_yes:
            if _try_click_xpaths(
                page,
                [
                    '//button[contains(., "Yes, Log In")]',
                    '//button[contains(., "Yes, Log in")]',
                    '//button[contains(., "Log In") and contains(., "Yes")]',
                ],
                timeout_each=3.0,
            ):
                done_yes = True
                time.sleep(1.05)
                print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {success_done_message}{Style.RESET_ALL}")
                return True
            if "cursor.com" in ulo and (
                "/dashboard" in ulo or "tab=settings" in ulo or "/settings" in ulo
            ):
                try:
                    for c in page.cookies() or []:
                        if c.get("name") == "WorkosCursorSessionToken" and (c.get("value") or "").strip():
                            done_yes = True
                            time.sleep(0.55)
                            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {success_done_message}{Style.RESET_ALL}")
                            return True
                except Exception:
                    pass

        time.sleep(0.45)

    fail = translator.get("agent_cli.automate_timeout") if translator else "Timeout: could not complete all steps."
    print(f"{Fore.YELLOW}{EMOJI['INFO']} {fail}{Style.RESET_ALL}")
    return False


def _save_cursor_web_session_to_disk(
    page,
    email: str,
    password: str,
    translator,
    cursor_cached_auth_type: str = "google",
    update_existing_email: str = None,
) -> bool:
    """
    Lit le cookie ``WorkosCursorSessionToken`` sur cursor.com, met à jour la base Cursor
    et ajoute une entrée dans ``cursor_accounts.txt`` (même format que l’inscription manuelle).
    Réinitialise le machine ID puis écrit la session dans SQLite et storage.json (évite logout/login en boucle).

    ``cursor_cached_auth_type`` : ``google`` (OAuth web) ou ``Auth_0`` (e-mail + mot de passe, comme l’inscription manuelle).
    """
    from account_manager import AccountManager
    from cursor_acc_info import get_subscription_label_for_token, get_usage_summary_for_token
    from cursor_auth import apply_cursor_session
    from get_user_token import parse_workos_session_cookie

    settings_url = "https://www.cursor.com/dashboard?tab=settings"
    msg = (
        translator.get("agent_cli.saving_web_session")
        if translator
        else "Saving session token and account to cursor_accounts.txt…"
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")

    max_attempts = 18
    retry_interval = 1.15

    for attempt in range(max_attempts):
        try:
            if attempt > 0 or "cursor.com" not in (page.url or "").lower():
                page.get(settings_url)
                time.sleep(1.15)
        except Exception:
            time.sleep(retry_interval)
            continue

        try:
            if ("cursor.com" in (page.url or "").lower()) and (
                "start-download" in (page.url or "").lower()
                or "/settings" in (page.url or "").lower()
                or "dashboard?tab=settings" in (page.url or "").lower()
            ):
                _dismiss_setup_prompts(page, translator)
                time.sleep(0.9)
        except Exception:
            pass

        try:
            cookies = page.cookies()
        except Exception:
            cookies = []

        for cookie in cookies:
            if cookie.get("name") != "WorkosCursorSessionToken":
                continue
            raw = cookie.get("value") or ""
            if not raw.strip():
                break
            try:
                parsed = parse_workos_session_cookie(raw, translator, allow_cn_refresh=False)
                token = parsed["access_token"]
            except Exception as e:
                print(
                    f"{Fore.RED}{EMOJI['ERROR']} "
                    f"{translator.get('agent_cli.save_web_session_token_error', error=str(e)) if translator else str(e)}"
                    f"{Style.RESET_ALL}"
                )
                return False

            subscription = get_subscription_label_for_token(token)
            usage_info = get_usage_summary_for_token(token)

            try:
                if not apply_cursor_session(
                    translator=translator,
                    email=email.strip(),
                    access_token=token,
                    refresh_token=token,
                    auth_type=cursor_cached_auth_type,
                    oauth_refresh=True,
                    session_cookie=parsed.get("session_cookie"),
                ):
                    print(
                        f"{Fore.YELLOW}{EMOJI['INFO']} "
                        f"{translator.get('agent_cli.save_web_session_db_warn', error='apply_cursor_session failed') if translator else 'Cursor session apply failed'}"
                        f"{Style.RESET_ALL}"
                    )
                    return False
            except Exception as e:
                print(
                    f"{Fore.YELLOW}{EMOJI['INFO']} "
                    f"{translator.get('agent_cli.save_web_session_db_warn', error=str(e)) if translator else f'Cursor DB: {e}'}"
                    f"{Style.RESET_ALL}"
                )
                return False

            am = AccountManager(translator)
            if update_existing_email:
                if am.update_account_session_info(
                    update_existing_email.strip(),
                    token,
                    subscription=subscription,
                    usage_info=usage_info,
                ):
                    ok = (
                        translator.get("agent_cli.save_web_session_updated")
                        if translator
                        else "Token updated in existing cursor_accounts.txt entry."
                    )
                    print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {ok}{Style.RESET_ALL}")
                    return True
                return False
            if am.save_account_info(email.strip(), password, token, subscription, usage_info=usage_info):
                ok = (
                    translator.get("agent_cli.save_web_session_ok")
                    if translator
                    else "Token and account saved to cursor_accounts.txt."
                )
                print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {ok}{Style.RESET_ALL}")
                return True
            return False

        if attempt < max_attempts - 1:
            print(
                f"{Fore.YELLOW}{EMOJI['INFO']} "
                f"{translator.get('agent_cli.save_web_session_retry', attempt=attempt + 1, max=max_attempts) if translator else f'Waiting for session cookie (attempt {attempt + 1}/{max_attempts})…'}"
                f"{Style.RESET_ALL}"
            )
            time.sleep(retry_interval)

    fail = (
        translator.get("agent_cli.save_web_session_fail")
        if translator
        else "Could not read WorkosCursorSessionToken — open Cursor dashboard in the browser tab or retry."
    )
    print(f"{Fore.RED}{EMOJI['ERROR']} {fail}{Style.RESET_ALL}")
    return False


def automate_cursor_web_login_flow(
    email: str,
    password: str,
    translator=None,
    update_existing: bool = False,
    use_chrome_public_profile: bool = True,
) -> bool:
    """
    Connexion web : authenticator → **Google** → identifiants sur ``accounts.google.com`` → Cursor.
    Par défaut : profil Chrome public (logout session courante puis login du compte cible).
    """
    if use_chrome_public_profile:
        st = (
            translator.get("agent_cli.chrome_google_logout_login_start", email=email)
            if translator
            else f"Chrome profile: logout current Cursor session, then Google login as {email}…"
        )
        print(f"{Fore.CYAN}{EMOJI['INFO']} {st}{Style.RESET_ALL}")
        return _automate_cursor_chrome_public_logout_login(
            email,
            password,
            translator,
            update_existing=update_existing,
            google_oauth=True,
            cursor_cached_auth_type="Google",
        )

    page = None
    session_dir = ""
    try:
        page, config, session_dir = _chromium_page_cli_login(translator)
        st = (
            translator.get("agent_cli.cursor_web_login_start")
            if translator
            else "Opening Cursor web sign-in (DrissionPage)…"
        )
        print(f"{Fore.CYAN}{EMOJI['INFO']} {st}{Style.RESET_ALL}")
        _open_authenticator_for_web_password_login(page, translator)
        time.sleep(0.5)
        done_msg = (
            translator.get("agent_cli.cursor_web_done")
            if translator
            else "Web sign-in steps completed. Open the Cursor app if needed."
        )
        ok = _authenticator_login_via_google_oauth_after_page_load(
            page, config, email, password, translator, done_msg, deadline_seconds=240.0
        )
        if not ok:
            return False
        return _save_cursor_web_session_to_disk(
            page,
            email,
            password,
            translator,
            update_existing_email=email if update_existing else None,
        )
    except Exception as e:
        err = (
            translator.get("agent_cli.automate_failed", error=str(e))
            if translator
            else f"Automation error: {e}"
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {err}{Style.RESET_ALL}")
        return False
    finally:
        if page:
            try:
                page.quit()
            except Exception:
                pass
        if session_dir and os.path.isdir(session_dir):
            try:
                shutil.rmtree(session_dir, ignore_errors=True)
            except Exception:
                pass


def automate_cursor_web_email_password_login(
    email: str,
    password: str,
    translator=None,
    update_existing: bool = False,
    use_chrome_public_profile: bool = True,
) -> bool:
    """
    Connexion web e-mail + mot de passe Cursor.
    Par défaut : profil Chrome public (logout puis login du compte cible).
    """
    if use_chrome_public_profile:
        st = (
            translator.get("agent_cli.chrome_email_logout_login_start", email=email)
            if translator
            else f"Chrome profile: logout current Cursor session, then login as {email}…"
        )
        print(f"{Fore.CYAN}{EMOJI['INFO']} {st}{Style.RESET_ALL}")
        return _automate_cursor_chrome_public_logout_login(
            email,
            password,
            translator,
            update_existing=update_existing,
            google_oauth=False,
            cursor_cached_auth_type="Auth_0",
        )

    page = None
    session_dir = ""
    try:
        page, config, session_dir = _chromium_page_cli_login(translator)
        st = (
            translator.get("agent_cli.email_password_web_login_start")
            if translator
            else "Ouverture de la connexion Cursor (e-mail + mot de passe)…"
        )
        print(f"{Fore.CYAN}{EMOJI['INFO']} {st}{Style.RESET_ALL}")
        _open_authenticator_for_web_password_login(page, translator)
        time.sleep(0.5)
        done_msg = (
            translator.get("agent_cli.cursor_web_done")
            if translator
            else "Web sign-in steps completed. Open the Cursor app if needed."
        )
        ok = _authenticator_login_steps_after_page_load(
            page, config, email, password, translator, done_msg, deadline_seconds=240.0
        )
        if not ok:
            return False
        return _save_cursor_web_session_to_disk(
            page,
            email,
            password,
            translator,
            cursor_cached_auth_type="Auth_0",
            update_existing_email=email if update_existing else None,
        )
    except Exception as e:
        err = (
            translator.get("agent_cli.automate_failed", error=str(e))
            if translator
            else f"Automation error: {e}"
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {err}{Style.RESET_ALL}")
        return False
    finally:
        if page:
            try:
                page.quit()
            except Exception:
                pass
        if session_dir and os.path.isdir(session_dir):
            try:
                shutil.rmtree(session_dir, ignore_errors=True)
            except Exception:
                pass


def automate_cli_agent_login_flow(
    url: str,
    email: str,
    password: str,
    agent_proc: Optional[subprocess.Popen] = None,
    translator=None,
) -> bool:
    """
    Ouvre l’URL loginDeepControl dans Chromium (DrissionPage) avec la géométrie du **mode 2**
    (``get_cli_login_mode2_window_rect`` / ``[AgentCliLogin]``), puis enchaîne :
    « Continue to sign in » → e-mail + Continuer/Continue → mot de passe + Se connecter/Sign in
    → éventuel Turnstile → « Yes, Log In » (ou équivalent FR).
    """
    url = normalize_cli_login_url(url)
    if not url.startswith(("https://", "http://")):
        print(
            f"{Fore.RED}{EMOJI['ERROR']} "
            f"{translator.get('agent_cli.url_invalid') if translator else 'Invalid URL'}{Style.RESET_ALL}"
        )
        return False

    page = None
    session_dir = ""
    try:
        page, config, session_dir = _chromium_page_cli_login(translator)
        msg = translator.get("agent_cli.automate_start") if translator else "Starting automated CLI login flow…"
        print(f"{Fore.CYAN}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")

        page.get(url)
        time.sleep(2.0)

        done_msg = (
            translator.get("agent_cli.automate_done")
            if translator
            else "Steps completed. Check terminal `agent login` and close the browser when finished."
        )
        return _authenticator_login_steps_after_page_load(
            page, config, email, password, translator, done_msg, deadline_seconds=150.0
        )

    except Exception as e:
        err = (
            translator.get("agent_cli.automate_failed", error=str(e))
            if translator
            else f"Automation error: {e}"
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {err}{Style.RESET_ALL}")
        return False
    finally:
        if agent_proc and agent_proc.poll() is None:
            try:
                agent_proc.wait(timeout=8)
            except Exception:
                try:
                    agent_proc.terminate()
                except Exception:
                    pass
        if page:
            try:
                page.quit()
            except Exception:
                pass
        if session_dir and os.path.isdir(session_dir):
            try:
                shutil.rmtree(session_dir, ignore_errors=True)
            except Exception:
                pass


def _dedupe_google_accounts_last_wins(accounts: List[dict]) -> List[dict]:
    """Même e-mail dans plusieurs blocs : garder le dernier (ordre fichier)."""
    by_email: dict = {}
    for acc in accounts:
        em = (acc.get("email") or "").strip().lower()
        if em:
            by_email[em] = acc
    return list(by_email.values())


def run_google_saved_login(translator=None) -> None:
    """
    Liste les comptes @gmail.com / @googlemail.com dans cursor_accounts.txt,
    puis connexion web Cursor (authenticator sign-in, DrissionPage), sans ``agent login``.
    """
    try:
        from account_manager import AccountManager

        proj = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(proj, "cursor_accounts.txt")
        am = AccountManager(translator, accounts_file=path)
        accounts = _dedupe_google_accounts_last_wins(am.get_saved_google_accounts())
    except Exception:
        accounts = []

    if not accounts:
        msg = (
            translator.get("agent_cli.google_saved_none")
            if translator
            else "No @gmail.com / @googlemail.com accounts in cursor_accounts.txt."
        )
        print(f"{Fore.YELLOW}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")
        return

    title = (
        translator.get("agent_cli.google_saved_title")
        if translator
        else "Saved Google-address accounts (cursor_accounts.txt)"
    )
    print(f"\n{Fore.CYAN}{EMOJI['INFO']} {title}{Style.RESET_ALL}")

    def _parse_bool(v):
        if isinstance(v, bool):
            return v
        s = str(v or "").strip().lower()
        if s in ("true", "1", "yes", "y", "oui", "o"):
            return True
        if s in ("false", "0", "no", "n", "non"):
            return False
        return None

    def _quota_str(a: dict) -> str:
        ui = a.get("usage_info") or {}
        pu = ui.get("premium_usage")
        pl = ui.get("max_premium_usage")
        pr = ui.get("premium_limit_reached")
        reached = _parse_bool(pr)
        base = ""
        if pu is not None or pl is not None:
            base = f"premium {pu if pu is not None else '?'} / {pl if pl is not None else '?'}"
        else:
            base = "premium ? / ?"
        if reached is True:
            base += " — À ÉVITER"
        return base

    for idx, acc in enumerate(accounts, start=1):
        em = (acc.get("email") or "").strip()
        has_pw = bool((acc.get("password") or "").strip())
        quota = _quota_str(acc)
        sub = (acc.get("subscription") or "—").strip() or "—"
        if translator:
            flag = (
                translator.get("agent_cli.google_saved_has_pw")
                if has_pw
                else translator.get("agent_cli.google_saved_no_pw")
            )
        else:
            flag = "password saved" if has_pw else "no password in file"
        print(f"  {Fore.GREEN}{idx}{Style.RESET_ALL}. {em} ({flag}) | {sub} | {quota}")

    prompt = (
        translator.get("agent_cli.google_saved_pick", n=len(accounts))
        if translator
        else f"Account number (1-{len(accounts)}), 0 = cancel: "
    )
    choice = input(f"\n{Fore.CYAN}{prompt}{Style.RESET_ALL}").strip()
    if not choice.isdigit() or int(choice) == 0:
        print(
            f"{Fore.YELLOW}{EMOJI['INFO']} "
            f"{translator.get('menu.operation_cancelled_by_user') if translator else 'Cancelled.'}{Style.RESET_ALL}"
        )
        return
    num = int(choice)
    if not (1 <= num <= len(accounts)):
        bad = (
            translator.get("menu.invalid_choice", choices=f"1-{len(accounts)}")
            if translator
            else "Invalid choice."
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {bad}{Style.RESET_ALL}")
        return

    sel = accounts[num - 1]
    email = (sel.get("email") or "").strip()
    password = (sel.get("password") or "").strip()
    if not password:
        pp = (
            translator.get("agent_cli.google_saved_password_prompt", email=email)
            if translator
            else f"Password for {email} (not stored in file): "
        )
        password = input(f"{Fore.YELLOW}{pp}{Style.RESET_ALL}").strip()
    if not email or not password:
        miss = translator.get("agent_cli.google_saved_missing_creds") if translator else "Email and password required."
        print(f"{Fore.RED}{EMOJI['ERROR']} {miss}{Style.RESET_ALL}")
        return

    automate_cursor_web_login_flow(email, password, translator)


def _logout_cursor_current_session(page, translator=None) -> bool:
    """Déconnecte réellement Cursor web dans le profil Chrome (HttpOnly + WorkOS logout)."""
    msg = (
        translator.get("agent_cli.chrome_logout_start")
        if translator
        else "Logging out current Cursor web session (Chrome profile)…"
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")

    session_before = _read_workos_session_cookie(page)

    try:
        page.get("https://www.cursor.com/dashboard/settings")
        time.sleep(1.0)
    except Exception:
        pass
    try:
        _dismiss_setup_prompts(page, translator)
        time.sleep(0.35)
    except Exception:
        pass

    if not session_before:
        session_before = _read_workos_session_cookie(page)

    for xp in [
        '//button[contains(., "Log Out")]',
        '//a[contains(., "Log Out")]',
        '//button[contains(., "Logout")]',
        '//a[contains(., "Logout")]',
        '//button[contains(., "Se déconnecter")]',
        '//a[contains(., "Se déconnecter")]',
        '//button[contains(., "Déconnexion")]',
        '//a[contains(., "Déconnexion")]',
    ]:
        try:
            el = page.ele(f"xpath:{xp}", timeout=1.0)
            if not el:
                continue
            el.click()
            time.sleep(1.0)
            break
        except Exception:
            continue

    if session_before:
        _workos_logout_navigation(page, session_before, translator)

    removed = _delete_cursor_session_cookies_cdp(page)
    cdp_msg = (
        translator.get("agent_cli.chrome_cookies_cleared", count=removed)
        if translator
        else f"Cursor/WorkOS cookies cleared via CDP ({removed} delete calls)."
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {cdp_msg}{Style.RESET_ALL}")

    if not _verify_cursor_web_logged_out(page, translator):
        _delete_cursor_session_cookies_cdp(page)
        try:
            page.get("https://authenticator.cursor.sh/")
            time.sleep(0.8)
        except Exception:
            pass

    if _cursor_session_cookie_present(page):
        warn = (
            translator.get("agent_cli.chrome_logout_verify_failed")
            if translator
            else "Warning: WorkosCursorSessionToken still present after logout — check Chrome profile in config."
        )
        print(f"{Fore.YELLOW}{EMOJI['INFO']} {warn}{Style.RESET_ALL}")
        return False

    ok_msg = (
        translator.get("agent_cli.chrome_logout_done")
        if translator
        else "Cursor web logout verified (no session cookie in Chrome profile)."
    )
    print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {ok_msg}{Style.RESET_ALL}")
    return True


def chrome_profile_logout_cursor_session(translator=None) -> bool:
    """Ouvre le profil Chrome configuré et déconnecte la session Cursor web courante."""
    page = None
    real_ud = ""
    cdp_ud = ""
    profile_dir = ""
    try:
        page, _config, profile_dir, real_ud, cdp_ud = _chromium_page_chrome_public_current_profile(translator)
        return _logout_cursor_current_session(page, translator)
    except Exception as e:
        err = (
            translator.get("agent_cli.automate_failed", error=str(e))
            if translator
            else f"Chrome logout error: {e}"
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {err}{Style.RESET_ALL}")
        return False
    finally:
        if page:
            try:
                page.quit()
            except Exception:
                pass
            time.sleep(0.5)
        if real_ud and cdp_ud and profile_dir:
            _sync_chrome_cdp_back_to_real(real_ud, cdp_ud, profile_dir, translator)


def _automate_cursor_chrome_public_logout_login(
    email: str,
    password: str,
    translator=None,
    update_existing: bool = False,
    google_oauth: bool = False,
    cursor_cached_auth_type: str = None,
) -> bool:
    """
    Chrome public (profil loic5488@gmail.com ou config) : logout session Cursor courante,
    puis connexion du compte cible et écriture jeton + base locale.
    """
    page = None
    real_ud = ""
    cdp_ud = ""
    profile_dir = ""
    try:
        page, config, profile_dir, real_ud, cdp_ud = _chromium_page_chrome_public_current_profile(translator)
        if not _logout_cursor_current_session(page, translator):
            return False
        _open_authenticator_for_web_password_login(page, translator)
        time.sleep(0.45)
        done_msg = (
            translator.get("agent_cli.cursor_web_done")
            if translator
            else "Web sign-in flow finished."
        )
        if google_oauth:
            ok = _authenticator_login_via_google_oauth_after_page_load(
                page, config, email, password, translator, done_msg, deadline_seconds=240.0
            )
            auth_type = cursor_cached_auth_type or "google"
        else:
            ok = _authenticator_login_steps_after_page_load(
                page, config, email, password, translator, done_msg, deadline_seconds=240.0
            )
            auth_type = cursor_cached_auth_type or "Auth_0"
        if not ok:
            return False
        return _save_cursor_web_session_to_disk(
            page,
            email,
            password,
            translator,
            cursor_cached_auth_type=auth_type,
            update_existing_email=email if update_existing else None,
        )
    except Exception as e:
        err = (
            translator.get("agent_cli.automate_failed", error=str(e))
            if translator
            else f"Automation error: {e}"
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {err}{Style.RESET_ALL}")
        return False
    finally:
        if page:
            try:
                page.quit()
            except Exception:
                pass
            time.sleep(0.5)
        if real_ud and cdp_ud and profile_dir:
            _sync_chrome_cdp_back_to_real(real_ud, cdp_ud, profile_dir, translator)


def run_logout_then_login_latest_saved(translator=None) -> None:
    """
    Chrome public (profil courant): déconnecte la session Cursor web courante, puis reconnecte
    automatiquement avec le dernier compte (email+mot de passe) de cursor_accounts.txt.
    """
    saved = load_last_saved_login_credentials(translator)
    if not saved:
        msg = (
            translator.get("agent_cli.no_saved_credentials")
            if translator
            else "No email + password saved in cursor_accounts.txt."
        )
        print(f"{Fore.YELLOW}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")
        return

    email, password = saved
    msg = (
        translator.get("agent_cli.logout_then_login_latest_start", email=email)
        if translator
        else f"Public Chrome flow: logout current Cursor session, then login with latest saved account {email}."
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")
    automate_cursor_web_email_password_login(
        email,
        password,
        translator,
        update_existing=False,
        use_chrome_public_profile=True,
    )


def run(translator=None, email: Optional[str] = None, password: Optional[str] = None):
    """
    Menu option 16 : lance `agent login` (NO_OPEN_BROWSER=1), récupère l'URL,
    puis exécute le flux DrissionPage (fenêtre mode 2 + clics).

    Si ``email`` et ``password`` sont fournis, ils priment sur le
    dernier compte dans cursor_accounts.txt et sur les invites.
    """
    launching = (
        translator.get("agent_cli.launching_agent_login")
        if translator
        else "Starting `agent login` (NO_OPEN_BROWSER=1) to retrieve URL..."
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {launching}{Style.RESET_ALL}")

    agent_proc, raw, log_path, log_fp = launch_agent_login_and_get_url(translator)
    if not agent_proc:
        err = (
            translator.get("agent_cli.agent_not_found")
            if translator
            else "agent executable not found."
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {err}{Style.RESET_ALL}")
        return

    if raw:
        msg = (
            translator.get("agent_cli.url_captured")
            if translator
            else "Login URL captured from agent output."
        )
        print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {msg}{Style.RESET_ALL}")
    else:
        warn = (
            translator.get("agent_cli.url_capture_failed")
            if translator
            else "Could not auto-capture URL. Paste it manually."
        )
        print(f"{Fore.YELLOW}{EMOJI['INFO']} {warn}{Style.RESET_ALL}")
        prompt = translator.get("agent_cli.prompt_url") if translator else "Paste login URL (one line): "
        raw = input(f"\n{Fore.YELLOW}{prompt}{Style.RESET_ALL}").strip()
        if not raw:
            try:
                if agent_proc.poll() is None:
                    agent_proc.terminate()
            except Exception:
                pass
            if log_fp:
                try:
                    log_fp.close()
                except Exception:
                    pass
            if log_path and os.path.isfile(log_path):
                try:
                    os.remove(log_path)
                except Exception:
                    pass
            print(
                f"{Fore.YELLOW}{EMOJI['INFO']} "
                f"{translator.get('menu.operation_cancelled_by_user') if translator else 'Cancelled.'}{Style.RESET_ALL}"
            )
            return

    forced_email = (email or "").strip()
    forced_password = (password or "").strip()
    saved = None
    if not (forced_email and forced_password):
        saved = load_last_saved_login_credentials(translator)
    use_email = forced_email
    use_password = forced_password
    if not use_email or not use_password:
        if saved:
            use_email, use_password = saved
            msg = (
                translator.get("agent_cli.using_saved_account", email=use_email)
                if translator
                else f"Using saved account: {use_email}"
            )
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {msg}{Style.RESET_ALL}")

    em_def = DEFAULT_CLI_LOGIN_EMAIL
    pw_def = DEFAULT_CLI_LOGIN_PASSWORD
    if not use_email or not use_password:
        if not saved:
            nw = (
                translator.get("agent_cli.no_saved_credentials")
                if translator
                else "No credentials in cursor_accounts.txt — enter them below."
            )
            print(f"{Fore.YELLOW}{EMOJI['INFO']} {nw}{Style.RESET_ALL}")
        if translator:
            ep = translator.get("agent_cli.email_prompt", default=em_def)
            pp = translator.get("agent_cli.password_prompt", default=pw_def)
        else:
            ep = f"Email (Enter = {em_def}): "
            pp = f"Password (Enter = {pw_def}): "
        use_email = input(f"\n{Fore.YELLOW}{ep}{Style.RESET_ALL}").strip() or em_def
        use_password = input(f"{Fore.YELLOW}{pp}{Style.RESET_ALL}").strip() or pw_def

    try:
        automate_cli_agent_login_flow(raw, use_email, use_password, agent_proc=agent_proc, translator=translator)
    finally:
        if log_fp:
            try:
                log_fp.close()
            except Exception:
                pass
        if log_path and os.path.isfile(log_path):
            try:
                os.remove(log_path)
            except Exception:
                pass
