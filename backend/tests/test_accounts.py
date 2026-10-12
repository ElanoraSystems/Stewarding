from sqlalchemy import select

from app.models import AuditLog

from .conftest import PASSWORD
from .helpers import MGR, STEWARD, SUP, loc_id

NEW_EMAIL = "new.hire@example.com"
INITIAL = "initial-pass-123"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def sign_in(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def hire(client, login, db, role="steward", email=NEW_EMAIL):
    body = {"employee_code": "E777", "full_name": "Nora Newhire", "job_title": "Steward", "email": email, "password": INITIAL,
            "role": role, "location_ids": [loc_id(db, "MK")]}
    r = client.post("/api/employees", json=body, headers=login(MGR))
    assert r.status_code == 201, r.text
    return r.json()


def test_a_new_employee_must_choose_their_own_password_before_anything_else(client, login, db):
    hire(client, login, db)
    first = sign_in(client, NEW_EMAIL, INITIAL).json()
    assert first["change_required"] is True
    h = auth(first["access_token"])
    assert client.get("/api/auth/me", headers=h).json()["change_required"] is True
    blocked = client.get("/api/attendance/me/status", headers=h)
    assert blocked.status_code == 403 and "Change your password" in blocked.json()["detail"]
    changed = client.post("/api/auth/change-password", json={"current_password": INITIAL, "new_password": "My-own-secret-77"}, headers=h)
    assert changed.status_code == 200
    assert client.get("/api/attendance/me/status", headers=h).status_code == 401  # the old session ended
    fresh = auth(changed.json()["access_token"])
    assert client.get("/api/attendance/me/status", headers=fresh).status_code == 200
    assert client.get("/api/auth/me", headers=fresh).json()["change_required"] is False
    assert sign_in(client, NEW_EMAIL, INITIAL).status_code == 401
    again = sign_in(client, NEW_EMAIL, "My-own-secret-77").json()
    assert again["change_required"] is False


def test_password_changes_are_checked(client, login, db):
    hire(client, login, db)
    h = auth(sign_in(client, NEW_EMAIL, INITIAL).json()["access_token"])

    def change(current, new):
        return client.post("/api/auth/change-password", json={"current_password": current, "new_password": new}, headers=h)

    assert change("wrong-password-1", "Brand-new-pass-9").status_code == 400
    assert change(INITIAL, "short1A").status_code == 422
    assert change(INITIAL, "alllowercaseletters").status_code == 400            # one kind of character
    assert change(INITIAL, "the-new.hire-2026").status_code == 400              # contains the sign-in name
    assert change(INITIAL, INITIAL).status_code == 400                          # not a change
    assert client.post("/api/auth/change-password", json={"current_password": INITIAL, "new_password": "Brand-new-pass-9"}).status_code == 401
    assert change(INITIAL, "Brand-new-pass-9").status_code == 200


def test_repeated_wrong_current_passwords_are_throttled(client, login, db):
    hire(client, login, db)
    h = auth(sign_in(client, NEW_EMAIL, INITIAL).json()["access_token"])
    codes = [client.post("/api/auth/change-password", json={"current_password": f"wrong-guess-{n}", "new_password": "Brand-new-pass-9"}, headers=h).status_code
             for n in range(6)]
    assert codes[:5] == [400] * 5 and codes[5] == 429


def test_manager_resets_a_forgotten_password(client, login, db):
    emp = hire(client, login, db)
    h = auth(sign_in(client, NEW_EMAIL, INITIAL).json()["access_token"])
    client.post("/api/auth/change-password", json={"current_password": INITIAL, "new_password": "Employee-chosen-5"}, headers=h)
    session = auth(sign_in(client, NEW_EMAIL, "Employee-chosen-5").json()["access_token"])
    assert client.get("/api/attendance/me/status", headers=session).status_code == 200
    reset = client.post(f"/api/employees/{emp['id']}/reset-password", json={}, headers=login(MGR))
    assert reset.status_code == 200 and reset.json()["change_required"] is True
    temp = reset.json()["temporary_password"]
    assert len(temp) == 12 and any(c.isdigit() for c in temp) and any(c.isalpha() for c in temp)
    assert client.get("/api/attendance/me/status", headers=session).status_code == 401   # open sessions ended
    assert sign_in(client, NEW_EMAIL, "Employee-chosen-5").status_code == 401
    after = sign_in(client, NEW_EMAIL, temp).json()
    assert after["change_required"] is True
    account = client.get(f"/api/employees/{emp['id']}", headers=login(MGR)).json()["account"]
    assert account["change_required"] is True and account["last_login_at"]
    other = client.post(f"/api/employees/{emp['id']}/reset-password", json={}, headers=login(MGR)).json()["temporary_password"]
    assert other != temp
    logged = [str(a.after) + str(a.before) for a in db.scalars(select(AuditLog).where(AuditLog.action == "password.reset"))]
    assert len(logged) == 2 and not any(temp in text or other in text for text in logged)


def test_reset_rules_and_permissions(client, login, db):
    emp = hire(client, login, db)
    mgr = login(MGR)
    for who in (SUP, STEWARD):
        assert client.post(f"/api/employees/{emp['id']}/reset-password", json={}, headers=login(who)).status_code == 403
    mine = client.get("/api/auth/me", headers=mgr).json()["employee"]["id"]
    assert client.post(f"/api/employees/{mine}/reset-password", json={}, headers=mgr).status_code == 400
    assert client.post("/api/employees/9999/reset-password", json={}, headers=mgr).status_code == 404
    assert client.post(f"/api/employees/{emp['id']}/reset-password", json={"new_password": "short"}, headers=mgr).status_code == 422
    assert client.post(f"/api/employees/{emp['id']}/reset-password", json={"new_password": "onlyletterspassword"}, headers=mgr).status_code == 400
    ok = client.post(f"/api/employees/{emp['id']}/reset-password", json={"new_password": "Chosen-by-boss-8"}, headers=mgr)
    assert ok.status_code == 200 and ok.json()["temporary_password"] == "Chosen-by-boss-8"
    assert sign_in(client, NEW_EMAIL, "Chosen-by-boss-8").json()["change_required"] is True


def test_a_manager_can_correct_an_email_but_not_their_own_role(client, login, db):
    emp = hire(client, login, db)
    mgr = login(MGR)
    assert client.put(f"/api/employees/{emp['id']}", json={"email": "nora.n@example.com"}, headers=mgr).status_code == 200
    assert sign_in(client, NEW_EMAIL, INITIAL).status_code == 401
    assert sign_in(client, "nora.n@example.com", INITIAL).status_code == 200
    assert client.put(f"/api/employees/{emp['id']}", json={"email": "manager@example.test"}, headers=mgr).status_code in (409, 422)
    assert client.put(f"/api/employees/{emp['id']}", json={"email": "sup.mk@example.com"}, headers=mgr).status_code == 200
    mine = client.get("/api/auth/me", headers=mgr).json()["employee"]["id"]
    assert client.put(f"/api/employees/{mine}", json={"role": "steward"}, headers=mgr).status_code == 400
    assert client.put(f"/api/employees/{emp['id']}", json={"role": "supervisor"}, headers=mgr).status_code == 200


def test_the_first_manager_account_is_not_forced_to_change(client, login):
    assert client.post("/api/auth/login", json={"email": MGR, "password": PASSWORD}).json()["change_required"] is False
