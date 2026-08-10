from httpx import ASGITransport, AsyncClient

ORIGIN = "https://polyglot.test"


async def client_for(service: object) -> AsyncClient:
    from polyglot.interfaces.http.app import create_app

    app = create_app(
        test_mode=True,
        identity_service=service,
        allowed_origin=ORIGIN,
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN)


async def register(client: AsyncClient) -> object:
    return await client.post(
        "/api/v1/accounts",
        headers={"Origin": ORIGIN, "Idempotency-Key": "register-http"},
        json={
            "provider_type": "local_password",
            "identifier": "http-owner@example.test",
            "password": "correct horse battery staple",
        },
    )


async def authenticate(client: AsyncClient, *, key: str = "authenticate-http") -> object:
    return await client.post(
        "/api/v1/session",
        headers={"Origin": ORIGIN, "Idempotency-Key": key},
        json={
            "provider_type": "local_password",
            "identifier": "http-owner@example.test",
            "password": "correct horse battery staple",
        },
    )


async def test_canonical_identity_routes_execute_and_return_closed_results(
    identity_service: object,
) -> None:
    async with await client_for(identity_service) as client:
        registered = await register(client)
        authenticated = await authenticate(client)
        csrf = authenticated.json()["csrf_token"]
        current = await client.get("/api/v1/session")
        preferences = await client.patch(
            "/api/v1/account/preferences",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "If-Match": '"1"'},
            json={"interface_locale": "fr-FR", "preferred_sprint_minutes": 35},
        )
        consent = await client.put(
            "/api/v1/consents/speech_training",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": csrf,
                "If-Match": '"0"',
                "Idempotency-Key": "consent-http",
            },
            json={
                "status": "granted",
                "policy_revision_id": "019fe900-4000-7000-8000-000000000001",
            },
        )
        changed = await client.put(
            "/api/v1/account/password",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": csrf,
                "Idempotency-Key": "password-http",
            },
            json={
                "current_password": "correct horse battery staple",
                "new_password": "new correct horse battery staple",
            },
        )

    assert registered.status_code == 201
    assert authenticated.status_code == 201
    assert current.status_code == 200
    assert preferences.status_code == 200
    assert preferences.json()["interface_locale"] == "fr-FR"
    assert consent.status_code == 200
    assert consent.json()["status"] == "granted"
    assert changed.status_code == 200
    assert current.json()["account_id"] == registered.json()["account_id"]


async def test_duplicate_registration_and_replay_conflict_use_w00_problems(
    identity_service: object,
) -> None:
    async with await client_for(identity_service) as client:
        first = await register(client)
        replay = await register(client)
        conflict = await client.post(
            "/api/v1/accounts",
            headers={"Origin": ORIGIN, "Idempotency-Key": "register-http"},
            json={
                "provider_type": "local_password",
                "identifier": "http-owner@example.test",
                "password": "different password value",
            },
        )
        duplicate = await client.post(
            "/api/v1/accounts",
            headers={"Origin": ORIGIN, "Idempotency-Key": "register-duplicate"},
            json={
                "provider_type": "local_password",
                "identifier": "http-owner@example.test",
                "password": "correct horse battery staple",
            },
        )

    assert first.status_code == 201 and replay.json() == first.json()
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "identity_conflict"


async def test_invalid_credentials_do_not_disclose_unknown_identity(
    identity_service: object,
) -> None:
    async with await client_for(identity_service) as client:
        await register(client)
        wrong_password = await client.post(
            "/api/v1/session",
            headers={"Origin": ORIGIN, "Idempotency-Key": "wrong-password"},
            json={
                "provider_type": "local_password",
                "identifier": "http-owner@example.test",
                "password": "incorrect password value",
            },
        )
        unknown = await client.post(
            "/api/v1/session",
            headers={"Origin": ORIGIN, "Idempotency-Key": "unknown-account"},
            json={
                "provider_type": "local_password",
                "identifier": "unknown@example.test",
                "password": "incorrect password value",
            },
        )

    assert wrong_password.status_code == unknown.status_code == 401
    assert wrong_password.json()["code"] == unknown.json()["code"] == "invalid_credentials"


async def test_if_match_and_closed_request_schema_block_stale_write_and_idor(
    identity_service: object,
) -> None:
    async with await client_for(identity_service) as client:
        await register(client)
        authenticated = await authenticate(client)
        csrf = authenticated.json()["csrf_token"]
        stale = await client.patch(
            "/api/v1/account/preferences",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "If-Match": '"7"'},
            json={"interface_locale": "fr-FR"},
        )
        idor = await client.patch(
            "/api/v1/account/preferences",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "If-Match": '"1"'},
            json={
                "interface_locale": "fr-FR",
                "account_id": "019fe900-4000-7000-8000-000000000099",
            },
        )

    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    assert idor.status_code == 422 and idor.json()["code"] == "validation_failed"
