# Inscription Cursor avec e-mail jetable (API mail.tm) — même déroulé que l’option 2, menu séparé.
import time

from colorama import Fore, Style

from config import get_config
from cursor_register_manual import CursorRegistration, EMOJI, log


class CursorDisposableRegistration(CursorRegistration):
    """Même flux que CursorRegistration, mais l’adresse est toujours créée via mail.tm et le code vient de l’API."""

    def __init__(self, translator=None):
        super().__init__(translator)
        self._disposable_tab = None

    def setup_email(self):
        try:
            from email_tabs.disposable_mail_tab import DisposableMailTab

            config = get_config(self.translator)
            self._disposable_tab = DisposableMailTab.create_random(self.translator, config)
            self.email_address = self._disposable_tab.address

            print(
                f"{Fore.CYAN}{EMOJI['MAIL']} "
                f"{self.translator.get('register.disposable_mail_created', address=self.email_address) if self.translator else f'Adresse jetable : {self.email_address}'}{Style.RESET_ALL}"
            )
            if self.translator:
                print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('register.disposable_domain_hint')}{Style.RESET_ALL}")
            else:
                print(
                    f"{Fore.YELLOW}{EMOJI['INFO']} Certains expéditeurs bloquent les domaines jetables ; sinon utilisez l’option 2.{Style.RESET_ALL}"
                )

            if config and config.has_section("RemoteNode") and config.get(
                "RemoteNode", "enabled", fallback="false"
            ).strip().lower() in ("true", "1", "yes"):
                if config.get("RemoteNode", "create_user_on_register", fallback="true").strip().lower() in (
                    "true",
                    "1",
                    "yes",
                ):
                    from remote_user_manager import create_remote_user, email_to_username

                    ssh_host = config.get("RemoteNode", "host", fallback="").strip()
                    ssh_user = config.get("RemoteNode", "user", fallback="pi").strip() or "pi"
                    if ssh_host:
                        uname = email_to_username(self.email_address)
                        if uname:
                            create_remote_user(uname, self.password, ssh_host, ssh_user, self.translator)
                    else:
                        log.warning("RemoteNode enabled but host is empty")
            else:
                if self.translator:
                    print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('remote_user.enable_in_config')}{Style.RESET_ALL}")

            print(
                f"{Fore.CYAN}{EMOJI['MAIL']} {self.translator.get('register.email_address')}: {self.email_address}{Style.RESET_ALL}\n"
            )
            return True
        except Exception as e:
            log.exception("Disposable email setup failed: %s", e)
            print(
                f"{Fore.RED}{EMOJI['ERROR']} "
                f"{self.translator.get('register.disposable_mail_failed', error=str(e)) if self.translator else str(e)}{Style.RESET_ALL}"
            )
            return False

    def get_verification_code(self):
        tab = getattr(self, "_disposable_tab", None)
        if not tab:
            return None
        try:
            tab.refresh_inbox()
            time.sleep(1.2)
            if tab.check_for_cursor_email():
                code = tab.get_verification_code()
                if code and code.isdigit() and len(code) == 6:
                    return code
            return None
        except Exception as e:
            log.exception("Disposable get_verification_code: %s", e)
            return None

    def register_cursor(self):
        browser_tab = None
        try:
            print(f"{Fore.CYAN}{EMOJI['START']} {self.translator.get('register.register_start')}...{Style.RESET_ALL}")
            if not self._disposable_tab:
                print(f"{Fore.RED}{EMOJI['ERROR']} Boîte jetable non initialisée.{Style.RESET_ALL}")
                return False
            print(
                f"{Fore.CYAN}{EMOJI['MAIL']} "
                f"{self.translator.get('register.using_disposable_mail') if self.translator else 'API mail.tm pour le code de vérification'}{Style.RESET_ALL}"
            )

            from new_signup import main as new_signup_main

            result, browser_tab = new_signup_main(
                email=self.email_address,
                password=self.password,
                first_name=self.first_name,
                last_name=self.last_name,
                email_tab=self._disposable_tab,
                controller=self,
                translator=self.translator,
            )

            if result:
                self.signup_tab = browser_tab
                success = self._get_account_info()

                config = get_config(self.translator)
                if (
                    success
                    and config
                    and config.has_section("RemoteNode")
                    and config.get("RemoteNode", "enabled", fallback="false").strip().lower() in ("true", "1", "yes")
                ):
                    ssh_host = config.get("RemoteNode", "host", fallback="").strip()
                    ssh_user = config.get("RemoteNode", "user", fallback="pi").strip() or "pi"
                    remove_home = config.get("RemoteNode", "remove_home_on_delete", fallback="true").strip().lower() in (
                        "true",
                        "1",
                        "yes",
                    )
                    if ssh_host:
                        from remote_user_manager import delete_remote_user, email_to_username

                        uname = email_to_username(self.email_address)
                        if uname:
                            delete_remote_user(
                                uname, ssh_host, ssh_user, remove_home=remove_home, translator=self.translator
                            )

                if browser_tab:
                    try:
                        browser_tab.quit()
                    except Exception:
                        pass
                return success
            return False
        except Exception as e:
            log.exception("Disposable registration error: %s", e)
            print(
                f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('register.register_process_error', error=str(e))}{Style.RESET_ALL}"
            )
            return False
        finally:
            if browser_tab:
                try:
                    browser_tab.quit()
                except Exception:
                    pass


def main(translator=None, wait_for_enter: bool = True):
    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    title = translator.get("register.title_disposable") if translator else "Inscription Cursor (e-mail jetable)"
    print(f"{Fore.CYAN}{EMOJI['START']} {title}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    reg = CursorDisposableRegistration(translator)
    ok = reg.start()

    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    if wait_for_enter:
        input(f"{EMOJI['INFO']} {translator.get('register.press_enter')}...")
    return bool(ok)


def test_mail_api(translator=None):
    """Vérifie que l’API mail.tm est joignable (sans lancer d’inscription)."""
    from email_tabs.disposable_mail_tab import test_provider

    return test_provider(translator)
