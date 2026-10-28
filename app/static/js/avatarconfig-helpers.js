/**
 * avatarconfig-helpers.js
 * Constantes de catálogo, funciones auxiliares de ordenamiento, reproductor UHD,
 * visor Lightbox y tarjeta de Configuración Manual para /avatarconfig.
 */

// Lista de las 56 señas re-extraídas en GPU en Google Colab (antes truncadas <= 30 frames)
export const TRUNCATED_REEXTRACTED_SIGNS = new Set([
  "Allá",
  "Alucinar, Alucinación",
  "Bailable, Bailar, Baile, Bailarín(a)",
  "Caña",
  "Caparazón",
  "Castañuela",
  "Condón",
  "Corbatín",
  "Evolución, Evolucionar",
  "Bahía",
  "Disimular, Encubrir intención",
  "Barbón",
  "Calificar, Calificación",
  "Conmoción",
  "Cólera",
  "Cóndor",
  "Ecovía, Metrobús",
  "Español",
  "Baño",
  "Barman, Cóctel, Coctelera",
  "Biología",
  "Cajón",
  "Cardiólogo",
  "Cáncer, Del zodiaco",
  "Champú",
  "Desesperación, Desesperado",
  "Extrañar",
  "Democracia, Democrático(a)",
  "Carísimo(a), Caro",
  "Asociación De Tungurahua",
  "Azúcar",
  "Cómoda",
  "Alternativa, Opción",
  "Bicicrós",
  "Brujería",
  "Clase, Comisión, Comité",
  "Colchón",
  "Cucharón",
  "Currículum vitae, Hoja de vida",
  "Escorpión",
  "Amonestación, Amonestar",
  "Azadón",
  "Babear, De atracción",
  "Buzón",
  "Charla, Exponer, Exposición",
  "Compás",
  "Confesar, Confesión",
  "Definir  Definición",
  "Armario, Closét",
  "Caballero, Señor",
  "Camarón",
  "Chichón",
  "Concluir, Conclusión",
  "Dinámico(a), Simpático",
  "Corazón acelerado",
  "Evangélico(a)",
]);

export function isReextractedSign(signName) {
  if (!signName) return false;
  const sNfc = signName.normalize('NFC').toLowerCase();
  const sNfd = signName.normalize('NFD').toLowerCase();
  for (const t of TRUNCATED_REEXTRACTED_SIGNS) {
    if (t.normalize('NFC').toLowerCase() === sNfc || t.normalize('NFD').toLowerCase() === sNfd) {
      return true;
    }
  }
  return false;
}

export function getNextVersion(ver = '2.7') {
  if (ver === '2.7') return '2.6';
  if (ver === '2.6') return '2.5';
  return '2.7';
}

export function getCmSortKey(cmId) {
  if (!cmId) return 99;
  if (cmId.endsWith('rostro')) return 10;
  if (cmId.endsWith('*')) return 11;
  const m = String(cmId).match(/(\d+)$/);
  return m ? parseInt(m[1], 10) : 99;
}

export function getVariantSortKey(vKey) {
  if (!vKey || vKey === 'base' || vKey === 'sin_recuadro') return 0;
  const m = String(vKey).match(/(\d+)$/);
  return m ? parseInt(m[1], 10) : 99;
}

