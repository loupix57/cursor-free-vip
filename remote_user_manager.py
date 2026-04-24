# remote_user_manager.py - Gestion des utilisateurs sur un nœud distant via SSH (adduser / deluser)
"""
Crée ou supprime des comptes utilisateur sur une machine Linux accessible en SSH
(par ex. pi@remote-host.lan) avec adduser et deluser --remove-home.
"""
from __future__ import annotations

import re
import subprocess
from typing import Optional, Set

from colorama import Fore, Style

from logger import get_logger

log = get_logger("remote_user_manager")

EMOJI = {"SUCCESS": "✅", "ERROR": "❌", "INFO": "ℹ️"}

# Comptes créés pour le mail Cursor : prénom_nom (même logique que email_to_username, une partie avec underscore)
MAIL_STYLE_USERNAME_RE = re.compile(r"^[a-z][a-z0-9]{1,22}_[a-z][a-z0-9]{1,22}$")

# Ne jamais supprimer ces comptes système / courants
DEFAULT_CLEANUP_SKIP_USERS = frozenset(
    {
        "pi",
        "debian",
        "ubuntu",
        "root",
        "admin",
        "syslog",
        "messagebus",
        "nobody",
        "www-data",
        "mail",
        "postfix",
        "dovecot",
        "clamav",
        "ftp",
        "sshd",
        "git",
        "sync",
        "games",
        "man",
        "lp",
        "news",
        "uucp",
        "proxy",
        "list",
        "irc",
        "gnats",
        "backup",
    }
)


def _extract_domains_from_postfix_output(raw_config: str) -> list[str]:
    """Extract domain names from `postconf` output."""
    if not raw_config:
        return []

    mail_domains: set[str] = set()
    for line in raw_config.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        if key not in {"mydestination", "myhostname"}:
            continue
        for part in value.split(","):
            candidate = part.strip().lower()
            if not candidate or candidate.startswith("$"):
                continue
            if candidate == "localhost" or candidate.startswith("localhost."):
                continue
            if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", candidate):
                if candidate.startswith("mail."):
                    root_domain = candidate[len("mail.") :]
                    if root_domain:
                        mail_domains.add(root_domain)
    return sorted(mail_domains)


def list_remote_mail_domains(ssh_host: str, ssh_user: str = "pi") -> list[str]:
    """List mail domains configured on remote Postfix host."""
    if not ssh_host:
        return []
    remote_commands = [
        "postconf mydestination myhostname",
        "cat /etc/postfix/main.cf 2>/dev/null",
        "sudo cat /etc/postfix/main.cf 2>/dev/null",
    ]

    last_error = ""
    for remote_cmd in remote_commands:
        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
            f"{ssh_user}@{ssh_host}",
            remote_cmd,
        ]
        try:
            r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=20)
            output = (r.stdout or "").strip()
            err = (r.stderr or "").strip()

            if r.returncode == 0 and output:
                domains = _extract_domains_from_postfix_output(output)
                if domains:
                    return domains

            last_error = err or output or f"exit code {r.returncode}"
        except Exception as e:
            last_error = str(e)

    if last_error:
        log.warning("list_remote_mail_domains failed: %s", last_error)
    return []


def email_to_username(email: str) -> str:
    """Dérive un nom d'utilisateur Linux valide depuis l'email (partie avant @)."""
    if not email or "@" not in email:
        return ""
    local = email.split("@")[0].strip().lower()
    # Remplacer . et - par _ ; ne garder que a-z, 0-9, _
    local = re.sub(r"[^a-z0-9_]", "_", local)
    # Éviter les _ multiples et limiter la longueur (32 caractères max sur Linux)
    local = re.sub(r"_+", "_", local).strip("_")
    return (local[:32]) if local else ""


def create_remote_user(
    username: str,
    password: str,
    ssh_host: str,
    ssh_user: str = "pi",
    translator=None,
) -> bool:
    """
    Crée un utilisateur sur la machine distante via SSH.
    Utilise: sudo adduser --disabled-password --gecos '' <username>
    puis: echo 'username:password' | sudo chpasswd
    """
    if not username or not ssh_host:
        log.warning("create_remote_user: username or ssh_host missing")
        return False
    # Échapper le mot de passe pour le shell distant (éviter les guillemets simples)
    safe_pass = password.replace("'", "'\"'\"'")
    # adduser (sans mot de passe interactif)
    add_cmd = f"sudo adduser --disabled-password --gecos '' {username}"
    # chpasswd pour définir le mot de passe
    chpasswd_cmd = f"echo '{username}:{safe_pass}' | sudo chpasswd"
    full_cmd = f"{add_cmd} && {chpasswd_cmd}"
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10", f"{ssh_user}@{ssh_host}", full_cmd]
    try:
        log.info("Creating remote user %s on %s@%s", username, ssh_user, ssh_host)
        if translator:
            print(f"{Fore.CYAN}{EMOJI['INFO']} {translator.get('remote_user.creating', username=username, host=ssh_host)}{Style.RESET_ALL}")
        else:
            print(f"{Fore.CYAN}{EMOJI['INFO']} Création du compte {username} sur {ssh_host}...{Style.RESET_ALL}")
        r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            log.warning("create_remote_user failed: %s", err)
            if translator:
                print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('remote_user.create_failed', username=username, error=err)}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}{EMOJI['ERROR']} Échec création compte {username}: {err}{Style.RESET_ALL}")
            return False
        if translator:
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {translator.get('remote_user.created', username=username, host=ssh_host)}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{EMOJI['INFO']} {translator.get('remote_user.same_password_as_cursor')}{Style.RESET_ALL}")
        else:
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} Compte {username} créé sur {ssh_host} (mot de passe = mot de passe Cursor ci-dessus).{Style.RESET_ALL}")
        return True
    except subprocess.TimeoutExpired:
        log.warning("create_remote_user timeout")
        if translator:
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('remote_user.timeout', host=ssh_host)}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}{EMOJI['ERROR']} Délai dépassé pour {ssh_host}.{Style.RESET_ALL}")
        return False
    except Exception as e:
        log.exception("create_remote_user error: %s", e)
        if translator:
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('remote_user.create_failed', username=username, error=str(e))}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}{EMOJI['ERROR']} Erreur: {e}{Style.RESET_ALL}")
        return False


