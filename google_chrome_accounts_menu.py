# Menu : comptes Gmail repérés dans Chrome + fichier cursor_accounts.txt → OAuth Google ou login web Cursor.
from typing import Optional

from colorama import Fore, Style, init as colorama_init

from account_manager import AccountManager
from chrome_gmail_scan import get_browser_user_data_dir, scan_chrome_user_data_for_gmail


def _build_rows(chrome_hints: list, saved_google: list) -> list:
    by_email: dict = {}
    for h in chrome_hints:
        em = (h.get("email") or "").lower().strip()
        if not em:
            continue
        pd = (h.get("profile_dir") or "").strip()
        if em not in by_email:
            by_email[em] = {"email": em, "profiles": [], "profile_labels": [], "saved": None}
        if pd and pd not in by_email[em]["profiles"]:
            by_email[em]["profiles"].append(pd)
            by_email[em]["profile_labels"].append(h.get("profile_label") or pd)
    for acc in saved_google:
        em = (acc.get("email") or "").lower().strip()
        if not em:
            continue
        # Enrichit seulement les e-mails déjà trouvés dans un profil "Profile N".
        if em in by_email:
            by_email[em]["saved"] = acc

    # Règle finale pour l'option 20 :
    # - si l'e-mail existe dans au moins un profil "Profile N", alors on exclut "Default"
    # - sinon (ex: compte trouvé uniquement dans Chrome "Default"), on le conserve quand même
    #   pour que la liste ne soit pas vide / incomplète.
    for row in by_email.values():
        profiles = row.get("profiles") or []
        labels = row.get("profile_labels") or []
        has_real_profile = any((p or "").startswith("Profile ") for p in profiles)
        if not has_real_profile:
            continue

        new_profiles = []
        new_labels = []
        for p, lbl in zip(profiles, labels):
            if (p or "").startswith("Profile "):
                new_profiles.append(p)
                new_labels.append(lbl)

        row["profiles"] = new_profiles
        row["profile_labels"] = new_labels

    return sorted(by_email.values(), key=lambda x: x["email"])


def _pick_chrome_profile_for_row(row: dict, translator) -> Optional[str]:
    profs = row.get("profiles") or []
    if not profs:
        return None
    if len(profs) == 1:
        return profs[0]
    print()
    for i, p in enumerate(profs, 1):
        lbl = (row.get("profile_labels") or [p] * len(profs))[i - 1] if row.get("profile_labels") else p
        print(f"  {i}. {lbl}  ({p})")
    try:
        c = input(
            f"{Fore.CYAN}{translator.get('chrome_gmail.chrome_profile_prompt', n=len(profs))}{Style.RESET_ALL}"
        ).strip()
        idx = int(c) - 1
        if 0 <= idx < len(profs):
            return profs[idx]
    except (ValueError, EOFError, KeyboardInterrupt):
        pass
    return profs[0]


def run(translator) -> None:
    colorama_init()
    print(f"\n{Fore.CYAN}{'═' * 70}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{translator.get('chrome_gmail.section_title')}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'═' * 70}{Style.RESET_ALL}\n")

    user_data = get_browser_user_data_dir(translator)
    chrome_rows = []
    if user_data:
        print(f"{Fore.YELLOW}{translator.get('chrome_gmail.user_data')}: {user_data}{Style.RESET_ALL}\n")
        chrome_rows = scan_chrome_user_data_for_gmail(user_data)
    else:
        print(f"{Fore.YELLOW}{translator.get('chrome_gmail.no_user_data')}{Style.RESET_ALL}\n")

    am = AccountManager(translator)
    saved = am.get_saved_google_accounts()
    rows = _build_rows(chrome_rows, saved)

    if not rows:
        print(f"{Fore.RED}{translator.get('chrome_gmail.none')}{Style.RESET_ALL}\n")
        input(f"\n{translator.get('menu.press_enter')}")
        return

    print(f"{Fore.GREEN}{translator.get('chrome_gmail.pick_account')}{Style.RESET_ALL}\n")
    for i, row in enumerate(rows, 1):
        em = row["email"]
        profs = row["profiles"]
        has_saved = row.get("saved") is not None
        parts = []
        if profs:
            parts.append(translator.get("chrome_gmail.tag_chrome") + ": " + ", ".join(profs))
        else:
            parts.append(translator.get("chrome_gmail.tag_file_only"))
        if has_saved:
            parts.append(translator.get("chrome_gmail.tag_password_file"))
        line = " | ".join(parts)
        print(f"  {Fore.CYAN}{i:2}.{Style.RESET_ALL} {em}")
        print(f"      {Fore.YELLOW}{line}{Style.RESET_ALL}")
    print()

    try:
        raw = input(f"{Fore.CYAN}{translator.get('chrome_gmail.enter_number')}: {Style.RESET_ALL}").strip()
        num = int(raw)
    except (ValueError, EOFError, KeyboardInterrupt):
        return
    if num <= 0 or num > len(rows):
        return

    row = rows[num - 1]
    email = row["email"]
    print()
    print(f"{Fore.GREEN}1.{Style.RESET_ALL} {translator.get('chrome_gmail.action_oauth')}")
    print(f"{Fore.GREEN}2.{Style.RESET_ALL} {translator.get('chrome_gmail.action_web_login')}")
    try:
        sub = input(f"{Fore.CYAN}{translator.get('chrome_gmail.choose_action')}: {Style.RESET_ALL}").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if sub == "1":
        preset = _pick_chrome_profile_for_row(row, translator) if row.get("profiles") else None
        try:
            from oauth_auth import main as oauth_main

            oauth_main("google", translator, preset_chrome_profile=preset)
        except Exception as e:
            print(f"{Fore.RED}{e}{Style.RESET_ALL}")
    elif sub == "2":
        password = None
        sav = row.get("saved")
        if sav and sav.get("password"):
            password = sav["password"]
            print(f"{Fore.GREEN}{translator.get('chrome_gmail.using_saved_password')}{Style.RESET_ALL}")
        else:
            try:
                import getpass

                password = getpass.getpass(translator.get("chrome_gmail.enter_password"))
            except (EOFError, KeyboardInterrupt):
                return
        if not password:
            print(f"{Fore.RED}{translator.get('chrome_gmail.no_password')}{Style.RESET_ALL}")
            input(f"\n{translator.get('menu.press_enter')}")
            return
        try:
            from agent_cli_helper import automate_cursor_web_login_flow

            ok = automate_cursor_web_login_flow(email, password, translator)
            if ok:
                print(f"{Fore.GREEN}{translator.get('chrome_gmail.web_ok')}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}{translator.get('chrome_gmail.web_fail')}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}{e}{Style.RESET_ALL}")
    input(f"\n{translator.get('menu.press_enter')}")
