"""Frases alternatives per als títols, les descripcions i els Shorts.

Cada vídeo tria les seues amb un número (l'identificador del vídeo): així dos vídeos
seguits no repeteixen les mateixes frases, i si es torna a fer un Short ix igual.
Les paraules clau per a les cerques («Cozy … Ambience», «Study With Me», «Sleep»…)
es mantenen sempre: només canvien els detalls.
"""
from __future__ import annotations

import random

VARIANTS = 8


def new_seed() -> int:
    return random.randrange(1_000_000)


def pick(options: list[str] | tuple[str, ...], seed: int, salt: int = 0) -> str:
    """Una opció segons el número del vídeo; `salt` fa que cada bloc gire a un ritme diferent."""
    return options[(seed * (2 * salt + 1) + salt) % len(options)]


# ---------------------------------------------------------------- Shorts

# Frase de dalt dels Shorts 2 i 3 (el primer porta la duració i el so).
# Sense comes ni apòstrofs, que FFmpeg els tracta de manera especial.
SHORT_PHRASES = (
    "Close your eyes and listen", "Stay a while", "Breathe in and slow down", "A quiet place to rest",
    "Let the world wait", "Just you and the sound", "Slow down for a moment", "Rest here for a while",
    "Leave the light on", "Nothing to do but listen", "A little calm for you", "Unwind softly",
    "Pause. Breathe. Listen.", "Your cozy corner", "Let your mind drift", "Settle in and relax",
    "Time to slow down", "Take a deep breath", "Find your calm here", "A moment just for you",
    "Rest your tired mind", "Quiet hours ahead", "Soft sounds and warm light", "Make yourself at home",
    "Let it all go quiet", "Sit back and breathe", "Everything can wait", "Warm and safe and quiet",
    "Stay cozy", "Listen to the quiet",
)


def short_phrase(seed: int, part: int) -> str:
    """Frase del Short 2 o 3. Cada vídeo en gasta dues de seguides: passen 15 vídeos abans de repetir-ne."""
    return SHORT_PHRASES[(2 * seed + part - 2) % len(SHORT_PHRASES)]


# ---------------------------------------------------------------- títols (detalls que canvien)

TITLE_DETAILS = {
    "pomodoro": ("Study With Me", "Study With Me", "Study & Focus With Me", "Study With Me", "Focus With Me"),
    "dormir": ("for Sleep & Relaxation", "for Deep Sleep", "to Fall Asleep Fast", "for Sleep & Rest", "for a Peaceful Night"),
    "ambient": ("{sounds}, No Music", "Pure {sounds}, No Music", "{sounds} Only, No Music", "{sounds}, No Music, No Talking"),
    "llegir": ("for Reading & Relaxing", "to Read & Unwind", "for Reading & Writing", "for Book Lovers", "for a Quiet Reading Night"),
    "rol": ("Tabletop RPG & Fantasy Background", "Tabletop RPG & D&D Background", "Tabletop RPG Session Ambience", "Tabletop RPG & Fantasy Ambience"),
    "soroll": ("for Sleep, Focus & Relaxation", "for Deep Sleep & Focus", "for Sleeping, Studying & Calm", "to Sleep & Focus", "for Sleep & Concentration"),
    "respiracio": ("to Calm Down", "for Stress & Anxiety Relief", "to Relax & Reset", "to Calm Your Mind"),
}


# ---------------------------------------------------------------- descripcions
# Primer paràgraf: sempre comença pel nom del lloc (és el que es veu en les cerques i el que porten els Shorts).

