from sqlalchemy import delete, select

from app.models import EmployeeLocation, Location, User


def test_the_users_own_locations_come_first_in_the_list_of_places(client, login, db):
    h = login("manager@example.test")
    names = [l["name"] for l in client.get("/api/auth/me", headers=h).json()["locations"]]
    assert names == sorted(names)
    last = db.scalar(select(Location).order_by(Location.name.desc()))
    emp = db.scalar(select(User).where(User.email == "manager@example.test")).employee
    db.execute(delete(EmployeeLocation).where(EmployeeLocation.employee_id == emp.id))
    db.add(EmployeeLocation(employee_id=emp.id, location_id=last.id))
    db.commit()
    assert client.get("/api/auth/me", headers=h).json()["locations"][0]["id"] == last.id
