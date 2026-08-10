from http.cookies import SimpleCookie

from .test_commands import ORIGIN, authenticate, client_for, register


async def test_authentication_sets_exact_secure_host_cookie_and_ignores_fixation(
    identity_service: object,
) -> None:
    async with await client_for(identity_service) as client:
        await register(client)
        client.cookies.set("__Host-polyglot_session", "attacker-fixed", domain="polyglot.test")
        response = await authenticate(client)

    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    morsel = cookie["__Host-polyglot_session"]
    assert response.status_code == 201
    assert morsel.value != "attacker-fixed"
    assert morsel["secure"] is True
    assert morsel["httponly"] is True
    assert morsel["samesite"] == "lax"
    assert morsel["path"] == "/"
    assert morsel["domain"] == ""


async def test_mutations_require_same_origin_and_session_bound_csrf(
    identity_service: object,
) -> None:
    async with await client_for(identity_service) as client:
        await register(client)
        authenticated = await authenticate(client)
        csrf = authenticated.json()["csrf_token"]
        cross_origin = await client.patch(
            "/api/v1/account/preferences",
            headers={
                "Origin": "https://attacker.invalid",
                "X-CSRF-Token": csrf,
                "If-Match": '"1"',
            },
            json={"interface_locale": "fr-FR"},
        )
        missing_origin = await client.patch(
            "/api/v1/account/preferences",
            headers={"X-CSRF-Token": csrf, "If-Match": '"1"'},
            json={"interface_locale": "fr-FR"},
        )
        missing_csrf = await client.patch(
            "/api/v1/account/preferences",
            headers={"Origin": ORIGIN, "If-Match": '"1"'},
            json={"interface_locale": "fr-FR"},
        )
        invalid_csrf = await client.patch(
            "/api/v1/account/preferences",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": "csrf-from-another-session",
                "If-Match": '"1"',
            },
            json={"interface_locale": "fr-FR"},
        )

    for response in (cross_origin, invalid_csrf):
        assert response.status_code == 403
        assert response.json()["code"] == "forbidden"
    for response in (missing_origin, missing_csrf):
        assert response.status_code == 422
        assert response.json()["code"] == "validation_failed"


async def test_revoke_clears_cookie_and_prevents_session_replay(
    identity_service: object,
) -> None:
    async with await client_for(identity_service) as client:
        await register(client)
        authenticated = await authenticate(client)
        response = await client.delete(
            "/api/v1/session",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": authenticated.json()["csrf_token"],
                "Idempotency-Key": "revoke-http",
            },
        )
        replay = await client.get("/api/v1/session")

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert replay.status_code == 401
