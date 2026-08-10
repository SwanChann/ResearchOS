from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from .config import load_config
from .errors import ResearchFlowError


DEFAULT_BASE_URL = "http://127.0.0.1:23119/api"
DEFAULT_LIBRARY = "users/0"
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_LIBRARY_PATTERN = re.compile(r"^(users/0|groups/[0-9]+)$")
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9]+$")
_LOOPBACK_OPENER = build_opener(ProxyHandler({}))


def validate_base_url(value: str) -> str:
    url = value.rstrip("/")
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in _LOOPBACK_HOSTS or parts.username or parts.password:
        raise ResearchFlowError("Zotero Local API must use an unauthenticated loopback http URL.")
    if parts.path.rstrip("/") != "/api" or parts.query or parts.fragment:
        raise ResearchFlowError("Zotero Local API URL must end at /api with no query or fragment.")
    return url


def validate_library(value: str) -> str:
    if not _LIBRARY_PATTERN.fullmatch(value):
        raise ResearchFlowError("Zotero library must be users/0 or groups/<numeric-id>.")
    return value


def validate_key(value: str, kind: str = "item") -> str:
    if not _KEY_PATTERN.fullmatch(value):
        raise ResearchFlowError(f"Invalid Zotero {kind} key: {value}")
    return value


def zotero_settings(config: dict[str, Any] | None = None) -> dict[str, str]:
    data = config or load_config()
    literature = data.get("preferences", {}).get("literature", {})
    configured = literature.get("zotero", {}) if isinstance(literature, dict) else {}
    base_url = validate_base_url(str(configured.get("base_url", DEFAULT_BASE_URL)))
    library = validate_library(str(configured.get("library", DEFAULT_LIBRARY)))
    return {
        "authority": str(literature.get("authority", "unconfigured")),
        "access": "read_only",
        "base_url": base_url,
        "library": library,
    }


@dataclass
class ZoteroResponse:
    body: bytes
    headers: dict[str, str]


