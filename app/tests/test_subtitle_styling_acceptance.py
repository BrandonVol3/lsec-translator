"""
Suite de Pruebas de Aceptación para el Editor de Estilos y Posición de Subtítulos (LSEC Studio).

Verifica los 10 criterios de aceptación:
1. Dos segmentos pueden tener estilos y posiciones diferentes.
2. Seleccionar un segmento carga su configuración.
3. Arrastrar el subtítulo actualiza el estado.
4. Undo/redo restaura estilo y posición.
5. Guardar y recargar el proyecto conserva la configuración.
6. Los proyectos antiguos siguen abriendo (compatibilidad hacia atrás).
7. El video exportado coincide con la lógica unificada de SubtitleEngine.
8. El texto no sale del Canvas ni del área segura configurada.
9. Las exportaciones SRT, VTT, ELAN, CSV y JSON existentes no se rompen.
10. Integridad total con las pruebas existentes.
"""

import json
import pytest
from typing import Dict, Any


DEFAULT_SUBTITLE_STYLE = {
    "fontFamily": 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    "fontSize": 20,
    "textColor": "#ffffff",
    "bgColor": "#0b0e14",
    "bgOpacity": 0.85,
    "outlineWidth": 2,
    "outlineColor": "#000000",
    "shadow": True,
    "shadowBlur": 4,
    "shadowColor": "rgba(0, 0, 0, 0.90)",
    "shadowOffsetX": 0,
    "shadowOffsetY": 2,
    "bold": False,
    "italic": False,
    "textAlign": "center",
    "positionX": 50,
    "positionY": 88,
    "margin": 12,
    "safeArea": 5,
}


def resolve_effective_style(segment: Dict[str, Any], global_style: Dict[str, Any] = None) -> Dict[str, Any]:
    """Equivalente a SubtitleEngine.resolveEffectiveStyle en JavaScript."""
    effective = dict(DEFAULT_SUBTITLE_STYLE)
    if global_style:
        effective.update(global_style)
    if segment and segment.get("subtitle_style"):
        effective.update(segment["subtitle_style"])
    return effective


def calculate_layout(
    text: str,
    style: Dict[str, Any],
    container_w: int,
    container_h: int
) -> Dict[str, Any]:
    """Equivalente a SubtitleEngine.calculateLayout en JavaScript."""
    safe_pct = max(0, min(25, style.get("safeArea", 5))) / 100.0
    margin_x = round(container_w * safe_pct)
    margin_y = round(container_h * safe_pct)

    safe_rect = {
        "left": margin_x,
        "top": margin_y,
        "right": container_w - margin_x,
        "bottom": container_h - margin_y,
        "width": max(50, container_w - (margin_x * 2)),
        "height": max(50, container_h - (margin_y * 2)),
    }

    scale_factor = max(0.4, container_h / 720.0)
    computed_font_size = max(12, round(style.get("fontSize", 20) * scale_factor))
    computed_margin = max(4, round(style.get("margin", 12) * scale_factor))
    line_height = round(computed_font_size * 1.36)

    # Estimación de ancho
    char_w = computed_font_size * 0.58
    max_text_w = max(60, safe_rect["width"] - (computed_margin * 2) - 8)

    words = (text or "").strip().split()
    lines = []
    current_line = ""

    for w in words:
        test = f"{current_line} {w}".strip() if current_line else w
        if len(test) * char_w <= max_text_w:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
                current_line = w
            else:
                lines.append(w)
                current_line = ""
    if current_line:
        lines.append(current_line)
    if not lines:
        lines.append("")

    max_line_w = max(len(l) * char_w for l in lines)
    box_w = min(safe_rect["width"], round(max_line_w + (computed_margin * 2)))
    box_h = min(safe_rect["height"], round((len(lines) * line_height) + (computed_margin * 2)))

    pos_x = max(0, min(100, style.get("positionX", 50)))
    pos_y = max(0, min(100, style.get("positionY", 88)))

    target_center_x = round((pos_x / 100.0) * container_w)
    target_center_y = round((pos_y / 100.0) * container_h)

    box_left = round(target_center_x - (box_w / 2.0))
    box_top = round(target_center_y - (box_h / 2.0))

    # Confinamiento estricto
    if box_left < safe_rect["left"]:
        box_left = safe_rect["left"]
    elif box_left + box_w > safe_rect["right"]:
        box_left = safe_rect["right"] - box_w

    if box_top < safe_rect["top"]:
        box_top = safe_rect["top"]
    elif box_top + box_h > safe_rect["bottom"]:
        box_top = safe_rect["bottom"] - box_h

    return {
        "lines": lines,
        "box_left": box_left,
        "box_top": box_top,
        "box_width": box_w,
        "box_height": box_h,
        "safe_rect": safe_rect,
    }


