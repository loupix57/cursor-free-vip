import os
from colorama import Fore, Style, init
import time
import random
from faker import Faker
from cursor_auth import CursorAuth, apply_cursor_session
from get_user_token import get_token_from_cookie, parse_workos_session_cookie
from cursor_acc_info import get_subscription_label_for_token, get_usage_summary_for_token
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
    def __init__(
        self,
        translator=None,
        external_personal_mail: bool = False,
        oauth_refresh_on_save: bool = False,
    ):
        self.translator = translator
        # True = Proton / autre boîte perso : pas de récup auto du code, saisie manuelle uniquement
        self.external_personal_mail = bool(external_personal_mail)
        # Set to display mode
        os.environ['BROWSER_HEADLESS'] = 'False'
        self.browser = None
        self.controller = None
        self.sign_up_url = "https://authenticator.cursor.sh/sign-up"
        # Nouvelle page settings avec données d’usage : dashboard?tab=settings
        self.settings_url = "https://www.cursor.com/dashboard?tab=settings"
        self.email_address = None
        self.signup_tab = None
        self.email_tab = None
        # Contrôle fin par flux : 1->2 peut activer le refresh OAuth explicitement.
        self.oauth_refresh_on_save = bool(oauth_refresh_on_save)
        
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
            if self.external_personal_mail:
                hint = (
                    self.translator.get("register.external_mail_intro")
                    if self.translator
                    else "Adresse complète (ex. jean_renee25@proton.me) — vous saisirez le code reçu dans cette boîte."
                )
                print(f"{Fore.CYAN}{EMOJI['MAIL']} {hint}{Style.RESET_ALL}")
                prompt = (
                    self.translator.get("register.external_mail_prompt")
                    if self.translator
                    else "E-mail : "
                )
                self.email_address = input(prompt).strip()
            else:
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

            # Créer le compte utilisateur sur le nœud distant (SSH) si configuré (inutile pour Proton / mail perso)
            config = get_config(self.translator)
            remote_created = False
            if not self.external_personal_mail:
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
                        print(f"{Fore.YELLOW}{EMOJI['INFO']} Pour créer un compte sur le nœud distant, activez [RemoteNode] dans la config (menu Principal → Configuration).{Style.RESET_ALL}")
                
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

            if self.external_personal_mail:
                log.info("External personal mail: manual verification code only")
                msg = (
                    self.translator.get("register.external_mail_code_hint", email=self.email_address or "")
                    if self.translator
                    else f"Ouvrez la boîte {self.email_address} et saisissez le code à 6 chiffres envoyé par Cursor :"
                )
                print(f"{Fore.CYAN}{EMOJI['CODE']} {msg}{Style.RESET_ALL}")
                code = input().strip()
                if not code.isdigit() or len(code) != 6:
                    log.warning("Invalid verification code format (expected 6 digits)")
                    print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.invalid_code') if self.translator else 'Invalid verification code'}{Style.RESET_ALL}")
                    return None
                return code

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
            if self.external_personal_mail:
                log.info("Registration with external personal mail: no TempMailPlus/LocalEmail tab")
                if self.translator:
                    print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('register.external_mail_no_auto_inbox')}{Style.RESET_ALL}")
            elif config and config.has_section('TempMailPlus') and config.getboolean('TempMailPlus', 'enabled'):
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
                translator=self.translator,
                use_chrome_public_profile=False,
            )
            
            if result:
                # Use the returned browser instance to get account information
                self.signup_tab = browser_tab  # Save browser instance
                success = self._get_account_info()

                # 1→2 : inscription d'abord (navigateur temporaire), puis session Chrome.
                if success and self.external_personal_mail:
                    if browser_tab:
                        try:
                            browser_tab.quit()
                        except Exception:
                            pass
                        browser_tab = None

                    from agent_cli_helper import automate_cursor_web_email_password_login

                    sync_msg = (
                        self.translator.get("register.external_mail_chrome_sync")
                        if self.translator
                        else "Synchronisation profil Chrome : logout puis login avec le nouveau compte…"
                    )
                    print(f"{Fore.CYAN}{EMOJI['INFO']} {sync_msg}{Style.RESET_ALL}")
                    if not automate_cursor_web_email_password_login(
                        self.email_address,
                        self.password,
                        self.translator,
                        update_existing=True,
                        use_chrome_public_profile=True,
                    ):
                        print(
                            f"{Fore.YELLOW}{EMOJI['INFO']} "
                            f"{self.translator.get('register.external_mail_chrome_sync_failed') if self.translator else 'Chrome sync failed — account saved locally anyway.'}"
                            f"{Style.RESET_ALL}"
                        )
                
                # Suppression nœud distant uniquement si le compte a été créé sur le nœud (mail jetable).
                if (
                    success
                    and not self.external_personal_mail
                    and config
                    and config.has_section('RemoteNode')
                    and config.get('RemoteNode', 'enabled', fallback='false').strip().lower() in ('true', '1', 'yes')
                ):
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
        """Get Account Information and Token. Dès la 2e étape (Review Settings / dashboard) le token est dispo, on essaie tout de suite."""
        try:
            start_time = time.time()
            try:
                current_url = self.signup_tab.url if hasattr(self.signup_tab, "url") else ""
            except Exception:
                current_url = ""
            print(f"{Fore.CYAN}{EMOJI['INFO']} Démarrage de la récupération du token et des infos compte (URL: {current_url or 'inconnue'})...{Style.RESET_ALL}")

            print(f"{Fore.CYAN}{EMOJI['WAIT']} {self.translator.get('register.get_token')}...{Style.RESET_ALL}")
            max_attempts = 24
            retry_interval = 1.2
            attempts = 0
            # D'abord essayer avec la page actuelle (souvent déjà dashboard après Review Settings)
            try_current_page_first = True

            while attempts < max_attempts:
                try:
                    if try_current_page_first and attempts == 0:
                        try_current_page_first = False
                        # Ne pas naviguer : on est peut-être déjà sur dashboard (2e étape)
                    else:
                        print(f"{Fore.CYAN}{EMOJI['WAIT']} Navigation vers la page settings pour lire le cookie (tentative {attempts + 1})...{Style.RESET_ALL}")
                        self.signup_tab.get(self.settings_url)
                        time.sleep(1.1)

                    cookies = self.signup_tab.cookies()
                    for cookie in cookies:
                        if cookie.get("name") == "WorkosCursorSessionToken":
                            raw_cookie = cookie.get("value") or ""
                            # Pas de serveur CN ici : le JWT du cookie suffit après inscription.
                            token = parse_workos_session_cookie(
                                raw_cookie, self.translator, allow_cn_refresh=False
                            )["access_token"]
                            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('register.token_success')}{Style.RESET_ALL}")
                            subscription = get_subscription_label_for_token(token)
                            usage_info = get_usage_summary_for_token(token)
                            if not self._save_account_info(
                                token, subscription, usage_info=usage_info, refresh_token=token
                            ):
                                return False
                            elapsed = time.time() - start_time
                            print(f"{Fore.CYAN}{EMOJI['INFO']} Récupération du token + infos compte terminée en {elapsed:.1f}s (tentatives: {attempts + 1}).{Style.RESET_ALL}")
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
            try:
                elapsed = time.time() - start_time
                print(f"{Fore.YELLOW}{EMOJI['WAIT']} Échec de la récupération du token après ~{elapsed:.1f}s.{Style.RESET_ALL}")
            except Exception:
                pass
            return False

    def _save_account_info(self, token, subscription, usage_info=None, refresh_token=None):
        """Save Account Information to File"""
        try:
            print(f"{Fore.CYAN}{EMOJI['KEY']} {self.translator.get('register.update_cursor_auth_info')}...{Style.RESET_ALL}")
            if not apply_cursor_session(
                translator=self.translator,
                email=self.email_address,
                access_token=token,
                refresh_token=refresh_token or token,
                auth_type="Auth_0",
                oauth_refresh=self.oauth_refresh_on_save,
            ):
                print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.cursor_auth_info_update_failed')}...{Style.RESET_ALL}")
                return False
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('register.cursor_auth_info_updated')}...{Style.RESET_ALL}")

            # Save account information to file using AccountManager
            account_manager = AccountManager(self.translator)
            if account_manager.save_account_info(self.email_address, self.password, token, subscription, usage_info=usage_info):
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

