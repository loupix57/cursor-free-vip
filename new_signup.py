from DrissionPage import ChromiumOptions, ChromiumPage
import time
import os
import signal
import random
import threading
from colorama import Fore, Style
import configparser
from pathlib import Path
import sys
from config import get_config
from utils import get_default_browser_path as utils_get_default_browser_path
from logger import get_logger

log = get_logger("new_signup")

# Add global variable at the beginning of the file
_translator = None

# Add global variable to track our Chrome processes
_chrome_process_ids = []

def cleanup_chrome_processes(translator=None):
    """Clean only Chrome processes launched by this script"""
    global _chrome_process_ids
    
    if not _chrome_process_ids:
        print("\nNo Chrome processes to clean...")
        return
        
    print("\nCleaning Chrome processes launched by this script...")
    try:
        if os.name == 'nt':
            for pid in _chrome_process_ids:
                try:
                    os.system(f'taskkill /F /PID {pid} /T 2>nul')
                except:
                    pass
        else:
            for pid in _chrome_process_ids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except:
                    pass
        _chrome_process_ids = []  # Reset the list after cleanup
    except Exception as e:
        if translator:
            print(f"{Fore.RED}❌ {translator.get('register.cleanup_error', error=str(e))}{Style.RESET_ALL}")
        else:
            print(f"Erreur lors du nettoyage des processus: {e}")

def signal_handler(signum, frame):
    """Handle Ctrl+C signal"""
    global _translator
    if _translator:
        print(f"{Fore.CYAN}{_translator.get('register.exit_signal')}{Style.RESET_ALL}")
    else:
        print("\nSignal de sortie reçu, fermeture en cours...")
    cleanup_chrome_processes(_translator)
    os._exit(0)

def simulate_human_input(page, url, config, translator=None):
    """Visit URL"""
    if translator:
        print(f"{Fore.CYAN}🚀 {translator.get('register.visiting_url')}: {url}{Style.RESET_ALL}")
    
    # First visit blank page
    page.get('about:blank')
    time.sleep(get_random_wait_time(config, 'page_load_wait'))
    
    # Visit target page
    page.get(url)
    time.sleep(get_random_wait_time(config, 'page_load_wait'))

def fill_signup_form(page, first_name, last_name, email, config, translator=None):
    """Fill signup form"""
    try:
        if translator:
            print(f"{Fore.CYAN}📧 {translator.get('register.filling_form')}{Style.RESET_ALL}")
        else:
            print("\nRemplissage du formulaire d'inscription...")
        
        # Fill first name
        first_name_input = page.ele("@name=first_name")
        if first_name_input:
            first_name_input.input(first_name)
            time.sleep(get_random_wait_time(config, 'input_wait'))
        
        # Fill last name
        last_name_input = page.ele("@name=last_name")
        if last_name_input:
            last_name_input.input(last_name)
            time.sleep(get_random_wait_time(config, 'input_wait'))
        
        # Fill email
        email_input = page.ele("@name=email")
        if email_input:
            email_input.input(email)
            time.sleep(get_random_wait_time(config, 'input_wait'))
        
        # Click submit button
        submit_button = page.ele("@type=submit")
        if submit_button:
            submit_button.click()
            time.sleep(get_random_wait_time(config, 'submit_wait'))
            
        if translator:
            print(f"{Fore.GREEN}✅ {translator.get('register.form_success')}{Style.RESET_ALL}")
        else:
            print("Form filled successfully")
        return True
        
    except Exception as e:
        if translator:
            print(f"{Fore.RED}❌ {translator.get('register.form_error', error=str(e))}{Style.RESET_ALL}")
        else:
            print(f"Error filling form: {e}")
        return False

def get_user_documents_path():
    """Get user Documents folder path"""
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Shell Folders") as key:
                documents_path, _ = winreg.QueryValueEx(key, "Personal")
                return documents_path
        except Exception as e:
            # fallback
            return os.path.join(os.path.expanduser("~"), "Documents")
    elif sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Documents")
    else:  # Linux
        # Get actual user's home directory
        sudo_user = os.environ.get('SUDO_USER')
        if sudo_user:
            return os.path.join("/home", sudo_user, "Documents")
        return os.path.join(os.path.expanduser("~"), "Documents")

def get_random_wait_time(config, timing_type='page_load_wait'):
    """
    Get random wait time from config
    Args:
        config: ConfigParser object
        timing_type: Type of timing to get (page_load_wait, input_wait, submit_wait)
    Returns:
        float: Random wait time or fixed time
    """
    try:
        if not config.has_section('Timing'):
            return random.uniform(0.1, 0.8)  # Default value
            
        if timing_type == 'random':
            min_time = float(config.get('Timing', 'min_random_time', fallback='0.1'))
            max_time = float(config.get('Timing', 'max_random_time', fallback='0.8'))
            return random.uniform(min_time, max_time)
            
        time_value = config.get('Timing', timing_type, fallback='0.1-0.8')
        
        # Check if it's a fixed time value
        if '-' not in time_value and ',' not in time_value:
            return float(time_value)  # Return fixed time
            
        # Process range time
        min_time, max_time = map(float, time_value.split('-' if '-' in time_value else ','))
        return random.uniform(min_time, max_time)
    except:
        return random.uniform(0.1, 0.8)  # Return default value when error

