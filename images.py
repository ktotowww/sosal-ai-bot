import urllib.parse

IMAGE_MODELS = {"flux", "zimage"}
DEFAULT_IMAGE_MODEL = "flux"
PIC_COMMANDS = ("/pic", "/meme")


def is_pic_command(text):
    tokens = (text or "").strip().split(maxsplit=1)
    if not tokens:
        return False
    first_token = tokens[0].lower()
    if not first_token:
        return False
    return first_token in PIC_COMMANDS or first_token.startswith(
        tuple(f"{command}@" for command in PIC_COMMANDS)
    )


def parse_pic_command(text):
    """Разбирает '/pic [flux|zimage] <промт>' -> (model_override, prompt)."""
    text = (text or "").strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        return None, None

    candidate = parts[1].lower()
    if candidate in IMAGE_MODELS:
        if len(parts) < 3 or not parts[2].strip():
            return candidate, None
        return candidate, parts[2].strip()

    return None, text.split(maxsplit=1)[1].strip()


def build_pollinations_url(prompt, model=DEFAULT_IMAGE_MODEL, width=1024, height=1024, seed=None, enhance=True):
    encoded_prompt = urllib.parse.quote(prompt)
    params = (
        f"model={model}"
        f"&width={width}"
        f"&height={height}"
        "&nologo=true"
        f"&enhance={'true' if enhance else 'false'}"
        "&private=true"
    )
    if seed is not None:
        params += f"&seed={seed}"
    return f"https://image.pollinations.ai/p/{encoded_prompt}?{params}"
