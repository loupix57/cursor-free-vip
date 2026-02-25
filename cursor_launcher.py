# cursor_launcher.py - Ouvrir Cursor et enchaînement Quit → Register → Ouvrir
"""
Fonctions utilitaires :
- open_cursor() : lance l’application Cursor.
- run_quit_register_reopen() : option 3 (fermer Cursor) puis option 2 (inscription) puis rouvre Cursor.
"""
import os
import sys
import subprocess
import platform
from colorama import Fore, Style

EMOJI = {"SUCCESS": "✅", "ERROR": "❌", "INFO": "ℹ️", "ROCKET": "🚀"}


def _get_cursor_executable(translator=None):
    """Retourne le chemin de l’exécutable Cursor (exe, .app ou binaire)."""
    from config import get_config
    config = get_config(translator)
    if not config:
        return None
    system = platform.system()
    if system == "Windows":
        if config.has_section("WindowsPaths") and config.has_option("WindowsPaths", "cursor_path"):
            app_dir = config.get("WindowsPaths", "cursor_path")
            # cursor_path = .../Programs/Cursor/resources/app → exe = .../Programs/Cursor/Cursor.exe
            base = os.path.dirname(os.path.dirname(app_dir))
            exe = os.path.join(base, "Cursor.exe")
            if os.path.isfile(exe):
                return exe
        local = os.getenv("LOCALAPPDATA", "")
        exe = os.path.join(local, "Programs", "Cursor", "Cursor.exe")
        if os.path.isfile(exe):
            return exe
        return None
    if system == "Darwin":
        app_path = "/Applications/Cursor.app"
        if config.has_section("MacPaths") and config.has_option("MacPaths", "cursor_path"):
            p = config.get("MacPaths", "cursor_path")
            if ".app" in p:
                app_path = p.split(".app")[0] + ".app"
        return app_path if os.path.isdir(app_path) else None
    # Linux
    if config.has_section("LinuxPaths") and config.has_option("LinuxPaths", "cursor_path"):
        app_dir = config.get("LinuxPaths", "cursor_path")
        base = os.path.dirname(os.path.dirname(app_dir))
        for name in ("cursor", "Cursor"):
            exe = os.path.join(base, name)
            if os.path.isfile(exe):
                return exe
    for path in ["/usr/bin/cursor", "/usr/local/bin/cursor"]:
        if os.path.isfile(path):
            return path
    return None


def open_cursor(translator=None):
    """
    Lance l’application Cursor.
    Returns:
        bool: True si le lancement a été effectué, False sinon.
    """
    try:
        exe = _get_cursor_executable(translator)
        if not exe:
            msg = translator.get("menu.open_cursor_not_found") if translator else "Cursor executable not found"
            print(f"{Fore.RED}{EMOJI['ERROR']} {msg}{Style.RESET_ALL}")
            return False
        if platform.system() == "Darwin":
            subprocess.Popen(["open", "-a", exe], start_new_session=True)
        elif platform.system() == "Windows":
            subprocess.Popen([exe], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS, close_fds=True)
        else:
            subprocess.Popen([exe], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        msg = translator.get("menu.open_cursor_ok") if translator else "Cursor launched"
        print(f"{Fore.GREEN}{EMOJI['ROCKET']} {msg}{Style.RESET_ALL}")
        return True
    except Exception as e:
        msg = translator.get("menu.open_cursor_error", error=str(e)) if translator else str(e)
        print(f"{Fore.RED}{EMOJI['ERROR']} {msg}{Style.RESET_ALL}")
        return False


def run_quit_register_reopen(translator=None):
    """
    Enchaîne : option 3 (fermer Cursor) → option 2 (inscription email) → rouvrir Cursor.
    """
    import quit_cursor
    import cursor_register_manual
    msg = translator.get("menu.quit_register_reopen") if translator else "Quit Cursor → Register (custom email) → Reopen Cursor"
    print(f"\n{Fore.CYAN}{EMOJI['INFO']} {msg}{Style.RESET_ALL}\n")
    quit_cursor.quit_cursor(translator)
    # Ne pas bloquer sur \"Press Enter\" dans ce flux automatique
    cursor_register_manual.main(translator, wait_for_enter=False)
    open_cursor(translator)


if __name__ == "__main__":
    from main import translator as main_translator
    if len(sys.argv) > 1 and sys.argv[1] == "reopen":
        run_quit_register_reopen(main_translator)
    else:
        open_cursor(main_translator)
