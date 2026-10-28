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
    "Nau espacial": "Deep Space Station",
    "Búnquer postapocalíptic": "Post-Apocalyptic Bunker",
    "Bosc": "Enchanted Forest",
    "Observatori": "Night Observatory",
    "Cafeteria acollidora": "Cozy Coffee Shop",
}


def publication_theme(theme: str) -> str:
    """Retorna el nom internacional de l'ambientació."""
    return THEMES.get(theme, theme)
