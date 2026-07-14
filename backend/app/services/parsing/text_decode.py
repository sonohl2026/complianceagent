from charset_normalizer import from_bytes

from app.services.parsing.base import ParsingError


def decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        pass
    result = from_bytes(content).best()
    if result is None:
        raise ParsingError("Could not determine text encoding")
    return str(result)
