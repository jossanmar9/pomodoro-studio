"""Títols i descripcions traduïts per a YouTube (castellà, portugués, alemany, francés, català, italià, japonés i coreà).

YouTube mostra el títol i la descripció en l'idioma de qui mira (o de qui cerca), i
els fa servir per a trobar el vídeo en eixes cerques. El text original continua en
anglés; la descripció traduïda porta una introducció en l'idioma i, després, la
descripció anglesa sencera (capítols i crèdits inclosos).
Ara la descripció també es tradueix sencera (vegeu `full_description`); si no
cap en el límit de YouTube, es torna a la forma antiga.
"""
from __future__ import annotations

import hashlib
import re

from app.services import translations_more as more

LANGUAGES = ("es", "pt", "de", "fr", *more.NEW_LANGUAGES)
MAX_DESCRIPTION_BYTES = 4900

# Nom públic en anglés → traducció.
THEME_NAMES: dict[str, dict[str, str]] = {
    "Medieval Library": {"es": "Biblioteca medieval", "pt": "Biblioteca medieval", "de": "Mittelalterliche Bibliothek", "fr": "Bibliothèque médiévale"},
    "Enchanted Wizard Library": {"es": "Biblioteca de magos encantada", "pt": "Biblioteca encantada de magos", "de": "Verzauberte Zauberbibliothek", "fr": "Bibliothèque enchantée de sorcier"},
    "Ancient Elven Library": {"es": "Antigua biblioteca élfica", "pt": "Antiga biblioteca élfica", "de": "Alte Elfenbibliothek", "fr": "Ancienne bibliothèque elfique"},
    "Medieval Tavern": {"es": "Taberna medieval", "pt": "Taverna medieval", "de": "Mittelalterliche Taverne", "fr": "Taverne médiévale"},
    "Alchemist Tower": {"es": "Torre del alquimista", "pt": "Torre do alquimista", "de": "Turm des Alchemisten", "fr": "Tour de l'alchimiste"},
    "Gothic Castle": {"es": "Castillo gótico", "pt": "Castelo gótico", "de": "Gotisches Schloss", "fr": "Château gothique"},
    "Rainy Cabin": {"es": "Cabaña con lluvia", "pt": "Cabana na chuva", "de": "Hütte im Regen", "fr": "Cabane sous la pluie"},
    "Victorian Library": {"es": "Biblioteca victoriana", "pt": "Biblioteca vitoriana", "de": "Viktorianische Bibliothek", "fr": "Bibliothèque victorienne"},
    "Pirate Ship": {"es": "Barco pirata", "pt": "Navio pirata", "de": "Piratenschiff", "fr": "Bateau pirate"},
    "Ancient Rome": {"es": "Antigua Roma", "pt": "Roma antiga", "de": "Antikes Rom", "fr": "Rome antique"},
    "Ancient Greece": {"es": "Antigua Grecia", "pt": "Grécia antiga", "de": "Antikes Griechenland", "fr": "Grèce antique"},
    "Feudal Japan": {"es": "Japón feudal", "pt": "Japão feudal", "de": "Feudales Japan", "fr": "Japon féodal"},
    "Cozy Bookstore": {"es": "Librería acogedora", "pt": "Livraria aconchegante", "de": "Gemütliche Buchhandlung", "fr": "Librairie cosy"},
    "Rainy Attic": {"es": "Desván con lluvia", "pt": "Sótão na chuva", "de": "Dachboden im Regen", "fr": "Grenier sous la pluie"},
    "Lighthouse in the Storm": {"es": "Faro en la tormenta", "pt": "Farol na tempestade", "de": "Leuchtturm im Sturm", "fr": "Phare dans la tempête"},
    "Kotatsu Room": {"es": "Habitación con kotatsu", "pt": "Quarto com kotatsu", "de": "Kotatsu-Zimmer", "fr": "Chambre avec kotatsu"},
    "Night Corner Shop": {"es": "Tienda de barrio de noche", "pt": "Lojinha de bairro à noite", "de": "Nächtlicher Eckladen", "fr": "Épicerie de quartier la nuit"},
    "Rural Train Station": {"es": "Estación de tren rural", "pt": "Estação de trem rural", "de": "Ländlicher Bahnhof", "fr": "Gare de campagne"},
    "Rainy Rooftop": {"es": "Azotea con lluvia", "pt": "Terraço com chuva", "de": "Dachterrasse im Regen", "fr": "Toit sous la pluie"},
    "Cozy Home Kitchen": {"es": "Cocina acogedora", "pt": "Cozinha aconchegante", "de": "Gemütliche Küche", "fr": "Cuisine cosy"},
    "Japanese Tea House": {"es": "Casa de té japonesa", "pt": "Casa de chá japonesa", "de": "Japanisches Teehaus", "fr": "Maison de thé japonaise"},
    "Enchanted Forest": {"es": "Bosque encantado", "pt": "Floresta encantada", "de": "Verzauberter Wald", "fr": "Forêt enchantée"},
    "Night Observatory": {"es": "Observatorio nocturno", "pt": "Observatório noturno", "de": "Sternwarte bei Nacht", "fr": "Observatoire de nuit"},
    "Cozy Coffee Shop": {"es": "Cafetería acogedora", "pt": "Cafeteria aconchegante", "de": "Gemütliches Café", "fr": "Café cosy"},
    "Modern Coffee Shop": {"es": "Cafetería moderna", "pt": "Cafeteria moderna", "de": "Modernes Café", "fr": "Café moderne"},
    "New York Coffee Shop": {"es": "Cafetería en Nueva York", "pt": "Cafeteria em Nova York", "de": "Café in New York", "fr": "Café à New York"},
    "Tokyo Café": {"es": "Cafetería en Tokio", "pt": "Café em Tóquio", "de": "Café in Tokio", "fr": "Café à Tokyo"},
    "Paris Café": {"es": "Café en París", "pt": "Café em Paris", "de": "Café in Paris", "fr": "Café parisien"},
    "City Park": {"es": "Parque en la ciudad", "pt": "Parque na cidade", "de": "Stadtpark", "fr": "Parc en ville"},
    "Cozy City Apartment": {"es": "Apartamento acogedor en la ciudad", "pt": "Apartamento aconchegante na cidade", "de": "Gemütliche Stadtwohnung", "fr": "Appartement cosy en ville"},
    "Cozy Reading Nook": {"es": "Rincón de lectura", "pt": "Cantinho de leitura", "de": "Gemütliche Leseecke", "fr": "Coin lecture cosy"},
    "Summer": {"es": "Verano", "pt": "Verão", "de": "Sommer", "fr": "Été"},
    "Autumn": {"es": "Otoño", "pt": "Outono", "de": "Herbst", "fr": "Automne"},
    "Spring": {"es": "Primavera", "pt": "Primavera", "de": "Frühling", "fr": "Printemps"},
    "Winter": {"es": "Invierno", "pt": "Inverno", "de": "Winter", "fr": "Hiver"},
    "Christmas": {"es": "Navidad", "pt": "Natal", "de": "Weihnachten", "fr": "Noël"},
    "Halloween": {"es": "Halloween", "pt": "Halloween", "de": "Halloween", "fr": "Halloween"},
    "Easter": {"es": "Pascua", "pt": "Páscoa", "de": "Ostern", "fr": "Pâques"},
    "Africa": {"es": "África", "pt": "África", "de": "Afrika", "fr": "Afrique"},
    "Asia": {"es": "Asia", "pt": "Ásia", "de": "Asien", "fr": "Asie"},
    "South America": {"es": "Sudamérica", "pt": "América do Sul", "de": "Südamerika", "fr": "Amérique du Sud"},
    "Europe": {"es": "Europa", "pt": "Europa", "de": "Europa", "fr": "Europe"},
    "North America": {"es": "Norteamérica", "pt": "América do Norte", "de": "Nordamerika", "fr": "Amérique du Nord"},
    "Airplane Window Seat": {"es": "Ventanilla de avión", "pt": "Janela do avião", "de": "Fensterplatz im Flugzeug", "fr": "Hublot d'avion"},
    "Night Train": {"es": "Tren nocturno", "pt": "Trem noturno", "de": "Nachtzug", "fr": "Train de nuit"},
    "Peaceful Beach": {"es": "Playa tranquila", "pt": "Praia tranquila", "de": "Ruhiger Strand", "fr": "Plage paisible"},
    "Gentle River": {"es": "Río tranquilo", "pt": "Rio tranquilo", "de": "Sanfter Fluss", "fr": "Rivière paisible"},
    "Victorian Greenhouse": {"es": "Invernadero victoriano", "pt": "Estufa vitoriana", "de": "Viktorianisches Gewächshaus", "fr": "Serre victorienne"},
    "Old Harbour": {"es": "Puerto antiguo", "pt": "Porto antigo", "de": "Alter Hafen", "fr": "Vieux port"},
    "Ancient Dungeon": {"es": "Mazmorra antigua", "pt": "Masmorra antiga", "de": "Uraltes Verlies", "fr": "Donjon ancien"},
    "Adventurers' Camp": {"es": "Campamento de aventureros", "pt": "Acampamento de aventureiros", "de": "Abenteurerlager", "fr": "Camp d'aventuriers"},
    "Dragon's Cave": {"es": "Cueva del dragón", "pt": "Caverna do dragão", "de": "Drachenhöhle", "fr": "Grotte du dragon"},
    "Custom Focus Ambience": {"es": "Ambiente de concentración", "pt": "Ambiente de foco", "de": "Fokus-Atmosphäre", "fr": "Ambiance de concentration"},
}

