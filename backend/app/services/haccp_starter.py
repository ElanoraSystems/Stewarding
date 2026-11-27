"""The starting content of a HACCP plan: a flow for each kind of food in which every step carries its own hazards, so the flow diagram and the hazard analysis are one list and cannot disagree.

It follows the structure of the Codex Alimentarius General Principles of Food Hygiene (CXC 1-1969) and its HACCP annex: a flow diagram covering every step, a hazard analysis of each step,
then control points, limits, monitoring, corrective action and verification. It is written in general terms and is a starting point: the HACCP team must check it against the current
Codex texts and local law, and against the kitchen's own menu and processes."""
from copy import deepcopy

B, C, P, A = "Biological", "Chemical", "Physical", "Allergen"


SIGNIFICANT = "Could cause illness or injury, and is reasonably likely without this control."
NOT_SIGNIFICANT = "Low severity, or unlikely while the prerequisite programmes (cleaning, hygiene, pest control, training) are followed."


def hz(hazard: str, kind: str, control: str, significant: bool = True, basis: str = "") -> dict:
    return {"hazard": hazard, "kind": kind, "significant": significant, "control": control, "basis": basis or (SIGNIFICANT if significant else NOT_SIGNIFICANT)}


def step(name: str, hazards: list[dict] | None = None, control: str = "", no: str = "", none: str = "") -> dict:
    """A process step; with `no` it is a decision: the question is the name, 'yes' goes on to the next step and `no` says what happens instead."""
    return {"name": name, "kind": "decision" if no else "step", "control": control, "no_action": no, "hazards": hazards or [], "no_hazard": none}


# Steps shared by several kinds of food.
def supplier():
    return step("Supplier approval and ordering", [hz("Food bought from an unapproved source arrives contaminated, mislabelled or unsafe", B,
                "Buy only from approved suppliers; keep their certificates and check them when they expire.")])


def receiving():
    return step("Receiving: temperature, packaging, labels and dates checked", [
        hz("Pathogens grow in food that arrives too warm", B, "Measure delivery temperature and judge it against the limit for that food; keep chilled and frozen goods moving to storage."),
        hz("Damaged packaging, foreign bodies or pests arrive with the goods", P, "Inspect packaging and the load; reject damaged or infested goods.", False),
        hz("Allergen labelling is missing or wrong", A, "Check labels name the allergens and that the product is the one ordered.")])


def accepted():
    return step("Within limits and in good condition?", [hz("Unsafe or out-of-date food is accepted into the kitchen", B, "Reject and return anything out of limit, damaged or past its date, and record the rejection.")],
                no="Reject and return the goods; record the rejection")


def labelled():
    return step("Label with received date and lot", [hz("Food is used past its date, or cannot be traced in a recall", B, "Label every item with its received date and lot so oldest stock is used first and a lot can be traced.", False)])


def chilled_store():
    return step("Chilled storage", [hz("Bacteria grow if the chiller is too warm; raw food contaminates ready-to-eat food", B,
                "Chillers checked at set times against their limits; raw food stored below ready-to-eat food and covered.")])


def frozen_store():
    return step("Frozen storage", [hz("Food thaws and refreezes if the freezer is too warm", B, "Freezers checked at set times against their limits; stock rotated.", False)])


def dry_store():
    return step("Dry storage", [hz("Moisture, pests or chemicals spoil or contaminate dry goods", C, "Stored off the floor in closed containers away from chemicals; pest checks recorded.", False),
                                hz("Mould and toxins develop in damp dry goods", B, "Keep dry goods dry and use them within their dates.", False)])


def issue():
    return step("Issue from store, oldest stock first", [hz("Old stock is used after its date", B, "First in, first out; dates checked at issue.", False)])


def defrost():
    return step("Defrosting", [hz("Bacteria grow while food thaws", B, "Defrost under refrigeration with the time in and time out recorded; never at room temperature.")])


def wash_produce():
    return step("Washing and sanitising fruit and vegetables", [hz("Pathogens, soil and chemical residues on raw produce", B, "Wash in clean water, sanitise ready-to-eat produce at the set strength and rinse.", False),
                                                               hz("Chemical residue from the sanitiser", C, "Sanitiser strength measured and the produce rinsed.", False)])


def prep_raw():
    return step("Preparing raw meat, poultry and fish in a separate area", [
        hz("Raw food contaminates ready-to-eat food and surfaces", B, "Separate boards, knives and area; colour coding; hands washed and surfaces sanitised between tasks."),
        hz("Allergens transfer between foods", A, "Allergen foods prepared with separate utensils and the area cleaned afterwards.")])