INTROS = {
    "pomodoro": (
        "{cozy} ambience to study and focus with me for {label_l}, with {sound}.",
        "{cozy} ambience for {label_l} of calm, steady focus, with {sound}.",
        "{cozy} ambience: {label_l} to study with me and keep your mind on one task, with {sound}.",
        "{cozy} ambience to sit down, open your notes and study with me for {label_l}, with {sound}.",
        "{cozy} ambience for a long, quiet study session: {label_l} with {sound}.",
        "{cozy} ambience to help you focus, one session at a time, for {label_l}, with {sound}.",
        "{cozy} ambience to beat procrastination and study with me for {label_l}, with {sound}.",
        "{cozy} ambience as your quiet study room for {label_l}, with {sound}.",
    ),
    "dormir": (
        "{cozy} ambience with {sound} to fall asleep, rest and relax. {label_c} with no timer, no alarms and no interruptions from us.",
        "{cozy} ambience with {sound} to help you drift off. {label_c} of calm, with no timer, no alarms and no interruptions from us.",
        "{cozy} ambience with {sound} for a deep, peaceful night's sleep. {label_c} without timers, alarms or sudden sounds from us.",
        "{cozy} ambience with {sound} to quiet a busy mind and fall asleep. {label_c}, no timer and no alarms.",
        "{cozy} ambience with {sound} for sleeping, napping or simply resting. {label_c} with nothing to interrupt you.",
        "{cozy} ambience with {sound} to slow down at the end of the day and sleep well. {label_c} with no timer and no alarms.",
        "{cozy} ambience with {sound} for restless nights or a calm bedtime routine. {label_c} of steady sound, with no interruptions from us.",
        "{cozy} ambience with {sound} to switch off and rest. {label_c} with no timer, no alarms and no talking.",
    ),
    "ambient": (
        "{cozy} ambience with pure {env_l} sounds: {label_l} with no music, no talking and no timer.",
        "{cozy} ambience with only {env_l} sounds: {label_l} of pure atmosphere, no music and no talking.",
        "{cozy} ambience with natural {env_l} sounds and nothing else: {label_l} with no music, no voices and no timer.",
        "{cozy} ambience for {label_l}, with pure {env_l} sounds and no music at all.",
        "{cozy} ambience made only of {env_l} sounds: {label_l}, no music, no talking, no interruptions.",
        "{cozy} ambience to step into for {label_l}, with pure {env_l} sounds and no music.",
        "{cozy} ambience with soft {env_l} sounds: {label_l} of calm, with no music and no timer.",
        "{cozy} ambience, just the {env_l} sounds: {label_l} with no music and no talking.",
    ),
    "llegir": (
        "{reading} ambience with {sound}. Grab a book and get comfortable for {label_l}.",
        "{reading} ambience with {sound}: {label_l} to get lost in a good book.",
        "{reading} ambience with {sound}. Make some tea, open your book and stay for {label_l}.",
        "{reading} ambience with {sound} for {label_l} of quiet pages and slow evenings.",
        "{reading} ambience with {sound}. Find your favorite blanket and read for {label_l}.",
        "{reading} ambience with {sound}: a calm corner to read, write or study for {label_l}.",
        "{reading} ambience with {sound}. One more chapter? You have {label_l}.",
        "{reading} ambience with {sound} to keep you company for {label_l} of reading.",
    ),
    "rol": (
        "{theme} ambience for your tabletop RPG and fantasy sessions, with {sound}. {label_c} without interruptions, so you can leave it playing while your party explores.",
        "{theme} ambience for your D&D and tabletop RPG sessions, with {sound}. {label_c} without interruptions to set the scene at your table.",
        "{theme} ambience with {sound} to bring your tabletop RPG campaign to life. {label_c}, no breaks, just atmosphere.",
        "{theme} ambience for game nights, one-shots and long campaigns, with {sound}. {label_c} of uninterrupted background.",
        "{theme} ambience with {sound} for tabletop RPG sessions. {label_c} so your players can feel the place while they roleplay.",
        "{theme} ambience for fantasy roleplaying, with {sound}. Press play when the party arrives: {label_l} without interruptions.",
        "{theme} ambience with {sound}, made for your next tabletop session. {label_c} of background so you can focus on the story.",
        "{theme} ambience for adventurers and game masters, with {sound}. {label_c} without interruptions.",
    ),
    "soroll": (
        "{label} of smooth {color_l} noise for sleeping, studying, focusing, relaxing or calming a baby. {uses}",
        "{label} of steady {color_l} noise to help you sleep, focus or relax. {uses}",
        "{label} of {color_l} noise to block out distractions and fall asleep. {uses}",
        "{label} of soft {color_l} noise for deep sleep, study sessions and calming a baby. {uses}",
        "{label} of continuous {color_l} noise for sleeping, concentrating or masking noisy neighbors. {uses}",
        "{label} of {color_l} noise for babies, light sleepers and busy minds. {uses}",
        "{label} of smooth, uninterrupted {color_l} noise for focus and restful sleep. {uses}",
        "{label} of gentle {color_l} noise to quiet the room and your mind. {uses}",
    ),
    "respiracio": (
        "A {minutes} minute guided breathing exercise ({pattern_l}) to calm down, ease stress and anxiety, focus before studying or unwind before sleep.",
        "A {minutes} minute guided breathing exercise ({pattern_l}) to slow down, release tension and feel calmer.",
        "Take {minutes} minutes for yourself with this guided breathing exercise ({pattern_l}) to relax body and mind.",
        "A {minutes} minute guided breathing exercise ({pattern_l}) for stressful days, busy minds or before sleep.",
        "A {minutes} minute guided breathing exercise ({pattern_l}) to reset before an exam, a meeting or bedtime.",
        "Breathe along for {minutes} minutes with this guided breathing exercise ({pattern_l}) and let your body settle.",
        "A {minutes} minute guided breathing exercise ({pattern_l}) to find calm and focus, one breath at a time.",
        "A short {minutes} minute guided breathing exercise ({pattern_l}) to unwind and come back to the present moment.",
    ),
}

