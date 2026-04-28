"""Auth router — register and login."""

import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, status
from loguru import logger

from verdeai_shared.auth.keycloak_admin import assign_realm_role, create_user
from verdeai_shared.db.mongo import get_database
from verdeai_shared.settings import settings as shared_settings

from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest, RegisterResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest) -> RegisterResponse:
    """Register a new user and tenant.

    1. Generate a fresh tenant_id UUID.
    2. Create the user in Keycloak with the tenant_id attribute.
    3. Assign the compliance-officer realm role.
    4. Upsert a users row in MongoDB keyed by Keycloak sub.
    """
    tenant_id = str(uuid.uuid4())

    # Step 1: Create user in Keycloak
    try:
        keycloak_sub = create_user(
            email=body.email,
            password=body.password,
            first_name=body.first_name,
            last_name=body.last_name,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.error("Keycloak user creation failed", error=str(exc))
        # Surface conflict errors (duplicate email) as 409
        err_msg = str(exc).lower()
        if "conflict" in err_msg or "exists" in err_msg or "409" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create user in identity provider",
        ) from exc

    # Step 2: Assign role
    try:
        assign_realm_role(keycloak_sub, "compliance-officer")
    except Exception as exc:
        logger.error("Role assignment failed", keycloak_sub=keycloak_sub, error=str(exc))
        # Non-fatal: user is created; role assignment failure logged only

    # Step 3: Upsert Mongo users row
    db = get_database()
    now = datetime.now(timezone.utc)
    result = await db.users.update_one(
        {"keycloak_sub": keycloak_sub},
        {
            "$set": {
                "keycloak_sub": keycloak_sub,
                "email": body.email,
                "tenant_id": tenant_id,
                "roles": ["compliance-officer"],
                "last_seen_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    # Fetch the upserted/updated document to get its _id
    user_doc = await db.users.find_one({"keycloak_sub": keycloak_sub})
    user_id = str(user_doc["_id"]) if user_doc else keycloak_sub

    logger.info("User registered", email=body.email, tenant_id=tenant_id)
    return RegisterResponse(
        user_id=user_id,
        keycloak_sub=keycloak_sub,
        tenant_id=tenant_id,
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    """Exchange email + password for a Keycloak access token.

    Proxies the Keycloak ROPC token endpoint so clients never need to
    know the Keycloak URL or client_id.
    """
    token_url = (
        f"{shared_settings.KEYCLOAK_URL}/realms/"
        f"{shared_settings.KEYCLOAK_REALM}/protocol/openid-connect/token"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": shared_settings.KEYCLOAK_FRONTEND_CLIENT_ID,
                "username": body.email,
                "password": body.password,
            },
        )

    if resp.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if resp.status_code != 200:
        logger.error("Keycloak token error", status=resp.status_code, body=resp.text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Identity provider error",
        )

    data = resp.json()
    return LoginResponse(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", ""),
        expires_in=data["expires_in"],
    )
