"""Auth schemas."""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    organisation_name: str = Field(min_length=1)


class RegisterResponse(BaseModel):
    user_id: str
    keycloak_sub: str
    tenant_id: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class WSTicketResponse(BaseModel):
    ticket: str
    expires_in: int