# Segon paràgraf: com o per a què usar el vídeo.
USES = {
    "pomodoro": (
        "Cozy study ambience for exams, homework, reading, writing or deep work. Put your phone away, make yourself something warm and start the first session.",
        "Perfect for exam season, homework, coding, writing or any task that needs your full attention. Silence your phone, grab some water and begin.",
        "Use it for studying, revising, working from home or deep reading. Set one small goal for each session and tick it off when the timer ends.",
        "A calm companion for exams, essays, projects and long to-do lists. Clear your desk, take a slow breath and press play.",
        "Study, write, code or plan your week: the timer keeps the rhythm so you don't have to. Step away from the screen during every break.",
        "Made for students, writers and anyone working on something that matters. Pick one task, put everything else aside and start.",
        "Whether it's finals, homework or a work deadline, you're not studying alone. Stretch, drink some water and rest your eyes in the breaks.",
        "Leave it running for revision, reading, writing or deep work. Make yourself a warm drink, get comfortable and let the first session begin.",
    ),
    "dormir": (
        "Close your eyes and let the cozy ambience carry you to sleep. Also lovely as calm background sound for reading or a quiet evening.",
        "Dim the lights, get under the blanket and let the sound do the rest. It also works well for meditation, reading or a lazy afternoon.",
        "Turn the volume low, breathe slowly and let your thoughts fade. Great for naps, travel or anyone who sleeps better with a little sound.",
        "Put your phone face down and let this place keep you company until morning. Also nice for relaxing, journaling or a quiet evening.",
        "A steady, gentle sound to mask noises from outside and help you stay asleep. Lovely for light sleepers and night owls too.",
        "Imagine yourself there, warm and safe, with nowhere to be. Let each breath get a little slower until you fall asleep.",
        "Leave it playing all night or just until you drift off. Also perfect as calm background sound for reading or unwinding.",
        "No sudden changes, no loud moments: just a soft, constant ambience for a better night.",
    ),
    "ambient": (
        "Cozy background ambience for studying, working, reading, relaxing or sleeping. Turn it up, turn it down, and let the place do the rest.",
        "Use it as background sound for work, study, reading, writing or sleep. Close your eyes and imagine you're really there.",
        "Ideal when music is too distracting: the sound fills the silence without asking for your attention.",
        "Leave it playing while you work, read, cook, draw or rest. A quiet place to come back to whenever you need it.",
        "Perfect for focus, relaxation or falling asleep. Put on your headphones and let the room around you disappear.",
        "Great for studying, working from home, meditation or a slow evening. Just press play and stay a while.",
        "A simple, steady ambience to help you focus, relax or sleep, without melodies to follow or words to listen to.",
        "Bring a little calm to your desk, your bedroom or your reading corner. Turn it low and let the sound do the rest.",
    ),
    "llegir": (
        "No timer, no alarms, no talking: just a cozy, quiet place to read, write in your journal or simply unwind.",
        "No timer and no talking, only a warm, quiet atmosphere for books, journaling or creative writing.",
        "Perfect for novels, study notes, poetry or your journal. Silence your phone and let the story take over.",
        "No alarms, no interruptions: just you, your book and a cozy place to stay.",
        "Great for reading sprints, book club catch-ups or a slow Sunday with a good story.",
        "Let the outside world fade away. Read, write, sketch or just sit and think for a while.",
        "Made for book lovers, writers and dreamers. No timer, no narration, just a quiet room to read in.",
        "A gentle ambience for fantasy, mysteries, classics or whatever is on your nightstand.",
    ),
    "rol": (
        "Made for game masters and players of fantasy roleplaying games, and for fantasy reading or writing. No timer, no narration.",
        "Perfect for D&D, Pathfinder and other fantasy RPGs, or for reading and writing fantasy. No timer, no narration.",
        "Set it at a low volume behind your table and let it do the worldbuilding for you. No timer, no narration.",
        "Also great for fantasy writing, worldbuilding, painting miniatures or reading. No timer, no narration.",
        "Use it for in-person or online sessions, solo play or campaign prep. No timer, no narration.",
        "A background that sets the mood without stealing the spotlight from your players. No timer, no narration.",
        "For dungeon masters who want atmosphere at the table, and for anyone who loves fantasy worlds. No timer, no narration.",
        "Roll for initiative, read a fantasy novel or prepare your next session with this sound in the background. No timer, no narration.",
    ),
    "soroll": (
        "No music, no voices, no ads in the middle from us.",
        "No music, no voices and no sudden changes from us.",
        "Just noise: no melody, no talking, nothing to pull your attention.",
        "Nothing changes and nothing interrupts: no music and no voices from us.",
        "Constant and predictable, with no music and no talking.",
        "Press play, lower the volume and let it run. No music and no voices from us.",
        "No music, no talking, no loud moments, just the same smooth sound all the way through.",
        "Steady from start to finish, with no voices and no music from us.",
    ),
}