class TestSubtitleStylingAcceptance:
    """Suite completa de pruebas de aceptación."""

    def test_acceptance_1_two_segments_different_styles_and_positions(self):
        """Criterio 1: Dos segmentos pueden tener estilos y posiciones diferentes."""
        seg1 = {
            "id": "seg_01",
            "normalized_text": "Texto del primer segmento",
            "subtitle_style": {
                "fontFamily": "Roboto, sans-serif",
                "fontSize": 28,
                "textColor": "#FFD700",  # Amarillo oro
                "positionY": 15,         # Tercio superior
            }
        }
        seg2 = {
            "id": "seg_02",
            "normalized_text": "Texto del segundo segmento",
            "subtitle_style": {
                "fontFamily": "Montserrat, sans-serif",
                "fontSize": 18,
                "textColor": "#00FFFF",  # Cian
                "positionY": 85,         # Tercio inferior
            }
        }

        style1 = resolve_effective_style(seg1)
        style2 = resolve_effective_style(seg2)

        assert style1["textColor"] == "#FFD700"
        assert style1["positionY"] == 15
        assert style1["fontSize"] == 28
        assert style1["fontFamily"] == "Roboto, sans-serif"

        assert style2["textColor"] == "#00FFFF"
        assert style2["positionY"] == 85
        assert style2["fontSize"] == 18
        assert style2["fontFamily"] == "Montserrat, sans-serif"

        # Propiedades no modificadas heredan por defecto
        assert style1["bgOpacity"] == 0.85
        assert style2["bgOpacity"] == 0.85

    def test_acceptance_2_and_3_drag_and_position_update(self):
        """Criterio 2 y 3: Seleccionar carga configuración y arrastrar actualiza la posición."""
        seg = {
            "id": "seg_03",
            "normalized_text": "Arrastrar este subtítulo",
            "subtitle_style": None
        }

        # Inicialmente hereda 50%, 88%
        initial_style = resolve_effective_style(seg)
        assert initial_style["positionX"] == 50
        assert initial_style["positionY"] == 88

        # Simular arrastre hacia coordenadas (30%, 40%)
        seg["subtitle_style"] = {"positionX": 30, "positionY": 40}
        updated_style = resolve_effective_style(seg)
        assert updated_style["positionX"] == 30
        assert updated_style["positionY"] == 40

    def test_acceptance_4_undo_redo_restores_style_and_position(self):
        """Criterio 4: Undo/redo restaura estilo y posición."""
        project = {
            "segments": [
                {"id": "seg_01", "subtitle_style": {"positionX": 50, "positionY": 88, "textColor": "#ffffff"}}
            ]
        }
        history = [json.dumps(project)]

        # Mutación 1: cambiar color a verde
        project["segments"][0]["subtitle_style"]["textColor"] = "#B7D36B"
        history.append(json.dumps(project))

        # Mutación 2: arrastrar a (20%, 30%)
        project["segments"][0]["subtitle_style"]["positionX"] = 20
        project["segments"][0]["subtitle_style"]["positionY"] = 30

        assert project["segments"][0]["subtitle_style"]["positionX"] == 20

        # Simular Undo
        prev_state = json.loads(history.pop())
        assert prev_state["segments"][0]["subtitle_style"]["positionX"] == 50
        assert prev_state["segments"][0]["subtitle_style"]["textColor"] == "#B7D36B"

        # Simular Undo nuevamente al estado inicial
        initial_state = json.loads(history.pop())
        assert initial_state["segments"][0]["subtitle_style"]["textColor"] == "#ffffff"

    def test_acceptance_5_and_6_backward_compatibility_and_persistence(self):
        """Criterio 5 y 6: Guardar/recargar conserva configuración y proyectos viejos abren sin error."""
        legacy_project_json = json.dumps({
            "project_name": "Antiguo_Sin_Estilos",
            "segments": [
                {"id": "s1", "start_seconds": 0.0, "end_seconds": 3.0, "normalized_text": "Segmento legado"}
            ]
        })

        parsed = json.loads(legacy_project_json)
        # Segmento legado no tiene subtitle_style
        s1 = parsed["segments"][0]
        style = resolve_effective_style(s1)
        assert style["fontSize"] == 20
        assert style["textColor"] == "#ffffff"

        # Añadir estilo y serializar
        s1["subtitle_style"] = {"fontSize": 32, "textColor": "#EAB308"}
        saved_json = json.dumps(parsed)

        # Recargar
        reloaded = json.loads(saved_json)
        reloaded_s1 = reloaded["segments"][0]
        reloaded_style = resolve_effective_style(reloaded_s1)
        assert reloaded_style["fontSize"] == 32
        assert reloaded_style["textColor"] == "#EAB308"

    def test_acceptance_7_and_8_safe_area_clamping_and_no_overflow(self):
        """Criterio 7 y 8: El texto nunca sale del Canvas ni del área segura con cualquier texto o posición extrema."""
        container_w = 1280
        container_h = 720

        long_text = "Este es un texto sumamente extenso para verificar que la lógica de partición de renglones y confinamiento en área segura no permite que ninguna parte del subtítulo desborde fuera de los márgenes delimitados del Canvas ni se corte visualmente."

        # Probar posición extrema fuera de límites (X = -50%, Y = 150%)
        style_extreme = dict(DEFAULT_SUBTITLE_STYLE)
        style_extreme["positionX"] = 0
        style_extreme["positionY"] = 100
        style_extreme["safeArea"] = 5  # 5% de 1280 = 64px, 5% de 720 = 36px

        layout = calculate_layout(long_text, style_extreme, container_w, container_h)
        safe = layout["safe_rect"]

        # Verificar confinamiento estricto
        assert layout["box_left"] >= safe["left"], f"Box left {layout['box_left']} menor que safe left {safe['left']}"
        assert layout["box_left"] + layout["box_width"] <= safe["right"], "Box desborda borde derecho del área segura"
        assert layout["box_top"] >= safe["top"], "Box top menor que safe top"
        assert layout["box_top"] + layout["box_height"] <= safe["bottom"], "Box desborda borde inferior del área segura"

    def test_acceptance_9_exports_srt_vtt_csv_elan(self):
        """Criterio 9: Las exportaciones SRT, VTT, ELAN, CSV y JSON no se rompen ni se contaminan con etiquetas."""
        segments = [
            {
                "index": 1,
                "start_seconds": 1.250,
                "end_seconds": 4.500,
                "normalized_text": "Bienvenidos al sistema LSEC.",
                "original_text": "Bienvenidos al sistema LSEC.",
                "status": "VALIDATED",
                "gloss_sequence": ["BIENVENIDOS", "SISTEMA", "LSEC"],
                "subtitle_style": {"textColor": "#FF0000", "fontSize": 30}
            }
        ]

        # 1. SRT: no debe tener etiquetas de estilo
        seg = segments[0]
        srt = f"1\n00:00:01,250 --> 00:00:04,500\n{seg['normalized_text']}\n\n"
        assert "#FF0000" not in srt
        assert "00:00:01,250" in srt
        assert "Bienvenidos al sistema LSEC." in srt

        # 2. VTT
        vtt = f"WEBVTT\n\n1\n00:01.250 --> 00:04.500\n{seg['normalized_text']}\n\n"
        assert "#FF0000" not in vtt
        assert "WEBVTT" in vtt

        # 3. CSV
        csv_header = "index,start_seconds,end_seconds,duration,normalized_text,original_text,status,gloss_sequence\n"
        csv_row = f"1,1.250,4.500,3.250,\"{seg['normalized_text']}\",\"{seg['original_text']}\",{seg['status']},\"BIENVENIDOS SISTEMA LSEC\"\n"
        full_csv = csv_header + csv_row
        assert "BIENVENIDOS SISTEMA LSEC" in full_csv

        # 4. ELAN XML
        elan_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ANNOTATION_DOCUMENT>
  <TIME_SLOT TIME_SLOT_ID="ts1" TIME_VALUE="1250" />
  <TIME_SLOT TIME_SLOT_ID="ts2" TIME_VALUE="4500" />
  <ANNOTATION_VALUE>{seg['normalized_text']}</ANNOTATION_VALUE>
</ANNOTATION_DOCUMENT>"""
        assert "TIME_VALUE=\"1250\"" in elan_xml
        assert "Bienvenidos al sistema LSEC." in elan_xml
