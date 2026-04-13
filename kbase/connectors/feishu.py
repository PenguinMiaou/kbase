"""Feishu (Lark) connector - auto-fetch docs, chats, emails via Open API.

Setup:
1. Go to https://open.feishu.cn → Create App → Get App ID & App Secret
2. Add permissions: docs:read, im:message:readonly, mail:message:readonly
3. Configure in KBase Settings → Connectors → Feishu
"""
import json
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

from kbase.config import get_workspace_dir


class _SkipModule(Exception):
    """Raised to skip a sync module."""
    pass


# Feishu API endpoints
FEISHU_BASE = "https://open.feishu.cn/open-apis"
LARK_BASE = "https://open.larksuite.com/open-apis"  # International


class FeishuConnector:
    """Fetch documents, chat messages, and emails from Feishu."""

    def __init__(self, app_id: str, app_secret: str, workspace: str = "default",
                 use_lark: bool = False, custom_domain: str = ""):
        self.app_id = app_id
        self.app_secret = app_secret
        self.workspace = workspace
        # Support custom enterprise domain (e.g. mycompany.feishu.cn)
        if custom_domain:
            domain = custom_domain.strip().rstrip("/")
            if not domain.endswith(".feishu.cn") and "." not in domain:
                domain = f"{domain}.feishu.cn"
            if not domain.startswith("http"):
                domain = f"https://{domain}"
            self.base = f"{domain}/open-apis"
        elif use_lark:
            self.base = LARK_BASE
        else:
            self.base = FEISHU_BASE
        self._tenant_token = None
        self._user_token = None
        self._token_expiry = 0
        self._state_file = get_workspace_dir(workspace) / "feishu_state.json"
        self._load_state()

    def _load_state(self):
        if self._state_file.exists():
            state = json.loads(self._state_file.read_text())
            self._user_token = state.get("user_token")
            self._token_expiry = state.get("token_expiry", 0)

    def _save_state(self):
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps({
            "user_token": self._user_token,
            "token_expiry": self._token_expiry,
        }))

    # ---- Auth ----

    def get_tenant_token(self) -> str:
        """Get tenant access token (app-level)."""
        if self._tenant_token and time.time() < self._token_expiry:
            return self._tenant_token

        data = json.dumps({
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }).encode()
        req = urllib.request.Request(
            f"{self.base}/auth/v3/tenant_access_token/internal",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())

        if result.get("code") != 0:
            raise ValueError(f"Feishu auth error: {result.get('msg', 'unknown')}")

        self._tenant_token = result["tenant_access_token"]
        self._token_expiry = time.time() + result.get("expire", 7200) - 60
        return self._tenant_token

    def get_oauth_url(self, redirect_uri: str, scopes: list = None) -> str:
        """Generate OAuth URL with specified scopes."""
        if not scopes:
            scopes = ["im:message", "im:message:readonly", "im:chat:readonly"]
        params = urllib.parse.urlencode({
            "app_id": self.app_id,
            "redirect_uri": redirect_uri,
            "state": "kbase_auth",
            "scope": " ".join(scopes),
        })
        return f"{self.base}/authen/v1/authorize?{params}"

    def exchange_code(self, code: str) -> dict:
        """Exchange OAuth code for user access token."""
        token = self.get_tenant_token()
        data = json.dumps({"grant_type": "authorization_code", "code": code}).encode()
        req = urllib.request.Request(
            f"{self.base}/authen/v1/oidc/access_token",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())

        if result.get("code") != 0:
            raise ValueError(f"OAuth error: {result.get('msg')}")

        self._user_token = result["data"]["access_token"]
        self._token_expiry = time.time() + result["data"].get("expires_in", 7200) - 60
        self._save_state()
        return result["data"]

    def _api(self, method: str, path: str, data: dict = None,
             params: dict = None, use_user_token: bool = True) -> dict:
        """Make authenticated API call."""
        token = self._user_token if use_user_token else self.get_tenant_token()
        if not token:
            raise ValueError("Not authenticated. Please connect Feishu first.")

        url = f"{self.base}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            url, data=body, method=method,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            raise ValueError(f"HTTP Error {e.code}: {error_body[:200]}")

    # ---- Documents ----

    def list_docs(self, folder_token: str = None, page_size: int = 50) -> list:
        """List documents from root folder or specified folder."""
        all_docs = []
        page_token = None

        # First get root folder token if not specified
        if not folder_token:
            try:
                result = self._api("GET", "/drive/explorer/v2/root_folder/meta")
                if result.get("code") == 0:
                    folder_token = result.get("data", {}).get("token", "")
            except Exception:
                pass

        while True:
            params = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token

            # Use folder children API
            path = f"/drive/v1/files" if not folder_token else f"/drive/explorer/v2/folder/{folder_token}/children"
            result = self._api("GET", path, params=params)

            if result.get("code") != 0:
                # Try alternative API
                result = self._api("GET", "/drive/v1/files", params={"page_size": page_size})
                if result.get("code") != 0:
                    raise ValueError(f"Feishu API error {result.get('code')}: {result.get('msg', 'unknown')}")

            # Handle different response formats
            files = result.get("data", {}).get("files", []) or result.get("data", {}).get("children", [])
            for f in files:
                all_docs.append({
                    "token": f.get("token", ""),
                    "name": f.get("name", f.get("title", "")),
                    "type": f.get("type", ""),
                    "url": f.get("url", ""),
                    "created": f.get("created_time", ""),
                    "modified": f.get("modified_time", f.get("edit_time", "")),
                })

            if not result.get("data", {}).get("has_more"):
                break
            page_token = result["data"].get("page_token")

        return all_docs

    def get_doc_content(self, doc_token: str, doc_type: str = "docx") -> str:
        """Get document content as text/markdown."""
        if doc_type in ("docx", "doc"):
            return self._get_docx_content(doc_token)
        elif doc_type == "sheet":
            return self._get_sheet_content(doc_token)
        return ""

    def _get_docx_content(self, doc_token: str) -> str:
        """Export docx as markdown-like text."""
        result = self._api("GET", f"/docx/v1/documents/{doc_token}/raw_content")
        if result.get("code") == 0:
            return result.get("data", {}).get("content", "")
        return ""

    def _get_sheet_content(self, sheet_token: str) -> str:
        """Get spreadsheet content."""
        result = self._api("GET", f"/sheets/v3/spreadsheets/{sheet_token}/sheets/query")
        if result.get("code") != 0:
            return ""

        parts = []
        for sheet in result.get("data", {}).get("sheets", []):
            sheet_id = sheet.get("sheet_id", "")
            title = sheet.get("title", "")
            # Read sheet data
            data_result = self._api(
                "GET",
                f"/sheets/v2/spreadsheets/{sheet_token}/values/{sheet_id}",
                params={"valueRenderOption": "ToString"},
            )
            if data_result.get("code") == 0:
                values = data_result.get("data", {}).get("valueRange", {}).get("values", [])
                parts.append(f"## Sheet: {title}")
                for row in values[:200]:
                    parts.append(" | ".join(str(c) for c in row))
        return "\n".join(parts)

    # ---- Chat Messages ----

    def list_chats(self, page_size: int = 50) -> list:
        """List chat groups/channels."""
        result = self._api("GET", "/im/v1/chats", params={"page_size": page_size})
        if result.get("code") != 0:
            return []
        return [
            {"id": c.get("chat_id"), "name": c.get("name", ""), "type": c.get("chat_type", "")}
            for c in result.get("data", {}).get("items", [])
        ]

    def get_chat_messages(self, chat_id: str, start_time: str = None,
                          page_size: int = 50) -> list:
        """Get messages from a chat."""
        params = {"container_id_type": "chat", "container_id": chat_id, "page_size": page_size}
        if start_time:
            params["start_time"] = start_time

        result = self._api("GET", "/im/v1/messages", params=params)
        if result.get("code") != 0:
            return []

        messages = []
        for msg in result.get("data", {}).get("items", []):
            body = msg.get("body", {})
            content = body.get("content", "")
            try:
                content_obj = json.loads(content)
                text = content_obj.get("text", content)
            except (json.JSONDecodeError, TypeError):
                text = content
            messages.append({
                "sender": msg.get("sender", {}).get("sender_id", {}).get("open_id", ""),
                "time": msg.get("create_time", ""),
                "type": msg.get("msg_type", ""),
                "text": text,
            })
        return messages

    # ---- Email ----

    def list_emails(self, page_size: int = 50) -> list:
        """List emails from user's mailbox."""
        # First get user's mailbox address
        try:
            mb_result = self._api("GET", "/mail/v1/users/me/mailboxes")
            mailbox_id = mb_result.get("data", {}).get("mailboxes", [{}])[0].get("mailbox_id", "me")
        except Exception:
            mailbox_id = "me"

        # List messages from INBOX
        result = self._api(
            "GET", f"/mail/v1/mailboxes/{mailbox_id}/messages",
            params={"page_size": page_size},
        )
        if result.get("code") != 0:
            raise ValueError(f"Mail API error {result.get('code')}: {result.get('msg', '')}")

        emails = []
        for msg in result.get("data", {}).get("items", []):
            emails.append({
                "id": msg.get("message_id", ""),
                "subject": msg.get("subject", ""),
                "from": msg.get("from", {}).get("address", ""),
                "date": msg.get("date", ""),
                "snippet": msg.get("snippet", ""),
            })
        return emails

    def get_email_content(self, message_id: str, mailbox_id: str = "me") -> str:
        """Get email body text."""
        result = self._api("GET", f"/mail/v1/mailboxes/{mailbox_id}/messages/{message_id}")
        if result.get("code") != 0:
            return ""
        return result.get("data", {}).get("body", {}).get("content", "")

    # ---- Sync All ----

    # Permission mapping for user-friendly error messages
    PERMISSION_HINTS = {
        "docs": {
            "required": ["docs:doc:readonly", "drive:drive:readonly"],
            "desc": "Cloud Documents / 云文档",
            "admin_required": True,
        },
        "chats": {
            "required": ["im:message", "im:message:readonly", "im:chat:readonly"],
            "desc": "Chat Messages / 聊天记录",
            "admin_required": False,
            "note": "After adding: re-publish app + re-OAuth / 添加后需重新发布+重新授权",
        },
        "emails": {
            "required": [
                "mail:user_mailbox.message:readonly",
                "mail:user_mailbox.message.body:read",
                "mail:user_mailbox.message.subject:read",
                "mail:user_mailbox.folder:read",
            ],
            "desc": "Feishu Mail / 飞书邮件",
            "admin_required": True,
        },
    }

    def sync_all(self, progress_callback=None,
                 sync_docs=True, sync_chats=True, sync_emails=True) -> dict:
        """Sync selected data — each module tried independently."""
        output_dir = get_workspace_dir(self.workspace) / "feishu_sync"
        output_dir.mkdir(parents=True, exist_ok=True)

        stats = {
            "docs": 0, "chats": 0, "emails": 0,
            "errors": [],
            "permissions": {},
        }

        # 1. Documents
        if progress_callback:
            progress_callback("Trying documents...")
        if not sync_docs:
            stats["permissions"]["docs"] = {"status": "skipped"}
        try:
            if not sync_docs:
                raise _SkipModule()
            docs = self.list_docs()
            stats["permissions"]["docs"] = {"status": "ok", "count": len(docs)}
            for doc in docs:
                try:
                    content = self.get_doc_content(doc["token"], doc["type"])
                    if content:
                        fname = f"feishu_doc_{doc['name']}.md"
                        safe_name = "".join(c if c.isalnum() or c in " _-." else "_" for c in fname)
                        (output_dir / safe_name).write_text(
                            f"# {doc['name']}\n\nSource: Feishu | Modified: {doc.get('modified','')}\n\n{content}",
                            encoding="utf-8",
                        )
                        stats["docs"] += 1
                except Exception as e:
                    stats["errors"].append(f"Doc {doc.get('name','?')}: {str(e)[:100]}")
        except _SkipModule:
            pass
        except Exception as e:
            err_str = str(e)
            is_permission = "permission" in err_str.lower() or "unauthorized" in err_str.lower() or "403" in err_str or "400" in err_str
            hint = self.PERMISSION_HINTS["docs"]
            if is_permission:
                stats["permissions"]["docs"] = {
                    "status": "no_permission",
                    "needed": hint["required"],
                    "admin": hint["admin_required"],
                    "error": err_str[:150],
                }
            else:
                stats["permissions"]["docs"] = {"status": "error", "error": err_str[:150]}
                stats["errors"].append(f"Docs: {err_str[:150]}")

        # 2. Chat messages
        if progress_callback:
            progress_callback("Trying chat messages...")
        if not sync_chats:
            stats["permissions"]["chats"] = {"status": "skipped"}
        try:
            if not sync_chats:
                raise _SkipModule()
            chats = self.list_chats()
            stats["permissions"]["chats"] = {"status": "ok", "count": len(chats)}
            chat_errors = []
            for idx, chat_info in enumerate(chats[:30]):
                if progress_callback:
                    progress_callback(f"Chat {idx+1}/{min(len(chats),30)}: {chat_info.get('name','')[:20]}")
                try:
                    messages = self.get_chat_messages(chat_info["id"])
                    if messages:
                        text_parts = [f"# Chat: {chat_info['name']}\n"]
                        for msg in messages:
                            text_parts.append(f"[{msg['time']}] {msg['text']}")
                        fname = f"feishu_chat_{chat_info['name']}.md"
                        safe_name = "".join(c if c.isalnum() or c in " _-." else "_" for c in fname)
                        (output_dir / safe_name).write_text("\n".join(text_parts), encoding="utf-8")
                        stats["chats"] += 1
                    else:
                        chat_errors.append(f"{chat_info.get('name','?')}: empty")
                except Exception as e:
                    chat_errors.append(f"{chat_info.get('name','?')}: {str(e)[:80]}")
            if chat_errors:
                # Show first few errors in stats
                stats["permissions"]["chats"]["chat_errors"] = chat_errors[:5]
                stats["permissions"]["chats"]["chat_error_count"] = len(chat_errors)
        except _SkipModule:
            pass
        except Exception as e:
            err_str = str(e)
            is_permission = "permission" in err_str.lower() or "unauthorized" in err_str.lower()
            hint = self.PERMISSION_HINTS["chats"]
            if is_permission:
                stats["permissions"]["chats"] = {"status": "no_permission", "needed": hint["required"]}
            else:
                stats["permissions"]["chats"] = {"status": "error", "error": err_str[:150]}

        # 3. Emails
        if progress_callback:
            progress_callback("Trying emails...")
        if not sync_emails:
            stats["permissions"]["emails"] = {"status": "skipped"}
        try:
            if not sync_emails:
                raise _SkipModule()
            emails = self.list_emails()
            stats["permissions"]["emails"] = {"status": "ok", "count": len(emails)}
            for email in emails:
                try:
                    body = self.get_email_content(email["id"])
                    if body or email.get("subject"):
                        text = f"# {email['subject']}\n\nFrom: {email['from']}\nDate: {email['date']}\n\n{body}"
                        fname = f"feishu_email_{email['subject'][:50]}.md"
                        safe_name = "".join(c if c.isalnum() or c in " _-." else "_" for c in fname)
                        (output_dir / safe_name).write_text(text, encoding="utf-8")
                        stats["emails"] += 1
                except Exception as e:
                    stats["errors"].append(f"Email: {str(e)[:100]}")
        except _SkipModule:
            pass
        except Exception as e:
            err_str = str(e)
            is_permission = "permission" in err_str.lower() or "unauthorized" in err_str.lower() or "404" in err_str
            hint = self.PERMISSION_HINTS["emails"]
            if is_permission:
                stats["permissions"]["emails"] = {"status": "no_permission", "needed": hint["required"]}
            else:
                stats["permissions"]["emails"] = {"status": "error", "error": err_str[:150]}

        stats["output_dir"] = str(output_dir)
        return stats


