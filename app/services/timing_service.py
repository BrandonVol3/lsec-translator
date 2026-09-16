"""
Servicio de Temporización y Sincronización LSEC (LSEC 2.1.1).

Calcula la duración planificada de la secuencia de glosas, pausas discursivas,
presupuesto de dactilología y paráfrasis.

Diferencia estrictamente entre:
- `source_audio_pauses_duration_ms`: Pausas de audio origen (dentro de la duración de audio).
- `extended_video_pauses_duration_ms`: Pausas extendidas en video para claridad del avatar.
- `video_timeline_markers`: Hitos de navegación temporal de video.
- `pause_events`: Eventos tipificados de pausa.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.core.schemas import (
    DiscourseBlock,
    GlossItem,
    GlossType,
    NonManualSpan,
    PauseEvent,
    PauseType,
    SpatialOperation,
    TimingPlan,
    VideoTimelineMarker,
)

logger = logging.getLogger(__name__)


class TimingService:
    """
    Servicio de cálculo y validación de tiempos para animación y subtitulado LSEC.
    """

    def __init__(self, target_signing_rate: float = 2.2) -> None:
        self.target_signing_rate = target_signing_rate

    def create_timing_plan(
        self,
        glosses: List[GlossItem],
        blocks: List[DiscourseBlock],
        spans: Optional[List[NonManualSpan]] = None,
        operations: Optional[List[SpatialOperation]] = None,
        source_audio_duration_seconds: Optional[float] = None,
    ) -> TimingPlan:
        """
        Calcula y construye el TimingPlan detallado para la secuencia generada.
        """
        spans = spans or []
        operations = operations or []

        if not glosses:
            return TimingPlan(
                planned_duration_ms=0,
                total_duration_ms=0,
                signs_duration_ms=0,
                fingerspelling_duration_ms=0,
                source_audio_pauses_duration_ms=0,
                extended_video_pauses_duration_ms=0,
            )

        # 1. Desglose de duraciones de glosas
        signs_duration_ms = sum(
            g.duration_ms for g in glosses if g.gloss_type != GlossType.FINGERSPELLING
        )
        fingerspelling_duration_ms = sum(
            g.duration_ms for g in glosses if g.gloss_type == GlossType.FINGERSPELLING
        )
        manual_sign_duration_ms = signs_duration_ms
        total_gloss_duration_ms = manual_sign_duration_ms + fingerspelling_duration_ms

        paraphrase_ms = sum(
            g.duration_ms for g in glosses if g.lexical_strategy == "semantic_paraphrase" or g.alignment_type == "PARAPHRASE"
        )

        # Duración de operaciones espaciales concurrentes
        spatial_operation_duration_ms = sum(
            200 for op in operations if op.operation_type in ("ESTABLISH", "LOCATE")
        )

        # Duración de spans no manuales concurrentes
        non_manual_concurrent_duration_ms = 0
        for s in spans:
            covered_g = [g for g in glosses if s.start_order <= g.order <= s.end_order]
            non_manual_concurrent_duration_ms += sum(g.duration_ms for g in covered_g)

        source_duration_ms = int(source_audio_duration_seconds * 1000) if source_audio_duration_seconds else None

        # 2. Cálculo de pausas y marcadores temporales
        pause_events: List[PauseEvent] = []
        video_markers: List[VideoTimelineMarker] = []
        source_audio_pause_points: List[float] = []
        extended_video_pause_points: List[float] = []

        accumulated_ms = 0
        source_audio_pauses_ms = 0
        extended_video_pauses_ms = 0

        # Crear marcador inicial
        video_markers.append(
            VideoTimelineMarker(
                marker_type="START",
                at_ms=0,
                label="Inicio de Traducción LSEC",
            )
        )

        for b in blocks:
            b_glosses = [g for g in glosses if b.start_order <= g.order <= b.end_order]
            b_dur = sum(g.duration_ms for g in b_glosses)

            # Marcador de inicio de bloque
            video_markers.append(
                VideoTimelineMarker(
                    marker_type="BLOCK_START",
                    at_ms=accumulated_ms,
                    label=f"Bloque {b.id}: {b.label}",
                    related_block_id=b.id,
                )
            )

            accumulated_ms += b_dur

            # Pausa inter-bloque
            if b.pause_after_ms > 0:
                is_within_audio = source_duration_ms is not None and accumulated_ms < source_duration_ms

                p_type = PauseType.SOURCE_AUDIO_PAUSE if is_within_audio else PauseType.EXTENDED_VIDEO_PAUSE
                if is_within_audio:
                    source_audio_pauses_ms += b.pause_after_ms
                    source_audio_pause_points.append(round(accumulated_ms / 1000.0, 2))
                else:
                    extended_video_pauses_ms += b.pause_after_ms
                    extended_video_pause_points.append(round(accumulated_ms / 1000.0, 2))

                is_last_block = (b.id == blocks[-1].id)
                reason_str = f"FINAL_PAUSE tras bloque {b.label}" if is_last_block else f"Transición discursiva tras bloque {b.label}"

                pause_events.append(
                    PauseEvent(
                        pause_type=p_type,
                        start_ms=accumulated_ms,
                        duration_ms=b.pause_after_ms,
                        related_block_id=b.id,
                        reason=reason_str,
                    )
                )

                video_markers.append(
                    VideoTimelineMarker(
                        marker_type="PAUSE",
                        at_ms=accumulated_ms,
                        label=f"Pausa ({b.pause_after_ms}ms) tras {b.label}",
                        related_block_id=b.id,
                    )
                )

                accumulated_ms += b.pause_after_ms

        # Marcador final
        video_markers.append(
            VideoTimelineMarker(
                marker_type="END",
                at_ms=accumulated_ms,
                label="Fin de Traducción LSEC",
            )
        )

        total_pause_budget_ms = source_audio_pauses_ms + extended_video_pauses_ms
        sequential_duration_ms = total_gloss_duration_ms + total_pause_budget_ms
        concurrent_duration_ms = non_manual_concurrent_duration_ms + spatial_operation_duration_ms

        planned_total_ms = sequential_duration_ms
        planned_seconds = planned_total_ms / 1000.0

        signing_rate = round(len(glosses) / planned_seconds, 2) if planned_seconds > 0 else self.target_signing_rate

        compression_ratio = 1.0
        requires_extended = False
        strategy = "natural_signing_rate"
        sync_status = "SYNCHRONIZED_WITH_SOURCE"
        warning = None

        if source_duration_ms and source_duration_ms > 0:
            compression_ratio = round(planned_total_ms / source_duration_ms, 2)
            if compression_ratio > 1.05 or planned_total_ms > source_duration_ms:
                requires_extended = True
                strategy = "extended_video"
                sync_status = "SYNCHRONIZED_WITH_EXTENSION"
                warning = (
                    f"La traducción LSEC requiere {planned_total_ms}ms frente a {source_duration_ms}ms de audio "
                    f"({int(compression_ratio * 100)}%). Se extiende video mediante pausas estructuradas."
                )

        translated_video_markers_seconds = [round(m.at_ms / 1000.0, 2) for m in video_markers]

        return TimingPlan(
            source_duration_ms=source_duration_ms,
            planned_duration_ms=planned_total_ms,
            total_duration_ms=planned_total_ms,
            signs_duration_ms=signs_duration_ms,
            fingerspelling_duration_ms=fingerspelling_duration_ms,
            source_audio_pauses_duration_ms=source_audio_pauses_ms,
            extended_video_pauses_duration_ms=extended_video_pauses_ms,
            manual_sign_duration_ms=manual_sign_duration_ms,
            spatial_operation_duration_ms=spatial_operation_duration_ms,
            non_manual_concurrent_duration_ms=non_manual_concurrent_duration_ms,
            sequential_duration_ms=sequential_duration_ms,
            concurrent_duration_ms=concurrent_duration_ms,
            compression_ratio=compression_ratio,
            signing_rate=signing_rate,
            pause_budget_ms=total_pause_budget_ms,
            paraphrase_budget_ms=paraphrase_ms,
            paraphrase_duration_ms=paraphrase_ms,
            requires_extended_video=requires_extended,
            synchronization_status=sync_status,
            recommended_playback_strategy=strategy,
            source_audio_pause_points_seconds=source_audio_pause_points,
            translated_video_timeline_markers_seconds=translated_video_markers_seconds,
            extended_video_pause_points_seconds=extended_video_pause_points,
            recommended_audio_pause_points=source_audio_pause_points,
            recommended_video_pause_points=extended_video_pause_points,
            pause_events=pause_events,
            video_timeline_markers=video_markers,
            timing_warning=warning,
        )
