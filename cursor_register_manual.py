import os
from colorama import Fore, Style, init
import time
import random
from faker import Faker
from cursor_auth import CursorAuth
from reset_machine_manual import MachineIDResetter
from get_user_token import get_token_from_cookie
from config import get_config
from account_manager import AccountManager
from logger import get_logger

log = get_logger("cursor_register_manual")

os.environ["PYTHONVERBOSE"] = "0"
os.environ["PYINSTALLER_VERBOSE"] = "0"

# Initialize colorama
init()

# Define emoji constants
EMOJI = {
    'START': '🚀',
    'FORM': '📝',
    'VERIFY': '🔄',
    'PASSWORD': '🔑',
    'CODE': '📱',
    'DONE': '✨',
    'ERROR': '❌',
    'WAIT': '⏳',
    'SUCCESS': '✅',
    'MAIL': '📧',
    'KEY': '🔐',
    'UPDATE': '🔄',
    'INFO': 'ℹ️'
}

class CursorRegistration:
    def __init__(self, translator=None):
        self.translator = translator
        # Set to display mode
        os.environ['BROWSER_HEADLESS'] = 'False'
        self.browser = None
        self.controller = None
        self.sign_up_url = "https://authenticator.cursor.sh/sign-up"
        self.settings_url = "https://www.cursor.com/settings"
        self.email_address = None
        self.signup_tab = None
        self.email_tab = None
        
        # initialize Faker instance
        self.faker = Faker()
        
        # generate account information
        self.password = self._generate_password()
        self.first_name = self.faker.first_name()
        self.last_name = self.faker.last_name()
        
        # modify the first letter of the first name(keep the original function)
        new_first_letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        self.first_name = new_first_letter + self.first_name[1:]
        
        print(f"\n{Fore.CYAN}{EMOJI['PASSWORD']} {self.translator.get('register.password')}: {self.password} {Style.RESET_ALL}")
        print(f"{Fore.CYAN}{EMOJI['FORM']} {self.translator.get('register.first_name')}: {self.first_name} {Style.RESET_ALL}")
        print(f"{Fore.CYAN}{EMOJI['FORM']} {self.translator.get('register.last_name')}: {self.last_name} {Style.RESET_ALL}")

    def _generate_password(self, length=12):
        """Generate password"""
        return self.faker.password(length=length, special_chars=True, digits=True, upper_case=True, lower_case=True)

    def setup_email(self):
        """Setup Email"""
        try:
            # Try to get a suggested email
            account_manager = AccountManager(self.translator)
            suggested_email = account_manager.suggest_email(self.first_name, self.last_name)
            
            if suggested_email:
                print(f"{Fore.CYAN}{EMOJI['START']} {self.translator.get('register.suggest_email', suggested_email=suggested_email) if self.translator else f'Suggested email: {suggested_email}'}")
                self.email_address = suggested_email
            else:
                # If there's no suggested email
                print(f"{Fore.CYAN}{EMOJI['START']} {self.translator.get('register.manual_email_input') if self.translator else 'Please enter your email address:'}")
                self.email_address = input().strip()
            
            # Validate if the email is valid
            if '@' not in self.email_address:
                print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.invalid_email') if self.translator else 'Invalid email address'}{Style.RESET_ALL}")
                return False

            # Créer le compte utilisateur sur le nœud distant (SSH) si configuré
            config = get_config(self.translator)
            remote_created = False
            if config and config.has_section('RemoteNode') and config.get('RemoteNode', 'enabled', fallback='false').strip().lower() in ('true', '1', 'yes'):
                if config.get('RemoteNode', 'create_user_on_register', fallback='true').strip().lower() in ('true', '1', 'yes'):
                    from remote_user_manager import email_to_username, create_remote_user
                    ssh_host = config.get('RemoteNode', 'host', fallback='').strip()
                    ssh_user = config.get('RemoteNode', 'user', fallback='pi').strip() or 'pi'
                    if ssh_host:
                        uname = email_to_username(self.email_address)
                        if uname:
                            remote_created = create_remote_user(uname, self.password, ssh_host, ssh_user, self.translator)
                        else:
                            log.warning("Could not derive username from email for remote user")
                    else:
                        log.warning("RemoteNode enabled but host is empty")
            else:
                # Rappel : pour créer le compte Linux automatiquement, activer [RemoteNode] dans la config
                if self.translator:
                    print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('remote_user.enable_in_config')}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}{EMOJI['INFO']} Pour créer un compte sur le nœud distant, activez [RemoteNode] dans la config (menu option 10).{Style.RESET_ALL}")
                
            print(f"{Fore.CYAN}{EMOJI['MAIL']} {self.translator.get('register.email_address')}: {self.email_address}" + "\n" + f"{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.email_setup_failed', error=str(e))}{Style.RESET_ALL}")
            return False

    def get_verification_code(self):
        """Récupère le code : d'abord depuis la boîte mail sur le nœud distant (si RemoteNode), sinon saisie manuelle."""
        try:
            import time
            import configparser
            from utils import get_user_documents_path
            # Lire la config depuis le fichier pour être sûr d'avoir [RemoteNode] à jour (éviter cache)
            config = get_config(self.translator)
            config_dir = os.path.join(get_user_documents_path(), ".cursor-free-vip")
            config_file = os.path.join(config_dir, "config.ini")
            if os.path.exists(config_file):
                fresh = configparser.ConfigParser()
                fresh.read(config_file, encoding="utf-8")
                if fresh.has_section("RemoteNode"):
                    config = fresh
            # Tentative de récupération du code depuis la boîte mail sur le nœud
            if config and config.has_section("RemoteNode") and config.get("RemoteNode", "enabled", fallback="false").strip().lower() in ("true", "1", "yes"):
                ssh_host = config.get("RemoteNode", "host", fallback="").strip()
                ssh_user = config.get("RemoteNode", "user", fallback="pi").strip() or "pi"
                if ssh_host and self.email_address and "@" in self.email_address:
                    from remote_user_manager import email_to_username, get_verification_code_from_remote_mail
                    uname = email_to_username(self.email_address)
                    if uname:
                        if self.translator:
                            print(f"{Fore.CYAN}{EMOJI['CODE']} {self.translator.get('remote_user.fetching_code_from_node')}{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.CYAN}{EMOJI['CODE']} Récupération du code depuis la boîte mail sur {ssh_host}...{Style.RESET_ALL}")
                        log.info("Attempting to fetch verification code from remote mail for %s@%s", uname, ssh_host)
                        for attempt in range(12):  # ~60 s avec 5 s entre chaque essai
                            code = get_verification_code_from_remote_mail(uname, ssh_host, ssh_user, self.translator)
                            if code:
                                if self.translator:
                                    print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('remote_user.code_retrieved')}{Style.RESET_ALL}")
                                else:
                                    print(f"{Fore.GREEN}{EMOJI['SUCCESS']} Code récupéré depuis le nœud.{Style.RESET_ALL}")
                                log.info("Verification code received from remote mail")
                                return code
                            if attempt < 11:
                                time.sleep(5)
                        if self.translator:
                            print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('remote_user.code_not_found_fallback')}{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.YELLOW}{EMOJI['INFO']} Code non trouvé sur le nœud, saisie manuelle.{Style.RESET_ALL}")

            log.info("Waiting for manual verification code input")
            print(f"{Fore.CYAN}{EMOJI['CODE']} {self.translator.get('register.manual_code_input') if self.translator else 'Please enter the verification code:'}")
            code = input().strip()
            
            if not code.isdigit() or len(code) != 6:
                log.warning("Invalid verification code format (expected 6 digits)")
                print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.invalid_code') if self.translator else 'Invalid verification code'}{Style.RESET_ALL}")
                return None
            log.info("Verification code received successfully")
            return code
            
        except Exception as e:
            log.exception("Code input failed: %s", e)
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.code_input_failed', error=str(e))}{Style.RESET_ALL}")
            return None

    def register_cursor(self):
        """Register Cursor"""
        browser_tab = None
        try:
            print(f"{Fore.CYAN}{EMOJI['START']} {self.translator.get('register.register_start')}...{Style.RESET_ALL}")
            
            # Check email source: TempMailPlus, LocalEmail (IMAP), or manual
            config = get_config(self.translator)
            email_tab = None
            if config and config.has_section('TempMailPlus') and config.getboolean('TempMailPlus', 'enabled'):
                email = config.get('TempMailPlus', 'email')
                epin = config.get('TempMailPlus', 'epin')
                if email and epin:
                    from email_tabs.tempmail_plus_tab import TempMailPlusTab
                    email_tab = TempMailPlusTab(email, epin, self.translator)
                    log.info("Using TempMailPlus for verification emails")
                    print(f"{Fore.CYAN}{EMOJI['MAIL']} {self.translator.get('register.using_tempmail_plus')}{Style.RESET_ALL}")
            elif config and config.has_section('LocalEmail') and config.getboolean('LocalEmail', 'enabled'):
                from email_tabs.local_imap_tab import LocalImapTab
                try:
                    email_tab = LocalImapTab.from_config(config, self.translator)
                    log.info("Using local IMAP mailbox for verification emails")
                    print(f"{Fore.CYAN}{EMOJI['MAIL']} {self.translator.get('register.using_local_email') if self.translator else 'Using local email (IMAP)'}{Style.RESET_ALL}")
                except Exception as e:
                    log.warning("LocalEmail config invalid, falling back to manual code: %s", e)
                    print(f"{Fore.YELLOW}{EMOJI['WAIT']} {self.translator.get('register.local_email_failed', error=str(e)) if self.translator else f'Local email failed: {e}, use manual code.'}{Style.RESET_ALL}")
            
            # Use new_signup.py directly for registration
            from new_signup import main as new_signup_main
            
            # Execute new registration process, passing translator
            result, browser_tab = new_signup_main(
                email=self.email_address,
                password=self.password,
                first_name=self.first_name,
                last_name=self.last_name,
                email_tab=email_tab,  # Pass email_tab if tempmail_plus is enabled
                controller=self,  # Pass self instead of self.controller
                translator=self.translator
            )
            
            if result:
                # Use the returned browser instance to get account information
                self.signup_tab = browser_tab  # Save browser instance
                success = self._get_account_info()
                
                # Une fois l'email validé et l'inscription réussie : supprimer le compte sur le nœud distant (--remove-home)
                config = get_config(self.translator)
                if success and config and config.has_section('RemoteNode') and config.get('RemoteNode', 'enabled', fallback='false').strip().lower() in ('true', '1', 'yes'):
                    ssh_host = config.get('RemoteNode', 'host', fallback='').strip()
                    ssh_user = config.get('RemoteNode', 'user', fallback='pi').strip() or 'pi'
                    remove_home = config.get('RemoteNode', 'remove_home_on_delete', fallback='true').strip().lower() in ('true', '1', 'yes')
                    if ssh_host:
                        from remote_user_manager import email_to_username, delete_remote_user
                        uname = email_to_username(self.email_address)
                        if uname:
                            delete_remote_user(uname, ssh_host, ssh_user, remove_home=remove_home, translator=self.translator)
                
                # Close browser after getting information
                if browser_tab:
                    try:
                        browser_tab.quit()
                    except:
                        pass
                
                return success
            
            return False
            
        except Exception as e:
            log.exception("Registration process error: %s", e)
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.register_process_error', error=str(e))}{Style.RESET_ALL}")
            return False
        finally:
            # Ensure browser is closed in any case
            if browser_tab:
                try:
                    browser_tab.quit()
                except:
                    pass
                
    def _get_account_info(self):
        """Get Account Information and Token"""
        try:
            self.signup_tab.get(self.settings_url)
            time.sleep(2)
            
            usage_selector = (
                "css:div.col-span-2 > div > div > div > div > "
                "div:nth-child(1) > div.flex.items-center.justify-between.gap-2 > "
                "span.font-mono.text-sm\\/\\[0\\.875rem\\]"
            )
            usage_ele = self.signup_tab.ele(usage_selector)
            total_usage = "Inconnu"
            if usage_ele:
                total_usage = usage_ele.text.split("/")[-1].strip()

            print(f"Total Usage: {total_usage}\n")
            print(f"{Fore.CYAN}{EMOJI['WAIT']} {self.translator.get('register.get_token')}...{Style.RESET_ALL}")
            max_attempts = 30
            retry_interval = 2
            attempts = 0

            while attempts < max_attempts:
                try:
                    cookies = self.signup_tab.cookies()
                    for cookie in cookies:
                        if cookie.get("name") == "WorkosCursorSessionToken":
                            token = get_token_from_cookie(cookie["value"], self.translator)
                            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('register.token_success')}{Style.RESET_ALL}")
                            self._save_account_info(token, total_usage)
                            return True

                    attempts += 1
                    if attempts < max_attempts:
                        print(f"{Fore.YELLOW}{EMOJI['WAIT']} {self.translator.get('register.token_attempt', attempt=attempts, time=retry_interval)}{Style.RESET_ALL}")
                        time.sleep(retry_interval)
                    else:
                        print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.token_max_attempts', max=max_attempts)}{Style.RESET_ALL}")

                except Exception as e:
                    print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.token_failed', error=str(e))}{Style.RESET_ALL}")
                    attempts += 1
                    if attempts < max_attempts:
                        print(f"{Fore.YELLOW}{EMOJI['WAIT']} {self.translator.get('register.token_attempt', attempt=attempts, time=retry_interval)}{Style.RESET_ALL}")
                        time.sleep(retry_interval)

            return False

        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.account_error', error=str(e))}{Style.RESET_ALL}")
            return False

    def _save_account_info(self, token, total_usage):
        """Save Account Information to File"""
        try:
            # Update authentication information first
            print(f"{Fore.CYAN}{EMOJI['KEY']} {self.translator.get('register.update_cursor_auth_info')}...{Style.RESET_ALL}")
            if self.update_cursor_auth(email=self.email_address, access_token=token, refresh_token=token, auth_type="Auth_0"):
                print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('register.cursor_auth_info_updated')}...{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.cursor_auth_info_update_failed')}...{Style.RESET_ALL}")

            # Reset machine ID
            print(f"{Fore.CYAN}{EMOJI['UPDATE']} {self.translator.get('register.reset_machine_id')}...{Style.RESET_ALL}")
            resetter = MachineIDResetter(self.translator)  # Create instance with translator
            if not resetter.reset_machine_ids():  # Call reset_machine_ids method directly
                raise Exception("Failed to reset machine ID")
            
            # Save account information to file using AccountManager
            account_manager = AccountManager(self.translator)
            if account_manager.save_account_info(self.email_address, self.password, token, total_usage):
                return True
            else:
                return False
            
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.save_account_info_failed', error=str(e))}{Style.RESET_ALL}")
            return False

    def start(self):
        """Start Registration Process"""
        try:
            if self.setup_email():
                if self.register_cursor():
                    print(f"\n{Fore.GREEN}{EMOJI['DONE']} {self.translator.get('register.cursor_registration_completed')}...{Style.RESET_ALL}")
                    return True
            return False
        finally:
            # Close email tab
            if hasattr(self, 'temp_email'):
                try:
                    self.temp_email.close()
                except:
                    pass

    def update_cursor_auth(self, email=None, access_token=None, refresh_token=None, auth_type="Auth_0"):
        """Convenient function to update Cursor authentication information"""
        auth_manager = CursorAuth(translator=self.translator)
        return auth_manager.update_auth(email, access_token, refresh_token, auth_type)

def main(translator=None):
    """Main function to be called from main.py"""
    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{EMOJI['START']} {translator.get('register.title')}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    registration = CursorRegistration(translator)
    registration.start()

    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    input(f"{EMOJI['INFO']} {translator.get('register.press_enter')}...")

if __name__ == "__main__":
    from main import translator as main_translator
    main(main_translator) 