def setup_driver(translator=None):
    """Setup browser driver"""
    global _chrome_process_ids
    
    try:
        # Get config
        config = get_config(translator)
        
        # Get browser type and path
        browser_type = config.get('Browser', 'default_browser', fallback='chrome')
        browser_path = config.get('Browser', f'{browser_type}_path', fallback=utils_get_default_browser_path(browser_type))
        
        if not browser_path or not os.path.exists(browser_path):
            if translator:
                print(f"{Fore.YELLOW}⚠️ {browser_type} {translator.get('register.browser_path_invalid')}{Style.RESET_ALL}")
            browser_path = utils_get_default_browser_path(browser_type)

        # For backward compatibility, also check Chrome path
        if browser_type == 'chrome':
            chrome_path = config.get('Chrome', 'chromepath', fallback=None)
            if chrome_path and os.path.exists(chrome_path):
                browser_path = chrome_path

        # Set browser options
        co = ChromiumOptions()
        
        # Set browser path
        co.set_browser_path(browser_path)
        
        # Use incognito mode
        co.set_argument("--incognito")

        if sys.platform == "linux":
            # Set Linux specific options
            co.set_argument("--no-sandbox")
            
        # Set random port
        co.auto_port()
        
        # Use headless mode (must be set to False, simulate human operation)
        co.headless(False)
        
        # Log browser info
        if translator:
            print(f"{Fore.CYAN}🌐 {translator.get('register.using_browser', browser=browser_type, path=browser_path)}{Style.RESET_ALL}")
        
        try:
            # Load extension
            extension_path = os.path.join(os.getcwd(), "turnstilePatch")
            if os.path.exists(extension_path):
                co.set_argument("--allow-extensions-in-incognito")
                co.add_extension(extension_path)
        except Exception as e:
            if translator:
                print(f"{Fore.RED}❌ {translator.get('register.extension_load_error', error=str(e))}{Style.RESET_ALL}")
            else:
                print(f"Error loading extension: {e}")
        
        if translator:
            print(f"{Fore.CYAN}🚀 {translator.get('register.starting_browser')}{Style.RESET_ALL}")
        else:
            print("Starting browser...")
        
        # Record Chrome processes before launching
        before_pids = []
        try:
            import psutil
            browser_process_names = {
                'chrome': ['chrome', 'chromium'],
                'edge': ['msedge', 'edge'],
                'firefox': ['firefox'],
                'brave': ['brave', 'brave-browser']
            }
            process_names = browser_process_names.get(browser_type, ['chrome'])
            before_pids = [p.pid for p in psutil.process_iter() if any(name in p.name().lower() for name in process_names)]
        except:
            pass
            
        # Launch browser
        page = ChromiumPage(co)
        
        # Wait a moment for browser to fully launch
        time.sleep(1)
        
        # Record browser processes after launching and find new ones
        try:
            import psutil
            process_names = browser_process_names.get(browser_type, ['chrome'])
            after_pids = [p.pid for p in psutil.process_iter() if any(name in p.name().lower() for name in process_names)]
            # Find new browser processes
            new_pids = [pid for pid in after_pids if pid not in before_pids]
            _chrome_process_ids.extend(new_pids)
            
            if _chrome_process_ids:
                print(f"{translator.get('register.tracking_processes', count=len(_chrome_process_ids), browser=browser_type)}")
            else:
                print(f"{Fore.YELLOW}Warning: {translator.get('register.no_new_processes_detected', browser=browser_type)}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{translator.get('register.could_not_track_processes', browser=browser_type, error=str(e))}")
            
        return config, page

    except Exception as e:
        if translator:
            print(f"{Fore.RED}❌ {translator.get('register.browser_setup_error', error=str(e))}{Style.RESET_ALL}")
        else:
            print(f"Error setting up browser: {e}")
        raise


def _try_click_human_verification_widgets(page, translator=None):
    """
    Si une case / contrôle « vérification humaine » est visible (hors iframe Turnstile déjà géré plus bas),
    tente de le cocher ou cliquer (libellés type « human », « not a robot », « verify », etc.).
    """
    try:
        # 1) Cases à cocher liées à un libellé explicite (évite les cases newsletter)
        label_xpaths = [
            'xpath://label[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "human")]',
            'xpath://label[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "humain")]',
            'xpath://label[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "not a robot")]',
            'xpath://label[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "pas un robot")]',
            'xpath://label[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "verify you are human")]',
            'xpath://label[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "confirm you")]',
            'xpath://*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "verify you are human")]//input[@type="checkbox"]',
            'xpath://input[@type="checkbox"][ancestor::*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "human")]]',
            'xpath://input[@type="checkbox"][ancestor::*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "not a robot")]]',
            'xpath://button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "verify")]',
            'xpath://button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "verifier")]',
            'xpath://button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "humain")]',
            'xpath://button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "human")]',
        ]
        for xp in label_xpaths:
            try:
                el = page.ele(xp, timeout=0.35)
                if not el:
                    continue
                tag = (getattr(el, "tag", None) or "").lower()
                if tag == "input" and str(el.attr("type") or "").lower() == "checkbox":
                    if str(el.attr("checked") or "").lower() in ("true", "checked"):
                        return False
                    el.click()
                    if translator:
                        print(f"{Fore.CYAN}ℹ️ Case « vérification humaine » cochée.{Style.RESET_ALL}")
                    return True
                el.click()
                if translator:
                    print(f"{Fore.CYAN}ℹ️ Clic sur la vérification « humain » (libellé).{Style.RESET_ALL}")
                return True
            except Exception:
                continue

        # 2) Zone Turnstile visible (conteneur) — clic de secours si le widget est là mais pas encore traité
        try:
            host = page.ele("@id=cf-turnstile", timeout=0.4) or page.ele(
                'xpath://*[contains(@class, "cf-turnstile") or contains(@class, "turnstile")]', timeout=0.3
            )
            if host:
                box = host.ele("tag:input", timeout=0.5)
                if box:
                    box.click()
                    if translator:
                        print(f"{Fore.CYAN}ℹ️ Clic sur la case Turnstile (conteneur direct).{Style.RESET_ALL}")
                    return True
        except Exception:
            pass

        # 2b) Clic JS de secours sur le premier élément interactif "human/robot/verify"
        try:
            js_clicked = page.run_js(
                """
                (() => {
                  const targets = [...document.querySelectorAll('button,label,[role="button"],[role="checkbox"],div')];
                  const isVisible = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 2 && r.height > 2 && !!(el.offsetParent || getComputedStyle(el).position === 'fixed');
                  };
                  for (const el of targets) {
                    const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (!t) continue;
                    if (!(t.includes('human') || t.includes('humain') || t.includes('not a robot') || t.includes('verify'))) continue;
                    if (!isVisible(el)) continue;
                    el.click();
                    return true;
                  }
                  return false;
                })();
                """
            )
            if js_clicked:
                if translator:
                    print(f"{Fore.CYAN}ℹ️ Clic JS de secours sur le challenge humain.{Style.RESET_ALL}")
                return True
        except Exception:
            pass

        # 3) rôle checkbox ARIA près d’un texte « human » / « verify » (évite les faux positifs)
        try:
            cb = page.ele(
                'xpath://*[@role="checkbox" and (@aria-checked="false" or not(@aria-checked))]'
                '[ancestor::*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "human") '
                'or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "verify") '
                'or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "robot")]]',
                timeout=0.35,
            )
            if cb:
                cb.click()
                if translator:
                    print(f"{Fore.CYAN}ℹ️ Clic sur contrôle « humain » (role=checkbox).{Style.RESET_ALL}")
                return True
        except Exception:
            pass
    except Exception:
        pass
    return False


