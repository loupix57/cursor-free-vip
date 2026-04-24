# agent_cli_helper.py — Option 16 : `agent login` + DrissionPage. Option 17 : connexion web Cursor (/sign-in), sans agent.
# et optionnellement automatiser le flux (fenêtre réduite, clics, saisie e-mail / mot de passe).
import os
import re
import sys
import time
import uuid
import shutil
import tempfile
import subprocess
import platform
from typing import List, Optional, Sequence, Tuple

from colorama import Fore, Style

EMOJI = {"INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌"}

DEFAULT_CLI_LOGIN_EMAIL = "continuer"
DEFAULT_CLI_LOGIN_PASSWORD = "connecter"

# Connexion web Cursor (e-mail / mot de passe), sans `agent login`
CURSOR_WEB_SIGN_IN = "https://authenticator.cursor.sh/sign-in"

# Défauts mode 2 si [AgentCliLogin] absent du config.ini (voir aussi config.py)
_MODE2_DEFAULT_W, _MODE2_DEFAULT_H = 680, 480
_MODE2_DEFAULT_X, _MODE2_DEFAULT_Y = 100, 72


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
    time.sleep(2.0)
    return page, config, session_dir


def _try_click_xpaths(page, xpaths: Sequence[str], timeout_each: float = 4.0) -> bool:
    for xp in xpaths:
        try:
            el = page.ele(f"xpath:{xp}", timeout=timeout_each)
            if el:
                el.click()
                time.sleep(1.2)
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
    time.sleep(0.6)
    return _try_click_xpaths(page, button_xpaths, timeout_each=5.0)


def _maybe_turnstile(page, config, translator) -> None:
    try:
        from new_signup import handle_turnstile

        handle_turnstile(page, config, translator)
    except Exception:
        time.sleep(1.5)


def _ele_ok(page, selector: str, timeout: float = 1.5) -> bool:
    try:
        return bool(page.ele(selector, timeout=timeout))
    except Exception:
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
    """Après ``page.get`` sur loginDeepControl ou /sign-in : e-mail, mot de passe, « Yes, Log In »."""
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
        timeout_each=3.0,
    )
    time.sleep(1.5)

    deadline = time.time() + deadline_seconds
    while time.time() < deadline and not done_yes:
        u = ""
        try:
            u = page.url or ""
        except Exception:
            pass

        if (
            "authenticator.cursor" in u
            and "/password" not in u
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
            time.sleep(1.5)
            continue

        if (
            "authenticator.cursor" in u
            and "password" in u
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
            time.sleep(2.0)
            continue

        if ("loginDeepControl" in u or "cursor.com" in u) and not done_yes:
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
                time.sleep(2.0)
                print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {success_done_message}{Style.RESET_ALL}")
                return True

        time.sleep(0.7)

    fail = translator.get("agent_cli.automate_timeout") if translator else "Timeout: could not complete all steps."
    print(f"{Fore.YELLOW}{EMOJI['INFO']} {fail}{Style.RESET_ALL}")
    return False


def automate_cursor_web_login_flow(email: str, password: str, translator=None) -> bool:
    """
    Connexion Cursor sur le web (authenticator / sign-in), e-mail + mot de passe,
    sans ``agent login`` ni URL loginDeepControl.
    """
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
        page.get(CURSOR_WEB_SIGN_IN)
        time.sleep(2.0)
        done_msg = (
            translator.get("agent_cli.cursor_web_done")
            if translator
            else "Web sign-in steps completed. Open the Cursor app if needed."
        )
        return _authenticator_login_steps_after_page_load(
            page, config, email, password, translator, done_msg, deadline_seconds=180.0
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
    for idx, acc in enumerate(accounts, start=1):
        em = (acc.get("email") or "").strip()
        has_pw = bool((acc.get("password") or "").strip())
        if translator:
            flag = (
                translator.get("agent_cli.google_saved_has_pw")
                if has_pw
                else translator.get("agent_cli.google_saved_no_pw")
            )
        else:
            flag = "password saved" if has_pw else "no password in file"
        print(f"  {Fore.GREEN}{idx}{Style.RESET_ALL}. {em} ({flag})")

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
