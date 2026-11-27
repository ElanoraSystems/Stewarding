from .helpers import MGR, loc_id


def cooking(client, h, db):
    return client.post("/api/equipment/from-template", json={"template": "cooking", "location_id": loc_id(db, "BQ")}, headers=h).json()


def record(client, h, point, value, food_type=None):
    check = point["schedules"][0]
    return client.post("/api/monitoring/readings", headers=h, json={"equipment_id": point["id"], "schedule_id": check["id"], "value": value, "reference": "Salmon", "food_type": food_type})


def test_the_cooking_point_comes_with_a_list_of_food_types(client, login, db, clock):
    clock.set(2026, 3, 2, 8, 0)  # lunchtime, when the lunch core temperature is due
    point = cooking(client, login(MGR), db)
    limits = {f["name"]: f["min_value"] for f in point["schedules"][0]["food_limits"]}
    assert limits["Poultry"] == 75 and limits["Fish and seafood"] == 63 and limits["Whole cuts of meat"] == 63 and limits["Other dishes"] == 75


def test_fish_at_65_passes_and_chicken_at_65_fails_and_the_type_is_kept(client, login, db, clock):
    clock.set(2026, 3, 2, 8, 0)  # lunchtime, when the lunch core temperature is due
    point = cooking(client, login(MGR), db)
    s = login(MGR)
    fish = record(client, s, point, 65, "Fish and seafood")
    assert fish.status_code == 201, fish.text
    assert fish.json()["passed"] and fish.json()["food_type"] == "Fish and seafood" and fish.json()["min_limit"] == 63


def test_chicken_at_65_fails_against_75(client, login, db, clock):
    clock.set(2026, 3, 2, 8, 0)  # lunchtime, when the lunch core temperature is due
    point = cooking(client, login(MGR), db)
    chicken = record(client, login(MGR), point, 65, "Poultry")
    assert chicken.status_code == 201 and not chicken.json()["passed"] and chicken.json()["min_limit"] == 75


def test_a_type_must_be_chosen_and_must_be_listed(client, login, db, clock):
    clock.set(2026, 3, 2, 8, 0)  # lunchtime, when the lunch core temperature is due
    point = cooking(client, login(MGR), db)
    s = login(MGR)
    assert record(client, s, point, 80).status_code == 400
    assert record(client, s, point, 80, "Dessert").status_code == 400


def test_a_check_without_a_list_keeps_its_single_limit(client, login, db, clock):
    clock.set(2026, 3, 2, 8, 0)  # lunchtime, when the lunch core temperature is due
    m = login(MGR)
    point = cooking(client, m, db)
    check = point["schedules"][0]
    body = {**{k: check[k] for k in ("stage", "parameter", "unit", "value_type", "source", "timing", "min_value", "max_value", "require_reference", "reference_label")}, "time_of_day": check["time_of_day"], "food_limits": None}
    assert client.put(f"/api/equipment/schedules/{check['id']}", json=body, headers=m).json()["food_limits"] is None
    plain = record(client, login(MGR), point, 65)
    assert plain.status_code == 201 and not plain.json()["passed"] and plain.json()["food_type"] is None


def test_a_list_is_checked_when_saved(client, login, db, clock):
    clock.set(2026, 3, 2, 8, 0)  # lunchtime, when the lunch core temperature is due
    m = login(MGR)
    point = cooking(client, m, db)
    check = point["schedules"][0]
    base = {k: check[k] for k in ("stage", "parameter", "unit", "value_type", "source", "timing", "min_value", "max_value", "require_reference", "reference_label")}
    base["time_of_day"] = check["time_of_day"]
    twice = [{"name": "Fish", "min_value": 63}, {"name": "fish", "min_value": 63}]
    backwards = [{"name": "Fish", "min_value": 90, "max_value": 60}, {"name": "Meat", "min_value": 75}]
    assert client.put(f"/api/equipment/schedules/{check['id']}", json={**base, "food_limits": twice}, headers=m).status_code == 422
    assert client.put(f"/api/equipment/schedules/{check['id']}", json={**base, "food_limits": backwards}, headers=m).status_code == 422