def handle_turnstile(page, config, translator=None):
    """Handle Turnstile verification"""
    try:
        log.info("Starting Turnstile verification")
        if translator:
            print(f"{Fore.CYAN}🔄 {translator.get('register.handling_turnstile')}{Style.RESET_ALL}")
        else:
            print("\nHandling Turnstile verification...")

        # Sur la page d'inscription / auth : tenter tout de suite de cocher une case « humain » si elle est affichée
        try:
            auth_url = page.url if hasattr(page, "url") else ""
            if (
                "authenticator.cursor" in auth_url
                or "sign-up" in auth_url
                or "sign_up" in auth_url.lower()
                or "/sign-in" in auth_url
            ):
                if _try_click_human_verification_widgets(page, translator):
                    time.sleep(0.4)
        except Exception:
            pass

        # Si on est déjà sur l'onboarding (Customize Your Experience, trial, etc.), considérer comme succès
        try:
            url = page.url if hasattr(page, 'url') else ''
            if 'onboarding' in url or '/trial' in url or 'cursor.com/dashboard' in url:
                log.info("Already on onboarding/dashboard page, skipping Turnstile")
                if translator:
                    print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
                return True
            if page.ele('xpath://button[contains(., "Continue")]', timeout=0.5) and page.ele('xpath://a[contains(., "Maybe Later")]', timeout=0.3):
                log.info("Continue + Maybe Later detected (onboarding), skipping Turnstile")
                if translator:
                    print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
                return True
        except Exception:
            pass

        # Écran "nous devons nous assurer que vous êtes humain" : souvent un clic manuel est requis.
        try:
            if _is_human_gate_screen(page):
                _try_click_human_verification_widgets(page, translator)
                # Si le badge de succès est déjà affiché, ne pas échouer immédiatement:
                # laisser la navigation finir puis valider.
                if _is_human_gate_success(page):
                    time.sleep(1.2)
                    if translator:
                        print(f"{Fore.CYAN}ℹ️ Vérification humaine validée, attente de la redirection...{Style.RESET_ALL}")
        except Exception:
            pass

        # Check first if verification is already successful (no need to retry)
        if check_verification_success(page, translator):
            log.info("Turnstile verification already successful, skipping retry")
            if translator:
                print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
            else:
                print("Verification already successful!")
            return True
        
        # from config
        turnstile_time = float(config.get('Turnstile', 'handle_turnstile_time', fallback='2'))
        random_time_str = config.get('Turnstile', 'handle_turnstile_random_time', fallback='1-3')
        
        # Parse random time range
        try:
            min_time, max_time = map(float, random_time_str.split('-'))
        except:
            min_time, max_time = 1, 3  # Default value
        
        max_retries = 1  # Reduced from 2 to 1 to avoid unnecessary retries
        retry_count = 0

        while retry_count < max_retries:
            retry_count += 1
            if retry_count > 1:
                if translator:
                    print(f"{Fore.CYAN}🔄 {translator.get('register.retry_verification', attempt=retry_count)}{Style.RESET_ALL}")
                else:
                    print(f"Retry attempt {retry_count}...")
                time.sleep(random.uniform(min_time, max_time))

            try:
                # Try to reset turnstile
                page.run_js("try { turnstile.reset() } catch(e) { }")
                time.sleep(turnstile_time)  # from config
                _try_click_human_verification_widgets(page, translator)

                # Locate verification box element (dans un thread avec timeout 15s max pour éviter ~2 min d'attente)
                challenge_check = None
                def _find_turnstile():
                    nonlocal challenge_check
                    try:
                        challenge_check = (
                            page.ele("@id=cf-turnstile", timeout=3)
                            .child()
                            .shadow_root.ele("tag:iframe")
                            .ele("tag:body")
                            .sr("tag:input")
                        )
                    except Exception:
                        pass
                th = threading.Thread(target=_find_turnstile, daemon=True)
                th.start()
                th.join(timeout=15)
                if th.is_alive():
                    log.debug("Turnstile element lookup timed out after 15s")

                if challenge_check:
                    if translator:
                        print(f"{Fore.CYAN}🔄 {translator.get('register.detect_turnstile')}{Style.RESET_ALL}")
                    else:
                        print("Detected verification box...")
                    
                    # from config
                    time.sleep(random.uniform(min_time, max_time))
                    challenge_check.click()
                    time.sleep(turnstile_time)  # from config

                    # check verification result
                    if check_verification_success(page, translator):
                        log.info("Turnstile verification successful after click")
                        if translator:
                            print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
                        else:
                            print("Verification successful!")
                        return True
                else:
                    # No challenge box found, check if already verified
                    if check_verification_success(page, translator):
                        log.info("Turnstile verification successful (no challenge box)")
                        if translator:
                            print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
                        else:
                            print("Verification successful!")
                        return True

            except Exception as e:
                log.debug("Turnstile attempt error: %s", e)
                # Don't print error on first attempt, only on retries
                if retry_count > 1:
                    if translator:
                        print(f"{Fore.YELLOW}⚠️ {translator.get('register.verification_attempt_failed')}{Style.RESET_ALL}")
                    else:
                        print(f"Verification attempt failed: {e}")

            # Check if verification has been successful after attempt
            if check_verification_success(page, translator):
                log.info("Turnstile verification successful after attempt")
                if translator:
                    print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
                else:
                    print("Verification successful!")
                return True

        # Final check before giving up
        if check_verification_success(page, translator):
            log.info("Turnstile verification successful on final check")
            if translator:
                print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
            else:
                print("Verification successful!")
            return True

        log.warning("Turnstile verification failed after all attempts")
        if translator:
            print(f"{Fore.RED}❌ {translator.get('register.verification_failed')}{Style.RESET_ALL}")
        else:
            print("Verification failed after all attempts")
        return False

    except Exception as e:
        log.exception("Turnstile verification error: %s", e)
        if translator:
            print(f"{Fore.RED}❌ {translator.get('register.verification_error', error=str(e))}{Style.RESET_ALL}")
        else:
            print(f"Error in verification process: {e}")
        return False


def _is_human_gate_screen(page) -> bool:
    try:
        url = (page.url if hasattr(page, "url") else "") or ""
        lu = url.lower()
        if "authenticator.cursor.sh/sign-up/password" in lu:
            if (
                page.ele('xpath://*[contains(., "nous devons nous assurer que vous êtes humain")]', timeout=0.2)
                or page.ele('xpath://*[contains(., "we need to verify you are human")]', timeout=0.2)
                or page.ele('xpath://*[contains(., "verify you are human")]', timeout=0.2)
            ):
                return True
        return False
    except Exception:
        return False


def _is_human_gate_success(page) -> bool:
    try:
        return bool(
            page.ele('xpath://*[contains(., "Succès")]', timeout=0.2)
            or page.ele('xpath://*[contains(., "Success")]', timeout=0.2)
        )
    except Exception:
        return False