# Sons de l'entorn (nom públic en anglés) → traducció.
SOUND_NAMES: dict[str, dict[str, str]] = {
    "Airplane Cabin": {"es": "Cabina de avión", "pt": "Cabine de avião", "de": "Flugzeugkabine", "fr": "Cabine d'avion"},
    "Autumn Wind": {"es": "Viento de otoño", "pt": "Vento de outono", "de": "Herbstwind", "fr": "Vent d'automne"},
    "Busy Tavern": {"es": "Taberna animada", "pt": "Taverna movimentada", "de": "Belebte Taverne", "fr": "Taverne animée"},
    "Café & Street Sounds": {"es": "Cafetería y calle", "pt": "Café e rua", "de": "Café und Straße", "fr": "Café et rue"},
    "Calm Music": {"es": "Música tranquila", "pt": "Música calma", "de": "Ruhige Musik", "fr": "Musique calme"},
    "Campfire Night": {"es": "Noche junto al fuego", "pt": "Noite de fogueira", "de": "Lagerfeuernacht", "fr": "Nuit au coin du feu"},
    "City Traffic": {"es": "Tráfico de ciudad", "pt": "Trânsito da cidade", "de": "Stadtverkehr", "fr": "Circulation en ville"},
    "City at Night": {"es": "Ciudad de noche", "pt": "Cidade à noite", "de": "Stadt bei Nacht", "fr": "Ville la nuit"},
    "Coffee Shop Chatter": {"es": "Murmullo de cafetería", "pt": "Burburinho de café", "de": "Café-Gemurmel", "fr": "Brouhaha de café"},
    "Crackling Fireplace": {"es": "Chimenea crepitante", "pt": "Lareira crepitante", "de": "Knisternder Kamin", "fr": "Feu de cheminée"},
    "Dripping Cave": {"es": "Cueva con goteo", "pt": "Caverna com gotejamento", "de": "Tropfende Höhle", "fr": "Grotte qui goutte"},
    "Dungeon Wind & Dripping Water": {"es": "Viento y goteo de mazmorra", "pt": "Vento e gotas na masmorra", "de": "Verlieswind und Tropfen", "fr": "Vent et gouttes de donjon"},
    "Fireplace & Thunderstorm": {"es": "Chimenea y tormenta", "pt": "Lareira e tempestade", "de": "Kamin und Gewitter", "fr": "Cheminée et orage"},
    "Forest Birdsong": {"es": "Pájaros en el bosque", "pt": "Pássaros na floresta", "de": "Vogelgesang im Wald", "fr": "Chants d'oiseaux en forêt"},
    "Forest Thunderstorm": {"es": "Tormenta en el bosque", "pt": "Tempestade na floresta", "de": "Gewitter im Wald", "fr": "Orage en forêt"},
    "Gentle Rain": {"es": "Lluvia suave", "pt": "Chuva suave", "de": "Sanfter Regen", "fr": "Pluie douce"},
    "Gentle River": {"es": "Río tranquilo", "pt": "Rio tranquilo", "de": "Sanfter Fluss", "fr": "Rivière paisible"},
    "Halloween Night": {"es": "Noche de Halloween", "pt": "Noite de Halloween", "de": "Halloween-Nacht", "fr": "Nuit d'Halloween"},
    "Howling Wind": {"es": "Viento aullando", "pt": "Vento uivante", "de": "Heulender Wind", "fr": "Vent hurlant"},
    "Howling Wind in the Trees": {"es": "Viento entre los árboles", "pt": "Vento nas árvores", "de": "Wind in den Bäumen", "fr": "Vent dans les arbres"},
    "Japanese Street": {"es": "Calle japonesa", "pt": "Rua japonesa", "de": "Japanische Straße", "fr": "Rue japonaise"},
    "Mountain Stream": {"es": "Arroyo de montaña", "pt": "Riacho na montanha", "de": "Gebirgsbach", "fr": "Ruisseau de montagne"},
    "Night Train": {"es": "Tren nocturno", "pt": "Trem noturno", "de": "Nachtzug", "fr": "Train de nuit"},
    "Ocean Waves": {"es": "Olas del mar", "pt": "Ondas do mar", "de": "Meeresrauschen", "fr": "Vagues de l'océan"},
    "Park & Plaza": {"es": "Parque y plaza", "pt": "Parque e praça", "de": "Park und Platz", "fr": "Parc et place"},
    "Quiet Night": {"es": "Noche tranquila", "pt": "Noite tranquila", "de": "Stille Nacht", "fr": "Nuit calme"},
    "Rain & Fireplace": {"es": "Lluvia y chimenea", "pt": "Chuva e lareira", "de": "Regen und Kamin", "fr": "Pluie et cheminée"},
    "Rain in the Forest": {"es": "Lluvia en el bosque", "pt": "Chuva na floresta", "de": "Regen im Wald", "fr": "Pluie en forêt"},
    "Summer Cicadas & Wind Chimes": {"es": "Cigarras y campanillas de viento", "pt": "Cigarras e sinos de vento", "de": "Zikaden und Windspiel", "fr": "Cigales et carillon à vent"},
    "Rain & Vinyl Crackle": {"es": "Lluvia y vinilo", "pt": "Chuva e vinil", "de": "Regen und Vinylknistern", "fr": "Pluie et craquements de vinyle"},
    "Rain on the Window": {"es": "Lluvia en la ventana", "pt": "Chuva na janela", "de": "Regen am Fenster", "fr": "Pluie sur la fenêtre"},
    "Rainy City": {"es": "Ciudad lluviosa", "pt": "Cidade chuvosa", "de": "Regnerische Stadt", "fr": "Ville sous la pluie"},
    "Rainy Harbour": {"es": "Puerto con lluvia", "pt": "Porto na chuva", "de": "Hafen im Regen", "fr": "Port sous la pluie"},
    "Rainy Library": {"es": "Biblioteca con lluvia", "pt": "Biblioteca na chuva", "de": "Bibliothek im Regen", "fr": "Bibliothèque sous la pluie"},
    "Spring Birdsong": {"es": "Pájaros de primavera", "pt": "Pássaros de primavera", "de": "Frühlingsvögel", "fr": "Oiseaux du printemps"},
    "Stormy Beach": {"es": "Playa con tormenta", "pt": "Praia com tempestade", "de": "Stürmischer Strand", "fr": "Plage sous l'orage"},
    "Stormy Sea": {"es": "Mar en tormenta", "pt": "Mar em tempestade", "de": "Stürmische See", "fr": "Mer déchaînée"},
    "Summer Night": {"es": "Noche de verano", "pt": "Noite de verão", "de": "Sommernacht", "fr": "Nuit d'été"},
    "Thunderstorm": {"es": "Tormenta", "pt": "Tempestade", "de": "Gewitter", "fr": "Orage"},
    "Ticking Clock & Fireplace": {"es": "Reloj y chimenea", "pt": "Relógio e lareira", "de": "Tickende Uhr und Kamin", "fr": "Horloge et cheminée"},
    "Winter Wind & Fireplace": {"es": "Viento de invierno y chimenea", "pt": "Vento de inverno e lareira", "de": "Winterwind und Kamin", "fr": "Vent d'hiver et cheminée"},
    "Noise": {"es": "Ruido", "pt": "Ruído", "de": "Rauschen", "fr": "Bruit"},
    "Jungle Birdsong": {"es": "Pájaros de la selva", "pt": "Pássaros da selva", "de": "Vogelgesang im Dschungel", "fr": "Oiseaux de la jungle"},
    "Jungle Night": {"es": "Noche en la selva", "pt": "Noite na selva", "de": "Dschungelnacht", "fr": "Nuit dans la jungle"},
    "Rainforest Rain": {"es": "Lluvia en la selva", "pt": "Chuva na floresta tropical", "de": "Regen im Regenwald", "fr": "Pluie dans la forêt tropicale"},
    "Jungle River": {"es": "Río de la selva", "pt": "Rio da selva", "de": "Dschungelfluss", "fr": "Rivière de la jungle"},
    "African Savanna Night": {"es": "Noche en la sabana africana", "pt": "Noite na savana africana", "de": "Nacht in der afrikanischen Savanne", "fr": "Nuit dans la savane africaine"},
    "Desert Wind": {"es": "Viento del desierto", "pt": "Vento do deserto", "de": "Wüstenwind", "fr": "Vent du désert"},
    "Monsoon Rain": {"es": "Lluvia monzónica", "pt": "Chuva de monção", "de": "Monsunregen", "fr": "Pluie de mousson"},
}