export async function fetchSignQA(signName, version = '2.7') {
  try {
    const vParam = version ? `?version=${version}` : '';
    const res = await fetch(`/api/v1/animations/${encodeURIComponent(signName)}/qa${vParam}`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchSignInfo(signName) {
  try {
    const res = await fetch(`/api/v1/animations/${encodeURIComponent(signName)}/info`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export function updateUHDVideoPlayer(signName, meta) {
  const videoEl = document.getElementById('avatar-uhd-video');
  const fallbackEl = document.getElementById('avatar-uhd-fallback');
  const fallbackLink = document.getElementById('btn-uhd-open-remote');
  const headerTitle = document.getElementById('uhd-header-sign-name');
  const catalogPosPill = document.getElementById('uhd-catalog-pos-pill');
  const videoTimeDisplay = document.getElementById('uhd-time-display');

  if (headerTitle) headerTitle.textContent = signName;
  if (catalogPosPill && meta) {
    catalogPosPill.textContent = `#${meta.catalog_index || '—'} Catálogo`;
  }

  if (!videoEl) return;

  const videoUrl = `/api/v1/animations/${encodeURIComponent(signName)}/video`;
  fallbackEl.style.display = 'none';
  videoEl.style.display = 'block';

  videoEl.src = videoUrl;
  videoEl.load();

  const speedSelect = document.getElementById('select-avatar-speed');
  if (speedSelect) videoEl.playbackRate = parseFloat(speedSelect.value);

  videoEl.onerror = () => {
    videoEl.style.display = 'none';
    fallbackEl.style.display = 'flex';
    const ytUrl = meta?.video_url || (meta?.video_id ? `https://www.youtube.com/watch?v=${meta.video_id}` : null);
    if (ytUrl && fallbackLink) {
      fallbackLink.href = ytUrl;
      fallbackLink.style.display = 'inline-flex';
    } else if (fallbackLink) {
      fallbackLink.style.display = 'none';
    }
  };

  videoEl.ontimeupdate = () => {
    if (videoTimeDisplay && videoEl.duration) {
      videoTimeDisplay.textContent = `${videoEl.currentTime.toFixed(2)}s / ${videoEl.duration.toFixed(2)}s`;
    }
  };
}

export function buildActiveSignHandshapeMeta(signName, info, allItems, handshapesById) {
  const itemFromList = allItems.find(it => it.sign === signName) || {};
  const merged = { ...itemFromList, ...(info || {}) };
  const cmMeta = merged.hand_configuration_meta || {};
  const cmId = merged.hand_configuration || cmMeta.id || 'configuracion_manual_*';
  const cfgFromCatalog = handshapesById[cmId] || {};

  const isRostro = cmId === 'configuracion_manual_rostro';
  const roman = cmMeta.roman || cfgFromCatalog.roman || (cmId.endsWith('*') ? '*' : cmId.replace('configuracion_manual_', '').toUpperCase());
  const colorHex = cmMeta.color_hex || cfgFromCatalog.color_hex || '#64748B';
  const cmName = cmMeta.name || cfgFromCatalog.name || cmId;
  const sheetUrl = cmMeta.sheet_url || cfgFromCatalog.sheet_url || (cmId.endsWith('*') ? null : `/configuracion-manual/${cmId}.jpg`);
  const variantId = merged.hand_variant || cmMeta.variant_id || (cmId.endsWith('*') ? 'configuracion_manual_*_sin_recuadro' : `${cmId}_base`);
  const variantKey = merged.hand_variant_key || cmMeta.variant_key || (cmId.endsWith('*') ? 'sin_recuadro' : 'base');
  const variantLabel = merged.hand_variant_label || cmMeta.variant_label || `${roman}-${variantKey.toUpperCase()}`;

  let variantImgUrl = cmMeta.variant_image_url;
  let variantCount = 0;
  if (cfgFromCatalog.variants) {
    const vObj = cfgFromCatalog.variants.find(v => v.variant_id === variantId || v.short_key === variantKey);
    if (vObj) {
      if (!variantImgUrl) variantImgUrl = vObj.image_url;
      variantCount = vObj.total_signs || 0;
    }
  }
  if (!variantCount) {
    variantCount = allItems.filter(it => it.hand_variant === variantId).length;
  }

  const activeMeta = {
    cmId,
    roman,
    colorHex,
    cmName,
    sheetUrl,
    variantId,
    variantKey,
    variantLabel,
    variantImgUrl,
    variantCount,
  };

  const badgeEl = document.getElementById('active-cm-badge');
  const thumbImg = document.getElementById('active-cm-variant-img');
  const thumbNoImg = document.getElementById('active-cm-no-img');
  const thumbBox = document.getElementById('active-cm-thumb-box');
  const titleEl = document.getElementById('active-cm-title');
  const subEl = document.getElementById('active-cm-subtitle');
  const grpCntEl = document.getElementById('active-cm-group-count');
  const btnSheet = document.getElementById('btn-active-cm-open-sheet');
  const uhdCmBtn = document.getElementById('btn-uhd-open-cm-sheet');
  const uhdCmTxt = document.getElementById('uhd-cm-pill-text');

  if (badgeEl) {
    if (isRostro) {
      badgeEl.textContent = `🎭 ${roman} · ${variantLabel}`;
    } else if (cmId.endsWith('*')) {
      badgeEl.textContent = 'CM * (Sin recuadro)';
    } else {
      badgeEl.textContent = `Lámina ${roman} · ${variantLabel}`;
    }
    badgeEl.style.borderColor = colorHex;
    badgeEl.style.color = 'var(--text-primary)';
    badgeEl.style.background = `${colorHex}22`;
  }

  if (thumbBox) thumbBox.style.borderColor = colorHex;

  if (variantImgUrl && !cmId.endsWith('*')) {
    if (thumbImg) {
      thumbImg.src = variantImgUrl;
      thumbImg.style.display = 'block';
    }
    if (thumbNoImg) thumbNoImg.style.display = 'none';
  } else {
    if (thumbImg) thumbImg.style.display = 'none';
    if (thumbNoImg) {
      thumbNoImg.style.display = 'block';
      thumbNoImg.textContent = roman || '*';
    }
  }

  if (titleEl) titleEl.textContent = cmName;
  if (subEl) {
    const alfaTag = merged.alphabetical_group ? ` · Letra: ${merged.alphabetical_group.toUpperCase()}` : '';
    if (isRostro) {
      subEl.textContent = `Expresión facial exclusiva (CNM) · Brazos en reposo biomecánico (${variantLabel})${alfaTag}`;
    } else if (cmId.endsWith('*')) {
      subEl.textContent = `Seña sin recuadro manual en el video original${alfaTag}`;
    } else {
      subEl.textContent = `Sub-variante: ${variantLabel} (${variantKey === 'base' ? 'Forma Base' : 'Variante ' + variantKey.toUpperCase()})${alfaTag}`;
    }
  }
  if (grpCntEl) grpCntEl.textContent = variantCount.toLocaleString();
  if (btnSheet) btnSheet.style.display = sheetUrl ? 'inline-flex' : 'none';
  if (uhdCmBtn && uhdCmTxt) {
    uhdCmTxt.textContent = isRostro
      ? `🎭 ROSTRO · ${variantKey.toUpperCase()}`
      : (cmId.endsWith('*') ? 'CM *' : `CM ${roman} · ${variantKey.toUpperCase()}`);
    uhdCmBtn.style.borderColor = colorHex;
    uhdCmBtn.style.display = 'inline-flex';
  }

  return activeMeta;
}

export function syncVersionUIElements(preferredVersion) {
  const isV27 = preferredVersion === '2.7';
  const isV26 = preferredVersion === '2.6';
  const isV25 = preferredVersion === '2.5';

  const navV27 = document.getElementById('nav-btn-v27');
  const navV26 = document.getElementById('nav-btn-v26');
  const navV25 = document.getElementById('nav-btn-v25');
  if (navV27) navV27.className = isV27 ? 'version-nav-btn active v27' : 'version-nav-btn';
  if (navV26) navV26.className = isV26 ? 'version-nav-btn active v26' : 'version-nav-btn';
  if (navV25) navV25.className = isV25 ? 'version-nav-btn active v25' : 'version-nav-btn';

  const cardV27 = document.getElementById('card-btn-v27');
  const cardV26 = document.getElementById('card-btn-v26');
  const cardV25 = document.getElementById('card-btn-v25');
  if (cardV27) {
    cardV27.className = isV27 ? 'version-card-btn active v27' : 'version-card-btn';
    const b27 = cardV27.querySelector('.version-card-btn-badge');
    if (b27) { b27.style.display = isV27 ? 'inline-block' : 'none'; b27.textContent = 'Activa'; }
  }
  if (cardV26) {
    cardV26.className = isV26 ? 'version-card-btn active v26' : 'version-card-btn';
    const b26 = cardV26.querySelector('.version-card-btn-badge');
    if (b26) { b26.style.display = isV26 ? 'inline-block' : 'none'; b26.textContent = 'Activa'; }
  }
  if (cardV25) {
    cardV25.className = isV25 ? 'version-card-btn active v25' : 'version-card-btn';
    const b25 = cardV25.querySelector('.version-card-btn-badge');
    if (b25) { b25.style.display = isV25 ? 'inline-block' : 'none'; b25.textContent = 'Activa'; }
  }

  const banner = document.getElementById('version-status-banner');
  const bannerText = document.getElementById('version-status-text');
  if (banner && bannerText) {
    if (isV27) {
      banner.className = 'version-status-banner v27';
      bannerText.textContent = '✓ Versión 2.7.3 Estabilizada: Configuración Manual oficial (I–IX) + IK Anti-Penetración + 52 Blendshapes.';
    } else if (isV26) {
      banner.className = 'version-status-banner v26';
      bannerText.textContent = '✓ Versión 2.6 Corregida: Cinemática optimizada, IK anti-penetración (~1cm) y 52 Blendshapes.';
    } else {
      banner.className = 'version-status-banner v25';
      bannerText.textContent = 'ℹ️ Versión 2.5 Directo: Captura directa 1:1 original sin postproceso cinemático de despeje.';
    }
  }

  const hudBadge = document.getElementById('hud-pipeline-badge');
  const hudExpr = document.getElementById('hud-expressions-badge');
  if (hudBadge) {
    if (isV27) {
      hudBadge.textContent = 'v2.7.3';
      hudBadge.style.background = '#e8f5ee';
      hudBadge.style.color = '#007a3d';
      hudBadge.style.borderColor = 'rgba(0, 122, 61, 0.35)';
    } else if (isV26) {
      hudBadge.textContent = 'v2.6';
      hudBadge.style.background = '#eff6ff';
      hudBadge.style.color = '#1d4ed8';
      hudBadge.style.borderColor = 'rgba(37, 99, 235, 0.35)';
    } else {
      hudBadge.textContent = 'v2.5';
      hudBadge.style.background = '#f1f5f9';
      hudBadge.style.color = '#475569';
      hudBadge.style.borderColor = 'rgba(100, 116, 139, 0.35)';
    }
  }
  if (hudExpr) {
    if (isV27 || isV26) {
      hudExpr.textContent = '🎭 52 ARKit';
      hudExpr.style.background = 'rgba(0, 122, 61, 0.1)';
      hudExpr.style.color = '#007a3d';
      hudExpr.style.borderColor = 'rgba(0, 122, 61, 0.25)';
    } else {
      hudExpr.textContent = '🎭 Sin ARKit';
      hudExpr.style.background = 'rgba(100, 116, 139, 0.12)';
      hudExpr.style.color = '#475569';
      hudExpr.style.borderColor = 'rgba(100, 116, 139, 0.25)';
    }
  }

  const infoPipe = document.getElementById('info-pipeline-version');
  const toggleBtn = document.getElementById('btn-toggle-pipeline-version');
  if (infoPipe) {
    infoPipe.textContent = isV27 ? 'v2.7.3 Estabilizada' : (isV26 ? 'v2.6 Corregida' : 'v2.5 Directo');
    infoPipe.style.color = isV27 ? '#007a3d' : (isV26 ? '#1d4ed8' : '#475569');
  }
  if (toggleBtn) {
    const nextVer = getNextVersion(preferredVersion);
    toggleBtn.textContent = `Ver v${nextVer}`;
    toggleBtn.title = `Alternar a versión v${nextVer}`;
  }
}

export function openLightboxModal(src, title, fallbackSignName = '') {
  const modal = document.getElementById('illustration-lightbox');
  const img = document.getElementById('lightbox-img');
  const titleEl = document.getElementById('lightbox-title');
  if (!modal || !img || !src) return;

  img.src = src;
  if (titleEl && title) {
    titleEl.textContent = title;
  } else if (titleEl && fallbackSignName) {
    titleEl.textContent = `Ilustración LSEC: ${fallbackSignName}`;
  }
  modal.style.display = 'flex';
}

export function closeLightboxModal() {
  const modal = document.getElementById('illustration-lightbox');
  if (modal) modal.style.display = 'none';
}

export function loadSignIllustrationPreview(signName, meta, onResult, onUnavailable) {
  const illImg = document.getElementById('sign-illustration-img');
  const illFallback = document.getElementById('sign-illustration-fallback');
  const illStatus = document.getElementById('illustration-status-badge');
  const illRemoteLink = document.getElementById('illustration-remote-link');
  const overlayImg = document.getElementById('uhd-illustration-overlay-img');
  const overlayTitle = document.getElementById('uhd-illustration-overlay-title');
  const btnToggleUhdIll = document.getElementById('btn-toggle-uhd-illustration');
  const zoomTag = document.getElementById('illustration-zoom-tag');

  if (!illImg) return;
  const illUrl = `/api/v1/animations/${encodeURIComponent(signName)}/illustration`;
  onResult(null);

  if (illStatus) {
    illStatus.textContent = 'Buscando...';
    illStatus.style.color = 'var(--text-muted)';
  }

  const testImg = new Image();
  testImg.onload = () => {
    onResult(illUrl);
    illImg.src = illUrl;
    illImg.style.display = 'block';
    if (illFallback) illFallback.style.display = 'none';
    if (zoomTag) zoomTag.style.display = 'block';
    if (illStatus) {
      illStatus.textContent = '✓ Disponible';
      illStatus.style.color = '#10b981';
    }
    if (overlayImg) overlayImg.src = illUrl;
    if (overlayTitle) {
      const catNum = meta?.catalog_index ? `#${meta.catalog_index} ` : '';
      overlayTitle.textContent = `Ilustración LSEC: ${catNum}${signName}`;
    }
    if (btnToggleUhdIll) btnToggleUhdIll.style.display = 'inline-flex';
  };

  testImg.onerror = () => {
    onResult(null);
    illImg.style.display = 'none';
    if (zoomTag) zoomTag.style.display = 'none';
    if (illFallback) illFallback.style.display = 'flex';
    if (illStatus) {
      illStatus.textContent = 'No disponible';
      illStatus.style.color = 'var(--text-muted)';
    }
    if (btnToggleUhdIll) btnToggleUhdIll.style.display = 'none';
    if (onUnavailable) onUnavailable();

    const remoteUrl = meta?.imagen_url;
    if (remoteUrl && illRemoteLink) {
      illRemoteLink.href = remoteUrl;
      illRemoteLink.style.display = 'inline-block';
    } else if (illRemoteLink) {
      illRemoteLink.style.display = 'none';
    }
  };
  testImg.src = illUrl;
}

export function renderSignSelectOptions(signsList, itemsList, currentSignName, activeVariantFilter, activeCmFilter) {
  const selectEl = document.getElementById('select-avatar-clip');
  const hintEl = document.getElementById('select-sign-index-hint');
  if (!selectEl) return;

  selectEl.innerHTML = '';
  if (!signsList || signsList.length === 0) {
    selectEl.innerHTML = '<option value="">No se encontraron señas con este filtro</option>';
    if (hintEl) hintEl.textContent = '0 encontradas';
    return;
  }

  const frag = document.createDocumentFragment();
  const seenNfc = new Set();
  let renderedCount = 0;
  const curNfc = currentSignName ? currentSignName.normalize('NFC') : '';

  signsList.forEach((rawSign, idx) => {
    if (!rawSign) return;
    const sign = String(rawSign).normalize('NFC').trim();
    if (!sign || seenNfc.has(sign)) return;
    seenNfc.add(sign);
    renderedCount++;

    const opt = document.createElement('option');
    opt.value = sign;
    const itemMeta = itemsList[idx] || {};
    const catIdx = itemMeta.catalog_index ? `#${itemMeta.catalog_index}` : `#${renderedCount}`;
    const vLbl = itemMeta.hand_variant_label ? ` [${itemMeta.hand_variant_label}]` : '';
    const isRe = isReextractedSign(sign) ? '✨ ' : '';
    opt.textContent = `${isRe}${catIdx}${vLbl}: ${sign}`;
    if (sign === curNfc) opt.selected = true;
    frag.appendChild(opt);
  });
  selectEl.appendChild(frag);

  if (hintEl) {
    const filterTag = activeVariantFilter
      ? 'Variante activa'
      : (activeCmFilter ? 'CM activa' : 'Catálogo');
    hintEl.textContent = `${renderedCount.toLocaleString()} señas (${filterTag})`;
  }
}
