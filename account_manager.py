import os
from colorama import Fore, Style
import re
from datetime import datetime
from collections import Counter

# Define emoji constants
EMOJI = {
    'SUCCESS': '✅',
    'ERROR': '❌',
    'INFO': 'ℹ️'
}

class AccountManager:
    _GOOGLE_EMAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})

    def __init__(self, translator=None, accounts_file=None):
        self.translator = translator
        self.accounts_file = accounts_file or "cursor_accounts.txt"
        self.domain_file = 'cursor_domain.txt'
    
    def save_account_info(self, email, password, token, total_usage):
        """Save account information to file"""
        try:
            with open(self.accounts_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*50}\n")
                f.write(f"Created At: {datetime.now().isoformat(timespec='seconds')}\n")
                f.write(f"Email: {email}\n")
                f.write(f"Password: {password}\n")
                f.write(f"Token: {token}\n")
                f.write(f"Usage Limit: {total_usage}\n")
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

            accounts.append(
                {
                    'email': email,
                    'password': entry.get('password', ''),
                    'token': token,
                    'usage_limit': entry.get('usage limit', ''),
                    'created_at': created_at,
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

    def get_reusable_accounts(self, min_days=30):
        """Get saved accounts that are at least min_days old."""
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
        return reusable
    
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
