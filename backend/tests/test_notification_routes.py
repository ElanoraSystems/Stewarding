from sqlalchemy import select

from app.models import Notification, User
from app.services.alerts import run_alerts

from .helpers import MGR, SUP, loc_id

URL = "/api/settings/notification-routes"


def who(db, kind):
    db.expire_all()
    return {db.get(User, n.user_id).email for n in db.scalars(select(Notification).where(Notification.kind == kind))}


def test_the_default_goes_by_role_type_and_the_settings_page_lists_the_kinds_and_roles(client, login):
    m = login(MGR)
    body = client.get(URL, headers=m).json()
    assert {c["key"] for c in body["categories"]} >= {"attendance", "checklists", "monitoring"} and body["routes"]["attendance"] is None
    assert {r["name"] for r in body["roles"]} >= {"manager", "supervisor", "steward"}
    assert client.get(URL, headers=login("steward.mk@example.test")).status_code == 403


def test_attendance_alerts_go_only_to_the_roles_chosen(client, login, db, clock):
    m = login(MGR)
    clock.set(2026, 3, 2, 2, 30)  # 06:30 Dubai: the morning steward is late checking in
    run_alerts(db, clock.now)
    db.commit()
    assert who(db, "no_checkin") >= {"manager@example.test", "sup.mk@example.test"}  # by default managers and supervisors at the location
    for n in db.scalars(select(Notification)):
        db.delete(n)
    db.commit()
    assert client.put(URL, json={"routes": {"attendance": ["manager"]}}, headers=m).status_code == 200
    clock.advance(minutes=1)
    run_alerts(db, clock.now)
    db.commit()
    got = who(db, "no_checkin")
    assert "manager@example.test" in got and "sup.mk@example.test" not in got  # the supervisor role was not chosen
    assert client.put(URL, json={"routes": {"attendance": None}}, headers=m).json()["routes"]["attendance"] is None  # back to the default


def test_the_routes_are_validated(client, login):
    m = login(MGR)
    assert client.put(URL, json={"routes": {"gossip": ["manager"]}}, headers=m).status_code == 400
    assert client.put(URL, json={"routes": {"attendance": ["no_such_role"]}}, headers=m).status_code == 400
    assert client.put(URL, json={"routes": {"attendance": []}}, headers=m).status_code == 200  # nobody chosen: nobody is told
