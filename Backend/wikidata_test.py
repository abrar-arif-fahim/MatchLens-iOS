
import json
from urllib.request import Request, urlopen

# Lionel Messi's Wikidata ID
player_id = "Q615"


# Function to download data from Wikidata
def get_wikidata(entity_id):
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"

    request = Request(
        url,
        headers={
            "User-Agent": "MatchLensUniversityProject/1.0 (educational project)"
        }
    )

    with urlopen(request, timeout=20) as response:
        data = json.load(response)

    return data["entities"][entity_id]


# Function to extract an entity ID from a property
def get_property_id(player, property_id):
    claims = player["claims"].get(property_id, [])

    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})

        if isinstance(value, dict) and "id" in value:
            return value["id"]

    return None


# Function to convert an entity ID to a readable name
def get_entity_name(entity_id):
    if entity_id is None:
        return "Not available"

    entity = get_wikidata(entity_id)

    return entity.get("labels", {}).get("en", {}).get(
        "value", entity_id
    )


# Retrieve player data
player = get_wikidata(player_id)

# Player name
name = player["labels"]["en"]["value"]

# Date of birth
birth_claims = player["claims"].get("P569", [])

if birth_claims:
    raw_date = birth_claims[0]["mainsnak"]["datavalue"]["value"]["time"]
    date_of_birth = raw_date[1:11]
else:
    date_of_birth = "Not available"

# Nationality / country of citizenship
nationality_id = get_property_id(player, "P27")
nationality = get_entity_name(nationality_id)

# Playing position
position_id = get_property_id(player, "P413")
position = get_entity_name(position_id)

# Display the extracted information
print("\n MATCHLENS PLAYER DATA ")
print("Player ID:", player_id)
print("Player Name:", name)
print("Date of Birth:", date_of_birth)
print("Nationality:", nationality)
print("Playing Position:", position)

