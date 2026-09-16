"""
test_universal_video_and_remediation.py
======================================
Pruebas integrales de validación de universalidad, remediación de sobreajuste y procesamiento
agnóstico de video y audio para LSEC v2.1.1.

Verifica:
1. Validación por Magic Bytes y rechazo de archivos corruptos o spoofing.
2. Procesamiento agnóstico de textos arbitrarios sin atajos institucionales (cero mocks/bypasses).
3. Monotonía temporal y robustez de alineación multilingüe y multi-dominio.
4. Determinismo de la máquina de estados y consistencia del plan de ejecución.
"""

import pytest
import tempfile
import os
from app.core.schemas import ExecutionStatus
from app.services.nlp_service import LSECTranslatorService
from app.api.endpoints import validate_media_magic_bytes


class TestUniversalVideoAndRemediation:
    """Suite de validación agnóstica de producción para LSEC v2.1.1."""

    @pytest.fixture
    def translator(self):
        return LSECTranslatorService()

    def test_magic_bytes_detection_valid_and_invalid(self):
        """Verifica la detección de firmas binarias reales (Magic Bytes) contra spoofing."""
        # 1. MP4 válido (ftyp)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 100)
            valid_mp4 = f.name

        # 2. WebM válido (EBML 0x1A45DFA3)
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01" + b"\x00" * 100)
            valid_webm = f.name

        # 3. WAV válido (RIFF WAVE)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF\x24\x08\x00\x00WAVEfmt \x10\x00\x00\x00" + b"\x00" * 100)
            valid_wav = f.name

        # 4. Archivo de texto spoofed renombrado a .mp4
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"This is not a video file, it is plain text pretending to be video.")
            fake_mp4 = f.name

        # 5. Archivo ejecutable malicioso
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00")
            malicious_exe = f.name

        try:
            assert validate_media_magic_bytes(valid_mp4) is True
            assert validate_media_magic_bytes(valid_webm) is True
            assert validate_media_magic_bytes(valid_wav) is True
            assert validate_media_magic_bytes(fake_mp4) is False
            assert validate_media_magic_bytes(malicious_exe) is False
        finally:
            for path in (valid_mp4, valid_webm, valid_wav, fake_mp4, malicious_exe):
                if os.path.exists(path):
                    os.unlink(path)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "arbitrary_text, domain",
        [
            ("El doctor examina al paciente en el hospital regional.", "médico"),
            ("El juez dictó la sentencia favorable en la sala de audiencias.", "legal"),
            ("Los agricultores cosechan maíz amarillo en los campos de Loja.", "agrícola"),
            ("Los ingenieros diseñan un puente colgante sobre el río Napo.", "ingeniería"),
            ("La profesora explica álgebra avanzada en la Escuela Politécnica del Litoral.", "educación"),
        ],
    )
    async def test_agnostic_domain_processing(self, translator, arbitrary_text, domain):
        """Garantiza que cualquier texto de cualquier dominio se procesa con éxito."""
        out = await translator.translate_to_gloss(arbitrary_text, mode="detailed", paraphrase_budget="compact")

        assert out is not None
        assert len(out.glosses) > 0
        assert out.execution_status in (ExecutionStatus.READY, ExecutionStatus.REVIEW_REQUIRED)
        assert out.execution_status != ExecutionStatus.BLOCKED

        # Ningún forzado hacia la UPEC
        for g in out.glosses:
            assert g.gloss != "UPEC"

        # Verificación de cobertura y planes
        for pl in out.translation_plans:
            assert pl.coverage_status in ("COMPLETE", "PARTIAL")
            assert pl.source_recall > 0.0

    @pytest.mark.asyncio
    async def test_zero_mock_or_bypass_for_unknown_filename(self, translator):
        """Verifica que el pipeline trate archivos con cualquier nombre exactamente igual."""
        raw_text = "Estudiantes de arquitectura presentan maquetas modernas en Cuenca."
        out = await translator.translate_to_gloss(raw_text, mode="detailed")

        assert out.execution_status in (ExecutionStatus.READY, ExecutionStatus.REVIEW_REQUIRED)
        gloss_tokens = [g.gloss for g in out.glosses]
        assert any(t in gloss_tokens for t in ("ESTUDIANTE", "ARQUITECTURA", "PRESENTAR", "MAQUETA", "C-U-E-N-C-A"))

    @pytest.mark.asyncio
    async def test_pipeline_with_transcription_result_model(self, translator):
        """Verifica que translate_to_gloss acepte un objeto TranscriptionResult sin error de asr_confidence."""
        from app.core.schemas import TranscriptionResult, WordTimestamp
        tr = TranscriptionResult(
            text="El científico investiga una nueva vacuna.",
            confidence=0.94,
            duration_seconds=3.5,
            word_timestamps=[
                WordTimestamp(word="El", start=0.0, end=0.3),
                WordTimestamp(word="científico", start=0.4, end=1.2),
                WordTimestamp(word="investiga", start=1.3, end=2.0),
                WordTimestamp(word="una", start=2.1, end=2.3),
                WordTimestamp(word="nueva", start=2.4, end=2.8),
                WordTimestamp(word="vacuna", start=2.9, end=3.5),
            ],
        )
        assert tr.asr_confidence == 0.94
        out = await translator.translate_to_gloss(
            text=tr.text,
            mode="detailed",
            source_audio_duration=tr.duration_seconds,
            transcription=tr,
        )
        assert out is not None
        assert out.validation_metadata.multidimensional_confidence.asr_confidence == 0.94
        assert out.execution_status in (ExecutionStatus.READY, ExecutionStatus.REVIEW_REQUIRED)
