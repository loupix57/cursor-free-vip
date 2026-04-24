# Boîte e-mail jetable via l’API publique mail.tm (sans clé API).
import re
import secrets
import string
import time
from typing import Any, List, Optional

import requests

from .email_tab_interface import EmailTabInterface
from logger import get_logger

log = get_logger("disposable_mail")

DEFAULT_API = "https://api.mail.tm"


def _domains_list(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("hydra:member") or data.get("member") or []
    return []


def _messages_list(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("hydra:member") or data.get("member") or []
    return []


class DisposableMailTab(EmailTabInterface):
    """Création d’une adresse sur mail.tm et lecture du code de vérification Cursor."""

    def __init__(
        self,
        address: str,
        mailbox_password: str,
        token: str,
        translator=None,
        api_base: str = DEFAULT_API,
        request_timeout: float = 25.0,
    ):
        self.address = address
        self._mailbox_password = mailbox_password
        self._token = token
        self.translator = translator
        self._api = (api_base or DEFAULT_API).rstrip("/")
        self._timeout = request_timeout
        self._cached_verification_code: Optional[str] = None
        self._ignored_message_ids: set = set()
        self._headers_json = {"Accept": "application/json", "Content-Type": "application/json"}

    def _auth_headers(self) -> dict:
        h = dict(self._headers_json)
        h["Authorization"] = f"Bearer {self._token}"
        return h

    @classmethod
    def create_random(cls, translator=None, config=None):
        api = DEFAULT_API
        timeout = 25.0
        if config and config.has_section("DisposableMail"):
            api = config.get("DisposableMail", "api_base", fallback=api).strip() or api
            try:
                timeout = float(config.get("DisposableMail", "request_timeout", fallback="25"))
            except ValueError:
                timeout = 25.0
        api = api.rstrip("/")
        h = {"Accept": "application/json"}

        dom_resp = requests.get(f"{api}/domains", headers=h, timeout=timeout)
        dom_resp.raise_for_status()
        domains = _domains_list(dom_resp.json())
        if not domains:
            raise RuntimeError("mail.tm: no domain available")
        domain = (domains[0].get("domain") or "").strip()
        if not domain:
            raise RuntimeError("mail.tm: invalid domain payload")

        local = "".join(
            secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12)
        )
        address = f"{local}@{domain}"
        mailbox_password = secrets.token_urlsafe(14)

        acc = requests.post(
            f"{api}/accounts",
            headers={**h, "Content-Type": "application/json"},
            json={"address": address, "password": mailbox_password},
            timeout=timeout,
        )
        acc.raise_for_status()

        tok = requests.post(
            f"{api}/token",
            headers={**h, "Content-Type": "application/json"},
            json={"address": address, "password": mailbox_password},
            timeout=timeout,
        )
        tok.raise_for_status()
        body = tok.json()
        token = body.get("token") or body.get("id")
        if not token:
            raise RuntimeError("mail.tm: no token in response")

        return cls(
            address=address,
            mailbox_password=mailbox_password,
            token=token,
            translator=translator,
            api_base=api,
            request_timeout=timeout,
        )

    def refresh_inbox(self) -> None:
        return

    def _fetch_messages_meta(self) -> List[dict]:
        r = requests.get(f"{self._api}/messages", headers=self._auth_headers(), timeout=self._timeout)
        r.raise_for_status()
        return _messages_list(r.json())

    def _fetch_message_body(self, msg_id: str) -> dict:
        r = requests.get(
            f"{self._api}/messages/{msg_id}",
            headers=self._auth_headers(),
            timeout=self._timeout,
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _is_cursor_mail(payload: dict) -> bool:
        frm = payload.get("from")
        if isinstance(frm, dict):
            from_addr = (frm.get("address") or frm.get("name") or "").lower()
        else:
            from_addr = str(frm or "").lower()
        subj = (payload.get("subject") or "").lower()
        if "cursor" in from_addr or "cursor" in subj or "authenticator" in from_addr:
            return True
        return False

    @staticmethod
    def _extract_code(text: str) -> str:
        if not text:
            return ""
        for m in re.finditer(r"\b(\d{6})\b", text):
            return m.group(1)
        return ""

    def check_for_cursor_email(self) -> bool:
        if self._cached_verification_code:
            return True
        try:
            metas = self._fetch_messages_meta()
            metas = sorted(
                metas,
                key=lambda x: str(x.get("createdAt") or x.get("receivedAt") or ""),
                reverse=True,
            )
            for item in metas:
                mid = item.get("id")
                if not mid or mid in self._ignored_message_ids:
                    continue
                body = self._fetch_message_body(mid)
                if not self._is_cursor_mail(body):
                    self._ignored_message_ids.add(mid)
                    continue
                intro = body.get("intro") or ""
                html = body.get("html") or ""
                text = intro + "\n" + re.sub(r"<[^>]+>", " ", html)
                code = self._extract_code(text)
                if code:
                    self._cached_verification_code = code
                    log.info("Disposable mail: code Cursor reçu pour %s", self.address)
                    return True
                self._ignored_message_ids.add(mid)
            return False
        except Exception as e:
            log.warning("Disposable check_for_cursor_email: %s", e)
            return False

    def get_verification_code(self) -> str:
        return self._cached_verification_code or ""


def test_provider(translator=None) -> bool:
    """Crée une boîte mail.tm et vérifie que l’API répond (sans inscription Cursor)."""
    from config import get_config

    cfg = get_config(translator)
    try:
        tab = DisposableMailTab.create_random(translator, cfg)
        msg = (
            translator.get("disposable.test_mailbox_ok", address=tab.address)
            if translator
            else f"Boîte créée : {tab.address}"
        )
        print(msg)
        n = len(tab._fetch_messages_meta())
        ok2 = (
            translator.get("disposable.test_list_ok", count=n)
            if translator
            else f"Lecture de la boîte OK ({n} message(s))."
        )
        print(ok2)
        return True
    except Exception as e:
        err = (
            translator.get("disposable.test_failed", error=str(e))
            if translator
            else f"Échec test API jetable : {e}"
        )
        print(err)
        return False


if __name__ == "__main__":
    test_provider(None)
