"""
Depurador determinista de disfluencias del habla espontánea (LSEC 2.2).

Se ejecuta ANTES de la normalización contextual y de spaCy. Elimina del texto
transcrito las unidades que no pertenecen al contenido proposicional y que, de
traducirse, producirían glosas parásitas en LSEC:

  1. Muletillas y vacilaciones ("eh", "mmm", "o sea", "digamos", "pos", ...).
  2. "este"/"esto" usados como relleno (no como demostrativo) y "bueno" como
     marcador de arranque (no como adjetivo).
  3. Repeticiones inmediatas y tartamudeos ("yo yo quiero", "vamos vamos",
     "yo quiero yo quiero").

Diseño:
  - 100% basado en reglas (sin modelos estadísticos ni LLM).
  - Trabaja sobre los tramos de caracteres de cada token del texto ORIGINAL, de
    modo que cada eliminación queda trazada con sus índices de token fuente. El
    validador estructural exige índices y tiempos para toda corrección.
  - Devuelve un mapa carácter-limpio → carácter-original para que las
    correcciones posteriores conserven el offset real.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Set, Tuple

# ── Catálogos ────────────────────────────────────────────────

# Vacilaciones fonéticas que nunca aportan contenido proposicional.
_ALWAYS_FILLER: Set[str] = {
    "eh", "ehh", "eeh", "eeeh", "em", "emm", "ehm", "mm", "mmm", "mmmm",
    "hmm", "hm", "mhm", "uh", "uhm", "umm", "digamos", "pos", "osea",
}

# Palabras tras las cuales "este"/"esto" funciona como relleno y no como
# demostrativo (un demostrativo exige un sustantivo a continuación).
_PRONOUNS: Set[str] = {
    "yo", "tú", "tu", "él", "ella", "usted", "nosotros", "nosotras",
    "ustedes", "ellos", "ellas", "me", "te", "se", "nos", "le", "les", "lo", "la",
}
_DETERMINERS: Set[str] = {"el", "la", "los", "las", "un", "una", "unos", "unas"}
_CONNECTORS: Set[str] = {
    "o", "y", "e", "que", "pues", "bueno", "no", "ya", "como", "pero",
    "entonces", "sí", "si", "es", "era", "hay",
}

# Palabras que se repiten de forma legítima (énfasis, intensidad, reduplicación
# léxica) y por tanto NO deben colapsarse.
_LEGIT_REPEAT: Set[str] = {
    "muy", "mucho", "más", "mas", "no", "sí", "si", "ya", "poco", "bien",
    "casi", "tan", "así", "asi", "nunca", "siempre", "ni", "tal", "uno", "dos",
}

_FILLER_DEMONSTRATIVES: Set[str] = {"este", "esto", "esta"}

# Verbos conocidos (formas flexionadas): "este quiero" → "este" es relleno.
def _known_verb_forms() -> Set[str]:
    try:
        from app.services.semantic_parser import SpanishVerbLexicon
        return set(SpanishVerbLexicon.KNOWN_VERB_FORMS.keys())
    except Exception:  # pragma: no cover - respaldo defensivo
        return set()


_WORD_RE = re.compile(r"[\wáéíóúñüÁÉÍÓÚÑÜ\-]+")
# Puntuación terminal que NO forma parte de puntos suspensivos.
_TERMINAL_RE = re.compile(r"(?<!\.)\.(?!\.)|[?!]")
_CLAUSE_BREAK_RE = re.compile(r"[.?!;:]|\.\.\.|…")


@dataclass
class RemovedSegment:
    """Tramo del texto original eliminado, con su trazabilidad."""
    start: int
    end: int
    text: str
    kind: str  # "disfluency" | "filler_demonstrative" | "discourse_opener" | "repetition"
    reason: str
    token_indexes: List[int] = field(default_factory=list)


@dataclass
class CleanResult:
    """Resultado de la depuración."""
    text: str
    char_map: List[int]
    removed: List[RemovedSegment] = field(default_factory=list)

    def to_original_offset(self, cleaned_pos: int) -> int:
        """Traduce una posición del texto limpio a la del texto original."""
        if not self.char_map:
            return cleaned_pos
        if cleaned_pos >= len(self.char_map):
            return self.char_map[-1] + 1
        return self.char_map[max(cleaned_pos, 0)]


def _core(word: str) -> str:
    return re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ]", "", word.lower())


class SpokenTextCleaner:
    """Elimina disfluencias y repeticiones del español hablado transcrito."""

    def __init__(self) -> None:
        self._verb_forms = _known_verb_forms()

    # ── API pública ──────────────────────────────────────────

    def clean(
        self,
        text: str,
        token_spans: Optional[Sequence[Tuple[int, int]]] = None,
    ) -> CleanResult:
        """
        Depura ``text``.

        Args:
            text: Transcripción original.
            token_spans: Tramos (inicio, fin) de cada token, alineados con los
                índices de ``word_timestamps``. Si se omite se tokeniza por
                palabras.
        """
        identity = CleanResult(text=text, char_map=list(range(len(text))))
        if not text or not text.strip():
            return identity

        if token_spans is None:
            token_spans = [(m.start(), m.end()) for m in _WORD_RE.finditer(text)]
        spans = list(token_spans)
        if not spans:
            return identity

        words = [text[s:e] for s, e in spans]
        cores = [_core(w) for w in words]
        n = len(spans)

        # gap_after[i]: texto entre el token i y el i+1 (o el final del texto).
        gap_after: List[str] = []
        for i in range(n):
            nxt = spans[i + 1][0] if i + 1 < n else len(text)
            gap_after.append(text[spans[i][1]:max(nxt, spans[i][1])])

        def starts_clause(i: int) -> bool:
            return i == 0 or bool(_CLAUSE_BREAK_RE.search(gap_after[i - 1]))

        def ends_clause_softly(i: int) -> bool:
            return "," in gap_after[i] or "..." in gap_after[i] or "…" in gap_after[i]

        removed_idx: dict[int, Tuple[str, str]] = {}

        # 1. Muletillas fonéticas siempre prescindibles.
        for i, c in enumerate(cores):
            if c in _ALWAYS_FILLER:
                removed_idx[i] = ("disfluency", f"muletilla '{words[i]}'")

        # 2. "o sea (que)" – marcador de reformulación.
        i = 0
        while i < n - 1:
            if cores[i] == "o" and cores[i + 1] == "sea":
                removed_idx[i] = ("disfluency", "muletilla 'o sea'")
                removed_idx[i + 1] = ("disfluency", "muletilla 'o sea'")
                if i + 2 < n and cores[i + 2] == "que":
                    removed_idx[i + 2] = ("disfluency", "muletilla 'o sea que'")
                    i += 1
                i += 2
                continue
            i += 1

        # 3. "este/esto/esta" como relleno.
        for i, c in enumerate(cores):
            if c not in _FILLER_DEMONSTRATIVES or i in removed_idx:
                continue
            nxt = cores[i + 1] if i + 1 < n else ""
            prev_removed = (i - 1) in removed_idx
            is_filler = (
                ends_clause_softly(i)
                or not nxt
                or prev_removed
                or (i + 1) in removed_idx
                or nxt in _PRONOUNS
                or nxt in _DETERMINERS
                or nxt in _CONNECTORS
                or nxt in self._verb_forms
                or nxt in _FILLER_DEMONSTRATIVES
            )
            # Demostrativo legítimo: "este libro", "esta casa", "esto es".
            if c == "esto" and nxt in {"es", "era", "fue", "son"}:
                is_filler = False
            if is_filler:
                removed_idx[i] = ("filler_demonstrative", f"relleno '{words[i]}'")

        # 4. "bueno" como arranque discursivo (no como adjetivo).
        for i, c in enumerate(cores):
            if c != "bueno" or i in removed_idx:
                continue
            nxt = cores[i + 1] if i + 1 < n else ""
            opener = starts_clause(i) and (
                ends_clause_softly(i)
                or nxt in {"pues", "o", "eh", "este", "entonces"}
                or nxt in _PRONOUNS
                or nxt in self._verb_forms
                or (i + 1) in removed_idx
            )
            if opener:
                removed_idx[i] = ("discourse_opener", "arranque 'bueno'")
                if nxt == "pues":
                    removed_idx[i + 1] = ("discourse_opener", "arranque 'bueno pues'")

        # 5. Repeticiones inmediatas (n-gramas de 3, 2 y 1 token).
        alive = [k for k in range(n) if k not in removed_idx]
        for size in (3, 2, 1):
            k = 0
            while k + 2 * size <= len(alive):
                a = alive[k:k + size]
                b = alive[k + size:k + 2 * size]
                same = all(cores[x] and cores[x] == cores[y] for x, y in zip(a, b))
                if same and size == 1 and cores[a[0]] in _LEGIT_REPEAT:
                    same = False
                if same and size == 1 and cores[a[0]].isdigit():
                    same = False
                # No colapsar si hay puntuación fuerte entre las repeticiones.
                if same and any(
                    _CLAUSE_BREAK_RE.search(gap_after[x]) for x in a[:-1] + [a[-1]]
                ):
                    same = False
                if same:
                    for x in a:
                        removed_idx[x] = (
                            "repetition",
                            f"repetición '{' '.join(words[y] for y in a)}'",
                        )
                    alive = [q for q in range(n) if q not in removed_idx]
                    continue
                k += 1

        if not removed_idx:
            return identity

        return self._rebuild(text, spans, words, gap_after, removed_idx)

    # ── Reconstrucción con mapa de offsets ───────────────────

    def _rebuild(
        self,
        text: str,
        spans: List[Tuple[int, int]],
        words: List[str],
        gap_after: List[str],
        removed_idx: dict,
    ) -> CleanResult:
        drop: Set[int] = set()
        segments: List[RemovedSegment] = []

        for i in sorted(removed_idx):
            s, e = spans[i]
            kind, reason = removed_idx[i]
            drop.update(range(s, e))

            gap = gap_after[i]
            gap_start = e
            term = _TERMINAL_RE.search(gap)
            if term:
                # Conserva la puntuación terminal y descarta lo previo del hueco.
                drop.update(range(gap_start, gap_start + term.start()))
                # Quita el espacio que quedaría antes de la puntuación.
                p = s - 1
                while p >= 0 and text[p].isspace():
                    drop.add(p)
                    p -= 1
            else:
                drop.update(range(gap_start, gap_start + len(gap)))

            segments.append(
                RemovedSegment(
                    start=s, end=e, text=words[i], kind=kind,
                    reason=reason, token_indexes=[i],
                )
            )

        kept = [idx for idx in range(len(text)) if idx not in drop]

        # Colapsa espacios duplicados y recorta extremos, manteniendo el mapa.
        out_idx: List[int] = []
        for idx in kept:
            if text[idx].isspace() and out_idx and text[out_idx[-1]].isspace():
                continue
            out_idx.append(idx)
        while out_idx and text[out_idx[0]].isspace():
            out_idx.pop(0)
        while out_idx and text[out_idx[-1]].isspace():
            out_idx.pop()

        cleaned = "".join(text[i] for i in out_idx)
        return CleanResult(text=cleaned, char_map=out_idx, removed=segments)
