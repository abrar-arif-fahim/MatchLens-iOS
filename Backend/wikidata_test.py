
"""Read Messi's Wikidata information when run directly, without import side effects."""

from prepare_multiple_players import (
    ValidationError, birth_date, claim_values, english_label, get_entity, readable_claims,
)


player_id = "Q615"


def get_wikidata(entity_id):
    # The shared helper validates responses and uses a timeout and User-Agent.
    return get_entity(entity_id, {})


def get_property_id(player, property_id):
    ids = {value.get("id") for value in claim_values(player, property_id)
           if isinstance(value, dict) and isinstance(value.get("id"), str)}
    # Never silently choose one of several values.
    return next(iter(ids)) if len(ids) == 1 else None


def get_entity_name(entity_id):
    return english_label(get_wikidata(entity_id)) if entity_id else "Not available"


def main():
    try:
        cache = {}
        player = get_entity(player_id, cache)
        fields = (
            ("Player ID", player_id),
            ("Player Name", english_label(player)),
            ("Date of Birth", birth_date(player)),
            ("Nationality", readable_claims(player, "P27", cache)),
            ("Playing Position", readable_claims(player, "P413", cache)),
        )
        print("\nMATCHLENS PLAYER DATA")
        for label, value in fields:
            print(f"{label}: {value}")
        return 0
    except ValidationError as error:
        print(f"Wikidata validation failed: {error}")
    except (ValueError, KeyError, TypeError, AttributeError, OSError):
        print("Could not retrieve complete, valid Wikidata information.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

