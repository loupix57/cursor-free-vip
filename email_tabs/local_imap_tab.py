# email_tabs/local_imap_tab.py - Local mailbox (IMAP) for reading Cursor verification codes
import imaplib
import email
import re
import time
from typing import Optional

from .email_tab_interface import EmailTabInterface
from logger import get_logger

log = get_logger("local_imap")


class LocalImapTab(EmailTabInterface):
    """Read verification code from a local mailbox via IMAP (e.g. Gmail, Outlook)."""

    # Sender patterns that indicate a Cursor verification email
    CURSOR_FROM_PATTERNS = ("cursor", "no-reply@cursor", "noreply@cursor", "authenticator.cursor")

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        translator=None,
        port: Optional[int] = None,
        use_ssl: bool = True,
        folder: str = "INBOX",
    ):
        self.host = host
        self.port = port or (993 if use_ssl else 143)
        self.user = user
        self.password = password
        self.use_ssl = use_ssl
        self.folder = folder
        self.translator = translator
        self._cached_verification_code: Optional[str] = None
        self._imap: Optional[imaplib.IMAP4] = None

    @classmethod
    def from_config(cls, config, translator=None):
        """Build LocalImapTab from config [LocalEmail] section."""
        host = config.get("LocalEmail", "host", fallback="").strip()
        user = config.get("LocalEmail", "user", fallback="").strip()
        password = config.get("LocalEmail", "password", fallback="").strip()
        if not host or not user or not password:
            raise ValueError("LocalEmail requires host, user and password in config")
        use_ssl_val = config.get("LocalEmail", "use_ssl", fallback="true").strip().lower()
        use_ssl = use_ssl_val in ("true", "1", "yes", "on")
        port_str = config.get("LocalEmail", "port", fallback="").strip()
        port = int(port_str) if port_str else (993 if use_ssl else 143)
        folder = config.get("LocalEmail", "folder", fallback="INBOX").strip() or "INBOX"
        return cls(
            host=host,
            user=user,
            password=password,
            translator=translator,
            port=port,
            use_ssl=use_ssl,
            folder=folder,
        )

    def _connect(self) -> bool:
        try:
            if self._imap:
                try:
                    self._imap.noop()
                except Exception:
                    self._imap = None
            if not self._imap:
                if self.use_ssl:
                    self._imap = imaplib.IMAP4_SSL(self.host, self.port)
                else:
                    self._imap = imaplib.IMAP4(self.host, self.port)
                self._imap.login(self.user, self.password)
                log.debug("IMAP connected to %s", self.host)
            return True
        except Exception as e:
            log.warning("IMAP connection failed: %s", e)
            self._imap = None
            return False

    def _disconnect(self):
        if self._imap:
            try:
                self._imap.logout()
            except Exception:
                pass
            self._imap = None

    def refresh_inbox(self) -> None:
        """No-op for IMAP; we fetch on demand in check_for_cursor_email."""
        pass

    def _is_cursor_sender(self, from_header: str) -> bool:
        if not from_header:
            return False
        lower = from_header.lower()
        return any(p in lower for p in self.CURSOR_FROM_PATTERNS)

    def _extract_code_from_body(self, text: str) -> Optional[str]:
        """Extract 6-digit verification code from email body."""
        if not text:
            return None
        # Common pattern: code alone on a line or inside text
        match = re.search(r"\b(\d{6})\b", text)
        return match.group(1) if match else None

    def check_for_cursor_email(self) -> bool:
        """Check IMAP inbox for a recent Cursor verification email and cache the code."""
        self._cached_verification_code = None
        if not self._connect():
            return False
        try:
            self._imap.select(self.folder, readonly=True)
            # Search all (or recent) emails; we look for Cursor sender and 6-digit code
            status, messages = self._imap.search(None, "ALL")
            if status != "OK" or not messages[0]:
                log.debug("IMAP search returned no messages")
                return False
            ids = messages[0].split()
            # Process newest first
            for uid in reversed(ids[-20:]):  # last 20 only
                try:
                    status, data = self._imap.fetch(uid, "(RFC822)")
                    if status != "OK" or not data:
                        continue
                    msg = email.message_from_bytes(data[0][1])
                    from_header = msg.get("From", "")
                    if not self._is_cursor_sender(from_header):
                        continue
                    subject = msg.get("Subject", "")
                    if "verification" not in subject.lower() and "code" not in subject.lower():
                        continue
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            ct = part.get_content_type()
                            if ct == "text/plain":
                                try:
                                    body = part.get_payload(decode=True)
                                    if body:
                                        body = body.decode("utf-8", errors="replace")
                                except Exception:
                                    pass
                                break
                    else:
                        try:
                            body = msg.get_payload(decode=True)
                            if body:
                                body = body.decode("utf-8", errors="replace")
                        except Exception:
                            pass
                    code = self._extract_code_from_body(body)
                    if code:
                        self._cached_verification_code = code
                        log.info("Found Cursor verification code in local mailbox")
                        return True
                except Exception as e:
                    log.debug("Error parsing message %s: %s", uid, e)
                    continue
            return False
        finally:
            self._disconnect()

    def get_verification_code(self) -> str:
        """Return the cached verification code from the last check_for_cursor_email."""
        return self._cached_verification_code or ""
