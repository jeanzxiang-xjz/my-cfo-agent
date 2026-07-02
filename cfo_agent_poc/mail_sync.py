from __future__ import annotations

import email
import imaplib
import re
from datetime import datetime
from email.header import decode_header
from email.message import Message
from pathlib import Path

from process_bill_image import process_image


DATA_DIR = Path(__file__).resolve().parent / "data"
ATTACHMENT_DIR = DATA_DIR / "mail_attachments"
DEFAULT_SUBJECT = "CFO_CAPTURE_SCREENSHOT"


def decode_mime_text(value: str | None) -> str:
    if not value:
        return ""
    pieces = []
    for payload, charset in decode_header(value):
        if isinstance(payload, bytes):
            try:
                pieces.append(payload.decode(charset or "utf-8", errors="replace"))
            except LookupError:
                pieces.append(payload.decode("utf-8", errors="replace"))
        else:
            pieces.append(payload)
    return "".join(pieces)


def image_attachments(message: Message):
    for part in message.walk():
        if part.is_multipart():
            continue
        content_type = part.get_content_type()
        filename = part.get_filename()
        if not content_type.startswith("image/") and not filename:
            continue

        decoded_name = decode_mime_text(filename)
        is_image_file = re.search(r"\.(png|jpe?g|heic|webp)$", decoded_name or "", re.I)
        if content_type.startswith("image/") or is_image_file:
            payload = part.get_payload(decode=True)
            if payload:
                yield decoded_name, payload


def connect_imap(host: str, user: str, password: str, mailbox: str, timeout: float) -> imaplib.IMAP4_SSL:
    client = imaplib.IMAP4_SSL(host, timeout=timeout)
    client.login(user, password)
    client.select(mailbox)
    return client


def safe_logout(client: imaplib.IMAP4_SSL | None) -> None:
    if client is None:
        return
    try:
        client.logout()
    except Exception:
        pass


def search_candidate_uids(client: imaplib.IMAP4_SSL, include_seen: bool, max_candidates: int) -> list[bytes]:
    seen_filter = "ALL" if include_seen else "UNSEEN"
    status, data = client.uid("search", None, seen_filter)
    if status != "OK" or not data or not data[0]:
        return []
    return data[0].split()[-max_candidates:]


def fetch_headers(client: imaplib.IMAP4_SSL, uid: bytes) -> Message | None:
    status, data = client.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM)])")
    if status != "OK" or not data:
        return None
    for item in data:
        if isinstance(item, tuple):
            return email.message_from_bytes(item[1])
    return None


def fetch_message(client: imaplib.IMAP4_SSL, uid: bytes) -> Message | None:
    status, data = client.uid("fetch", uid, "(RFC822)")
    if status != "OK" or not data:
        return None
    for item in data:
        if isinstance(item, tuple):
            return email.message_from_bytes(item[1])
    return None


def process_mailbox_once_detailed(
    client: imaplib.IMAP4_SSL,
    subject: str,
    mark_seen: bool,
    include_seen: bool,
    max_candidates: int,
) -> dict:
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "candidate_count": 0,
        "matched_messages": 0,
        "processed_attachments": 0,
        "items": [],
    }

    uids = search_candidate_uids(client, include_seen=include_seen, max_candidates=max_candidates)
    result["candidate_count"] = len(uids)
    for uid in uids:
        headers = fetch_headers(client, uid)
        if headers is None:
            continue

        message_subject = decode_mime_text(headers.get("Subject"))
        if subject not in message_subject:
            continue
        result["matched_messages"] += 1

        message = fetch_message(client, uid)
        if message is None:
            continue

        source_hint = "alipay" if "ALIPAY" in message_subject.upper() else None
        source_hint = "wechat" if "WECHAT" in message_subject.upper() else source_hint
        date_header = decode_mime_text(headers.get("Date") or message.get("Date"))

        attachment_count = 0
        for index, (filename, payload) in enumerate(image_attachments(message), start=1):
            suffix = Path(filename or "").suffix or ".png"
            out_path = ATTACHMENT_DIR / f"mail_{uid.decode()}_{index}{suffix}"
            out_path.write_bytes(payload)
            parsed = process_image(
                str(out_path),
                source="email_screenshot",
                source_hint=source_hint,
                captured_at=date_header or datetime.now().isoformat(timespec="seconds"),
            )
            result["items"].append({
                "uid": uid.decode(),
                "subject": message_subject,
                "amount": parsed.amount,
                "merchant": parsed.merchant,
                "category": parsed.category,
                "paid_at": parsed.paid_at,
                "transaction_uid": parsed.transaction_uid,
            })
            attachment_count += 1
            result["processed_attachments"] += 1

        if attachment_count and mark_seen:
            client.uid("store", uid, "+FLAGS", "(\\Seen)")

    return result
