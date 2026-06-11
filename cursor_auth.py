import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

from colorama import Fore, Style, init
from config import get_config

# Initialize colorama
init()

# Define emoji and color constants
EMOJI = {
    "DB": "🗄️",
    "UPDATE": "🔄",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARN": "⚠️",
    "INFO": "ℹ️",
    "FILE": "📄",
    "KEY": "🔐",
}

AUTH_STORAGE_KEYS = (
    "cursorAuth/cachedSignUpType",
    "cursorAuth/cachedEmail",
    "cursorAuth/accessToken",
    "cursorAuth/refreshToken",
)


def _cursor_paths_from_config(config):
    """Retourne (sqlite_path, storage_json_path) pour la plateforme courante."""
    if sys.platform == "win32":
        section = "WindowsPaths"
    elif sys.platform == "darwin":
        section = "MacPaths"
    elif sys.platform == "linux":
        section = "LinuxPaths"
    else:
        raise ValueError(f"Unsupported platform: {sys.platform}")
    if not config.has_section(section):
        raise ValueError(f"{section} not configured")
    return (
        config.get(section, "sqlite_path"),
        config.get(section, "storage_path"),
    )


def _normalize_auth_type(auth_type: str) -> str:
    mapping = {
        "google": "Google",
        "github": "GitHub",
        "auth_0": "Auth_0",
    }
    key = (auth_type or "Auth_0").strip()
    return mapping.get(key.lower(), key)


