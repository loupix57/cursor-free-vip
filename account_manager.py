import os
import configparser
import shutil
import time
from colorama import Fore, Style
import re
from datetime import datetime, timedelta
from collections import Counter

from utils import get_user_documents_path


def resolve_accounts_file_path(translator=None) -> str:
    """
    Résout le chemin de cursor_accounts.txt.
    Priorité : [Account].accounts_file dans config.ini → fichier projet → Documents/.cursor-free-vip/.
    """
    project_root = os.path.dirname(os.path.abspath(__file__))
    project_file = os.path.join(project_root, "cursor_accounts.txt")
    shared_file = os.path.join(get_user_documents_path(), ".cursor-free-vip", "cursor_accounts.txt")

    try:
        from config import get_config

        cfg = get_config(translator)
        if cfg and cfg.has_section("Account"):
            custom = (cfg.get("Account", "accounts_file", fallback="") or "").strip()
            if custom:
                return os.path.normpath(os.path.expanduser(os.path.expandvars(custom)))
    except Exception:
        pass

    if os.path.exists(project_file):
        return project_file
    if os.path.exists(shared_file):
        return shared_file
    return shared_file


def save_accounts_file_config(path: str, translator=None) -> bool:
    """Enregistre [Account].accounts_file dans config.ini."""
    try:
        from config import get_config

        config = get_config(translator)
        if not config:
            return False
        if not config.has_section("Account"):
            config.add_section("Account")
        config.set("Account", "accounts_file", (path or "").strip())

        config_dir = os.path.join(get_user_documents_path(), ".cursor-free-vip")
        os.makedirs(config_dir, exist_ok=True)
        config_file = os.path.join(config_dir, "config.ini")
        with open(config_file, "w", encoding="utf-8") as f:
            config.write(f)
        return True
    except Exception:
        return False