# Comiat (sempre amb el nom del canal).
OUTROS = (
    "Original ambience created for {channel}. New cozy videos every week: subscribe and leave the light on.",
    "Made with care for {channel}. Subscribe for a new cozy place every week.",
    "An original ambience by {channel}. If it helped, subscribe and come back anytime.",
    "Created for {channel}. New cozy ambiences every week: subscribe so you never miss one.",
    "Original ambience by {channel}. Save it to a playlist and come back whenever you need some calm.",
    "Made for {channel}. Subscribe and leave the light on: there's a new cozy place every week.",
    "An original {channel} ambience. Tell us in the comments where you're listening from.",
    "Created for {channel}. Thank you for being here, see you in the next cozy place.",
)


# ---------------------------------------------------------------- primer comentari del canal

COMMENTS = {
    "pomodoro": (
        "What are you studying today? Tell us below and let's stay focused together 🕯️",
        "Write your goal for this session here, and come back to tick it off when you're done ✍️",
        "How many sessions are you doing today? Good luck, you've got this 🤍",
        "Studying for an exam? Share the subject and the date, we're cheering for you 📚",
        "Before you start: put your phone face down, get some water and take one deep breath. Ready? 🕯️",
        "Where are you studying from today? Let's fill this place with quiet focus ✨",
        "Drop a 🕯️ when you finish your first session",
        "What's the one task you want done by the end of this video? Write it here so you keep your word 💪",
    ),
    "sleep": (
        "Sleep well. Where are you listening from tonight? 🌙",
        "Leave a 🌙 if you fell asleep before the end",
        "Do you sleep better with rain, fire or quiet music? Tell us below 🤍",
        "Wishing you a calm, restful night. Thank you for being here ✨",
        "What helps you fall asleep besides sounds like these? Share your tips 🛏️",
        "Goodnight from The Amber Window. Rest, you've done enough today 🕯️",
        "Is it night where you are, or is this an afternoon nap? 😴",
        "Close your eyes and breathe slowly. We'll keep the light on for you 🌙",
    ),
    "reading": (
        "What are you reading right now? We're always looking for the next book 📖",
        "Share the book on your nightstand, let's build a reading list together 📚",
        "Tea, coffee or hot chocolate for this reading session? ☕",
        "Leave a 📖 if you finished a chapter with this ambience",
        "What's the coziest book you've ever read? Tell us below 🕯️",
        "Paper book, e-reader or audiobook today? ✨",
        "Which place should we make next for reading? Ideas are welcome 🤍",
        "Writing, journaling or reading tonight? Tell us what you're working on ✍️",
    ),
    "rpg": (
        "What's happening at your table tonight? Tell us about your campaign 🎲",
        "Which system are you playing: D&D, Pathfinder or something else? 🐉",
        "Game masters: what scene are you using this ambience for? ⚔️",
        "Which place should we make next for your sessions? Leave your ideas below 🗺️",
        "Roll a d20 in the comments: what did you get? 🎲",
        "Share the best moment of your last session 🕯️",
        "Is your party exploring, fighting or resting at the inn right now? 🍺",
        "Players or game master? Tell us who's listening 🎲",
    ),
    "noise": (
        "What do you use this noise for: sleep, focus or calming a baby? 🤍",
        "Brown, pink or white: which colour works best for you?",
        "Leave a 💤 if it helped you fall asleep",
        "Is it noisy where you live? Tell us what this helps you block out",
        "Do you listen with headphones or speakers? Share your setup 🎧",
        "Sleep well and focus well. Thank you for listening 🕯️",
        "How long do you usually leave it playing? 🌙",
        "Which length should we make next? Tell us below",
    ),
    "breathing": (
        "How do you feel after this exercise? Tell us in one word 🤍",
        "Leave a 🌿 if you feel a little calmer now",
        "When do you use breathing exercises: before sleep, before exams or during the day?",
        "Which breathing pattern should we make next? 🌬️",
        "Take a moment for yourself. How was this session for you? ✨",
        "Share this with someone who needs a calm minute today 🤍",
        "Did you do it with your eyes open or closed? 🌿",
        "Breathe gently and be kind to yourself today 🕯️",
    ),
}
COMMENT_GROUPS = {"pomodoro": "pomodoro", "dormir": "sleep", "llegir": "reading", "ambient": "sleep", "rol": "rpg", "soroll": "noise", "respiracio": "breathing"}


def first_comment(fmt: str, seed: int) -> str:
    return pick(COMMENTS[COMMENT_GROUPS.get(fmt, "pomodoro")], seed, 3)
