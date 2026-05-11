"""Pydantic models for WebDAV-backed data sources (CRUD API)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceType(StrEnum):
    OWNCLOUD = "OWNCLOUD"
    NEXTCLOUD = "NEXTCLOUD"
    GENERIC_WEBDAV = "GENERIC_WEBDAV"
    LOCAL_FOLDER = "LOCAL_FOLDER"


WEBDAV_KINDS = frozenset(
    {
        SourceType.OWNCLOUD,
        SourceType.NEXTCLOUD,
        SourceType.GENERIC_WEBDAV,
    }
)


class DataSourceCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, strip_whitespace=True)]
    source_type: str
    server_url: Annotated[str, Field(min_length=1, strip_whitespace=True)]
    webdav_root_path: str | None = None
    username: str | None = None
    credential_secret: str | None = None
    description: str | None = None
    is_active: bool = True

    @field_validator("source_type")
    @classmethod
    def validate_source_type_create(cls, v: str) -> str:
        s = v.strip().upper()
        if s not in {e.value for e in SourceType}:
            raise ValueError(
                "source_type must be one of: OWNCLOUD, NEXTCLOUD, GENERIC_WEBDAV, LOCAL_FOLDER"
            )
        return s

    @field_validator("server_url")
    @classmethod
    def strip_server_url(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def validate_urls_and_paths(self):  # type: ignore[no-untyped-def]
        st = SourceType(self.source_type)
        url = self.server_url.strip()

        if st == SourceType.LOCAL_FOLDER:
            if len(url) < 1:
                raise ValueError("server_url cannot be empty")
            return self

        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(
                "server_url must start with http:// or https:// for WebDAV source types"
            )

        if st in WEBDAV_KINDS:
            if not self.webdav_root_path or not str(self.webdav_root_path).strip():
                raise ValueError(
                    "webdav_root_path is required for OWNCLOUD, NEXTCLOUD, and GENERIC_WEBDAV"
                )
        return self


class DataSourceUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=1, strip_whitespace=True)] = None
    source_type: str | None = None
    server_url: Annotated[str | None, Field(min_length=1, strip_whitespace=True)] = None
    webdav_root_path: str | None = None
    username: str | None = None
    credential_secret: str | None = None
    description: str | None = None
    is_active: bool | None = None

    @field_validator("source_type")
    @classmethod
    def validate_source_type_upd(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip().upper()
        if s not in {e.value for e in SourceType}:
            raise ValueError(
                "source_type must be one of: OWNCLOUD, NEXTCLOUD, GENERIC_WEBDAV, LOCAL_FOLDER"
            )
        return s

    @field_validator("server_url")
    @classmethod
    def strip_server_url_upd(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip()

    @model_validator(mode="after")
    def validate_update_consistency(self):  # type: ignore[no-untyped-def]
        if self.source_type is not None:
            st = SourceType(self.source_type)
            if self.server_url is not None:
                url = self.server_url.strip()
                if st != SourceType.LOCAL_FOLDER and not (
                    url.startswith("http://") or url.startswith("https://")
                ):
                    raise ValueError(
                        "server_url must start with http:// or https:// "
                        "for WebDAV source types"
                    )

            rp = self.webdav_root_path
            if rp is not None and not rp.strip() and st in WEBDAV_KINDS:
                raise ValueError("webdav_root_path cannot be empty for WebDAV source types")

        if (
            self.webdav_root_path is not None
            and self.webdav_root_path.strip()
            and self.source_type is None
            and self.server_url is None
        ):
            return self

        return self


class DataSourceResponse(BaseModel):
    id: UUID
    name: str
    source_type: str
    server_url: str
    webdav_root_path: str | None
    username: str | None
    has_credential: bool
    description: str | None
    is_active: bool
    last_connection_test_at: datetime | None
    last_connection_success: bool | None
    last_connection_message: str | None
    last_scan_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    warnings: list[str] | None = None

    model_config = {"from_attributes": True}


class DataSourceListEnvelope(BaseModel):
    items: list[DataSourceResponse]
    total: int