def handle_post_verification_onboarding(page, config, translator=None):
    """
    Étapes à franchir avant de rafraîchir le token (dans l'ordre possible) :
    1) Data Sharing (cursor.com/dashboard) : toggle "Share Data" OFF puis Continue
    2) Customize Your Experience (onboarding/role) : Maybe Later ou Continue
    3) Claim your free Pro trial (trial) : Skip for now
    4) Review Settings (dashboard) : Continue
    On boucle jusqu'à 6 étapes ou jusqu'à arriver sur settings.
    """
    try:
        base_wait = get_random_wait_time(config, 'verification_success_wait')
        # Onboarding doit être très rapide : borne le délai à ~0.3–1s
        wait = max(0.3, min(base_wait, 1.0))
        start_time = time.time()
        last_url = ""
        deferred_setup_clicked = False

        if translator:
            print(f"{Fore.CYAN}ℹ️ Post-vérification : début du passage des écrans d’onboarding...{Style.RESET_ALL}")

        # Jusqu'à 6 itérations max : role → trial → dashboard/share-data → settings
        for step in range(6):
            url = ""
            time.sleep(wait)
            try:
                url = page.url if hasattr(page, 'url') else ''
                last_url = url or last_url

                # Log détaillé de la step + URL + type de page détecté
                page_type = "inconnue"
                if 'onboarding/role' in url:
                    page_type = "onboarding/role"
                elif '/trial' in url:
                    page_type = "trial"
                elif 'start-download' in url:
                    page_type = "start_download"
                elif 'dashboard?tab=settings' in url or 'cursor.com/dashboard/settings' in url:
                    page_type = "dashboard_settings"
                elif 'cursor.com/settings' in url:
                    page_type = "settings"
                elif 'cursor.com/dashboard' in url:
                    page_type = "dashboard"

                if translator:
                    print(
                        f"{Fore.CYAN}ℹ️ Step post‑vérif {step + 1}/6 – URL: {url or 'inconnue'} (page: {page_type}){Style.RESET_ALL}"
                    )

                # Blocage anti-abus côté Cursor : vérification téléphone/SMS obligatoire.
                if _is_phone_verification_challenge(page, url):
                    print(
                        f"{Fore.YELLOW}⚠️ Phone verification challenge detected (radar-challenge). "
                        f"Automatic flow is paused here and requires manual completion in browser.{Style.RESET_ALL}"
                    )
                    return False

                # Vérifier très tôt à CHAQUE étape si le partage de données est activé.
                _ensure_share_data_disabled(page, translator)

                # Page /trial : case marketing + « Skip for now » uniquement (ne pas cliquer « Continue » ni sauter vers start-download).
                if '/trial' in url and 'cursor.com' in url:
                    _ensure_trial_marketing_opt_out_checkbox(page, translator)
                    if _safe_click_skip_for_now_trial(page, translator):
                        clicked = True
                        _log_step(step, "Skip for now", translator)
                        time.sleep(get_random_wait_time(config, 'page_load_wait'))
                        continue

                clicked = False

                # PRIORITÉ : écran « Connect GitHub/GitLab to finish setup » (start-download OU settings).
                # Ne jamais utiliser un xpath //*[contains(., "Maybe later")] : le clic tombe sur Connect GitHub/GitLab.
                if not clicked and _is_connect_provider_setup_page(page):
                    if _safe_click_maybe_later_on_provider_setup(page, translator):
                        clicked = True
                        deferred_setup_clicked = True
                        _log_step(step, "Maybe later", translator)

                # Page 1: Customize Your Experience → cliquer en priorité sur "Skip for now" / "Maybe Later"
                if 'onboarding/role' in url and not clicked:
                    for label in ("Skip for now", "Skip", "Passer", "Maybe Later", "Maybe later"):
                        try:
                            # Bouton
                            btn = page.ele(f'xpath://button[contains(., "{label}")]', timeout=0.6)
                            if not btn:
                                # Lien éventuel
                                btn = page.ele(f'xpath://a[contains(., "{label}")]', timeout=0.6)
                            if btn:
                                btn.click()
                                clicked = True
                                _log_step(step, label, translator)
                                break
                        except Exception:
                            continue

                # Page 3: écran "You're all set! Download Cursor" → cliquer sur "I'll do this later"
                if 'start-download' in url and not clicked:
                    for label in (
                        "I'll do this later",
                        "I’ll do this later",  # apostrophe typographique éventuelle
                        "I will do this later",
                        "Je le ferai plus tard",
                    ):
                        try:
                            btn = page.ele(f'xpath://button[contains(., "{label}")]', timeout=0.8)
                            if not btn:
                                btn = page.ele(f'xpath://a[contains(., "{label}")]', timeout=0.8)
                            if btn:
                                btn.click()
                                clicked = True
                                _log_step(step, label, translator)
                                break
                        except Exception:
                            continue

                # Page "Connect GitHub to finish setup" sur dashboard/settings → cliquer "Maybe later" / variantes
                if ('dashboard/settings' in url or 'dashboard?tab=settings' in url or 'cursor.com/settings' in url) and not clicked:
                    # Priorité 1: écran "Review Settings" (pas l'écran Connect GitHub) → bouton Continue
                    try:
                        is_connect_setup = (
                            page.ele('xpath://*[contains(., "Connect GitHub to finish setup")]', timeout=0.4)
                            or page.ele('xpath://button[contains(., "Connect GitHub")]', timeout=0.3)
                            or page.ele('xpath://button[contains(., "Connect GitLab")]', timeout=0.3)
                        )
                        if not is_connect_setup:
                            review_continue = page.ele('xpath://button[contains(., "Continue")]', timeout=0.8)
                            if review_continue:
                                review_continue.click()
                                clicked = True
                                _log_step(step, "Continue", translator)
                    except Exception:
                        pass

                # Même écran sur settings (si pas déjà traité ci-dessus) : variantes texte sur <a>/<button> uniquement
                if ('dashboard/settings' in url or 'dashboard?tab=settings' in url or 'cursor.com/settings' in url) and not clicked:
                    for label in (
                        "I'll do this later",
                        "I’ll do this later",
                        "No thanks",
                        "Not now",
                        "Skip for now",
                        "Plus tard",
                    ):
                        try:
                            btn = page.ele(f'xpath://button[contains(., "{label}")]', timeout=0.5)
                            if not btn:
                                btn = page.ele(f'xpath://a[contains(., "{label}")]', timeout=0.5)
                            if btn:
                                btn.click()
                                clicked = True
                                deferred_setup_clicked = True
                                _log_step(step, label, translator)
                                break
                        except Exception:
                            continue
                    if not clicked and _is_connect_provider_setup_page(page):
                        if _safe_click_maybe_later_on_provider_setup(page, translator):
                            clicked = True
                            deferred_setup_clicked = True
                            _log_step(step, "Maybe later", translator)

                # Optimisation: si on vient de cliquer un bouton de report ("later")
                # et qu'on est déjà sur dashboard/settings, inutile de continuer la boucle.
                if deferred_setup_clicked and (
                    'dashboard/settings' in url
                    or 'dashboard?tab=settings' in url
                    or 'cursor.com/settings' in url
                ):
                    # Petite pause pour laisser la navigation se stabiliser si nécessaire.
                    time.sleep(0.25)
                    try:
                        stabilized_url = page.url if hasattr(page, 'url') else url
                    except Exception:
                        stabilized_url = url
                    if translator:
                        elapsed = time.time() - start_time
                        print(f"{Fore.CYAN}ℹ️ Onboarding terminé (bouton \"later\" cliqué), URL: {stabilized_url or 'inconnue'} en {elapsed:.1f}s.{Style.RESET_ALL}")
                    return True

                # Cas 1 : on est déjà sur la page Settings (toutes variantes d'URL), sans bouton "Continue" → fin immédiate
                if (
                    (
                        'cursor.com/settings' in url
                        or 'dashboard?tab=settings' in url
                        or 'cursor.com/dashboard/settings' in url
                    )
                    and not page.ele('xpath://button[contains(., "Continue")]', timeout=0.3)
                ):
                    if translator:
                        elapsed = time.time() - start_time
                        print(f"{Fore.CYAN}ℹ️ Onboarding terminé, page settings détectée en {elapsed:.1f}s.{Style.RESET_ALL}")
                    return True

                # Cas 2 : simple dashboard sans autres écrans (pas de bouton "Continue") → on considère l'onboarding comme terminé
                if 'cursor.com/dashboard' in url and not any(
                    page.ele(sel, timeout=0.3)
                    for sel in [
                        'xpath://button[contains(., "Continue")]',
                        'xpath://button[contains(., "Start")]',
                        'xpath://button[contains(., "Next")]',
                    ]
                ):
                    if translator:
                        elapsed = time.time() - start_time
                        print(f"{Fore.CYAN}ℹ️ Onboarding terminé, page dashboard détectée en {elapsed:.1f}s.{Style.RESET_ALL}")
                    return True
                if page.ele("Account Settings", timeout=0.5):
                    if translator:
                        elapsed = time.time() - start_time
                        print(f"{Fore.CYAN}ℹ️ Onboarding terminé, écran Account Settings détecté en {elapsed:.1f}s.{Style.RESET_ALL}")
                    return True
            except Exception:
                pass

            # 1) Data Sharing : revérifier aussi en fin d'étape.
            _ensure_share_data_disabled(page, translator)

            # 1b) Retry : parfois le lien « Maybe later » n’est pas encore cliquable en début d’étape.
            if not clicked and _is_connect_provider_setup_page(page):
                if _safe_click_maybe_later_on_provider_setup(page, translator):
                    clicked = True
                    deferred_setup_clicked = True
                    _log_step(step, "Maybe later", translator)

            # 2) Boutons / liens génériques : Skip for now, Maybe later, Continue, etc.
            # Sur l’écran Connect GitHub/GitLab, ne pas enchaîner des clics génériques qui pourraient viser le mauvais contrôle.
            # Sur /trial : ne JAMAIS cliquer « Continue » (paiement / suite) — uniquement Skip for now.
            try:
                cur_u = page.url if hasattr(page, "url") else ""
            except Exception:
                cur_u = ""
            on_trial = "/trial" in cur_u and "cursor.com" in cur_u

            if not (_is_connect_provider_setup_page(page) and not clicked):
                if on_trial and not clicked:
                    _ensure_trial_marketing_opt_out_checkbox(page, translator)
                    if _safe_click_skip_for_now_trial(page, translator):
                        clicked = True
                        _log_step(step, "Skip for now", translator)
                btn_labels = (
                    ("Skip for now", "Maybe Later", "Maybe later", "Skip", "Passer", "Plus tard")
                    if on_trial
                    else ("Skip for now", "Maybe Later", "Maybe later", "Continue", "Continuer", "Let me later", "Plus tard", "Skip", "Passer")
                )
                for label in btn_labels:
                    if clicked:
                        break
                    try:
                        btn = page.ele(f'xpath://button[contains(., "{label}")]', timeout=0.5)
                        if btn:
                            btn.click()
                            clicked = True
                            _log_step(step, label, translator)
                            break
                    except Exception:
                        continue
                if not clicked:
                    link_labels = (
                        ("Skip for now", "Maybe Later", "Maybe later", "Plus tard")
                        if on_trial
                        else ("Skip for now", "Maybe Later", "Maybe later", "Continue", "Continuer", "Plus tard")
                    )
                    for label in link_labels:
                        try:
                            link = page.ele(f'xpath://a[contains(., "{label}")]', timeout=0.5)
                            if link:
                                link.click()
                                clicked = True
                                _log_step(step, label, translator)
                                break
                        except Exception:
                            continue
                if not clicked and not on_trial:
                    try:
                        any_btn = page.ele("Continue", timeout=0.5) or page.ele("Continuer", timeout=0.5) or page.ele("Skip for now", timeout=0.5) or page.ele("Maybe Later", timeout=0.5)
                        if any_btn:
                            any_btn.click()
                            clicked = True
                            _log_step(step, "continue/skip", translator)
                    except Exception:
                        pass

        # Si on sort de la boucle sans retour explicite, logguer l’URL courante pour le debug
        if translator:
            elapsed = time.time() - start_time
            safe_url = last_url or (page.url if hasattr(page, 'url') else '')
            print(f"{Fore.CYAN}ℹ️ Onboarding terminé après 6 itérations (durée ~{elapsed:.1f}s), URL actuelle : {safe_url}{Style.RESET_ALL}")
        return True
    except Exception as e:
        log.debug("Post-verification onboarding: %s", e)
        return True  # Ne pas bloquer le flux


