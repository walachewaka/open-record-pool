"""Schemas for the SSO surface (MOO-88)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class AuthProviderSchema(BaseModel):
    """One sign-in button on the login gate. Never carries client ids/secrets."""

    id: str
    display_name: str


class AuthMethodsSchema(BaseModel):
    local_login: bool
    providers: List[AuthProviderSchema] = []


class IdentitySchema(BaseModel):
    id: int
    provider: str
    provider_name: str
    email: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class AdminSSOProviderSchema(BaseModel):
    id: str
    display_name: str
    issuer: str
    client_id: str
    scopes: str
    provisioning: str
    allowed_domains: List[str] = []
    role_mapping: bool = False
    redirect_uri: str
    linked_identities: int = 0
    discovery: str = "unchecked"


class AdminSSOStatusSchema(BaseModel):
    local_login: bool
    email_autolink: bool
    providers: List[AdminSSOProviderSchema] = []