def main(translator=None, wait_for_enter: bool = True):
    """Main function to be called from main.py

    Args:
        translator: translator instance passed from main.
        wait_for_enter: si True, affiche \"Press Enter to Exit\" à la fin.
                        Utile pour l'option 2 directe, mais désactivé
                        quand on enchaîne dans un flux automatique (option 13).
    """
    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{EMOJI['START']} {translator.get('register.title')}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    registration = CursorRegistration(translator)
    ok = registration.start()

    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    if wait_for_enter:
        input(f"{EMOJI['INFO']} {translator.get('register.press_enter')}...")
    return bool(ok)


def main_external_mail(translator=None, wait_for_enter: bool = True):
    """Comme l’option 2, mais e-mail perso (Proton, etc.) et code de vérification saisi à la main."""
    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    title = (
        translator.get("register.title_external_mail")
        if translator
        else "Inscription Cursor — e-mail perso + code manuel"
    )
    print(f"{Fore.CYAN}{EMOJI['START']} {title}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    registration = CursorRegistration(
        translator,
        external_personal_mail=True,
        oauth_refresh_on_save=True,
    )
    ok = registration.start()

    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    if wait_for_enter:
        input(f"{EMOJI['INFO']} {translator.get('register.press_enter')}...")
    return bool(ok)


