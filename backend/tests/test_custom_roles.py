from sqlalchemy import select

from app.models import AuditLog, Role, User
from app.services.notify import recipients

from .helpers import MGR, STEWARD, SUP, loc_id

CHEF_PASSWORD = "Kitchen-pass-9876!"


def make_role(client, h, label="Head Chef", tier="supervisor", permissions=None):
    perms = permissions if permissions is not None else ["dashboard.view", "inventory.module", "inventory.view", "inventory.count", "report.view"]
    return client.post("/api/roles", headers=h, json={"label": label, "tier": tier, "permissions": perms})


def hire(client, db, h, role, email, places=("MK",), **extra):
    body = {"full_name": "Test Person", "job_title": "Head Chef", "email": email, "password": CHEF_PASSWORD, "role": role,
            "location_ids": [loc_id(db, p) for p in places], **extra}
    made = client.post("/api/employees", headers=h, json=body)
    assert made.status_code == 201, made.text
    db.expire_all()
    db.scalar(select(User).where(User.email == email)).must_change_password = False
    db.commit()
    token = client.post("/api/auth/login", json={"email": email, "password": CHEF_PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_a_manager_makes_a_role_and_the_person_gets_exactly_those_permissions(client, login, db, clock):
    m = login(MGR)
    made = make_role(client, m)
    assert made.status_code == 201 and made.json()["name"] == "head_chef" and made.json()["label"] == "Head Chef"
    chef = hire(client, db, m, "head_chef", "chef@example.com")
    assert client.get("/api/inventory/items", headers=chef).status_code == 200
    assert client.post("/api/employees", headers=chef, json={}).status_code == 403
    assert client.get("/api/roles", headers=chef).status_code == 403
    me = client.get("/api/auth/me", headers=chef).json()
    assert me["tier"] == "supervisor" and me["role_label"] == "Head Chef" and "settings.manage" not in me["permissions"]
    assert {mod["key"] for mod in me["modules"]} >= {"inventory", "reports"} and "settings" not in {mod["key"] for mod in me["modules"]}


def test_only_a_manager_can_change_roles(client, login, db, clock):
    for who in (SUP, STEWARD):
        assert make_role(client, login(who)).status_code == 403
    assert client.get("/api/roles/catalog", headers=login(SUP)).status_code == 403


def test_a_role_is_checked_before_it_is_saved(client, login, db, clock):
    m = login(MGR)
    assert make_role(client, m, permissions=["not.a.permission"]).status_code == 422
    assert make_role(client, m, tier="manager").status_code == 422
    assert make_role(client, m, permissions=[]).status_code == 422
    assert make_role(client, m).status_code == 201
    assert make_role(client, m, label="head chef").status_code == 409
    assert make_role(client, m, label="Supervisor").status_code == 409


def test_built_in_roles_are_fixed_and_a_role_in_use_cannot_be_deleted(client, login, db, clock):
    m = login(MGR)
    builtin = db.scalar(select(Role).where(Role.name == "supervisor"))
    assert client.put(f"/api/roles/{builtin.id}", headers=m, json={"label": "Boss"}).status_code == 400
    assert client.delete(f"/api/roles/{builtin.id}", headers=m).status_code == 400
    role = make_role(client, m).json()
    hire(client, db, m, role["name"], "chef@example.com")
    assert client.delete(f"/api/roles/{role['id']}", headers=m).status_code == 409
    spare = make_role(client, m, label="Spare Role").json()
    assert client.delete(f"/api/roles/{spare['id']}", headers=m).status_code == 200
    actions = {a.action for a in db.scalars(select(AuditLog))}
    assert {"role.create", "role.delete"} <= actions


def test_changing_a_role_changes_what_its_people_may_do(client, login, db, clock):
    m = login(MGR)
    role = make_role(client, m).json()
    chef = hire(client, db, m, role["name"], "chef@example.com")
    assert client.get("/api/breakage", headers=chef).status_code == 403
    changed = client.put(f"/api/roles/{role['id']}", headers=m, json={"permissions": ["dashboard.view", "breakage.view"]})
    assert changed.status_code == 200 and changed.json()["users"] == 1
    assert client.get("/api/breakage", headers=chef).status_code == 200
    assert client.get("/api/inventory/items", headers=chef).status_code == 403


def test_the_tier_decides_who_is_told_and_what_they_see(client, login, db, clock):
    m = login(MGR)
    make_role(client, m)
    make_role(client, m, label="Kitchen Porter", tier="steward", permissions=["dashboard.view", "attendance.self", "checklist.view"])
    chef = hire(client, db, m, "head_chef", "chef@example.com", places=("BQ",))
    porter = hire(client, db, m, "kitchen_porter", "porter@example.com")
    chef_id = db.scalar(select(User.id).where(User.email == "chef@example.com"))
    assert chef_id in recipients(db, loc_id(db, "BQ"), "supervisor")
    assert chef_id not in recipients(db, loc_id(db, "RB"), "supervisor")
    assert client.get("/api/dashboard", headers=porter).json()["role"] == "steward"
    assert client.get("/api/dashboard", headers=chef).json().get("role") != "steward"


def test_nobody_can_hand_out_more_access_than_they_hold(client, login, db, clock):
    m = login(MGR)
    make_role(client, m, label="Hr Lead", permissions=["dashboard.view", "employee.view", "employee.manage"])
    make_role(client, m, label="Boss Light", permissions=["dashboard.view", "settings.manage"])
    hr = hire(client, db, m, "hr_lead", "hr@example.com")
    sent = {"full_name": "New Hire", "job_title": "Cook", "email": "new@example.com", "password": CHEF_PASSWORD,
            "location_ids": [loc_id(db, "MK")]}
    assert client.post("/api/employees", headers=hr, json={**sent, "role": "manager"}).status_code == 403
    assert client.post("/api/employees", headers=hr, json={**sent, "role": "boss_light"}).status_code == 403
    assert client.post("/api/employees", headers=hr, json={**sent, "role": "nonexistent"}).status_code == 400
    assert client.post("/api/employees", headers=hr, json={**sent, "role": "steward"}).status_code == 403   # steward holds permissions the HR lead does not
    names = {o["name"] for o in client.get("/api/roles/options", headers=hr).json()}
    assert "manager" not in names and "boss_light" not in names and "hr_lead" in names
    assert {"manager", "supervisor", "steward", "hr_lead", "boss_light"} <= {o["name"] for o in client.get("/api/roles/options", headers=m).json()}