def prep_rte():
    return step("Preparing ready-to-eat food on clean, separate boards", [
        hz("Cross-contamination from raw food, hands or surfaces", B, "Clean, separate boards and knives; handwashing; surfaces sanitised."),
        hz("Allergens transfer between foods", A, "Allergen foods prepared with separate utensils and the area cleaned afterwards."),
        hz("Glass, metal, packaging or other foreign bodies", P, "Equipment and packaging checked; broken items reported and the food discarded.", False)])


def portioning():
    return step("Portioning, marinating and assembly", [hz("Bacteria grow while food is out of the chiller", B, "Keep food chilled and work in small batches within the time allowed."),
                                                       hz("Allergen ingredients in marinades and sauces", A, "Recipe allergens recorded; marinades labelled.")])


def cooking():
    return step("Cooking", [hz("Pathogens survive if the core does not reach the limit", B, "Cook to the core temperature limit for the type of food and time required.")])


def core_check():
    return step("Core temperature at or above the limit?", [hz("Undercooked food is served", B, "Core temperature measured with a calibrated probe and judged against the limit for the type of food.")],
                no="Keep cooking, then check again before service")


def hot_hold(tag="CCP"):
    return step("Hot holding", [hz("Bacteria grow if hot food falls below the holding temperature", B, "Holding temperature checked at regular intervals against the limit.")], control=tag)


def hot_hold_check():
    return step("Held at or above the limit?", [hz("Food held too cool is served", B, "Each check recorded; corrective action taken when out of limit.")],
                no="Reheat once to the limit if within time, or discard")


def cooling(name="Cooling"):
    return step(name, [hz("Spores and bacteria grow while cooked food cools", B, "Cooling log with a temperature and a time limit at each stage.")], control="CCP")


def cooling_check():
    return step("Cooled within the time and temperature limits?", [hz("Food cooled too slowly is kept", B, "Every stage recorded; failures acted on.")], no="Discard, or follow the recorded corrective action")


def store_cooked():
    return step("Storing cooked food chilled, labelled and dated", [hz("Bacteria grow or food is kept too long", B, "Covered, labelled with the date and used within the shelf life set.")])


def reheating():
    return step("Reheating", [hz("Pathogens survive if food is not reheated through", B, "Reheat once, to the core temperature limit, and hold hot or serve.")])


def reheat_check():
    return step("Core temperature after reheating at or above the limit?", [hz("Food not reheated through is served", B, "Core temperature measured and recorded.")], no="Continue reheating and check again, or discard")


def cold_hold():
    return step("Cold holding", [hz("Bacteria grow if cold food warms up", B, "Chilled display and chillers checked against the limit; food kept covered.")])


def cold_check():
    return step("Held at or below the limit?", [hz("Food held too warm is served", B, "Temperature checked and recorded; corrective action when out of limit.")], no="Discard, or return to the chiller once if within time")


def service():
    return step("Plating and service", [hz("Contamination at plating and service", B, "Clean hands and utensils; serve within the time allowed.", False),
                                        hz("Wrong allergen information given to the guest", A, "Allergen information is available and staff are trained to give it.")])


def transport():
    return step("Transport to other outlets or events", [hz("Food warms or cools to an unsafe temperature in transit", B, "Insulated, clean, covered containers; temperature and time recorded on arrival.")])


def discard():
    return step("Discarding food at the end of its shelf life", [hz("Food kept past its date is served", B, "Dates checked daily and expired food discarded and recorded.", False)])


def weighing():
    return step("Weighing and scaling ingredients", [hz("Allergen ingredients (gluten, milk, eggs, nuts, soy, sesame) cross-contaminate other recipes", A, "Allergen ingredients scaled with separate scoops and containers; recipes list their allergens."),
                                                    hz("Foreign bodies in flour and dry ingredients", P, "Sieve dry ingredients where needed; check scoops and containers are intact.", False)])


