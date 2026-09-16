/**
 * LSEC Studio 2.1.1 — SubtitleEngine
 * 
 * Motor unificado de estilos, resolución de estilo efectivo, cálculo de layout,
 * word-wrapping, confinamiento estricto en área segura y renderizado Canvas.
 * Garantiza coincidencia visual 1:1 entre la vista previa interactiva y el video exportado.
 */

const DEFAULT_SUBTITLE_STYLE = {
  fontFamily: 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  fontSize: 20, // Tamaño de fuente base en px (normalizado para 720p base)
  textColor: '#ffffff', // Color blanco por defecto
  bgColor: '#000000',
  bgOpacity: 0.0, // Fondo transparente por defecto (0% opacidad)
  outlineWidth: 0, // Sin contorno por defecto (0px grosor)
  outlineColor: 'transparent',
  shadow: true, // Sombra de texto suave para legibilidad sobre video
  shadowBlur: 3,
  shadowColor: 'rgba(0, 0, 0, 0.85)',
  shadowOffsetX: 0,
  shadowOffsetY: 1,
  bold: false,
  italic: false,
  textAlign: 'center', // 'left' | 'center' | 'right'
  positionX: 50, // Porcentaje horizontal 0% a 100% (50 = centro)
  positionY: 88, // Porcentaje vertical 0% a 100% (88 = tercio inferior estándar)
  margin: 6, // Margen interior / padding en px
  safeArea: 5 // Porcentaje de margen para el área segura (ej. 5% = bordes protegidos)
};

class SubtitleEngine {
  /**
   * Resuelve el estilo efectivo de un segmento combinando:
   * Estilo predeterminado del sistema + Preferencias globales del usuario + Personalización del segmento
   * 
   * @param {Object} segment - Segmento activo o null
   * @param {Object} globalStyle - Preferencias globales de appState.state.overlays.subtitleStyle
   * @returns {Object} Estilo efectivo resuelto con todos los campos garantizados
   */
  static resolveEffectiveStyle(segment, globalStyle = null) {
    const global = globalStyle || (window.appState && window.appState.state?.overlays?.subtitleStyle) || {};
    const segStyle = (segment && (segment.subtitle_style || segment.custom_style)) || {};

    return {
      ...DEFAULT_SUBTITLE_STYLE,
      ...global,
      ...segStyle
    };
  }

  /**
   * Convierte un color hexadecimal (#fff o #ffffff) y una opacidad (0.0 - 1.0) en string rgba(...)
   */
  static hexToRgba(hex, opacity = 1.0) {
    if (!hex) return `rgba(11, 14, 20, ${opacity})`;
    let c = hex.replace('#', '').trim();
    if (c.length === 3) {
      c = c[0] + c[0] + c[1] + c[1] + c[2] + c[2];
    }
    if (c.length !== 6) {
      return hex.startsWith('rgba') ? hex : `rgba(11, 14, 20, ${opacity})`;
    }
    const num = parseInt(c, 16);
    const r = (num >> 16) & 255;
    const g = (num >> 8) & 255;
    const b = num & 255;
    return `rgba(${r}, ${g}, ${b}, ${Math.max(0, Math.min(1, opacity))})`;
  }

  /**
   * Calcula las dimensiones del área segura en píxeles para un contenedor o canvas dado
   */
  static getSafeAreaRect(containerWidth, containerHeight, safeAreaPct = 5) {
    const pct = Math.max(0, Math.min(25, safeAreaPct !== undefined ? safeAreaPct : 5)) / 100;
    const marginX = Math.round(containerWidth * pct);
    const marginY = Math.round(containerHeight * pct);

    return {
      left: marginX,
      top: marginY,
      right: containerWidth - marginX,
      bottom: containerHeight - marginY,
      width: Math.max(50, containerWidth - (marginX * 2)),
      height: Math.max(50, containerHeight - (marginY * 2)),
      marginX,
      marginY
    };
  }