def _log_step(step, label, translator=None):
    msg = f"Étape {step + 1} : {label}..." if translator and 'fr' in str(getattr(translator, 'locale', '') or '') else f"Step {step + 1}: {label}..."
    print(f"{Fore.CYAN}🔄 {msg}{Style.RESET_ALL}")


def _is_phone_verification_challenge(page, current_url: str = "") -> bool:
    """Detect Cursor radar-challenge page asking for phone/SMS verification."""
    try:
        url = (current_url or (page.url if hasattr(page, "url") else "") or "").lower()
    except Exception:
        url = (current_url or "").lower()

    if "authenticator.cursor.sh/radar-challenge" in url:
        return True

    # Fallback selectors when URL did not update yet.
    checks = [
        'xpath://h1[contains(., "Saisissez votre numéro de téléphone")]',
        'xpath://h1[contains(., "Enter your phone number")]',
        'xpath://button[contains(., "Envoyer le code de vérification")]',
        'xpath://button[contains(., "Send verification code")]',
        'xpath://input[@type="tel"]',
    ]
    for sel in checks:
        try:
            if page.ele(sel, timeout=0.25):
                return True
        except Exception:
            continue
    return False


def _is_connect_provider_setup_page(page):
    """Écran « Connect GitHub/GitLab to finish setup » (souvent start-download ou dashboard/settings)."""
    try:
        # Ne pas confondre avec l’écran « Review Settings » (liste d’intégrations + Continue).
        if page.ele('xpath://*[contains(., "Review Settings")]', timeout=0.2):
            return False
        if page.ele('xpath://*[contains(., "Connect GitHub to finish setup")]', timeout=0.4):
            return True
        if page.ele('xpath://h1[contains(., "Connect GitHub to finish setup")]', timeout=0.25):
            return True
        gh = page.ele('xpath://button[contains(., "Connect GitHub")]', timeout=0.35)
        gl = page.ele('xpath://button[contains(., "Connect GitLab")]', timeout=0.35)
        if gh or gl:
            # Même sans titre encore rendu, présence des deux gros boutons + lien Maybe later = cet écran
            if page.ele(
                'xpath://a[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "maybe later")]',
                timeout=0.35,
            ):
                return True
    except Exception:
        pass
    return False