# Script optionnel sur le nœud distant pour lire le Maildir sans demander de mot de passe
# (sudo NOPASSWD pour ce script uniquement). Voir scripts/read-user-maildir.sh.
REMOTE_READ_MAILDIR_SCRIPT = "/usr/local/bin/read-user-maildir"

# Faux positifs à ignorer : 646464 = couleur CSS #646464 dans le HTML de l'email Cursor
FAKE_VERIFICATION_CODES = frozenset({"646464", "202602", "210226", "202621", "171704"})


def _extract_cursor_verification_code(raw_mail_content: str) -> str:
    """
    Extrait le code à 6 chiffres de l'email de vérification Cursor.
    Évite les faux positifs (ex. 646464 = #646464 dans le CSS du HTML).
    Gère le quoted-printable (=0A, =0D=0A) et le HTML.
    """
    if not raw_mail_content:
        return ""
    # Normaliser quoted-printable : =0A, =0D=0A, =\n → \n pour que les motifs \n(\d{6})\n matchent
    text = re.sub(r"=\s*\n", "", raw_mail_content)  # soft line break
    text = re.sub(r"=0D=0A", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"=0A", "\n", text, flags=re.IGNORECASE)
    # 1) Contexte typique Cursor (texte + HTML)
    context_patterns = [
        r"(?:v=E9rification|vérification|verification)\s*est\s*(\d{6})",
        r"est\s+(\d{6})\s*\.\s*Ce code",
        r"\n(\d{6})\n\n.*?Ce code expire",
        r"\n(\d{6})\n.*?Ce code expire",  # une seule newline
        r">\s*(\d{6})\s*<",  # HTML: >681531</div> ou > 681531 <
        r"letter-spacing:2px[^>]*>(\d{6})<",  # style du code dans l'email Cursor
        r"(\d{6})\s*\.\s*Ce code expire",  # code juste avant ". Ce code expire"
    ]
    for pat in context_patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            code = m.group(1)
            if code not in FAKE_VERIFICATION_CODES:
                return code
    # 2) Tous les codes à 6 chiffres en excluant les faux positifs, prendre le dernier
    all_codes = re.findall(r"\b(\d{6})\b", text)
    valid = [c for c in all_codes if c not in FAKE_VERIFICATION_CODES]
    if valid:
        return valid[-1]
    return all_codes[-1] if all_codes else ""


def get_verification_code_from_remote_mail(
    username: str,
    ssh_host: str,
    ssh_user: str = "pi",
    translator=None,
) -> str:
    """
    Récupère le code de vérification (6 chiffres) depuis la boîte mail du compte
    sur le nœud distant. Supporte :
    - Maildir : /home/<username>/Maildir/new/* (Postfix/Dovecot)
    - mbox : /var/mail/<username> ou /var/spool/mail/<username>
    Utilise en priorité le script read-user-maildir sur le serveur si présent
    (évite que sudo demande un mot de passe). Sinon tente sudo cat (peut demander un mot de passe).
    Retourne le dernier code à 6 chiffres trouvé (email Cursor le plus récent).
    """
    if not username or not ssh_host:
        return ""
    # 1) Script dédié sur le serveur (NOPASSWD) — ne demande pas de mot de passe
    # 2) Sinon sudo cat (peut demander le mot de passe de pi ou autre)
    for cmd in [
        f"sudo {REMOTE_READ_MAILDIR_SCRIPT} {username}",
        (
            f"(sudo cat /home/{username}/Maildir/new/* 2>/dev/null; "
            f"sudo cat /var/mail/{username} 2>/dev/null; "
            f"sudo cat /var/spool/mail/{username} 2>/dev/null); true"
        ),
    ]:
        ssh_cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10",
            f"{ssh_user}@{ssh_host}",
            cmd,
        ]
        try:
            r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=15)
            out = (r.stdout or "") + (r.stderr or "")
            code = _extract_cursor_verification_code(out)
            if code:
                log.info("Verification code from remote mail for %s: %s", username, code[:2] + "****")
                return code
        except Exception as e:
            log.debug("get_verification_code_from_remote_mail: %s", e)
    return ""


