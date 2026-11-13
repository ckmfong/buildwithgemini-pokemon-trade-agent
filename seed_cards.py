from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-04-e4af8e742d59"

SEEDED_CARDS = [
    {
        "id": "charizard-base-set",
        "name": "Charizard (1st Edition Base Set)",
        "set": "Base Set",
        "type": "Fire",
        "rarity": "Holo Rare",
        "condition": "Near Mint",
        "estimated_value_usd": 350.0,
        "available_for_trade": True,
        "owner": "system",
        "notes": "Classic shadowless holo base set card."
    },
    {
        "id": "blastoise-base-set",
        "name": "Blastoise",
        "set": "Base Set",
        "type": "Water",
        "rarity": "Holo Rare",
        "condition": "Lightly Played",
        "estimated_value_usd": 85.0,
        "available_for_trade": True,
        "owner": "system",
        "notes": "Original water gun titan."
    },
    {
        "id": "pikachu-illustrator",
        "name": "Pikachu Illustrator Promo",
        "set": "CoroCoro Promo",
        "type": "Lightning",
        "rarity": "Ultra Rare Promo",
        "condition": "Mint",
        "estimated_value_usd": 5000.0,
        "available_for_trade": False,
        "owner": "museum",
        "notes": "Holy grail of collector cards."
    },
    {
        "id": "gengar-vmax-alt",
        "name": "Gengar VMAX (Alternate Art)",
        "set": "Fusion Strike",
        "type": "Psychic / Dark",
        "rarity": "Secret Rare",
        "condition": "Near Mint",
        "estimated_value_usd": 220.0,
        "available_for_trade": True,
        "owner": "system",
        "notes": "Giant Gengar swallowing buildings art."
    },
    {
        "id": "rayquaza-vmax-alt",
        "name": "Rayquaza VMAX (Alternate Art)",
        "set": "Evolving Skies",
        "type": "Dragon",
        "rarity": "Secret Rare",
        "condition": "Near Mint",
        "estimated_value_usd": 290.0,
        "available_for_trade": True,
        "owner": "system",
        "notes": "Sky high dragon with incredible foil detailing."
    }
]

def seed():
    db = firestore.Client(project=PROJECT_ID)
    collection = db.collection("pokemon_cards")
    print(f"Seeding cards into collection 'pokemon_cards' in project '{PROJECT_ID}'...")
    for card in SEEDED_CARDS:
        doc_ref = collection.document(card["id"])
        doc_ref.set(card)
        print(f"Seeded: {card['name']} (${card['estimated_value_usd']})")
    print("Seeding completed successfully!")

if __name__ == "__main__":
    seed()