def main_sign_in_email_password(translator=None, wait_for_enter: bool = True):
    """Connexion web (e-mail + mot de passe Cursor), enregistrement du jeton et du compte, puis reset machine ID comme l’option 2."""
    import getpass

    from agent_cli_helper import automate_cursor_web_email_password_login

    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    title = (
        translator.get("register.sign_in_email_password_title")
        if translator
        else "Connexion Cursor — e-mail + mot de passe"
    )
    print(f"{Fore.CYAN}{EMOJI['KEY']} {title}{Style.RESET_ALL}")
    intro = (
        translator.get("register.sign_in_email_password_intro")
        if translator
        else "Un navigateur s’ouvre sur l’authenticator. Les identifiants ci-dessous sont aussi saisis automatiquement dans le flux."
    )
    print(f"{Fore.CYAN}{EMOJI['INFO']} {intro}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    ep = translator.get("register.sign_in_email_prompt") if translator else "E-mail : "
    em = input(ep).strip()
    if "@" not in em:
        print(
            f"{Fore.RED}{EMOJI['ERROR']} "
            f"{translator.get('register.invalid_email') if translator else 'Adresse e-mail invalide.'}{Style.RESET_ALL}"
        )
        if wait_for_enter:
            input(f"{EMOJI['INFO']} {translator.get('register.press_enter')}...")
        return False

    pp = translator.get("register.sign_in_password_prompt") if translator else "Mot de passe (saisie masquée) : "
    pw = getpass.getpass(pp).strip()
    if not pw:
        print(
            f"{Fore.RED}{EMOJI['ERROR']} "
            f"{translator.get('register.sign_in_password_empty') if translator else 'Mot de passe vide.'}{Style.RESET_ALL}"
        )
        if wait_for_enter:
            input(f"{EMOJI['INFO']} {translator.get('register.press_enter')}...")
        return False

    ok = automate_cursor_web_email_password_login(em, pw, translator)
    if ok:
        done_all = (
            translator.get("register.sign_in_completed")
            if translator
            else "Connexion, jeton enregistré — terminé."
        )
        print(f"{Fore.GREEN}{EMOJI['DONE']} {done_all}{Style.RESET_ALL}")
    else:
        fail = (
            translator.get("register.sign_in_failed")
            if translator
            else "Connexion ou enregistrement du jeton échoué."
        )
        print(f"{Fore.RED}{EMOJI['ERROR']} {fail}{Style.RESET_ALL}")

    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    if wait_for_enter:
        input(f"{EMOJI['INFO']} {translator.get('register.press_enter')}...")
    return bool(ok)


def change_email_domain(translator=None):
    """Allow user to change preferred email domain."""
    account_manager = AccountManager(translator)
    by_domain = account_manager.get_email_counts_by_domain()
    # Note: on n'affiche plus le récap "cursor_accounts.txt par domaine" au début.
    # On utilise seulement by_domain pour afficher le nombre juste à côté des domaines "node12.lan".

    # Bonus: ajouter l'e-mail "principal" actuellement stocké dans la base locale Cursor
    # si cet e-mail n'est pas présent dans cursor_accounts.txt.
    try:
        import sqlite3
        import sys as _sys
        from config import get_config as _get_config

        cfg = _get_config(translator)
        sqlite_path = None
        if _sys.platform == "win32" and cfg and cfg.has_section("WindowsPaths"):
            sqlite_path = cfg.get("WindowsPaths", "sqlite_path", fallback=None)
        elif _sys.platform == "linux" and cfg and cfg.has_section("LinuxPaths"):
            sqlite_path = cfg.get("LinuxPaths", "sqlite_path", fallback=None)
        elif _sys.platform == "darwin" and cfg and cfg.has_section("MacPaths"):
            sqlite_path = cfg.get("MacPaths", "sqlite_path", fallback=None)

        if sqlite_path and os.path.exists(sqlite_path):
            conn = sqlite3.connect(sqlite_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT value FROM ItemTable WHERE key = ?",
                ("cursorAuth/cachedEmail",),
            )
            row = cur.fetchone()
            conn.close()

            cached_email = (row[0] or "").strip() if row else ""
            if cached_email and "@" in cached_email:
                cached_email_l = cached_email.lower()
                saved_emails = {
                    (a.get("email") or "").strip().lower()
                    for a in account_manager.get_saved_accounts()
                    if (a.get("email") or "").strip()
                }
                if cached_email_l not in saved_emails:
                    cached_domain = cached_email_l.rsplit("@", 1)[-1].lower()
                    if cached_domain:
                        by_domain = by_domain or {}
                        by_domain[cached_domain] = by_domain.get(cached_domain, 0) + 1
    except Exception:
        # Si la DB Cursor est inaccessible, on continue quand même (comptage depuis le fichier).
        pass

    # Mark domains "épuisés" si radar-challenge a été détecté lors d'une inscription.
    radar_domains = set()
    try:
        radar_log_path = os.path.join(os.path.dirname(__file__), "radar_challenge_log.txt")
        if os.path.exists(radar_log_path):
            with open(radar_log_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = (line or "").strip().split("|")
                    # Format : iso_ts|email|domain|url
                    if len(parts) >= 3:
                        dn = (parts[2] or "").strip().lower()
                        if dn:
                            radar_domains.add(dn)
    except Exception:
        radar_domains = set()

    current = account_manager.get_preferred_domain() or account_manager.get_last_email_domain()
    if current:
        print(f"{Fore.CYAN}{EMOJI['INFO']} Domaine préféré / dernier utilisé: {current}{Style.RESET_ALL}")

    remote_domains = []
    try:
        from remote_user_manager import list_remote_mail_domains
        remote_domains = list_remote_mail_domains("node12.lan", "pi")
    except Exception:
        remote_domains = []

    new_domain = ""
    if remote_domains:
        print(f"{Fore.CYAN}{EMOJI['INFO']} Domaines trouvés sur node12.lan :{Style.RESET_ALL}")
        # Alignement vertical du "[nb]" : on formate en largeur fixe (les "\t" ne s'alignent pas toujours).
        max_domain_len = max(len((d or "").strip()) for d in remote_domains) if remote_domains else 0
        for idx, domain in enumerate(remote_domains, start=1):
            dn = (domain or "").strip().lower()
            n = by_domain.get(dn, 0) if by_domain else 0
            # Demande utilisateur : si radar-challenge → domaine épuisé → afficher nb=0
            if dn in radar_domains:
                n = 0
            # Demande utilisateur : "2 tab", mais on réalise l'alignement via une colonne fixe.
            # Exemple: "casinotruc.com        [3]"
            padded_domain = str(domain or "").strip().ljust(max_domain_len + 4)
            print(f"{Fore.GREEN}{idx}{Style.RESET_ALL}. {padded_domain}[{n}]")
        if radar_domains:
            exhausted = ", ".join(sorted(radar_domains))
            print(f"\n{Fore.YELLOW}{EMOJI['INFO']} Domaines épuisés (radar-challenge) : {exhausted}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}0{Style.RESET_ALL}. Saisie manuelle")

        choice = input(f"Choisissez un domaine (0-{len(remote_domains)}): ").strip()
        if choice.isdigit():
            choice_num = int(choice)
            if 1 <= choice_num <= len(remote_domains):
                new_domain = remote_domains[choice_num - 1]

    if not new_domain:
        new_domain = input("Nouveau nom de domaine (ex: example.com): ").strip().lower()

    if account_manager.set_preferred_domain(new_domain):
        print(f"{Fore.GREEN}{EMOJI['SUCCESS']} Domaine enregistré: {new_domain}{Style.RESET_ALL}")
        return True

    print(f"{Fore.RED}{EMOJI['ERROR']} Domaine invalide.{Style.RESET_ALL}")
    return False


def _default_reuse_min_days(translator=None) -> int:
    try:
        cfg = get_config(translator)
        if cfg and cfg.has_section("Account"):
            return max(0, int(cfg.get("Account", "reuse_min_days", fallback="31").strip()))
    except (ValueError, TypeError):
        pass
    return 31


def _is_google_saved_email(email: str) -> bool:
    em = (email or "").strip().lower()
    if "@" not in em:
        return False
    domain = em.rsplit("@", 1)[-1]
    return domain in AccountManager._GOOGLE_EMAIL_DOMAINS


def _chrome_logout_login_reuse_account(email: str, password: str, translator=None) -> bool:
    """Profil Chrome (loic5488@gmail.com) : logout session Cursor courante, login du compte cible."""
    from agent_cli_helper import (
        automate_cursor_web_email_password_login,
        automate_cursor_web_login_flow,
    )

    if _is_google_saved_email(email):
        return automate_cursor_web_login_flow(
            email.strip(),
            password,
            translator=translator,
            update_existing=True,
        )
    return automate_cursor_web_email_password_login(
        email.strip(),
        password,
        translator=translator,
        update_existing=True,
    )


def _finalize_reuse_account(account_manager, email: str, translator=None) -> bool:
    if account_manager.touch_account_created_at(email):
        msg = (
            translator.get("register.reuse_date_updated")
            if translator
            else "Date du compte mise à jour à aujourd’hui (ne sera plus proposé avant le délai minimum)."
        )
        print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {msg}{Style.RESET_ALL}")
    else:
        warn = (
            translator.get("register.reuse_date_update_failed")
            if translator
            else "Compte appliqué, mais impossible de mettre à jour la date dans cursor_accounts.txt."
        )
        print(f"{Fore.YELLOW}{EMOJI['INFO']} {warn}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{EMOJI['DONE']} Compte réutilisé avec succès.{Style.RESET_ALL}")
    return True


def reuse_existing_account(translator=None, min_days: int = None):
    """Réutilise un compte >= min_days jours ; remet Created At à aujourd’hui après succès."""
    if min_days is None:
        min_days = _default_reuse_min_days(translator)
    try:
        prompt = (
            translator.get("register.reuse_min_days_prompt", min_days=min_days)
            if translator
            else f"Âge minimum du compte en jours (Entrée = {min_days}): "
        )
        raw_days = input(prompt).strip()
        if raw_days:
            min_days = int(raw_days)
            if min_days < 0:
                raise ValueError("negative days")
    except Exception:
        print(f"{Fore.YELLOW}{EMOJI['INFO']} Valeur invalide, utilisation de {min_days} jours.{Style.RESET_ALL}")

    account_manager = AccountManager(translator)
    accounts = account_manager.get_reusable_accounts(min_days=min_days)
    if not accounts:
        print(f"{Fore.YELLOW}{EMOJI['INFO']} Aucun compte réutilisable (>= {min_days} jours) trouvé.{Style.RESET_ALL}")
        return False

    # Filtrer automatiquement les comptes dont le quota premium est atteint (à éviter).
    def _parse_bool(v):
        if isinstance(v, bool):
            return v
        s = str(v or "").strip().lower()
        if s in ("true", "1", "yes", "y", "oui", "o"):
            return True
        if s in ("false", "0", "no", "n", "non"):
            return False
        return None

    safe, avoided = [], []
    for a in accounts:
        reached = _parse_bool((a.get("usage_info") or {}).get("premium_limit_reached"))
        (avoided if reached is True else safe).append(a)

    if avoided:
        print(
            f"{Fore.YELLOW}{EMOJI['INFO']} {len(avoided)} compte(s) ignoré(s) car quota premium atteint (Premium Limit Reached=True).{Style.RESET_ALL}"
        )
    accounts = safe or accounts  # si tout est "évité", on affiche quand même tout

    def _quota_str(a: dict) -> str:
        ui = a.get("usage_info") or {}
        pu = ui.get("premium_usage")
        pl = ui.get("max_premium_usage")
        bu = ui.get("basic_usage")
        bl = ui.get("max_basic_usage")
        pr = ui.get("premium_limit_reached")
        # valeurs souvent string -> on affiche tel quel
        q = []
        if pu is not None or pl is not None:
            q.append(f"premium {pu if pu is not None else '?'} / {pl if pl is not None else '?'}")
        if bu is not None or bl is not None:
            q.append(f"basic {bu if bu is not None else '?'} / {bl if bl is not None else '?'}")
        reached = _parse_bool(pr)
        if reached is True:
            q.append("À ÉVITER")
        return " | ".join(q) if q else "quota: ?"

    print(f"\n{Fore.CYAN}{EMOJI['INFO']} Comptes réutilisables (>= {min_days} jours):{Style.RESET_ALL}")
    for idx, acc in enumerate(accounts, start=1):
        sub = (acc.get('subscription') or acc.get('usage_limit') or '—').strip() or '—'
        age = acc.get('age_days')
        quota = _quota_str(acc)
        print(f"{Fore.GREEN}{idx}{Style.RESET_ALL}. {acc['email']} | âge: {age} jours | abonnement: {sub} | {quota}")

    choice = input(f"Sélectionnez un compte (1-{len(accounts)}): ").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(accounts)):
        print(f"{Fore.RED}{EMOJI['ERROR']} Choix invalide.{Style.RESET_ALL}")
        return False

    selected = accounts[int(choice) - 1]
    token = selected.get('token')
    if not token:
        print(f"{Fore.RED}{EMOJI['ERROR']} Token manquant pour ce compte.{Style.RESET_ALL}")
        return False

    print(f"{Fore.CYAN}{EMOJI['KEY']} Application du compte: {selected['email']}{Style.RESET_ALL}")
    password = (selected.get("password") or "").strip()

    if password:
        start_msg = (
            translator.get("register.reuse_chrome_logout_login", email=selected["email"])
            if translator
            else (
                f"Profil Chrome : déconnexion de la session Cursor courante, "
                f"puis connexion avec {selected['email']}…"
            )
        )
        print(f"{Fore.CYAN}{EMOJI['INFO']} {start_msg}{Style.RESET_ALL}")
        if not _chrome_logout_login_reuse_account(selected["email"], password, translator):
            print(f"{Fore.RED}{EMOJI['ERROR']} Échec logout/login Chrome / mise à jour auth Cursor.{Style.RESET_ALL}")
            return False
        return _finalize_reuse_account(account_manager, selected["email"], translator)

    session_result = {}
    if not apply_cursor_session(
        translator=translator,
        email=selected["email"],
        access_token=token,
        refresh_token=token,
        auth_type="Auth_0",
        oauth_refresh=True,
        strict_oauth=True,
        session_result=session_result,
    ):
        msg = (
            translator.get("register.reuse_relogin_no_password")
            if translator
            else "Mot de passe absent dans cursor_accounts.txt — impossible de faire logout/login Chrome."
        )
        print(f"{Fore.YELLOW}{EMOJI['INFO']} {msg}{Style.RESET_ALL}")
        print(f"{Fore.RED}{EMOJI['ERROR']} Échec mise à jour auth Cursor.{Style.RESET_ALL}")
        return False

    new_token = (session_result.get("access_token") or "").strip()
    if new_token and new_token != token.strip():
        if account_manager.update_account_token(selected["email"], new_token):
            msg = (
                translator.get("register.reuse_token_updated")
                if translator
                else "Jeton mis à jour dans cursor_accounts.txt après rafraîchissement OAuth."
            )
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {msg}{Style.RESET_ALL}")

    return _finalize_reuse_account(account_manager, selected["email"], translator)


if __name__ == "__main__":
    from main import translator as main_translator
    main(main_translator) 