  /**
   * Calcula el diseño métrico, partición de líneas, dimensiones y posición confinada al área segura.
   * 
   * @param {CanvasRenderingContext2D|Function} ctxOrMeasure - Contexto 2D para medir texto o función medidora
   * @param {string} text - Texto del subtítulo
   * @param {Object} style - Estilo efectivo resuelto
   * @param {number} containerWidth - Ancho del lienzo o contenedor en px
   * @param {number} containerHeight - Alto del lienzo o contenedor en px
   * @returns {Object} Información completa de layout
   */
  static calculateLayout(ctxOrMeasure, text, style, containerWidth, containerHeight) {
    const safeRect = this.getSafeAreaRect(containerWidth, containerHeight, style.safeArea);

    // Escala dimensional relativa referenciada a altura estándar 720p
    const scaleFactor = Math.max(0.4, containerHeight / 720);
    const computedFontSize = Math.max(12, Math.round(style.fontSize * scaleFactor));
    const computedMargin = Math.max(4, Math.round(style.margin * scaleFactor));
    const computedOutline = Math.max(0, Math.round((style.outlineWidth || 0) * scaleFactor));
    const computedShadowBlur = Math.max(0, Math.round((style.shadowBlur || 4) * scaleFactor));
    const lineHeight = Math.round(computedFontSize * 1.36);

    // Helper de medición
    let measureTextWidth;
    if (ctxOrMeasure && typeof ctxOrMeasure.measureText === 'function') {
      const fontStr = `${style.italic ? 'italic ' : ''}${style.bold ? '700 ' : '500 '}${computedFontSize}px ${style.fontFamily}`;
      ctxOrMeasure.font = fontStr;
      measureTextWidth = (str) => ctxOrMeasure.measureText(str).width;
    } else if (typeof ctxOrMeasure === 'function') {
      measureTextWidth = ctxOrMeasure;
    } else {
      // Estimación de ancho por caracteres si no hay contexto disponible
      measureTextWidth = (str) => str.length * (computedFontSize * 0.58);
    }

    // Partición de texto respetando ancho del área segura menos márgenes
    const rawText = (text || '').trim();
    const maxTextWidth = Math.max(60, safeRect.width - (computedMargin * 2) - 8);
    const words = rawText.split(/\s+/).filter(Boolean);
    const lines = [];
    let currentLine = '';

    for (const w of words) {
      const testLine = currentLine ? `${currentLine} ${w}` : w;
      const testWidth = measureTextWidth(testLine);

      if (testWidth <= maxTextWidth) {
        currentLine = testLine;
      } else {
        if (currentLine) {
          lines.push(currentLine);
          currentLine = w;
        } else {
          // Palabra única excede ancho máximo
          lines.push(w);
          currentLine = '';
        }
      }
    }
    if (currentLine) {
      lines.push(currentLine);
    }

    if (lines.length === 0) {
      lines.push('');
    }

    // Medición del ancho de cada línea
    let maxLineWidth = 0;
    const lineWidths = lines.map(line => {
      const w = measureTextWidth(line);
      if (w > maxLineWidth) maxLineWidth = w;
      return w;
    });

    const boxWidth = Math.min(safeRect.width, Math.round(maxLineWidth + (computedMargin * 2)));
    const boxHeight = Math.min(safeRect.height, Math.round((lines.length * lineHeight) + (computedMargin * 2)));

    // Cálculo de centro deseado según positionX y positionY (0 a 100%)
    const posX = Math.max(0, Math.min(100, style.positionX !== undefined ? style.positionX : 50));
    const posY = Math.max(0, Math.min(100, style.positionY !== undefined ? style.positionY : 88));

    const targetCenterX = Math.round((posX / 100) * containerWidth);
    const targetCenterY = Math.round((posY / 100) * containerHeight);

    let boxLeft = Math.round(targetCenterX - (boxWidth / 2));
    let boxTop = Math.round(targetCenterY - (boxHeight / 2));

    // CONFINAMIENTO ESTRICTO EN ÁREA SEGURA (Evita desborde del Canvas)
    if (boxLeft < safeRect.left) {
      boxLeft = safeRect.left;
    } else if (boxLeft + boxWidth > safeRect.right) {
      boxLeft = safeRect.right - boxWidth;
    }

    if (boxTop < safeRect.top) {
      boxTop = safeRect.top;
    } else if (boxTop + boxHeight > safeRect.bottom) {
      boxTop = safeRect.bottom - boxHeight;
    }

    return {
      lines,
      lineWidths,
      computedFontSize,
      computedMargin,
      computedOutline,
      computedShadowBlur,
      lineHeight,
      boxLeft,
      boxTop,
      boxWidth,
      boxHeight,
      safeRect,
      scaleFactor,
      posX,
      posY
    };
  }

