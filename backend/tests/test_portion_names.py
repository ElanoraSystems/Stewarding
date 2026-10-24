from .helpers import MGR, SUP
from .test_traceability import LOTS, butcher, food, part, receive, rule


def names(client, h, **params):
    return client.get(f"{LOTS}/portion-names", headers=h, params=params).json()


def test_a_custom_portion_name_is_saved_to_the_list_once(client, login, db, clock):
    m, sup = login(MGR), login(SUP)
    item = food(client, m)
    rule(client, m)
    cook = butcher(client, db, m)
    lot = receive(client, sup, db, item).json()
    for description in ("Breast portions", "breast PORTIONS"):
        assert client.post(f"{LOTS}/{lot['id']}/split", headers=cook, json={"parts": [part(description=description, count=2)]}).status_code == 201
    saved = names(client, m)
    assert [(n["name"], n["food_item_id"]) for n in saved] == [("Breast portions", item)]


def test_managers_keep_the_list_and_others_only_read_it(client, login, db):
    m, sup = login(MGR), login(SUP)
    item = food(client, m)
    made = client.post(f"{LOTS}/portion-names", headers=m, json={"name": "Thigh strips", "food_item_id": item})
    assert made.status_code == 201 and made.json()["food_item"] == "Chicken breast"
    assert client.post(f"{LOTS}/portion-names", headers=m, json={"name": "thigh STRIPS"}).status_code == 409
    assert client.post(f"{LOTS}/portion-names", headers=sup, json={"name": "Wings"}).status_code == 403
    assert [n["name"] for n in names(client, sup)] == ["Thigh strips"]
    pid = made.json()["id"]
    assert client.put(f"{LOTS}/portion-names/{pid}", headers=m, json={"active": False}).status_code == 200
    assert names(client, m) == [] and len(names(client, m, include_inactive=True)) == 1
    assert client.post(f"{LOTS}/portion-names", headers=m, json={"name": "Wings", "food_item_id": 9999}).status_code == 400
    assert client.delete(f"{LOTS}/portion-names/{pid}", headers=sup).status_code == 403
    assert client.delete(f"{LOTS}/portion-names/{pid}", headers=m).status_code == 200
    assert names(client, m, include_inactive=True) == []


def test_lot_search_finds_a_lot_by_its_portion_name_and_shows_the_supplier_batch(client, login, db, clock):
    m, sup = login(MGR), login(SUP)
    item = food(client, m)
    rule(client, m)
    cook = butcher(client, db, m)
    lot = receive(client, sup, db, item).json()
    client.post(f"{LOTS}/{lot['id']}/split", headers=cook, json={"parts": [part(description="Satay skewers", count=3)]})
    found = client.get(f"{LOTS}/search", headers=cook, params={"q": "satay"}).json()
    assert len(found) == 1 and found[0]["pack"] == "Satay skewers" and found[0]["supplier_lot"] == "B2610-884"
