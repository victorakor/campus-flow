"""Input cleaning and validation helpers."""


def clean_choice(value, options, label):
    """Match input to one of the options, ignoring case and extra spaces."""
    for option in options:
        if str(value).strip().lower() == option.lower():
            return option
    raise ValueError(f"Invalid {label} '{value}'. Choose from: {', '.join(options)}.")


def clean_title(value):
    if not str(value).strip():
        raise ValueError("Title must not be blank.")
    return str(value).strip()


def clean_users(value):
    text = str(value).strip()
    if not (text.isascii() and text.isdigit()) or int(text) < 1:
        raise ValueError(f"Affected users must be a positive whole number (got '{value}').")
    return int(text)