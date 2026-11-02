"""Catàleg central d'ambientacions.

La interfície interna usa valencià i les metadades públiques poden usar un nom
internacional en anglés.
"""

THEMES: dict[str, str] = {
    "Biblioteca medieval": "Medieval Library",
    "Biblioteca màgica": "Enchanted Wizard Library",
    "Biblioteca èlfica": "Ancient Elven Library",
    "Taverna medieval": "Medieval Tavern",
    "Torre de l'alquimista": "Alchemist Tower",
    "Castell gòtic": "Gothic Castle",
    "Cabana amb pluja": "Rainy Cabin",
    "Biblioteca victoriana": "Victorian Library",
    "Vaixell pirata": "Pirate Ship",
    "Roma antiga": "Ancient Rome",
    "Grècia antiga": "Ancient Greece",
    "Japó feudal": "Feudal Japan",
    "Búnquer postapocalíptic": "Post-Apocalyptic Bunker",
    "Bosc": "Enchanted Forest",
    "Observatori": "Night Observatory",
    "Cafeteria acollidora": "Cozy Coffee Shop",
    "Cafeteria moderna": "Modern Coffee Shop",
    "Cafeteria a Nova York": "New York Coffee Shop",
    "Cafeteria a Tòquio": "Tokyo Café",
    "Cafeteria a París": "Paris Café",
    "Parc a la ciutat": "City Park",
    "Apartament a la ciutat": "Cozy City Apartment",
    "Racó de lectura": "Cozy Reading Nook",
    "Cafeteria d'hivern": "Winter Coffee Shop",
    "Bosc nevat": "Snowy Forest",
    "Cabana de Halloween": "Halloween Cottage",
    "Biblioteca de Halloween": "Halloween Library",
    "Matí de Pasqua": "Easter Morning Cottage",
    "Cabana de tardor": "Autumn Cabin",
    "Cafeteria de tardor": "Autumn Coffee Shop",
    "Bosc de tardor": "Autumn Forest",
    "Jardí de primavera": "Spring Garden",
    "Racó de primavera": "Spring Reading Nook",
    "Porxo d'estiu": "Summer Porch",
    "Nit d'estiu": "Summer Night Lake",
    "Casa de la platja": "Cozy Beach House",
    "Cabana de Nadal": "Christmas Cabin",
    "Sala de Nadal": "Cozy Christmas Living Room",
    "Cafeteria de Nadal": "Christmas Coffee Shop",
    "Biblioteca de Nadal": "Christmas Library",
    "Poble nevat": "Snowy Christmas Village",
    "Mercat de Nadal": "Christmas Market",
    "Avió": "Airplane Window Seat",
    "Tren": "Night Train",
    "Platja": "Peaceful Beach",
    "Riu": "Gentle River",
    "Hivernacle": "Victorian Greenhouse",
    "Port": "Old Harbour",
    "Cabana a la neu": "Snowy Cabin",
    "Masmorra": "Ancient Dungeon",
    "Campament d'aventurers": "Adventurers' Camp",
    "Cova del drac": "Dragon's Cave",
    "Personalitzada": "Custom Focus Ambience",
}


def publication_theme(theme: str) -> str:
    """Retorna el nom internacional de l'ambientació."""
    return THEMES.get(theme, theme)