PROCESSES = {
    "Hot food": ("CXC 1-1969; CXC 39-1993 (precooked and cooked foods in mass catering)", [
        supplier(), receiving(), accepted(), labelled(), chilled_store(), frozen_store(), dry_store(), issue(), defrost(), wash_produce(), prep_raw(), portioning(), cooking(), core_check(),
        hot_hold(), hot_hold_check(), service(), transport(), cooling("Cooling of leftovers"), cooling_check(), store_cooked(), reheating(), reheat_check()]),
    "Cold food and salads": ("CXC 1-1969; CXC 39-1993", [
        supplier(), receiving(), accepted(), labelled(), chilled_store(), wash_produce(), prep_rte(), step("Dressing, mixing and assembly", [
            hz("Bacteria and allergens are added by hands, utensils and dressings", B, "Clean hands and utensils; dressings and fillings kept chilled and labelled with allergens.")]),
        step("Portioning and labelling with the use-by date", [hz("Food is kept past its safe life", B, "Each portion labelled with its date; shelf life set for each product.", False)]),
        cold_hold(), cold_check(), step("Cold display and service", [hz("Food warms on display", B, "Display checked against the limit; food on display only for the time allowed.")]), discard()]),
    "Stocks, soups and sauces": ("CXC 1-1969; CXC 39-1993", [
        supplier(), receiving(), accepted(), labelled(), chilled_store(), dry_store(), step("Preparing bones, meat and vegetables", [
            hz("Raw food contaminates surfaces and ready-to-eat food", B, "Separate boards and area; hands and surfaces cleaned after raw food."),
            hz("Bone fragments and foreign bodies", P, "Strain and check the finished product.", False)]),
        step("Cooking and simmering", [hz("Pathogens survive if the core does not reach the limit", B, "Bring to the temperature limit and hold for the time required.")]),
        step("Skimming and straining", [hz("Fragments and fat carried into the finished product", P, "Strained through clean, intact strainers.", False)]),
        cooling(), cooling_check(), store_cooked(), step("Reheating to a rolling boil", [hz("Pathogens survive if reheating is incomplete", B, "Reheat once to a rolling boil and check the core temperature.")]),
        reheat_check(), hot_hold(), hot_hold_check(), service()]),
    "Sushi and raw fish": ("CXC 1-1969; CXC 52-2003 (fish and fishery products)", [
        step("Approved fish supplier; parasite-control certificate or freezing record checked", [hz("Parasites in fish eaten raw", B, "Use fish frozen for parasite control or with the supplier's certificate; keep the records."),
                                                                                              hz("Histamine and biotoxins in some fish", C, "Buy from approved suppliers who control temperature from catch.")]),
        step("Receiving fish: temperature, smell and appearance", [hz("Bacteria and histamine form in fish that arrives too warm", B, "Measure temperature, check smell and appearance; reject if out of limit.")]),
        step("Within limits and in good condition?", [hz("Unsafe fish is accepted", B, "Reject and return; record the rejection.")], no="Reject and return the fish; record the rejection"),
        step("Chilled storage, raw fish kept apart", [hz("Cross-contamination and growth in storage", B, "Raw fish stored apart, covered and below the limit; checked at set times.")]),
        step("Cooking sushi rice", [hz("Spore-forming bacteria survive in rice", B, "Cook the rice fully and use it within the time allowed.")]),
        step("Adding vinegar to the rice and holding it", [hz("Bacteria grow in rice that is not acidified or is held too long", B, "Acidify the rice with vinegar, hold it for no longer than the time set and keep it covered.")], control="OPRP"),
        step("Rice acidified and within the time limit?", [hz("Unsafe rice is used", B, "Check and record acidification and time held.")], no="Discard the rice"),
        step("Preparing raw fish on its own board and knife", [hz("Raw fish contaminates other foods and surfaces", B, "Dedicated board and knife; hands washed and surfaces sanitised."),
                                                              hz("Allergens (fish, soy, sesame, gluten) transfer between foods", A, "Allergen foods handled with separate utensils.")]),
        step("Rolling and assembly", [hz("Contamination from hands and utensils", B, "Clean hands, gloves where used, sanitised utensils; assemble quickly and keep chilled.")]),
        cold_hold(), cold_check(), step("Display and service within the time allowed", [hz("Bacteria grow while sushi is on display", B, "Display chilled; remove after the time set.")]),
        step("Discarding what is left at the end of service", [hz("Old sushi is kept and served", B, "Discard everything left at the end of service and record it.", False)])]),
    "Bakery (breads and doughs)": ("CXC 1-1969; CXC 75-2015 (low-moisture foods such as flour)", [
        supplier(), receiving(), accepted(), labelled(), dry_store(), chilled_store(), weighing(),
        step("Mixing and kneading", [hz("Contamination from equipment and raw egg or dairy", B, "Clean, sanitised mixers and bowls; hands washed; raw egg handled apart."),
                                    hz("Metal fragments from worn equipment", P, "Equipment checked before use.", False)]),
        step("Proofing and resting", [hz("Bacteria grow in warm, moist conditions", B, "Proof for the time set; do not leave filled or dairy doughs warm.", False)]),
        step("Shaping and filling", [hz("Cross-contamination from fillings, hands and surfaces", B, "Fillings kept chilled until used; clean hands and utensils."),
                                    hz("Allergens in fillings and toppings (nuts, sesame, milk, egg)", A, "Allergen fillings and toppings kept separate and labelled.")]),
        step("Baking", [hz("Pathogens survive if baking is too short or too cool", B, "Bake to the set time and temperature; check the oven works.")]),
        step("Core temperature of filled and egg products at or above the limit?", [hz("Undercooked filled or egg products are served", B, "Core temperature checked and recorded for filled and egg products.")], no="Bake longer, then check again"),
        step("Cooling on racks", [hz("Bacteria grow or condensation forms if cooled slowly or covered while warm", B, "Cool on clean racks, away from raw ingredients and pests; do not wrap until cool.", False)]),
        step("Glazing, filling with cream and topping", [hz("Bacteria grow in cream, custard and fresh fillings", B, "Cream and custard fillings kept chilled and added to cooled products; products with them held chilled."),
                                                        hz("Allergens in glazes and toppings", A, "Allergens in toppings recorded and labelled.")]),
        step("Slicing, packing and labelling", [hz("Undeclared allergens (gluten, milk, eggs, nuts, soy, sesame)", A, "Every item labelled with its allergens and use-by date; labels checked against the recipe."),
                                               hz("Packaging contaminates the product", P, "Clean, food-grade packaging stored covered.", False)]),
        step("Storage and display", [hz("Products with fresh cream or custard held warm", B, "Hold cream and custard products chilled and check the temperature."),
                                    hz("Mould on bread kept too long", B, "Shelf life set and dates checked.", False)]),
        discard()]),
    "Pastry and desserts": ("CXC 1-1969; CXC 39-1993; CXC 75-2015 for flour and other low-moisture ingredients", [
        supplier(), receiving(), accepted(), labelled(), chilled_store(), dry_store(), weighing(),
        step("Making custards, creams and fillings (heating)", [hz("Pathogens from eggs and dairy survive if not heated enough", B, "Heat to the temperature limit and hold for the time required; use pasteurised egg where the recipe is not heated.")]),
        step("Core temperature of custards and creams at or above the limit?", [hz("Undercooked egg and dairy fillings are used", B, "Core temperature checked with a calibrated probe and recorded.")], no="Keep heating, then check again"),
        cooling("Cooling of custards, creams and fillings"), cooling_check(),
        step("Making and baking pastry and sponges", [hz("Contamination from raw egg, dairy and hands", B, "Clean equipment and hands; raw egg handled apart."),
                                                     hz("Allergens in mixes and decorations", A, "Allergen ingredients scaled and labelled separately.")]),
        step("Whipping cream and assembly", [hz("Bacteria grow in cream and assembled desserts out of the chiller", B, "Whip and assemble in small batches from chilled ingredients and return to the chiller quickly."),
                                            hz("Contamination from hands, whisks and bowls", B, "Sanitised equipment and clean hands.", False)]),
        step("Chilling and setting", [hz("Bacteria grow if desserts set slowly or at room temperature", B, "Set in the chiller within the time allowed.")]),
        step("Decorating and finishing", [hz("Contamination from hands and decorations; allergens in decorations (nuts, sesame, milk)", A, "Clean hands and utensils; allergen decorations labelled.")]),
        cold_hold(), cold_check(), step("Labelling and display", [hz("Undeclared allergens and wrong dates", A, "Each dessert labelled with allergens and use-by date; display chilled.")]), discard()]),
    "Cleaning, hygiene and waste (all areas)": ("CXC 1-1969", [
        step("Fit to work, with no illness?", [hz("Ill staff contaminate food", B, "Staff report illness; anyone with vomiting, diarrhoea or infected wounds is excluded from handling food.")], no="Exclude from food handling and report to the supervisor"),
        step("Handwashing and clean uniform", [hz("Hands spread pathogens", B, "Hands washed at the set times and after raw food, the toilet, waste and breaks.")]),
        step("Cleaning and sanitising surfaces and equipment", [hz("Surviving bacteria on surfaces; chemical residue", B, "Clean then sanitise at the set strength; checklists completed and approved."),
                                                              hz("Cleaning chemicals contaminate food", C, "Chemicals stored apart, labelled, and used as directed.")]),
        step("Surface clean and sanitiser at the right strength?", [hz("Dirty surfaces are used for food", B, "Strength measured and recorded.", False)], no="Clean and sanitise again"),
        step("Dishwashing and glass washing", [hz("Wash and rinse temperatures too low leave pathogens", B, "Wash and final rinse temperatures checked and recorded.")]),
        step("Leftovers and food waste", [hz("Waste attracts pests and contaminates food", B, "Waste in covered bins, removed regularly and kept apart from food.", False)]),
        step("Pest control and waste removal", [hz("Pests contaminate food and surfaces", B, "Contracted pest control, proofing and checks recorded.", False)])]),
}


def starter_processes() -> list[dict]:
    return [{"name": name, "references": refs, "confirmed_on": "", "confirmed_by": "", "steps": deepcopy(steps)} for name, (refs, steps) in PROCESSES.items()]