def _safe_click_maybe_later_on_provider_setup(page, translator=None):
    """
    Clic UNIQUEMENT sur un lien ou bouton dont le texte est essentiellement « Maybe later ».
    Ne pas utiliser //*[contains(., "Maybe later")] : un ancêtre englobe toute la carte ;
    le clic au centre tombe sur « Connect GitHub » / « Connect GitLab » et ouvre des onglets OAuth.
    """
    # Ciblage strict : "Maybe later" / "Plus tard" uniquement.
    # Tentative JS d'abord (plus robuste que certains clics Selenium-like sur texte gris).
    try:
        js_ok = page.run_js(
            """
            (() => {
              const candidates = [...document.querySelectorAll('a,button,[role="link"],[role="button"],span,div,p')];
              const normalize = (s) => (s || '').trim().toLowerCase().replace(/\\s+/g, ' ');
              const visible = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 2 && r.height > 2 && !!(el.offsetParent || getComputedStyle(el).position === 'fixed');
              };
              const clickableAncestor = (el) => {
                let cur = el;
                for (let i = 0; i < 5 && cur; i++) {
                  const tag = (cur.tagName || '').toLowerCase();
                  const role = (cur.getAttribute && cur.getAttribute('role')) || '';
                  if (tag === 'a' || tag === 'button' || role === 'link' || role === 'button') return cur;
                  cur = cur.parentElement;
                }
                return el;
              };
              for (const el of candidates) {
                const txt = normalize(el.innerText || el.textContent);
                if (!(txt === 'maybe later' || txt === 'plus tard')) continue;
                if (!visible(el)) continue;
                const target = clickableAncestor(el);
                target.scrollIntoView({ block: 'center', inline: 'center' });
                try { target.click(); } catch (_) {}
                // fallback événement souris pour UI qui ignore click() direct
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
            if translator:
                print(f"{Fore.CYAN}ℹ️ Clic JS sécurisé sur « Maybe later ».{Style.RESET_ALL}")
            return True
    except Exception:
        pass

    xpaths = [
        'xpath://a[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "maybe later")]',
        'xpath://button[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "maybe later")]',
        'xpath://*[@role="link" and contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "maybe later")]',
    ]
    for xp in xpaths:
        try:
            el = page.ele(xp, timeout=0.7)
            if not el:
                continue
            raw = (getattr(el, "text", None) or "").strip().lower()
            if "maybe later" not in raw:
                continue
            if "connect github" in raw or "connect gitlab" in raw:
                continue
            el.click()
            if translator:
                print(f"{Fore.CYAN}ℹ️ Clic sécurisé sur « Maybe later » (écran Connect GitHub/GitLab).{Style.RESET_ALL}")
            return True
        except Exception:
            continue
    return False


def _ensure_trial_marketing_opt_out_checkbox(page, translator=None):
    """
    Page Pro /trial : coche « I do not want to receive marketing emails from Cursor » si présente et pas déjà cochée.
    """
    try:
        xpaths = [
            'xpath://label[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "marketing emails")]//input[@type="checkbox"]',
            'xpath://label[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "do not want to receive")]//input[@type="checkbox"]',
            'xpath://input[@type="checkbox"][ancestor::*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "marketing emails")]]',
            'xpath://input[@type="checkbox"][ancestor::*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "do not want to receive")]]',
        ]
        for xp in xpaths:
            cb = page.ele(xp, timeout=0.6)
            if not cb:
                continue
            checked = str(cb.attr("checked") or "").lower() in ("true", "checked", "1")
            try:
                if hasattr(cb, "states") and cb.states and getattr(cb.states, "is_selected", None):
                    checked = checked or bool(cb.states.is_selected)
            except Exception:
                pass
            if checked:
                return True
            cb.click()
            time.sleep(0.25)
            if translator:
                print(f"{Fore.CYAN}ℹ️ Case « pas d’e-mails marketing » cochée.{Style.RESET_ALL}")
            return True
        lab = page.ele(
            'xpath://label[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "marketing emails")]',
            timeout=0.4,
        )
        if lab:
            lab.click()
            time.sleep(0.2)
            if translator:
                print(f"{Fore.CYAN}ℹ️ Case marketing (clic sur le libellé).{Style.RESET_ALL}")
            return True
    except Exception:
        pass
    return False


def _safe_click_skip_for_now_trial(page, translator=None):
    """
    Page /trial : clic uniquement sur le lien/bouton « Skip for now » (sous Continue).
    Ne pas utiliser la boucle générique : elle cliquait sur « Continue » avant le lien.
    """
    xpaths = [
        'xpath://a[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "skip for now")]',
        'xpath://button[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "skip for now")]',
        'xpath://*[@role="link" and contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "skip for now")]',
    ]
    for xp in xpaths:
        try:
            el = page.ele(xp, timeout=0.9)
            if not el:
                continue
            raw = (getattr(el, "text", None) or "").strip().lower()
            if "skip for now" not in raw:
                continue
            if "continue" in raw and "skip" not in raw:
                continue
            el.click()
            if translator:
                print(f"{Fore.CYAN}ℹ️ Clic sécurisé sur « Skip for now » (page trial).{Style.RESET_ALL}")
            return True
        except Exception:
            continue
    return False


def _ensure_share_data_disabled(page, translator=None):
    """
    Essaie de désactiver 'Share Data' si activé.
    Appelé à chaque étape de l'onboarding pour éviter de rater le toggle.
    """
    try:
        toggled = False

        # Ciblage précis via bloc contenant "Share Data" / "partage"
        share_switch = page.ele(
            'xpath://*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "share data") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "partage")]//*[@role="switch"]',
            timeout=0.4
        )
        if share_switch and str(share_switch.attr('aria-checked') or '').lower() == 'true':
            share_switch.click()
            toggled = True

        # Fallback checkbox dans un bloc "Share Data"
        if not toggled:
            share_checkbox = page.ele(
                'xpath://*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "share data") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "partage")]//input[@type="checkbox"]',
                timeout=0.4
            )
            if share_checkbox and (
                share_checkbox.attr('checked')
                or (getattr(share_checkbox, 'state', None) and 'checked' in str(share_checkbox.state).lower())
            ):
                share_checkbox.click()
                toggled = True

        # Dernier fallback : switch global si visible et activé
        if not toggled:
            any_switch = page.ele('xpath://*[@role="switch"]', timeout=0.3)
            if any_switch and str(any_switch.attr('aria-checked') or '').lower() == 'true':
                any_switch.click()
                toggled = True

        if toggled:
            time.sleep(0.3)
            if translator:
                print(f"{Fore.CYAN}🔄 Désactivation du partage de données...{Style.RESET_ALL}")
            return True
    except Exception:
        pass
    return False


def run_onboarding_and_go_to_settings(browser_tab, config, translator=None):
    """
    Centralise la séquence après la réussite de la vérification :
    - si l’on est tombé directement sur /trial, on force un passage préalable par /onboarding/role
    - puis on enchaîne les écrans d’onboarding
    - puis on va sur /dashboard?tab=settings et on refait une passe rapide si besoin.
    """
    try:
        try:
            current_url = browser_tab.url if hasattr(browser_tab, 'url') else ''
        except Exception:
            current_url = ''

        # Si Cursor nous a envoyés directement sur /trial, forcer d'abord /onboarding/role
        if '/trial' in current_url and 'onboarding/role' not in current_url:
            role_url = "https://cursor.com/onboarding/role?next=%2Ftrial%3FreturnTo%3D%252Fdashboard"
            if translator:
                print(f"{Fore.CYAN}ℹ️ Redirection vers la page d’onboarding (rôle) avant de continuer...{Style.RESET_ALL}")
            browser_tab.get(role_url)
            time.sleep(get_random_wait_time(config, 'page_load_wait'))
    except Exception:
        # Ne jamais bloquer le flux si la redirection échoue
        pass

    # 1) Passer les écrans d’onboarding (role → trial → start-download / dashboard)
    if not handle_post_verification_onboarding(browser_tab, config, translator):
        return False

    # 2) Aller sur la page settings pour lire le cookie
    if translator:
        print(f"{Fore.CYAN}🔑 {translator.get('register.visiting_url')}: https://www.cursor.com/dashboard?tab=settings{Style.RESET_ALL}")
    browser_tab.get("https://www.cursor.com/dashboard?tab=settings")
    time.sleep(get_random_wait_time(config, 'settings_page_load_wait'))

    # 3) Dernière passe au cas où Cursor affiche encore un écran intermédiaire
    if not handle_post_verification_onboarding(browser_tab, config, translator):
        return False
    return True


def check_verification_success(page, translator=None):
    """Check if verification is successful"""
    try:
        # Check if there is a subsequent form element, indicating verification has passed
        if (page.ele("@name=password", timeout=0.5) or 
            page.ele("@name=email", timeout=0.5) or
            page.ele("@data-index=0", timeout=0.5) or
            page.ele("Account Settings", timeout=0.5)):
            return True
        
        # Check if there is an error message
        error_messages = [
            'xpath://div[contains(text(), "Can\'t verify the user is human")]',
            'xpath://div[contains(text(), "Error: 600010")]',
            'xpath://div[contains(text(), "Please try again")]'
        ]
        
        for error_xpath in error_messages:
            if page.ele(error_xpath):
                return False
            
        return False
    except:
        return False

def generate_password(length=12):
    """Generate random password"""
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    return ''.join(random.choices(chars, k=length))

def fill_password(page, password: str, config, translator=None):
    """
    Fill password form
    """
    try:
        print(f"{Fore.CYAN}🔑 {translator.get('register.setting_password') if translator else 'Setting password'}{Style.RESET_ALL}")
        
        # Fill password
        password_input = page.ele("@name=password")
        print(f"{Fore.CYAN}🔑 {translator.get('register.setting_on_password')}: {password}{Style.RESET_ALL}")
        if password_input:
            password_input.input(password)

        # Click submit button
        submit_button = page.ele("@type=submit")
        if submit_button:
            submit_button.click()
            time.sleep(get_random_wait_time(config, 'submit_wait'))
            
        print(f"{Fore.GREEN}✅ {translator.get('register.password_submitted') if translator else 'Password submitted'}{Style.RESET_ALL}")
        
        return True
        
    except Exception as e:
        print(f"{Fore.RED}❌ {translator.get('register.password_error', error=str(e)) if translator else f'Error setting password: {str(e)}'}{Style.RESET_ALL}")

        return False

def handle_verification_code(browser_tab, email_tab, controller, config, translator=None):
    """Handle verification code"""
    try:
        log.info("handle_verification_code: email_tab=%s", "yes" if email_tab else "manual")
        if translator:
            print(f"\n{Fore.CYAN}🔄 {translator.get('register.waiting_for_verification_code')}{Style.RESET_ALL}")
            
        # Check if using manual input verification code
        if hasattr(controller, 'get_verification_code') and email_tab is None:  # Manual mode
            verification_code = controller.get_verification_code()
            if verification_code:
                log.info("Manual verification code received, filling and handling turnstile")
                # Fill verification code in registration page
                for i, digit in enumerate(verification_code):
                    browser_tab.ele(f"@data-index={i}").input(digit)
                    time.sleep(get_random_wait_time(config, 'verification_code_input'))
                
                print(f"{translator.get('register.verification_success')}")
                # Attendre que la page valide le code avant Turnstile (évite échec immédiat)
                time.sleep(get_random_wait_time(config, 'verification_success_wait'))
                time.sleep(2)  # délai supplémentaire après code manuel
                
                # Handle last Turnstile verification avec retries (la page peut mettre du temps à afficher le widget)
                for turnstile_attempt in range(3):
                    if handle_turnstile(browser_tab, config, translator):
                        if translator:
                            print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
                        time.sleep(get_random_wait_time(config, 'verification_retry_wait'))
                        if run_onboarding_and_go_to_settings(browser_tab, config, translator):
                            return True, browser_tab
                        return False, None
                    if turnstile_attempt < 2:
                        time.sleep(5)  # attendre avant nouvel essai
                log.warning("Turnstile verification failed after manual code")
                return False, None
                
        # Automatic verification code logic
        elif email_tab:
            print(f"{Fore.CYAN}🔄 {translator.get('register.waiting_for_verification_code')}{Style.RESET_ALL}")
            time.sleep(get_random_wait_time(config, 'email_check_initial_wait'))

            # Use existing email_tab to refresh email
            email_tab.refresh_inbox()
            time.sleep(get_random_wait_time(config, 'email_refresh_wait'))

            # Check if there is a verification code email
            if email_tab.check_for_cursor_email():
                verification_code = email_tab.get_verification_code()
                if verification_code:
                    log.info("Verification code from email: %s", verification_code[:2] + "****")
                    # Fill verification code in registration page
                    for i, digit in enumerate(verification_code):
                        browser_tab.ele(f"@data-index={i}").input(digit)
                        time.sleep(get_random_wait_time(config, 'verification_code_input'))
                    
                    if translator:
                        print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
                    time.sleep(get_random_wait_time(config, 'verification_success_wait'))
                    
                    # Handle last Turnstile verification
                    if handle_turnstile(browser_tab, config, translator):
                        if translator:
                            print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
                        time.sleep(get_random_wait_time(config, 'verification_retry_wait'))
                        if run_onboarding_and_go_to_settings(browser_tab, config, translator):
                            return True, browser_tab
                        return False, None
                        
                    else:
                        log.warning("Turnstile verification failed after email code")
                        if translator:
                            print(f"{Fore.RED}❌ {translator.get('register.final_verification_failed') if translator else 'Dernière vérification échouée'}{Style.RESET_ALL}")
                        else:
                            print("Dernière vérification échouée")
                        return False, None
                        
            # Get verification code, set timeout (polling)
            verification_code = None
            max_attempts = 20
            retry_interval = get_random_wait_time(config, 'retry_interval')  # Use get_random_wait_time
            start_time = time.time()
            timeout = float(config.get('Timing', 'max_timeout', fallback='160'))  # This can be kept unchanged because it is a fixed value

            if translator:
                print(f"{Fore.CYAN}{translator.get('register.start_getting_verification_code')}{Style.RESET_ALL}")
            
            for attempt in range(max_attempts):
                # Check if timeout
                if time.time() - start_time > timeout:
                    if translator:
                        print(f"{Fore.RED}❌ {translator.get('register.verification_timeout')}{Style.RESET_ALL}")
                    break
                    
                verification_code = controller.get_verification_code()
                if verification_code:
                    if translator:
                        print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
                    break
                    
                remaining_time = int(timeout - (time.time() - start_time))
                if translator:
                    print(f"{Fore.CYAN}{translator.get('register.try_get_code', attempt=attempt + 1, time=remaining_time)}{Style.RESET_ALL}")
                
                # Refresh email
                email_tab.refresh_inbox()
                time.sleep(retry_interval)  # Use get_random_wait_time
            
            if verification_code:
                # Fill verification code in registration page
                for i, digit in enumerate(verification_code):
                    browser_tab.ele(f"@data-index={i}").input(digit)
                    time.sleep(get_random_wait_time(config, 'verification_code_input'))
                
                if translator:
                    print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
                time.sleep(get_random_wait_time(config, 'verification_success_wait'))
                
                # Handle last Turnstile verification
                if handle_turnstile(browser_tab, config, translator):
                    if translator:
                        print(f"{Fore.GREEN}✅ {translator.get('register.verification_success')}{Style.RESET_ALL}")
                    time.sleep(get_random_wait_time(config, 'verification_retry_wait'))
                    if run_onboarding_and_go_to_settings(browser_tab, config, translator):
                        return True, browser_tab
                    return False, None
                    
                else:
                    if translator:
                        print(f"{Fore.RED}❌ {translator.get('register.verification_failed')}{Style.RESET_ALL}")
                    return False, None
                
            return False, None
            
    except Exception as e:
        log.exception("Verification error: %s", e)
        if translator:
            print(f"{Fore.RED}❌ {translator.get('register.verification_error', error=str(e))}{Style.RESET_ALL}")
        return False, None

def handle_sign_in(browser_tab, email, password, translator=None):
    """Handle login process"""
    try:
        # Check if on login page
        sign_in_header = browser_tab.ele('xpath://h1[contains(text(), "Sign in")]')
        if not sign_in_header:
            return True  # If not on login page, it means login is successful
            
        print(f"{Fore.CYAN}Page de connexion détectée, démarrage de la connexion...{Style.RESET_ALL}")
        
        # Fill email
        email_input = browser_tab.ele('@name=email')
        if email_input:
            email_input.input(email)
            time.sleep(1)
            
            # Click Continue
            continue_button = browser_tab.ele('xpath://button[contains(@class, "BrandedButton") and text()="Continue"]')
            if continue_button:
                continue_button.click()
                time.sleep(2)
                
                # Handle Turnstile verification
                if handle_turnstile(browser_tab, translator):
                    # Fill password
                    password_input = browser_tab.ele('@name=password')
                    if password_input:
                        password_input.input(password)
                        time.sleep(1)
                        
                        # Click Sign in
                        sign_in_button = browser_tab.ele('xpath://button[@name="intent" and @value="password"]')
                        if sign_in_button:
                            sign_in_button.click()
                            time.sleep(2)
                            
                            # Handle last Turnstile verification
                            if handle_turnstile(browser_tab, translator):
                                print(f"{Fore.GREEN}Login successful!{Style.RESET_ALL}")
                                time.sleep(3)
                                return True
                                
        print(f"{Fore.RED}Login failed{Style.RESET_ALL}")
        return False
        
    except Exception as e:
        print(f"{Fore.RED}Login process error: {str(e)}{Style.RESET_ALL}")
        return False

def main(email=None, password=None, first_name=None, last_name=None, email_tab=None, controller=None, translator=None):
    """Main function, can receive account information, email tab, and translator"""
    global _translator
    global _chrome_process_ids
    _translator = translator  # Save to global variable
    _chrome_process_ids = []  # Reset the process IDs list
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    page = None
    success = False
    try:
        config, page = setup_driver(translator)
        if translator:
            print(f"{Fore.CYAN}🚀 {translator.get('register.browser_started')}{Style.RESET_ALL}")
        
        # Visit registration page
        url = "https://authenticator.cursor.sh/sign-up"
        
        # Visit page
        simulate_human_input(page, url, config, translator)
        if translator:
            print(f"{Fore.CYAN}🔄 {translator.get('register.waiting_for_page_load')}{Style.RESET_ALL}")
        time.sleep(get_random_wait_time(config, 'page_load_wait'))
        
        # If account information is not provided, generate random information
        if not all([email, password, first_name, last_name]):
            first_name = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=6)).capitalize()
            last_name = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=6)).capitalize()
            email = f"{first_name.lower()}{random.randint(100,999)}@example.com"
            password = generate_password()
            
            # Save account information
            with open('test_accounts.txt', 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*50}\n")
                f.write(f"Email: {email}\n")
                f.write(f"Password: {password}\n")
                f.write(f"{'='*50}\n")
        
        # Fill form
        if fill_signup_form(page, first_name, last_name, email, config, translator):
            if translator:
                print(f"\n{Fore.GREEN}✅ {translator.get('register.form_submitted')}{Style.RESET_ALL}")
            
            # Handle first Turnstile verification
            if handle_turnstile(page, config, translator):
                if translator:
                    print(f"\n{Fore.GREEN}✅ {translator.get('register.first_verification_passed')}{Style.RESET_ALL}")
                
                # Fill password
                if fill_password(page, password, config, translator):
                    if translator:
                        print(f"\n{Fore.CYAN}🔄 {translator.get('register.waiting_for_second_verification')}{Style.RESET_ALL}")
                                        
                    # Handle second Turnstile verification
                    if handle_turnstile(page, config, translator):
                        if translator:
                            print(f"\n{Fore.CYAN}🔄 {translator.get('register.waiting_for_verification_code')}{Style.RESET_ALL}")
                        if handle_verification_code(page, email_tab, controller, config, translator):
                            success = True
                            return True, page
                        else:
                            print(f"\n{Fore.RED}❌ {translator.get('register.verification_code_processing_failed') if translator else 'Verification code processing failed'}{Style.RESET_ALL}")
                    else:
                        print(f"\n{Fore.RED}❌ {translator.get('register.second_verification_failed') if translator else 'Second verification failed'}{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.RED}❌ {translator.get('register.second_verification_failed') if translator else 'Second verification failed'}{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.RED}❌ {translator.get('register.first_verification_failed') if translator else 'First verification failed'}{Style.RESET_ALL}")
        
        return False, None
        
    except Exception as e:
        print(f"Une erreur s'est produite: {e}")
        return False, None
    finally:
        if page and not success:  # Only clean up when failed
            try:
                page.quit()
            except:
                pass
            cleanup_chrome_processes(translator)

if __name__ == "__main__":
    main()  # Run without parameters, use randomly generated information 