def _reset_machine_id_enabled(translator=None, explicit: bool = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    cfg = get_config(translator)
    if not cfg or not cfg.has_section("Auth"):
        return False
    return cfg.get("Auth", "reset_machine_id_on_session", fallback="false").strip().lower() in (
        "true",
        "1",
        "yes",
        "on",
    )


def apply_cursor_session(
    translator=None,
    email=None,
    access_token=None,
    refresh_token=None,
    auth_type="Auth_0",
    reset_machine_ids=None,
    oauth_refresh=None,
    strict_oauth: bool = False,
    session_result: dict = None,
    session_cookie: str = None,
):
    """
    Écrit une session Cursor valide pour l’IDE :
    - JWT uniquement dans accessToken / refreshToken (jamais le cookie WorkOS brut)
    - validation OAuth api2.cursor.sh avant écriture
    - sync storage.json + state.vscdb
    - pas de reset machine ID par défaut (sinon « log out and back in » côté API)
    """
    from get_user_token import prepare_tokens_for_storage

    prepared = prepare_tokens_for_storage(
        access_token,
        refresh_token,
        translator=translator,
        oauth_refresh=oauth_refresh,
        strict=strict_oauth,
        session_cookie=session_cookie,
    )
    if prepared.get("should_logout") or not prepared.get("ok"):
        if prepared.get("error") == "reuse_token_expired":
            msg = (
                translator.get("auth.reuse_token_expired")
                if translator
                else "Saved account token is expired. Reconnect this account in the browser, then update cursor_accounts.txt."
            )
        else:
            msg = (
                translator.get("auth.session_invalid_logout")
                if translator
                else "Session invalid for Cursor IDE — log in again in the browser and rerun the script (do not reset machine ID here)."
            )
        print(f"{Fore.RED}{EMOJI['ERROR']} {msg}{Style.RESET_ALL}")
        if session_result is not None:
            session_result.clear()
            session_result.update(
                {
                    "ok": False,
                    "error": prepared.get("error") or "invalid_token",
                    "email": email,
                }
            )
        return False

    access = prepared["access_token"]
    refresh = prepared["refresh_token"]
    auth_type = _normalize_auth_type(auth_type)

    if _reset_machine_id_enabled(translator, reset_machine_ids):
        from reset_machine_manual import MachineIDResetter

        print(
            f"{Fore.CYAN}{EMOJI['UPDATE']} "
            f"{translator.get('auth.reset_before_session') if translator else 'Resetting machine ID before writing session…'}"
            f"{Style.RESET_ALL}"
        )
        if not MachineIDResetter(translator).reset_machine_ids():
            print(
                f"{Fore.YELLOW}{EMOJI['WARN']} "
                f"{translator.get('auth.reset_before_session_failed') if translator else 'Machine ID reset failed; continuing with auth update anyway.'}"
                f"{Style.RESET_ALL}"
            )

    if session_result is not None:
        session_result.clear()
        session_result.update(
            {
                "ok": True,
                "access_token": access,
                "refresh_token": refresh,
                "email": email,
            }
        )

    auth = CursorAuth(translator)
    return auth.update_auth(
        email=email,
        access_token=access,
        refresh_token=refresh,
        auth_type=auth_type,
    )


class CursorAuth:
    def __init__(self, translator=None):
        self.translator = translator
        self.db_path = None
        self.storage_path = None
        self.conn = None

        config = get_config(translator)
        if not config:
            print(
                f"{Fore.RED}{EMOJI['ERROR']} "
                f"{self.translator.get('auth.config_error') if self.translator else 'Failed to load configuration'}"
                f"{Style.RESET_ALL}"
            )
            sys.exit(1)

        try:
            self.db_path, self.storage_path = _cursor_paths_from_config(config)
            if not os.path.exists(os.path.dirname(self.db_path)):
                raise FileNotFoundError(
                    f"Database directory not found: {os.path.dirname(self.db_path)}"
                )
        except Exception as e:
            print(
                f"{Fore.RED}{EMOJI['ERROR']} "
                f"{self.translator.get('auth.path_error', error=str(e)) if self.translator else f'Error getting database path: {str(e)}'}"
                f"{Style.RESET_ALL}"
            )
            sys.exit(1)

        if not os.path.exists(self.db_path):
            print(
                f"{Fore.RED}{EMOJI['ERROR']} "
                f"{self.translator.get('auth.db_not_found', path=self.db_path) if self.translator else f'Database not found: {self.db_path}'}"
                f"{Style.RESET_ALL}"
            )
            return

        if not os.access(self.db_path, os.R_OK | os.W_OK):
            print(
                f"{Fore.RED}{EMOJI['ERROR']} "
                f"{self.translator.get('auth.db_permission_error') if self.translator else 'Database permission error'}"
                f"{Style.RESET_ALL}"
            )
            return

        # Connexion SQLite uniquement dans update_auth (évite le double message « Connected to Database »).

    def _sync_storage_json(self, updates):
        """Miroir des clés cursorAuth/* dans storage.json (lu par l’IDE au démarrage)."""
        path = self.storage_path
        if not path:
            return False
        try:
            storage_dir = os.path.dirname(path)
            if storage_dir and not os.path.exists(storage_dir):
                os.makedirs(storage_dir, exist_ok=True)

            data = {}
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    data = {}

            for key, value in updates:
                data[key] = value

            if os.path.exists(path):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup = f"{path}.auth_bak.{ts}"
                try:
                    shutil.copy2(path, backup)
                except Exception:
                    pass

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

            print(
                f"{EMOJI['SUCCESS']} {Fore.GREEN}"
                f"{self.translator.get('auth.storage_json_synced') if self.translator else 'storage.json synced with session (email + tokens).'}"
                f"{Style.RESET_ALL}"
            )
            return True
        except Exception as e:
            print(
                f"{EMOJI['WARN']} {Fore.YELLOW}"
                f"{self.translator.get('auth.storage_json_sync_failed', error=str(e)) if self.translator else f'Could not sync storage.json: {e}'}"
                f"{Style.RESET_ALL}"
            )
            return False

    def update_auth(self, email=None, access_token=None, refresh_token=None, auth_type="Auth_0"):
        conn = None
        try:
            if email is not None:
                email = str(email).strip()

            db_dir = os.path.dirname(self.db_path)
            if not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            if not os.path.exists(self.db_path):
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ItemTable (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """
                )
                conn.commit()
                if sys.platform != "win32":
                    os.chmod(self.db_path, 0o644)
                conn.close()

            conn = sqlite3.connect(self.db_path)
            print(
                f"{EMOJI['INFO']} {Fore.GREEN} "
                f"{self.translator.get('auth.connected_to_database') if self.translator else 'Connected to database'}"
                f"{Style.RESET_ALL}"
            )
            cursor = conn.cursor()

            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")

            updates = [("cursorAuth/cachedSignUpType", auth_type)]

            if email is not None:
                updates.append(("cursorAuth/cachedEmail", email))
            if access_token is not None:
                updates.append(("cursorAuth/accessToken", access_token))
            if refresh_token is not None:
                updates.append(("cursorAuth/refreshToken", refresh_token))

            if access_token is not None:
                try:
                    from cursor_acc_info import UsageManager

                    profile = UsageManager.get_stripe_profile(access_token)
                    if isinstance(profile, dict):
                        if profile.get("membershipType"):
                            updates.append(
                                ("cursorAuth/stripeMembershipType", str(profile["membershipType"]))
                            )
                        if profile.get("subscriptionStatus"):
                            updates.append(
                                (
                                    "cursorAuth/stripeSubscriptionStatus",
                                    str(profile["subscriptionStatus"]),
                                )
                            )
                except Exception:
                    pass

            cursor.execute("BEGIN TRANSACTION")
            try:
                for key, value in updates:
                    cursor.execute("SELECT COUNT(*) FROM ItemTable WHERE key = ?", (key,))
                    if cursor.fetchone()[0] == 0:
                        cursor.execute(
                            "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
                            (key, value),
                        )
                    else:
                        cursor.execute(
                            "UPDATE ItemTable SET value = ? WHERE key = ?",
                            (value, key),
                        )
                    short = key.split("/")[-1]
                    print(
                        f"{EMOJI['INFO']} {Fore.CYAN} "
                        f"{self.translator.get('auth.updating_pair') if self.translator else 'Updating key-value pair:'} {short}…"
                        f"{Style.RESET_ALL}"
                    )

                cursor.execute("COMMIT")
            except Exception:
                cursor.execute("ROLLBACK")
                raise

            storage_ok = self._sync_storage_json(updates)
            if storage_ok:
                print(
                    f"{EMOJI['SUCCESS']} {Fore.GREEN}"
                    f"{self.translator.get('auth.database_updated_successfully') if self.translator else 'Database updated successfully'}"
                    f"{Style.RESET_ALL}"
                )
            else:
                print(
                    f"{EMOJI['WARN']} {Fore.YELLOW}"
                    f"{self.translator.get('auth.database_updated_sqlite_only') if self.translator else 'SQLite updated but storage.json sync failed — close Cursor and retry, or login may loop.'}"
                    f"{Style.RESET_ALL}"
                )
            return True

        except sqlite3.Error as e:
            print(
                f"\n{EMOJI['ERROR']} {Fore.RED} "
                f"{self.translator.get('auth.database_error', error=str(e)) if self.translator else f'Database error: {str(e)}'}"
                f"{Style.RESET_ALL}"
            )
            return False
        except Exception as e:
            print(
                f"\n{EMOJI['ERROR']} {Fore.RED} "
                f"{self.translator.get('auth.an_error_occurred', error=str(e)) if self.translator else f'An error occurred: {str(e)}'}"
                f"{Style.RESET_ALL}"
            )
            return False
        finally:
            if conn:
                conn.close()
                print(
                    f"{EMOJI['DB']} {Fore.CYAN} "
                    f"{self.translator.get('auth.database_connection_closed') if self.translator else 'Database connection closed'}"
                    f"{Style.RESET_ALL}"
                )