NOISE_NAMES = {
    "Brown": {"es": "Ruido marrón", "pt": "Ruído marrom", "de": "Braunes Rauschen", "fr": "Bruit brun"},
    "Pink": {"es": "Ruido rosa", "pt": "Ruído rosa", "de": "Rosa Rauschen", "fr": "Bruit rose"},
    "White": {"es": "Ruido blanco", "pt": "Ruído branco", "de": "Weißes Rauschen", "fr": "Bruit blanc"},
}

BREATH_NAMES = {
    "Box Breathing": {"es": "Respiración cuadrada", "pt": "Respiração quadrada", "de": "Box-Atmung", "fr": "Respiration carrée"},
    "4-7-8 Breathing": {"es": "Respiración 4-7-8", "pt": "Respiração 4-7-8", "de": "4-7-8-Atmung", "fr": "Respiration 4-7-8"},
    "Coherent Breathing": {"es": "Respiración coherente", "pt": "Respiração coerente", "de": "Kohärente Atmung", "fr": "Cohérence cardiaque"},
}

# Paraules de cada idioma.
WORDS = {
    "es": {"cozy": "Ambiente acogedor", "hour": "hora", "hours": "horas", "minutes": "minutos", "study": "para estudiar", "sleep": "para dormir",
           "read": "para leer", "ambient": "sonido ambiente sin música", "rpg": "ambiente para rol", "deep": "Trabajo profundo",
           "breath": "guiada", "noise": "para dormir y concentrarse", "dark": "pantalla oscura",
           "intro": "{theme} con {sound}{music}: {duration} {purpose}, sin interrupciones por nuestra parte.",
           "with_music": " y música suave", "no_music": " (Sin música)", "full": "Vídeo completo", "below": "Descripción original en inglés:"},
    "pt": {"cozy": "Ambiente aconchegante", "hour": "hora", "hours": "horas", "minutes": "minutos", "study": "para estudar", "sleep": "para dormir",
           "read": "para ler", "ambient": "som ambiente sem música", "rpg": "ambiente para RPG", "deep": "Trabalho focado",
           "breath": "guiada", "noise": "para dormir e focar", "dark": "tela escura",
           "intro": "{theme} com {sound}{music}: {duration} {purpose}, sem interrupções da nossa parte.",
           "with_music": " e música suave", "no_music": " (Sem música)", "full": "Vídeo completo", "below": "Descrição original em inglês:"},
    "de": {"cozy": "Gemütliche Atmosphäre", "hour": "Stunde", "hours": "Stunden", "minutes": "Minuten", "study": "zum Lernen", "sleep": "zum Einschlafen",
           "read": "zum Lesen", "ambient": "Ambient-Sounds ohne Musik", "rpg": "Atmosphäre für Rollenspiele", "deep": "Deep Work",
           "breath": "geführt", "noise": "zum Schlafen und Konzentrieren", "dark": "dunkler Bildschirm",
           "intro": "{theme} · Klänge: {sound}{music}. {duration} {purpose}, ohne Unterbrechungen von uns.",
           "with_music": " und sanfte Musik", "no_music": " (Ohne Musik)", "full": "Ganzes Video", "below": "Originalbeschreibung auf Englisch:"},
    "fr": {"cozy": "Ambiance cosy", "hour": "heure", "hours": "heures", "minutes": "minutes", "study": "pour étudier", "sleep": "pour dormir",
           "read": "pour lire", "ambient": "sons d'ambiance sans musique", "rpg": "ambiance pour jeu de rôle", "deep": "Travail profond",
           "breath": "guidée", "noise": "pour dormir et se concentrer", "dark": "écran sombre",
           "intro": "{theme} avec {sound}{music} : {duration} {purpose}, sans interruption de notre part.",
           "with_music": " et musique douce", "no_music": " (Sans musique)", "full": "Vidéo complète", "below": "Description originale en anglais :"},
}