class ZoteroClient:
    """Read-only client for Zotero's loopback Local API.

    This class intentionally exposes no generic request method and constructs
    every request with GET. Zotero write authorization and API keys are outside
    the ResearchFlow integration boundary.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, library: str = DEFAULT_LIBRARY, timeout: float = 5.0):
        self.base_url = validate_base_url(base_url)
        self.library = validate_library(library)
        self.timeout = timeout
        self.server_id: str | None = None

    @classmethod
    def from_config(cls, library: str | None = None) -> "ZoteroClient":
        settings = zotero_settings()
        return cls(settings["base_url"], library or settings["library"])

    def _get(self, path: str = "", params: dict[str, Any] | None = None, accept: str = "application/json") -> ZoteroResponse:
        suffix = "/" + path.lstrip("/") if path else "/"
        url = self.base_url + suffix
        query = {key: value for key, value in (params or {}).items() if value is not None}
        if query:
            url += "?" + urlencode(query, doseq=True)
        headers = {"Accept": accept, "Zotero-API-Version": "3"}
        if self.server_id:
            headers["Zotero-Server-ID"] = self.server_id
        request = Request(url, headers=headers, method="GET")
        try:
            with _LOOPBACK_OPENER.open(request, timeout=self.timeout) as response:
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                server_id = response_headers.get("zotero-server-id")
                if server_id:
                    if self.server_id and self.server_id != server_id:
                        raise ResearchFlowError("Zotero database changed during the request; discard this handoff and retry.")
                    self.server_id = server_id
                return ZoteroResponse(response.read(), response_headers)
        except HTTPError as exc:
            if exc.code == 403:
                detail = "Enable Zotero Settings > Advanced > Allow other applications on this computer to communicate with Zotero."
            elif exc.code == 412:
                detail = "The Zotero database identity changed; retry without cached state."
            else:
                detail = f"HTTP {exc.code} {exc.reason}"
            raise ResearchFlowError(f"Zotero Local API request failed: {detail}") from exc
        except URLError as exc:
            raise ResearchFlowError(
                f"Cannot reach Zotero Local API at {self.base_url}. Start Zotero and enable local API access."
            ) from exc
        except OSError as exc:
            raise ResearchFlowError(f"Zotero Local API request failed: {exc}") from exc

    def _json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self._get(path, params)
        try:
            return json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResearchFlowError(f"Zotero returned invalid JSON for {path or '/api/'}.") from exc

    def status(self) -> dict[str, Any]:
        response = self._get()
        return {
            "available": True,
            "access": "read_only",
            "base_url": self.base_url,
            "library": self.library,
            "api_version": response.headers.get("zotero-api-version"),
            "schema_version": response.headers.get("zotero-schema-version"),
            "server_id": response.headers.get("zotero-server-id"),
        }

    def libraries(self) -> list[dict[str, Any]]:
        self.status()
        result = [{"library": "users/0", "type": "user", "name": "My Library"}]
        groups = self._json("users/0/groups")
        for group in groups:
            data = group.get("data", group)
            group_id = data.get("id") or group.get("id")
            if group_id is not None:
                result.append({"library": f"groups/{group_id}", "type": "group", "name": data.get("name")})
        return result

    def collections(self) -> list[dict[str, Any]]:
        self.status()
        return self._json(f"{self.library}/collections")

    def search(self, query: str, collection: str | None = None, tag: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
        if not query.strip():
            raise ResearchFlowError("Zotero search query cannot be empty.")
        if not 1 <= limit <= 200:
            raise ResearchFlowError("Zotero search limit must be between 1 and 200.")
        self.status()
        path = f"{self.library}/items/top"
        if collection:
            path = f"{self.library}/collections/{validate_key(collection, 'collection')}/items/top"
        items = self._json(path, {"q": query, "qmode": "everything", "tag": tag, "limit": limit})
        return [item for item in items if item.get("data", {}).get("itemType") not in {"attachment", "note", "annotation"}]

    def item(self, item_key: str) -> dict[str, Any]:
        self.status()
        item = self._json(f"{self.library}/items/{validate_key(item_key)}")
        item_type = item.get("data", {}).get("itemType")
        if item_type in {"attachment", "note", "annotation"}:
            raise ResearchFlowError(f"Zotero item {item_key} is {item_type}, not a bibliographic parent item.")
        return item

    def context(self, item_key: str) -> dict[str, Any]:
        item = self.item(item_key)
        children = self._json(f"{self.library}/items/{validate_key(item_key)}/children")
        attachments: list[dict[str, Any]] = []
        notes: list[dict[str, Any]] = []
        for child in children:
            data = child.get("data", {})
            if data.get("itemType") == "attachment":
                attachment = dict(child)
                attachment_key = child.get("key") or data.get("key")
                if attachment_key:
                    attachment_key = validate_key(str(attachment_key), "attachment")
                    attachment["annotations"] = self._json(f"{self.library}/items/{attachment_key}/children")
                    try:
                        response = self._get(
                            f"{self.library}/items/{attachment_key}/file/view/url",
                            accept="text/plain",
                        )
                        attachment["file_url"] = response.body.decode("utf-8").strip()
                    except ResearchFlowError as exc:
                        attachment["file_url"] = None
                        attachment["file_url_error"] = str(exc)
                attachments.append(attachment)
            elif data.get("itemType") == "note":
                notes.append(child)
        return {"item": item, "attachments": attachments, "notes": notes}

    def bibliography(self, item_keys: list[str], style: str = "apa", locale: str = "en-US") -> str:
        if not item_keys:
            raise ResearchFlowError("At least one Zotero item key is required.")
        keys = [validate_key(value) for value in item_keys]
        self.status()
        response = self._get(
            f"{self.library}/items",
            {"itemKey": ",".join(keys), "format": "bib", "style": style, "locale": locale},
            accept="text/html",
        )
        return response.body.decode("utf-8")


def item_metadata(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data", {})
    creators = []
    for creator in data.get("creators", []):
        name = creator.get("name") or " ".join(part for part in (creator.get("firstName"), creator.get("lastName")) if part)
        if name:
            creators.append(name)
    date = str(data.get("date") or "")
    match = re.search(r"(?<![0-9])(19[0-9]{2}|20[0-9]{2}|21[0-9]{2})(?![0-9])", date)
    venue = next((data.get(field) for field in ("publicationTitle", "proceedingsTitle", "conferenceName", "bookTitle", "publisher") if data.get(field)), None)
    doi = str(data.get("DOI") or "").strip()
    url = data.get("url") or (f"https://doi.org/{doi}" if doi else None)
    return {
        "title": str(data.get("title") or "Untitled Zotero item"),
        "authors": creators,
        "venue": venue,
        "year": int(match.group(1)) if match else None,
        "url": url,
        "tags": [tag.get("tag") for tag in data.get("tags", []) if tag.get("tag")],
        "item_version": item.get("version") or data.get("version"),
    }
