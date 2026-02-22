import os
import sys
import platform
import shutil
from colorama import Fore, Style, init
import subprocess
from config import get_config
import re
import tempfile

# Initialize colorama
init()

# Define emoji constants
EMOJI = {
    "PROCESS": "🔄",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "INFO": "ℹ️",
    "FOLDER": "📁",
    "FILE": "📄",
    "STOP": "🛑",
    "CHECK": "✔️"
}

class AutoUpdateDisabler:
    def __init__(self, translator=None):
        self.translator = translator
        self.system = platform.system()
        
        # Get path from configuration file
        config = get_config(translator)
        if config:
            if self.system == "Windows":
                self.updater_path = config.get('WindowsPaths', 'updater_path', fallback=os.path.join(os.getenv("LOCALAPPDATA", ""), "cursor-updater"))
                self.update_yml_path = config.get('WindowsPaths', 'update_yml_path', fallback=os.path.join(os.getenv("LOCALAPPDATA", ""), "Programs", "Cursor", "resources", "app", "update.yml"))
                self.product_json_path = config.get('WindowsPaths', 'product_json_path', fallback=os.path.join(os.getenv("LOCALAPPDATA", ""), "Programs", "Cursor", "resources", "app", "product.json"))
            elif self.system == "Darwin":
                self.updater_path = config.get('MacPaths', 'updater_path', fallback=os.path.expanduser("~/Library/Application Support/cursor-updater"))
                self.update_yml_path = config.get('MacPaths', 'update_yml_path', fallback="/Applications/Cursor.app/Contents/Resources/app-update.yml")
                self.product_json_path = config.get('MacPaths', 'product_json_path', fallback="/Applications/Cursor.app/Contents/Resources/app/product.json")
            elif self.system == "Linux":
                self.updater_path = config.get('LinuxPaths', 'updater_path', fallback=os.path.expanduser("~/.config/cursor-updater"))
                self.update_yml_path = config.get('LinuxPaths', 'update_yml_path', fallback=os.path.expanduser("~/.config/cursor/resources/app-update.yml"))
                self.product_json_path = config.get('LinuxPaths', 'product_json_path', fallback=os.path.expanduser("~/.config/cursor/resources/app/product.json"))
        else:
            # If configuration loading fails, use default paths
            self.updater_paths = {
                "Windows": os.path.join(os.getenv("LOCALAPPDATA", ""), "cursor-updater"),
                "Darwin": os.path.expanduser("~/Library/Application Support/cursor-updater"),
                "Linux": os.path.expanduser("~/.config/cursor-updater")
            }
            self.updater_path = self.updater_paths.get(self.system)
            
            self.update_yml_paths = {
                "Windows": os.path.join(os.getenv("LOCALAPPDATA", ""), "Programs", "Cursor", "resources", "app", "update.yml"),
                "Darwin": "/Applications/Cursor.app/Contents/Resources/app-update.yml",
                "Linux": os.path.expanduser("~/.config/cursor/resources/app-update.yml")
            }
            self.update_yml_path = self.update_yml_paths.get(self.system)

            self.product_json_paths = {
                "Windows": os.path.join(os.getenv("LOCALAPPDATA", ""), "Programs", "Cursor", "resources", "app", "product.json"),
                "Darwin": "/Applications/Cursor.app/Contents/Resources/app/product.json",
                "Linux": os.path.expanduser("~/.config/cursor/resources/app/product.json")
            }
            self.product_json_path = self.product_json_paths.get(self.system)

    def _remove_update_url(self):
        """Remove update URL"""
        try:
            original_stat = os.stat(self.product_json_path)
            original_mode = original_stat.st_mode
            original_uid = original_stat.st_uid
            original_gid = original_stat.st_gid

            with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
                with open(self.product_json_path, "r", encoding="utf-8") as product_json_file:
                    content = product_json_file.read()
                
                patterns = {
                    r"https://api2.cursor.sh/aiserver.v1.AuthService/DownloadUpdate": r"",
                    r"https://api2.cursor.sh/updates": r"",
                    r"http://cursorapi.com/updates": r"",
                }
                
                for pattern, replacement in patterns.items():
                    content = re.sub(pattern, replacement, content)

                tmp_file.write(content)
                tmp_path = tmp_file.name

            shutil.copy2(self.product_json_path, self.product_json_path + ".old")
            shutil.move(tmp_path, self.product_json_path)

            os.chmod(self.product_json_path, original_mode)
            if os.name != "nt":
                os.chown(self.product_json_path, original_uid, original_gid)

            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('reset.file_modified')}{Style.RESET_ALL}")
            return True

        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.modify_file_failed', error=str(e))}{Style.RESET_ALL}")
            if "tmp_path" in locals():
                os.unlink(tmp_path)
            return False

    def _kill_cursor_processes(self):
        """End all Cursor processes"""
        try:
            print(f"{Fore.CYAN}{EMOJI['PROCESS']} {self.translator.get('update.killing_processes') if self.translator else 'Arrêt des processus Cursor...'}{Style.RESET_ALL}")
            
            if self.system == "Windows":
                subprocess.run(['taskkill', '/F', '/IM', 'Cursor.exe', '/T'], capture_output=True)
            else:
                subprocess.run(['pkill', '-f', 'Cursor'], capture_output=True)
                
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('update.processes_killed') if self.translator else 'Processus Cursor terminés'}{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('update.kill_process_failed', error=str(e)) if self.translator else f'Échec de l\'arrêt des processus: {e}'}{Style.RESET_ALL}")
            return False

    def _remove_updater_directory(self):
        """Delete updater directory"""
        try:
            updater_path = self.updater_path
            if not updater_path:
                raise OSError(self.translator.get('update.unsupported_os', system=self.system) if self.translator else f"Système d'exploitation non supporté: {self.system}")

            print(f"{Fore.CYAN}{EMOJI['FOLDER']} {self.translator.get('update.removing_directory') if self.translator else 'Suppression du répertoire de mise à jour...'}{Style.RESET_ALL}")
            
            if os.path.exists(updater_path):
                try:
                    if os.path.isdir(updater_path):
                        shutil.rmtree(updater_path)
                    else:
                        os.remove(updater_path)
                    print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('update.directory_removed') if self.translator else 'Répertoire de mise à jour supprimé'}{Style.RESET_ALL}")
                except PermissionError:
                    print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('update.directory_locked', path=updater_path) if self.translator else f'Répertoire verrouillé, suppression ignorée: {updater_path}'}{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('update.remove_directory_failed', error=str(e)) if self.translator else f'Échec de la suppression du répertoire: {e}'}{Style.RESET_ALL}")
            return True
    
    def _clear_update_yml_file(self):
        """Clear update.yml file"""
        try:
            update_yml_path = self.update_yml_path
            if not update_yml_path:
                raise OSError(self.translator.get('update.unsupported_os', system=self.system) if self.translator else f"Système d'exploitation non supporté: {self.system}")
            
            print(f"{Fore.CYAN}{EMOJI['FILE']} {self.translator.get('update.clearing_update_yml') if self.translator else 'Vidage du fichier de configuration de mise à jour...'}{Style.RESET_ALL}")
            
            if os.path.exists(update_yml_path):
                try:
                    with open(update_yml_path, 'w') as f:
                        f.write('')
                    print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('update.update_yml_cleared') if self.translator else 'Fichier de configuration de mise à jour vidé'}{Style.RESET_ALL}")
                except PermissionError:
                    print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('update.yml_locked') if self.translator else 'Fichier de configuration verrouillé, vidage ignoré'}{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('update.update_yml_not_found') if self.translator else 'Fichier de configuration de mise à jour introuvable'}{Style.RESET_ALL}")
            return True
                
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('update.clear_update_yml_failed', error=str(e)) if self.translator else f'Échec du vidage du fichier de configuration: {e}'}{Style.RESET_ALL}")
            return False

    def _create_blocking_file(self):
        """Create blocking files"""
        try:
            # Vérifier updater_path
            updater_path = self.updater_path
            if not updater_path:
                raise OSError(self.translator.get('update.unsupported_os', system=self.system) if self.translator else f"Système d'exploitation non supporté: {self.system}")

            print(f"{Fore.CYAN}{EMOJI['FILE']} {self.translator.get('update.creating_block_file') if self.translator else 'Création du fichier de blocage...'}{Style.RESET_ALL}")
            
            # Créer le fichier de blocage updater_path
            try:
                os.makedirs(os.path.dirname(updater_path), exist_ok=True)
                open(updater_path, 'w').close()
                
                # Définir updater_path en lecture seule
                if self.system == "Windows":
                    os.system(f'attrib +r "{updater_path}"')
                else:
                    os.chmod(updater_path, 0o444)  # Définir en lecture seule
                
                print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('update.block_file_created') if self.translator else 'Fichier de blocage créé'}: {updater_path}{Style.RESET_ALL}")
            except PermissionError:
                print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('update.block_file_locked') if self.translator else 'Fichier verrouillé, création ignorée'}{Style.RESET_ALL}")
            
            # Vérifier update_yml_path
            update_yml_path = self.update_yml_path
            if update_yml_path and os.path.exists(os.path.dirname(update_yml_path)):
                try:
                    # Créer le fichier de blocage update_yml_path
                    with open(update_yml_path, 'w') as f:
                        f.write('# This file is locked to prevent auto-updates\nversion: 0.0.0\n')
                    
                    # Définir update_yml_path en lecture seule
                    if self.system == "Windows":
                        os.system(f'attrib +r "{update_yml_path}"')
                    else:
                        os.chmod(update_yml_path, 0o444)  # Définir en lecture seule
                    
                    print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('update.yml_locked') if self.translator else 'Fichier de configuration verrouillé'}: {update_yml_path}{Style.RESET_ALL}")
                except PermissionError:
                    print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('update.yml_already_locked') if self.translator else 'Fichier de configuration déjà verrouillé, modification ignorée'}{Style.RESET_ALL}")
            
            return True
            
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('update.create_block_file_failed', error=str(e)) if self.translator else f'Échec de la création du fichier de blocage: {e}'}{Style.RESET_ALL}")
            return True  # Retourner True pour continuer l'exécution

    def disable_auto_update(self):
        """Disable auto update"""
        try:
            print(f"{Fore.CYAN}{EMOJI['INFO']} {self.translator.get('update.start_disable') if self.translator else 'Démarrage de la désactivation de la mise à jour automatique...'}{Style.RESET_ALL}")
            
            # 1. Arrêter les processus
            if not self._kill_cursor_processes():
                return False
                
            # 2. Supprimer le répertoire - continuer même en cas d'échec
            self._remove_updater_directory()
                
            # 3. Vider le fichier update.yml
            if not self._clear_update_yml_file():
                return False
                
            # 4. Créer le fichier de blocage
            if not self._create_blocking_file():
                return False
                
            # 5. Supprimer l'URL de mise à jour de product.json
            if not self._remove_update_url():
                return False
                
            print(f"{Fore.GREEN}{EMOJI['CHECK']} {self.translator.get('update.disable_success') if self.translator else 'Mise à jour automatique désactivée'}{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('update.disable_failed', error=str(e)) if self.translator else f'Échec de la désactivation de la mise à jour automatique: {e}'}{Style.RESET_ALL}")
            return False

def run(translator=None):
    """Convenient function for directly calling the disable function"""
    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{EMOJI['STOP']} {translator.get('update.title') if translator else 'Disable Cursor Auto Update'}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    disabler = AutoUpdateDisabler(translator)
    disabler.disable_auto_update()

    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    input(f"{EMOJI['INFO']} {translator.get('update.press_enter') if translator else 'Press Enter to Continue...'}")

if __name__ == "__main__":
    from main import translator as main_translator
    run(main_translator) 