def backup_accounts_file(accounts_file: str, translator=None) -> str:
    """Sauvegarde cursor_accounts.txt avant opération risquée."""
    if not accounts_file or not os.path.isfile(accounts_file):
        return ""
    backup_dir = os.path.join(get_user_documents_path(), ".cursor-free-vip", "backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"cursor_accounts_{stamp}.txt")
    shutil.copy2(accounts_file, backup_path)
    msg = (
        translator.get("account.backup_created", path=backup_path)
        if translator
        else f"Sauvegarde comptes : {backup_path}"
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")
    return backup_path


def acquire_accounts_file_lock(accounts_file: str, translator=None, stale_hours: float = 2.0) -> bool:
    """Verrou léger pour éviter édition simultanée multi-PC."""
    if not accounts_file:
        return True
    lock_path = accounts_file + ".lock"
    try:
        if os.path.isfile(lock_path):
            age_h = (time.time() - os.path.getmtime(lock_path)) / 3600.0
            if age_h < stale_hours:
                warn = (
                    translator.get("account.file_locked", path=lock_path)
                    if translator
                    else f"Fichier comptes peut-être utilisé sur un autre PC ({lock_path})."
                )
                print(f"{Fore.YELLOW}{EMOJI['INFO']} {warn}{Style.RESET_ALL}")
                return False
        with open(lock_path, "w", encoding="utf-8") as f:
            f.write(f"pid={os.getpid()}\nstarted={datetime.now().isoformat(timespec='seconds')}\n")
        return True
    except OSError:
        return True


def release_accounts_file_lock(accounts_file: str) -> None:
    if not accounts_file:
        return
    lock_path = accounts_file + ".lock"
    try:
        if os.path.isfile(lock_path):
            os.remove(lock_path)
    except OSError:
        pass


# Define emoji constants
EMOJI = {
    'SUCCESS': '✅',
    'ERROR': '❌',
    'INFO': 'ℹ️'
}

class AccountManager:
    _GOOGLE_EMAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})
    _BLOCK_SEP = "=" * 50

    def __init__(self, translator=None, accounts_file=None):
        self.translator = translator
        self.accounts_file = accounts_file or resolve_accounts_file_path(translator)
        self.domain_file = 'cursor_domain.txt'

    def _ensure_accounts_parent_dir(self) -> None:
        parent = os.path.dirname(os.path.abspath(self.accounts_file))
        if parent:
            os.makedirs(parent, exist_ok=True)
    
    def save_account_info(self, email, password, token, subscription, usage_info=None):
        """Enregistre le compte dans cursor_accounts.txt (abonnement via API + usage/limites via API)."""
        try:
            sub = (subscription or "").strip() or "Unknown"
            self._ensure_accounts_parent_dir()
            backup_accounts_file(self.accounts_file, self.translator)
            with open(self.accounts_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*50}\n")
                f.write(f"Created At: {datetime.now().isoformat(timespec='seconds')}\n")
                f.write(f"Email: {email}\n")
                f.write(f"Password: {password}\n")
                f.write(f"Token: {token}\n")
                f.write(f"Subscription: {sub}\n")
                try:
                    ui = usage_info or {}
                    pu = ui.get("premium_usage")
                    ml = ui.get("max_premium_usage")
                    bu = ui.get("basic_usage")
                    bl = ui.get("max_basic_usage")
                    reached = ui.get("premium_limit_reached")
                    if pu is not None:
                        f.write(f"Premium Usage: {pu}\n")
                    if ml is not None:
                        f.write(f"Premium Limit: {ml}\n")
                    if bu is not None:
                        f.write(f"Basic Usage: {bu}\n")
                    if bl is not None:
                        f.write(f"Basic Limit: {bl}\n")
                    if reached is not None:
                        f.write(f"Premium Limit Reached: {str(bool(reached))}\n")
                except Exception:
                    pass
                f.write(f"{'='*50}\n")
                
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('register.account_info_saved') if self.translator else 'Account information saved'}...{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            error_msg = self.translator.get('register.save_account_info_failed', error=str(e)) if self.translator else f'Failed to save account information: {str(e)}'
            print(f"{Fore.RED}{EMOJI['ERROR']} {error_msg}{Style.RESET_ALL}")
            return False
    
    def get_last_email_domain(self):
        """Get the domain from the last used email"""
        try:
            preferred_domain = self.get_preferred_domain()
            if preferred_domain:
                return preferred_domain

            if not os.path.exists(self.accounts_file):
                return None
            
            # Only read the last 1KB of data from the file
            with open(self.accounts_file, 'rb') as f:
                # Get file size
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                
                if file_size == 0:
                    return None
                
                # Determine the number of bytes to read, maximum 1KB
                read_size = min(1024, file_size)
                
                # Move to the appropriate position to start reading
                f.seek(file_size - read_size)
                
                # Read the end data
                data = f.read(read_size).decode('utf-8', errors='ignore')
            
            # Split by lines and search in reverse
            lines = data.split('\n')
            for line in reversed(lines):
                if line.strip().startswith('Email:'):
                    email = line.split('Email:')[1].strip()
                    # Extract domain part (after @)
                    if '@' in email:
                        return email.split('@')[1]
                    return None
            
            # If no email is found in the last 1KB
            return None
        except Exception as e:
            error_msg = self.translator.get('account.get_last_email_domain_failed', error=str(e)) if self.translator else f'Failed to get the last used email domain: {str(e)}'
            print(f"{Fore.RED}{EMOJI['ERROR']} {error_msg}{Style.RESET_ALL}")
            return None

    def get_preferred_domain(self):
        """Get preferred domain from dedicated file."""
        try:
            if not os.path.exists(self.domain_file):
                return None
            with open(self.domain_file, 'r', encoding='utf-8') as f:
                domain = f.read().strip().lower()
            if domain and re.fullmatch(r"[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", domain):
                return domain
            return None
        except Exception:
            return None

    def set_preferred_domain(self, domain):
        """Persist preferred email domain."""
        try:
            cleaned = (domain or '').strip().lower()
            if not re.fullmatch(r"[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", cleaned):
                return False
            with open(self.domain_file, 'w', encoding='utf-8') as f:
                f.write(cleaned)
            return True
        except Exception:
            return False

    def get_saved_accounts(self):
        """Read saved accounts from cursor_accounts.txt."""
        accounts = []
        if not os.path.exists(self.accounts_file):
            return accounts

        try:
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return accounts

        blocks = [b.strip() for b in content.split('=' * 50) if b.strip()]
        for block in blocks:
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            entry = {}
            for line in lines:
                if ':' not in line:
                    continue
                key, value = line.split(':', 1)
                entry[key.strip().lower()] = value.strip()

            email = entry.get('email')
            token = entry.get('token')
            if not email or not token:
                continue

            created_at_raw = entry.get('created at')
            created_at = None
            if created_at_raw:
                try:
                    created_at = datetime.fromisoformat(created_at_raw)
                except ValueError:
                    created_at = None

            last_reused_raw = entry.get('last reused at')
            last_reused_at = None
            if last_reused_raw:
                try:
                    last_reused_at = datetime.fromisoformat(last_reused_raw)
                except ValueError:
                    last_reused_at = None

            sub = (entry.get('subscription') or '').strip()
            if not sub:
                sub = (entry.get('usage limit') or '').strip()
            usage_info = {
                "premium_usage": entry.get("premium usage"),
                "max_premium_usage": entry.get("premium limit"),
                "basic_usage": entry.get("basic usage"),
                "max_basic_usage": entry.get("basic limit"),
                "premium_limit_reached": entry.get("premium limit reached"),
            }
            accounts.append(
                {
                    'email': email,
                    'password': entry.get('password', ''),
                    'token': token,
                    'subscription': sub,
                    'usage_limit': (entry.get('usage limit') or '').strip(),
                    'usage_info': usage_info,
                    'created_at': created_at,
                    'last_reused_at': last_reused_at,
                }
            )
        return accounts

    def get_saved_google_accounts(self):
        """Comptes enregistrés dont l’e-mail est @gmail.com ou @googlemail.com (ordre fichier)."""
        out = []
        for account in self.get_saved_accounts():
            email = (account.get("email") or "").strip()
            if "@" not in email:
                continue
            domain = email.rsplit("@", 1)[-1].lower()
            if domain in self._GOOGLE_EMAIL_DOMAINS:
                out.append(dict(account))
        return out

    def get_email_counts_by_domain(self):
        """Nombre de comptes enregistrés par domaine (extrait de l'email dans cursor_accounts.txt)."""
        counts = Counter()
        for account in self.get_saved_accounts():
            email = (account.get('email') or '').strip()
            if '@' in email:
                domain = email.rsplit('@', 1)[-1].lower()
                if domain:
                    counts[domain] += 1
        return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0].lower())))

    def get_reusable_accounts(self, min_days=31):
        """Comptes réutilisables (>= min_days), du plus ancien au plus récent."""
        now = datetime.now()
        reusable = []
        for account in self.get_saved_accounts():
            created_at = account.get('created_at')
            age_days = None
            if created_at:
                age_days = (now - created_at).days
            account_copy = dict(account)
            account_copy['age_days'] = age_days
            if age_days is not None and age_days >= min_days:
                reusable.append(account_copy)
        reusable.sort(
            key=lambda a: (
                a.get("created_at") is None,
                a.get("created_at") or datetime.max,
            )
        )
        return reusable

    def _split_account_block_bodies(self, content: str) -> list:
        """Découpe cursor_accounts.txt en corps de blocs (sans les lignes ======)."""
        bodies = []
        for part in content.split(self._BLOCK_SEP):
            body = part.strip("\n\r")
            if body:
                bodies.append(body)
        return bodies

    def _serialize_account_block_bodies(self, bodies: list) -> str:
        """Même format que save_account_info : retours ligne avant/après chaque séparateur."""
        if not bodies:
            return ""
        chunks = []
        for body in bodies:
            chunks.append(f"\n{self._BLOCK_SEP}\n{body}\n")
        return "".join(chunks) + f"{self._BLOCK_SEP}\n"

    def _usage_field_lines(self, usage_info: dict) -> list:
        ui = usage_info or {}
        lines = []
        mapping = (
            ("Premium Usage", "premium_usage"),
            ("Premium Limit", "max_premium_usage"),
            ("Basic Usage", "basic_usage"),
            ("Basic Limit", "max_basic_usage"),
            ("Premium Limit Reached", "premium_limit_reached"),
        )
        for label, key in mapping:
            val = ui.get(key)
            if val is not None:
                if key == "premium_limit_reached":
                    val = str(bool(val))
                lines.append(f"{label}: {val}")
        return lines

    def update_account_session_info(
        self,
        email: str,
        token: str,
        subscription: str = None,
        usage_info: dict = None,
    ) -> bool:
        """Met à jour Token / Subscription / quotas d’un compte existant."""
        target = (email or "").strip().lower()
        new_token = (token or "").strip()
        if not target or not new_token or not os.path.exists(self.accounts_file):
            return False

        try:
            with open(self.accounts_file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return False

        bodies = self._split_account_block_bodies(content)
        updated = False
        new_bodies = []
        usage_keys = {
            "premium usage",
            "premium limit",
            "basic usage",
            "basic limit",
            "premium limit reached",
        }

        for body in bodies:
            block_email = None
            for line in body.splitlines():
                if line.strip().lower().startswith("email:"):
                    block_email = line.split(":", 1)[1].strip().lower()
                    break

            if block_email == target:
                updated = True
                out_lines = []
                has_subscription = False
                for line in body.splitlines():
                    low = line.strip().lower()
                    if low.startswith("token:"):
                        out_lines.append(f"Token: {new_token}")
                    elif low.startswith("subscription:") and subscription:
                        out_lines.append(f"Subscription: {(subscription or '').strip() or 'Unknown'}")
                        has_subscription = True
                    elif low.split(":", 1)[0].strip().lower() in usage_keys and usage_info:
                        continue
                    else:
                        out_lines.append(line)
                if subscription and not has_subscription:
                    out_lines.append(f"Subscription: {(subscription or '').strip() or 'Unknown'}")
                if usage_info:
                    out_lines.extend(self._usage_field_lines(usage_info))
                body = "\n".join(out_lines)

            new_bodies.append(body)

        if not updated:
            return False

        try:
            with open(self.accounts_file, "w", encoding="utf-8") as f:
                f.write(self._serialize_account_block_bodies(new_bodies))
            return True
        except OSError:
            return False

    def update_account_token(self, email: str, token: str) -> bool:
        """Met à jour la ligne Token: pour un compte dans cursor_accounts.txt."""
        target = (email or "").strip().lower()
        new_token = (token or "").strip()
        if not target or not new_token or not os.path.exists(self.accounts_file):
            return False

        try:
            with open(self.accounts_file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return False

        bodies = self._split_account_block_bodies(content)
        updated = False
        new_bodies = []

        for body in bodies:
            block_email = None
            for line in body.splitlines():
                if line.strip().lower().startswith("email:"):
                    block_email = line.split(":", 1)[1].strip().lower()
                    break

            if block_email == target:
                updated = True
                out_lines = []
                for line in body.splitlines():
                    if line.strip().lower().startswith("token:"):
                        out_lines.append(f"Token: {new_token}")
                    else:
                        out_lines.append(line)
                body = "\n".join(out_lines)

            new_bodies.append(body)

        if not updated:
            return False

        try:
            with open(self.accounts_file, "w", encoding="utf-8") as f:
                f.write(self._serialize_account_block_bodies(new_bodies))
            return True
        except OSError:
            return False

    def touch_account_created_at(self, email: str, reused_at=None) -> bool:
        """
        Remet Created At à aujourd’hui pour le compte réutilisé (évite de le reproposer trop tôt).
        Ajoute ou met à jour Last Reused At.
        """
        target = (email or "").strip().lower()
        if not target or not os.path.exists(self.accounts_file):
            return False

        when = reused_at or datetime.now()
        created_stamp = when.isoformat(timespec="seconds")
        reused_stamp = created_stamp

        try:
            with open(self.accounts_file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return False

        bodies = self._split_account_block_bodies(content)
        updated = False
        new_bodies = []

        for body in bodies:
            block_email = None
            for line in body.splitlines():
                if line.strip().lower().startswith("email:"):
                    block_email = line.split(":", 1)[1].strip().lower()
                    break

            if block_email == target:
                updated = True
                out_lines = []
                has_created = False
                has_reused = False
                for line in body.splitlines():
                    low = line.strip().lower()
                    if low.startswith("created at:"):
                        out_lines.append(f"Created At: {created_stamp}")
                        has_created = True
                    elif low.startswith("last reused at:"):
                        out_lines.append(f"Last Reused At: {reused_stamp}")
                        has_reused = True
                    else:
                        out_lines.append(line)
                if not has_created:
                    out_lines.insert(0, f"Created At: {created_stamp}")
                if not has_reused:
                    out_lines.append(f"Last Reused At: {reused_stamp}")
                body = "\n".join(out_lines)

            new_bodies.append(body)

        if not updated:
            return False

        try:
            with open(self.accounts_file, "w", encoding="utf-8") as f:
                f.write(self._serialize_account_block_bodies(new_bodies))
            return True
        except OSError:
            return False

    def suggest_email(self, first_name, last_name):
        """Generate a suggested email based on first and last name with the last used domain"""
        try:
            # Get the last used email domain
            domain = self.get_last_email_domain()
            if not domain:
                return None
            
            # Generate email prefix: firstname_lastname (underscore) pour correspondre au compte Linux sur le nœud distant
            email_prefix = f"{first_name.lower()}_{last_name.lower()}"
            
            # Combine prefix and domain
            suggested_email = f"{email_prefix}@{domain}"
            
            return suggested_email
        
        except Exception as e:
            error_msg = self.translator.get('account.suggest_email_failed', error=str(e)) if self.translator else f'Failed to suggest email: {str(e)}'
            print(f"{Fore.RED}{EMOJI['ERROR']} {error_msg}{Style.RESET_ALL}")
            return None


def configure_shared_accounts_file(translator=None) -> bool:
    """Configure le chemin partagé de cursor_accounts.txt (multi-PC)."""
    current = resolve_accounts_file_path(translator)
    am = AccountManager(translator, accounts_file=current)
    count = len(am.get_saved_accounts())

    intro = (
        translator.get("account.shared_file_intro")
        if translator
        else "Chemin du fichier comptes (cursor_accounts.txt). Mettez le même chemin sur chaque PC (OneDrive, NAS…)."
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {intro}{Style.RESET_ALL}")
    hint_cfg = (
        translator.get("account.shared_config_hint")
        if translator
        else "Astuce multi-PC : [Account] shared_config_ini dans config.ini pour partager Chrome/RemoteNode."
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {hint_cfg}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{EMOJI['INFO']} {translator.get('account.shared_file_current', path=current) if translator else f'Actuel : {current}'}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{EMOJI['INFO']} {translator.get('account.shared_file_count', count=count) if translator else f'Comptes enregistrés : {count}'}{Style.RESET_ALL}")

    prompt = (
        translator.get("account.shared_file_prompt")
        if translator
        else "Nouveau chemin (Entrée = garder, « auto » = défaut Documents/.cursor-free-vip) : "
    )
    raw = input(prompt).strip()
    if not raw:
        return True
    if raw.lower() in ("auto", "defaut", "défaut", "default"):
        new_path = ""
    else:
        new_path = os.path.normpath(os.path.expanduser(os.path.expandvars(raw)))

    if new_path and not os.path.isfile(new_path):
        parent = os.path.dirname(new_path)
        if parent and not os.path.isdir(parent):
            yn = (
                input(
                    translator.get("account.shared_file_create_parent")
                    if translator
                    else "Le dossier parent n'existe pas. Le créer ? (oui/non) : "
                )
                .strip()
                .lower()
            )
            if yn not in ("oui", "o", "yes", "y"):
                return False
            os.makedirs(parent, exist_ok=True)

    if not save_accounts_file_config(new_path, translator):
        err = (
            translator.get("account.shared_file_save_failed")
            if translator
            else "Impossible d'enregistrer le chemin dans config.ini."
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {err}{Style.RESET_ALL}")
        return False

    resolved = resolve_accounts_file_path(translator)
    ok = (
        translator.get("account.shared_file_saved", path=resolved)
        if translator
        else f"Chemin enregistré : {resolved}"
    )
    print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {ok}{Style.RESET_ALL}")
    return True
