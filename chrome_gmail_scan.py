# Détection des adresses @gmail / @googlemail dans les données Chrome (Preferences, Secure Preferences).
import os
import re
import sys
from typing import Dict, List, Optional, Set

GMAIL_RE = re.compile(
    r"[a-zA-Z0-9][a-zA-Z0-9._%+-]*@(?:gmail\.com|googlemail\.com)\b",
    re.IGNORECASE,
)


def _profile_display_names(user_data_dir: str) -> Dict[str, str]:
    """Lit info_cache (Local State) pour libellés Default / Profile N."""
    out: Dict[str, str] = {}
    path = os.path.join(user_data_dir, "Local State")
    if not os.path.isfile(path):
        return out
    try:
        import json

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            state = json.load(f)
        cache = state.get("profile", {}).get("info_cache", {}) or {}
        for profile_dir, info in cache.items():
            key = profile_dir.replace("\\", "/")
            if key == "Default" or key.startswith("Profile "):
                name = (info or {}).get("name") or key
                if key.lower() == "default":
                    name = f"{name} (Default)"
                out[key] = name
    except Exception:
        pass
    return out


def _iter_chrome_profile_dirs(user_data_dir: str) -> List[str]:
    if not user_data_dir or not os.path.isdir(user_data_dir):
        return []
    names = []
    try:
        for name in os.listdir(user_data_dir):
            if name == "Default":
                p = os.path.join(user_data_dir, name)
                if os.path.isdir(p):
                    names.append(name)
            elif name.startswith("Profile ") and os.path.isdir(os.path.join(user_data_dir, name)):
                names.append(name)
    except OSError:
        return []
    def sort_key(n: str) -> tuple:
        if n == "Default":
            return (0, n)
        try:
            return (1, int(n.replace("Profile ", "").strip() or "0"))
        except ValueError:
            return (2, n)

    return sorted(names, key=sort_key)


def _emails_in_json_file(path: str) -> Set[str]:
    if not os.path.isfile(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        return {m.group(0).lower() for m in GMAIL_RE.finditer(raw)}
    except OSError:
        return set()


def scan_chrome_user_data_for_gmail(user_data_dir: str) -> List[dict]:
    """
    Pour chaque profil Chrome, extrait les @gmail.com / @googlemail.com trouvés
    dans Preferences et Secure Preferences (chaînes JSON brutes).
    Retourne une liste de {email, profile_dir, profile_label}.
    """
    labels = _profile_display_names(user_data_dir)
    rows: List[dict] = []
    seen: Set[tuple] = set()
    for profile_dir in _iter_chrome_profile_dirs(user_data_dir):
        base = os.path.join(user_data_dir, profile_dir)
        emails: Set[str] = set()
        emails |= _emails_in_json_file(os.path.join(base, "Preferences"))
        emails |= _emails_in_json_file(os.path.join(base, "Secure Preferences"))
        label = labels.get(profile_dir, profile_dir)
        for em in sorted(emails):
            key = (em, profile_dir)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "email": em,
                    "profile_dir": profile_dir,
                    "profile_label": label,
                }
            )
    return rows


def _read_profile_account_email(user_data_dir: str, profile_dir: str) -> Optional[str]:
    """E-mail principal du profil Chrome (champ account_info dans Preferences)."""
    pref_path = os.path.join(user_data_dir, profile_dir, "Preferences")
    if not os.path.isfile(pref_path):
        return None
    try:
        import json

        with open(pref_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        for acc in data.get("account_info") or []:
            em = (acc.get("email") or "").strip().lower()
            if em and "@" in em:
                return em
        name = (data.get("profile") or {}).get("name") or ""
        if "@" in name:
            return name.strip().lower()
    except Exception:
        pass
    return None


def find_chrome_profile_for_email(user_data_dir: str, email: str) -> Optional[dict]:
    """
    Trouve le profil Chrome dont account_info correspond à l'e-mail (méthode fiable).
    Retourne {profile_dir, profile_label, account_email} ou None.
    """
    if not user_data_dir or not os.path.isdir(user_data_dir):
        return None
    target = (email or "").strip().lower()
    if not target or "@" not in target:
        return None

    labels = _profile_display_names(user_data_dir)
    for profile_dir in _iter_chrome_profile_dirs(user_data_dir):
        account_email = _read_profile_account_email(user_data_dir, profile_dir)
        if account_email == target:
            return {
                "profile_dir": profile_dir,
                "profile_label": labels.get(profile_dir, profile_dir),
                "account_email": account_email,
            }

    # Repli : scan regex (historique Gmail dans Preferences)
    for row in scan_chrome_user_data_for_gmail(user_data_dir):
        if (row.get("email") or "").strip().lower() == target:
            pd = (row.get("profile_dir") or "").strip()
            if pd:
                return {
                    "profile_dir": pd,
                    "profile_label": row.get("profile_label") or pd,
                    "account_email": target,
                }
    return None


def get_browser_user_data_dir(translator=None, browser_type: Optional[str] = None) -> Optional[str]:
    """Même logique de répertoire User Data que OAuthHandler (Chrome / Edge / Brave)."""
    from config import get_config

    cfg = get_config(translator)
    bt = (browser_type or cfg.get("Browser", "default_browser", fallback="chrome") or "chrome").strip().lower()
    if os.name == "nt":
        dirs = {
            "chrome": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data"),
            "brave": os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "User Data"),
            "edge": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data"),
        }
    elif sys.platform == "darwin":
        dirs = {
            "chrome": os.path.expanduser("~/Library/Application Support/Google/Chrome"),
            "brave": os.path.expanduser("~/Library/Application Support/BraveSoftware/Brave-Browser"),
            "edge": os.path.expanduser("~/Library/Application Support/Microsoft Edge"),
        }
    else:
        dirs = {
            "chrome": os.path.expanduser("~/.config/google-chrome"),
            "brave": os.path.expanduser("~/.config/BraveSoftware/Brave-Browser"),
            "edge": os.path.expanduser("~/.config/microsoft-edge"),
        }
    path = dirs.get(bt) or dirs.get("chrome")
    if path and os.path.isdir(path):
        return path
    chrome = dirs.get("chrome")
    if chrome and os.path.isdir(chrome):
        return chrome
    return None