def matches_mail_style_username(username: str) -> bool:
    """True si le nom ressemble à un compte mail Cursor (firstname_lastname, minuscules)."""
    if not username:
        return False
    return bool(MAIL_STYLE_USERNAME_RE.match(username.strip().lower()))


def get_cleanup_skip_usernames(config) -> Set[str]:
    """Ensemble des noms à ne jamais supprimer (défaut + [RemoteNode] cleanup_skip_users)."""
    skip = set(DEFAULT_CLEANUP_SKIP_USERS)
    if config and config.has_section("RemoteNode"):
        raw = config.get("RemoteNode", "cleanup_skip_users", fallback="").strip()
        for part in raw.split(","):
            p = part.strip().lower()
            if p:
                skip.add(p)
    return skip


def list_remote_users_with_home_under_home(ssh_host: str, ssh_user: str = "pi") -> list[str]:
    """
    Liste les noms d'utilisateur dont le répertoire personnel est sous /home/ (via getent passwd).
    """
    if not ssh_host:
        return []
    remote_cmd = r"getent passwd | awk -F: '$6 ~ /^\/home\// {print $1}'"
    ssh_cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        f"{ssh_user}@{ssh_host}",
        remote_cmd,
    ]
    try:
        r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=25)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            log.warning("list_remote_users_with_home_under_home failed: %s", err)
            return []
        return [line.strip() for line in (r.stdout or "").splitlines() if line.strip()]
    except Exception as e:
        log.exception("list_remote_users_with_home_under_home: %s", e)
        return []


def find_mail_style_users_on_remote(
    ssh_host: str,
    ssh_user: str = "pi",
    skip_usernames: Optional[Set[str]] = None,
) -> list[str]:
    """
    Trouve sur le nœud distant les comptes au format prénom_nom (comptes mail Cursor typiques).
    """
    skip = skip_usernames if skip_usernames is not None else set(DEFAULT_CLEANUP_SKIP_USERS)
    skip_l = {s.lower() for s in skip}
    all_home = list_remote_users_with_home_under_home(ssh_host, ssh_user)
    out = []
    for name in all_home:
        low = name.strip().lower()
        if low in skip_l:
            continue
        if matches_mail_style_username(low):
            out.append(name.strip())
    return sorted(set(out), key=str.lower)


def cleanup_mail_style_users_on_remote(
    ssh_host: str,
    ssh_user: str = "pi",
    remove_home: bool = True,
    skip_usernames: Optional[Set[str]] = None,
    translator=None,
) -> tuple[int, int, list[str]]:
    """
    Supprime tous les comptes détectés comme « mail Cursor » (firstname_lastname).
    Retourne (nombre_supprimés, nombre_échecs, liste_des_candidats).
    """
    candidates = find_mail_style_users_on_remote(ssh_host, ssh_user, skip_usernames=skip_usernames)
    if not candidates:
        return 0, 0, []
    ok = 0
    fail = 0
    for uname in candidates:
        if delete_remote_user(uname, ssh_host, ssh_user, remove_home=remove_home, translator=translator):
            ok += 1
        else:
            fail += 1
    return ok, fail, candidates


def delete_remote_user(
    username: str,
    ssh_host: str,
    ssh_user: str = "pi",
    remove_home: bool = True,
    translator=None,
) -> bool:
    """
    Supprime un utilisateur sur la machine distante via SSH.
    Utilise: sudo deluser --remove-home <username>
    """
    if not username or not ssh_host:
        log.warning("delete_remote_user: username or ssh_host missing")
        return False
    flag = "--remove-home" if remove_home else ""
    full_cmd = f"sudo deluser {flag} {username}".strip()
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10", f"{ssh_user}@{ssh_host}", full_cmd]
    try:
        log.info("Deleting remote user %s on %s@%s", username, ssh_user, ssh_host)
        if translator:
            print(f"{Fore.CYAN}{EMOJI['INFO']} {translator.get('remote_user.deleting', username=username, host=ssh_host)}{Style.RESET_ALL}")
        else:
            print(f"{Fore.CYAN}{EMOJI['INFO']} Suppression du compte {username} sur {ssh_host}...{Style.RESET_ALL}")
        r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            log.warning("delete_remote_user failed: %s", err)
            if translator:
                print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('remote_user.delete_failed', username=username, error=err)}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}{EMOJI['ERROR']} Échec suppression {username}: {err}{Style.RESET_ALL}")
            return False
        if translator:
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {translator.get('remote_user.deleted', username=username, host=ssh_host)}{Style.RESET_ALL}")
        else:
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} Compte {username} supprimé sur {ssh_host}.{Style.RESET_ALL}")
        return True
    except Exception as e:
        log.exception("delete_remote_user error: %s", e)
        if translator:
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('remote_user.delete_failed', username=username, error=str(e))}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}{EMOJI['ERROR']} Erreur: {e}{Style.RESET_ALL}")
        return False