for _table, _extra in ((THEME_NAMES, more.THEMES), (SOUND_NAMES, more.SOUNDS), (NOISE_NAMES, more.NOISES), (BREATH_NAMES, more.BREATHS)):
    for _name, _values in _extra.items():
        _table.setdefault(_name, {}).update(zip(more.NEW_LANGUAGES, _values))
WORDS.update(more.WORDS)
DESCRIPTION = more.DESCRIPTION
CHANNEL_NAME = "The Amber Window"
NO_SPACE_LANGUAGES = {"ja", "ko"}  # «2時間», «30분»


def _tr(table: dict[str, dict[str, str]], name: str, lang: str) -> str:
    return table.get(name, {}).get(lang, name)


def duration_text(minutes: int, lang: str) -> str:
    words = WORDS[lang]
    gap = "" if lang in NO_SPACE_LANGUAGES else " "
    if minutes < 60 or minutes % 60:
        return f"{minutes}{gap}{words['minutes']}"
    hours = minutes // 60
    return f"{hours}{gap}{words['hour'] if hours == 1 else words['hours']}"


def _fit(options: list[str], suffix: str = "") -> str:
    candidates = [f"{t}{suffix}" for t in options] + options if suffix else options
    return next((t for t in candidates if len(t) <= 100), options[-1][:100])


