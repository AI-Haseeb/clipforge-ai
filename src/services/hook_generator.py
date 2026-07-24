import random  # generates random choices and variation


HOOK_TEMPLATES = [
    "STOP DOING THIS",
    "NOBODY TALKS ABOUT THIS",
    "YOU WON'T BELIEVE THIS",
    "THIS CHANGES EVERYTHING",
    "WATCH THIS BEFORE YOU START",
    "THE BIGGEST MISTAKE",
    "MOST PEOPLE GET THIS WRONG",
    "DON'T MAKE THIS MISTAKE",
    "THIS WORKS BETTER THAN YOU THINK",
    "THE TRUTH ABOUT THIS",
]
def generate_hooks(title: str, count: int = 5):  # generates text, media, metadata, captions, or thumbnails
    title = (title or "").strip()

    hooks = []

    if title:
        hooks.append(title.upper())

    pool = HOOK_TEMPLATES.copy()
    random.shuffle(pool)

    for h in pool:
        if len(hooks) >= count:
            break
        hooks.append(h)

    return hooks[:count]