  /**
   * Renderiza el subtítulo directamente sobre un Canvas 2D
   */
  static drawToCanvas(ctx, layout, text, style, options = {}) {
    if (!ctx || !layout || !layout.lines || layout.lines.length === 0) return;

    ctx.save();

    const {
      lines,
      computedFontSize,
      computedMargin,
      computedOutline,
      computedShadowBlur,
      lineHeight,
      boxLeft,
      boxTop,
      boxWidth,
      boxHeight
    } = layout;

    const radius = Math.max(4, Math.round(layout.scaleFactor * 6));

    // 1. Dibujar Fondo de la Caja de Subtítulo (solo si no es transparente)
    const isTransparentBg = (style.bgOpacity !== undefined && style.bgOpacity <= 0) || style.bgColor === 'transparent';
    if (!isTransparentBg) {
      const bgFill = this.hexToRgba(style.bgColor, style.bgOpacity);
      ctx.beginPath();
      if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(boxLeft, boxTop, boxWidth, boxHeight, radius);
      } else {
        ctx.rect(boxLeft, boxTop, boxWidth, boxHeight);
      }
      ctx.fillStyle = bgFill;
      ctx.fill();

      // Borde sutil del recuadro
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // 2. Configurar Tipografía
    const fontStyle = `${style.italic ? 'italic ' : ''}${style.bold ? '700 ' : '500 '}${computedFontSize}px ${style.fontFamily}`;
    ctx.font = fontStyle;
    ctx.textBaseline = 'middle';

    // 3. Renderizar cada línea de texto
    const textStartY = boxTop + computedMargin + (lineHeight / 2);

    lines.forEach((line, idx) => {
      const lineY = textStartY + (idx * lineHeight);
      let textX;

      if (style.textAlign === 'left') {
        textX = boxLeft + computedMargin;
        ctx.textAlign = 'left';
      } else if (style.textAlign === 'right') {
        textX = boxLeft + boxWidth - computedMargin;
        ctx.textAlign = 'right';
      } else {
        textX = boxLeft + (boxWidth / 2);
        ctx.textAlign = 'center';
      }

      // Dibujar contorno de texto si outlineWidth > 0
      if (computedOutline > 0) {
        ctx.save();
        ctx.lineWidth = computedOutline * 2;
        ctx.strokeStyle = style.outlineColor || '#000000';
        ctx.lineJoin = 'round';
        ctx.miterLimit = 2;
        ctx.strokeText(line, textX, lineY);
        ctx.restore();
      }

      // Sombra de texto
      if (style.shadow) {
        ctx.shadowColor = style.shadowColor || 'rgba(0, 0, 0, 0.85)';
        ctx.shadowBlur = computedShadowBlur;
        ctx.shadowOffsetX = style.shadowOffsetX !== undefined ? style.shadowOffsetX : 0;
        ctx.shadowOffsetY = style.shadowOffsetY !== undefined ? style.shadowOffsetY : 1;
      } else {
        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;
      }

      // Relleno principal de texto
      ctx.fillStyle = style.textColor || '#ffffff';
      ctx.fillText(line, textX, lineY);
    });

    ctx.restore();
  }

  /**
   * Dibuja la guía visual del área segura sobre un Canvas 2D (exclusivo para vista previa)
   */
  static drawSafeAreaGuide(ctx, safeRect, containerWidth, containerHeight, label = 'Área Segura') {
    if (!ctx || !safeRect) return;

    ctx.save();
    ctx.strokeStyle = 'rgba(183, 211, 107, 0.75)'; // Verde LSEC
    ctx.lineWidth = 1.5;
    ctx.setLineDash([6, 4]);

    ctx.strokeRect(safeRect.left, safeRect.top, safeRect.width, safeRect.height);

    // Etiqueta indicadora en la esquina superior izquierda
    ctx.setLineDash([]);
    ctx.font = '600 11px monospace';
    ctx.fillStyle = 'rgba(183, 211, 107, 0.9)';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'bottom';
    ctx.fillText(`${label} (${Math.round((safeRect.left / containerWidth) * 100)}%)`, safeRect.left + 4, safeRect.top - 3);

    ctx.restore();
  }
}

// Exportación en ambiente global del navegador
if (typeof window !== 'undefined') {
  window.DEFAULT_SUBTITLE_STYLE = DEFAULT_SUBTITLE_STYLE;
  window.SubtitleEngine = SubtitleEngine;
}
