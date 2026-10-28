/**
 * export-disclaimer.js
 * Aviso fijo, en letra pequeña, que se incrusta en CADA fotograma del video exportado.
 * LSEC Studio es un prototipo académico: su salida es una propuesta computacional y no sustituye
 * a una persona intérprete.
 */
(function (global) {
  const EXPORT_DISCLAIMER_TEXT =
    'Propuesta computacional pendiente de validación por personas sordas nativas o profesional intérprete de LSEC';

  /**
   * Dibuja el aviso en la franja inferior del cuadro, fuera del recuadro del intérprete.
   * @param {CanvasRenderingContext2D} ctx
   * @param {number} width
   * @param {number} height
   * @param {{x:number, w:number}} [safeArea] - ancho horizontal libre (excluye el recuadro del avatar)
   */
  function drawExportDisclaimer(ctx, width, height, safeArea) {
    const margin = Math.max(6, Math.round(width * 0.012));
    const areaX = safeArea ? safeArea.x : margin;
    const areaW = Math.max(40, safeArea ? safeArea.w : width - margin * 2);
    let fontPx = Math.max(10, Math.round(height * 0.0155));

    ctx.save();
    const setFont = () => { ctx.font = `500 ${fontPx}px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`; };
    setFont();
    const padX = Math.round(fontPx * 0.6);
    const padY = Math.round(fontPx * 0.32);
    while (fontPx > 8 && ctx.measureText(EXPORT_DISCLAIMER_TEXT).width + padX * 2 > areaW) {
      fontPx -= 1;
      setFont();
    }
    const textW = ctx.measureText(EXPORT_DISCLAIMER_TEXT).width;
    const boxW = Math.min(areaW, Math.ceil(textW + padX * 2));
    const boxH = fontPx + padY * 2;
    const boxX = areaX;
    const boxY = height - boxH - Math.max(4, Math.round(height * 0.012));

    ctx.fillStyle = 'rgba(0, 0, 0, 0.45)';
    ctx.beginPath();
    ctx.roundRect(boxX, boxY, boxW, boxH, Math.round(boxH * 0.3));
    ctx.fill();
    ctx.fillStyle = 'rgba(255, 255, 255, 0.88)';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(EXPORT_DISCLAIMER_TEXT, boxX + padX, boxY + boxH / 2, boxW - padX);
    ctx.restore();
    global.__exportDisclaimerFrames = (global.__exportDisclaimerFrames || 0) + 1;
  }

  global.LSECExportDisclaimer = Object.freeze({ text: EXPORT_DISCLAIMER_TEXT, draw: drawExportDisclaimer });
})(typeof window !== 'undefined' ? window : globalThis);