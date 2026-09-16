"""
Generador de marcas de tiempo de referencia de audio (LSEC 2.1.1).

Provee funciones de generación sintética lineal continua de marcas de tiempo
para textos cuando no se dispone de audio real ni transcripción ASR.
"""

from typing import List, Optional
from app.core.schemas import WordTimestamp




def get_word_timestamps_for_text(text: str, duration_seconds: Optional[float] = None) -> List[WordTimestamp]:
    """
    Genera marcas de tiempo monotónicas continuas para un texto cuando no se dispone
    de audio real ni de transcripción ASR (modo fallback agnóstico).
    """
    import re
    clean_text = text.strip()
    words = re.findall(r"\b[\w\.\-]+\b", clean_text)
    if not words:
        return []

    dur = duration_seconds or (len(words) * 0.45)
    step = dur / max(len(words), 1)
    res: List[WordTimestamp] = []
    curr = 0.0
    for w in words:
        end_t = round(curr + step, 3)
        res.append(WordTimestamp(word=w, start=round(curr, 3), end=end_t, probability=0.95))
        curr = end_t
    return res