# Connector registry for future expansion
CONNECTORS = {
    "feishu": {
        "name": "Feishu (飞书)",
        "desc": "同步飞书云文档、聊天记录、邮件",
        "logo": "/static/logos/feishu.png",
        "fields": [
            {"key": "app_id", "label": "App ID", "type": "text", "placeholder": "cli_xxx"},
            {"key": "app_secret", "label": "App Secret", "type": "password", "placeholder": "xxx"},
            {"key": "use_lark", "label": "Use Lark (国际版, 非飞书用户勾选)", "type": "checkbox"},
        ],
        "scopes": [
            {"key": "im:message", "label": "Chat Messages / 聊天消息", "admin": False, "default": True},
            {"key": "im:message:readonly", "label": "Read Chat / 读取聊天", "admin": False, "default": True},
            {"key": "im:chat:readonly", "label": "List Chats / 列出群组", "admin": False, "default": True},
            {"key": "docs:doc:readonly", "label": "Read Docs / 读取文档", "admin": True, "default": False},
            {"key": "drive:drive:readonly", "label": "Read Drive / 读取云盘", "admin": True, "default": False},
            {"key": "mail:user_mailbox.message:readonly", "label": "Read Emails / 读取邮件", "admin": True, "default": False},
            {"key": "mail:user_mailbox.message.body:read", "label": "Email Body / 邮件正文", "admin": True, "default": False},
            {"key": "contact:user.email:readonly", "label": "User Email Info / 用户邮箱信息", "admin": True, "default": False},
        ],
        "signup_url": "https://open.feishu.cn/app",
        "setup_note": "OAuth setup: Copy the Redirect URI below and add it to your Feishu app > Security Settings > Redirect URLs",
    },
    "google-drive": {
        "name": "Google Drive",
        "desc": "Sync Google Docs, Sheets, Slides",
        "logo": "/static/logos/google-drive.png",
        "fields": [
            {"key": "credentials_json", "label": "Service Account JSON", "type": "file"},
        ],
        "signup_url": "https://console.cloud.google.com/apis/credentials",
        "coming_soon": True,
    },
    "notion": {
        "name": "Notion",
        "desc": "Sync Notion pages and databases",
        "logo": "/static/logos/notion.webp",
        "fields": [
            {"key": "api_key", "label": "Integration Token", "type": "password"},
        ],
        "signup_url": "https://www.notion.so/my-integrations",
        "coming_soon": True,
    },
    "onedrive": {
        "name": "OneDrive / SharePoint",
        "desc": "Sync Microsoft 365 documents",
        "logo": "/static/logos/onedrive.png",
        "fields": [],
        "signup_url": "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps",
        "coming_soon": True,
    },
    "imap-email": {
        "name": "Email (IMAP)",
        "desc": "Import emails via IMAP (Gmail, Outlook, etc.)",
        "logo": "/static/logos/email-imap.png",
        "fields": [
            {"key": "server", "label": "IMAP Server", "type": "text", "placeholder": "imap.gmail.com"},
            {"key": "port", "label": "Port", "type": "text", "placeholder": "993"},
            {"key": "email", "label": "Email", "type": "text"},
            {"key": "password", "label": "Password/App Password", "type": "password"},
        ],
        "coming_soon": True,
    },
}