def _purpose(fmt: str, words: dict[str, str]) -> str:
    return {"pomodoro": words["study"], "dormir": words["sleep"], "llegir": words["read"], "ambient": words["ambient"],
            "rol": words["rpg"], "soroll": words["noise"]}.get(fmt, words["study"])


def localized_texts(*, fmt: str, public_theme: str, sound: str, duration_minutes: int, english_description: str,
                    focus: int = 25, pause: int = 5, music: bool = False, noise: str | None = None, breath: str | None = None,
                    dim: bool = False) -> dict[str, dict[str, str]]:
    """Títol i descripció per a cada idioma, en el format de «localizations» de YouTube."""
    result: dict[str, dict[str, str]] = {}
    english_rest = english_description.split("\n\n", 1)[-1] if "\n\n" in english_description else english_description
    for lang in LANGUAGES:
        words = WORDS[lang]
        duration = duration_text(duration_minutes, lang)
        dark = f" · {words['dark'].capitalize()}" if dim else ""
        no_music = "" if music or fmt == "ambient" else words["no_music"]
        if fmt == "soroll" and noise in NOISE_NAMES:
            name = NOISE_NAMES[noise][lang]
            title = _fit([f"{name} {words['noise']} | {duration}{dark}", f"{name} | {duration}{dark}"], no_music)
            theme, sound_text = name, name.lower()
        elif fmt == "respiracio" and breath in BREATH_NAMES:
            name = BREATH_NAMES[breath][lang]
            theme, sound_text = name, _tr(SOUND_NAMES, sound, lang).lower()
            title = _fit([f"{name} {words['breath']} | {duration} | {_tr(SOUND_NAMES, sound, lang)}", f"{name} {words['breath']} | {duration}"], no_music)
        else:
            theme, sound_name = _tr(THEME_NAMES, public_theme, lang), _tr(SOUND_NAMES, sound, lang)
            sound_text = sound_name.lower() if lang != "de" else sound_name
            if fmt == "pomodoro":
                rhythm = f"Pomodoro {focus}/{pause}" if (focus, pause) in {(25, 5), (50, 10)} else f"{words['deep']} {focus}/{pause}"
                middle = f"{sound_name} | {rhythm} {words['study']}"
            else:
                middle = f"{sound_name} {_purpose(fmt, words)}"
            title = _fit([
                f"{words['cozy']}: {theme} | {middle} | {duration}{dark}",
                f"{theme} | {middle} | {duration}{dark}",
                f"{theme} | {sound_name} | {duration}",
                f"{theme} | {duration}",
            ], no_music)
        intro = words["intro"].format(theme=theme, sound=sound_text, music=words["with_music"] if music else "",
                                      duration=duration, purpose=_purpose(fmt, words))
        description = full_description(lang, fmt, intro, english_description, focus=focus, pause=pause, deep=(focus, pause) not in {(25, 5), (50, 10)},
                                       dim=dim) or f"{intro}\n\n{words['below']}\n\n{english_rest}"
        if len(description.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
            description = f"{intro}\n\n{english_rest}"
        if len(description.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
            description = description.encode("utf-8")[:MAX_DESCRIPTION_BYTES].decode("utf-8", "ignore")
        result[lang] = {"title": title, "description": description}
    return result


CHAPTER_LABELS = (
    (re.compile(r"^Starting soon$"), "starting"), (re.compile(r"^Focus session (\d+)$"), "focus"), (re.compile(r"^Break$"), "break"),
    (re.compile(r"^Hour (\d+)$"), "hour"), (re.compile(r"^Part (\d+)$"), "part"), (re.compile(r"^Dark screen$"), "darkchapter"),
)
CREDIT_HEADERS = {"Music:": "music", "Ambient sounds:": "sounds"}


def _chapter_line(line: str, text: dict[str, str]) -> str:
    stamp, _, label = line.partition(" ")
    for pattern, key in CHAPTER_LABELS:
        found = pattern.match(label)
        if found:
            return f"{stamp} {text[key].format(n=found.group(1) if found.groups() else '')}"
    return line


def _credit_block(block: str, text: dict[str, str]) -> str:
    lines = []
    for line in block.split("\n"):
        if line in CREDIT_HEADERS:
            line = text[CREDIT_HEADERS[line]]
        elif line.startswith("Licenses: "):
            line = f"{text['licenses']} {line[len('Licenses: '):]}"
        lines.append(line)
    return "\n".join(lines)


def full_description(lang: str, fmt: str, intro: str, english: str, *, focus: int = 25, pause: int = 5, deep: bool = False,
                     dim: bool = False) -> str | None:
    """Descripció sencera en l'idioma: introducció, per a què serveix, capítols, crèdits (amb els noms originals) i comiat.

    Es basa en la descripció anglesa: en copia els capítols (traduïts), els crèdits i els hashtags.
    Torna None si no se'n pot fer una que càpia en el límit de YouTube.
    """
    text = DESCRIPTION.get(lang)
    if not text or fmt not in text["uses"]:
        return None
    seed = int(hashlib.sha256(english.encode("utf-8")).hexdigest(), 16)
    blocks = [b.strip() for b in english.split("\n\n") if b.strip()]
    chapters = next((b for b in blocks if b.startswith("Chapters:")), "")
    credits = [b for b in blocks if b.split("\n")[0] in CREDIT_HEADERS or b.startswith("Licenses: ")]
    hashtags = blocks[-1] if blocks and blocks[-1].startswith("#") else ""
    second = [text["uses"][fmt][seed % 2]]
    if fmt == "pomodoro":
        method = WORDS[lang]["deep"] if deep else "Pomodoro"
        first = f"{intro}\n{text['timer'].format(method=method, focus=focus, pause=pause)}"
        if "A soft chime" in english:
            first += f" {text['chime']}"
    else:
        first = intro
    if fmt == "soroll":
        second.append(text["black"] if "stays black" in english else (text["dim"].format(minutes=30) if dim else ""))
    elif dim:
        second.append(text["dim"].format(minutes=30))
    parts = [first, " ".join(p for p in second if p)]
    if fmt == "respiracio":
        parts.append(text["safe"])
    if chapters:
        lines = chapters.split("\n")[1:]
        parts.append("\n".join([text["chapters"], *(_chapter_line(line, text) for line in lines)]))
    if fmt == "soroll":
        parts.append(text["generated"])
    parts += [_credit_block(b, text) for b in credits]
    parts += [text["outros"][(seed // 2) % len(text["outros"])].format(channel=CHANNEL_NAME), hashtags]
    description = "\n\n".join(p for p in parts if p)
    return description if len(description.encode("utf-8")) <= MAX_DESCRIPTION_BYTES else None


def localized_short(base: dict[str, dict[str, str]], video_id: str) -> dict[str, dict[str, str]]:
    """Versió per al Short: títol curt amb #shorts i enllaç al vídeo complet."""
    result = {}
    for lang, texts in base.items():
        head = texts["title"].split(" | ")[0]
        title = f"{head} #shorts" if len(head) <= 92 else head[:92].rstrip() + " #shorts"
        intro = texts["description"].split("\n\n")[0]
        result[lang] = {"title": title, "description": f"{WORDS[lang]['full']}: https://youtu.be/{video_id}\n\n{intro}\n\n#shorts"}
    return result
