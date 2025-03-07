import unicodedata
import re

def clean_string(input_string: str) -> str:
    cleaned = input_string.strip().lower()
    cleaned = unicodedata.normalize('NFD', cleaned)
    cleaned = re.sub(r'[^\w\s.,!?-]', '', cleaned)
    cleaned = re.sub(r'[\u0300-\u036f]', '', cleaned)
    return cleaned

def parse_course_ids(input_text):
    """Limpia y procesa el input para extraer los course IDs."""
    cleaned = input_text.replace(",", "\n").replace(" ", "\n")
    return list(filter(None, map(lambda x: x.strip(), cleaned.split("\n"))))

