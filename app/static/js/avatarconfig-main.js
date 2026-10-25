/**
 * avatarconfig-main.js
 * Controlador principal de la vista de calibración y verificación /avatarconfig.
 */

import * as THREE from 'three';
window.THREE = THREE;
import { AvatarPanelController } from '/static/js/avatar/avatar-controller.js?v=2.3.0';
window.AvatarPanelController = AvatarPanelController;

import {
  PHASE3_REVIEW_STORAGE_KEY, isReextractedSign, getNextVersion,
  getCmSortKey, getVariantSortKey, fetchSignQA, fetchSignInfo,
  updateUHDVideoPlayer, buildActiveSignHandshapeMeta, syncVersionUIElements,
  getPhase3ReviewFromForm, setPhase3Form, exportPhase3ReviewsData,
  openLightboxModal, closeLightboxModal, loadSignIllustrationPreview, renderSignSelectOptions,
} from './avatarconfig-helpers.js?v=3.2.0';

let allSigns = [], allItems = [], displayedSigns = [], displayedItems = [];
let currentSignName = null, currentSignIndex = -1, isComparisonMode = true;
let verifiedSigns = new Set(), currentIllustrationUrl = null, isUhdIllustrationOpen = false;
let preferredVersion = '2.7', handshapesCatalog = null, handshapesById = {};
let activeCmFilter = '', activeVariantFilter = '', activeAlfaFilter = '', activeSortOrder = 'catalog';
let activeSignCmMeta = null, phase3Reviews = {}, phase3SampleItems = [];

function setPreferredVersion(newVer) {
  if (newVer !== '2.7' && newVer !== '2.6' && newVer !== '2.5') return;
  preferredVersion = newVer;
  if (window.avatarController) {
    window.avatarController.preferredVersion = newVer;
    if (typeof window.avatarController.syncController?.setPreferredVersion === 'function') {
      window.avatarController.syncController.setPreferredVersion(newVer);
    }
  }
  syncVersionUIElements(preferredVersion);
  if (currentSignName) playSign(currentSignName);
}

try {
  const stored = localStorage.getItem('lsec_verified_signs_set');
  if (stored) verifiedSigns = new Set(JSON.parse(stored));
} catch (e) { console.warn('No se pudo leer localStorage:', e); }

function updateVerificationBadge() {
  const badge = document.getElementById('verification-progress-pill');
  if (badge && allSigns.length > 0) badge.textContent = `✓ ${verifiedSigns.size.toLocaleString()} / ${allSigns.length.toLocaleString()} VERIFICADAS`;
}

function updatePhase3Progress() {
  const progress = document.getElementById('phase3-review-progress');
  if (!progress) return;
  const reviewed = phase3SampleItems.filter(item => phase3Reviews[item.signId]?.decision && phase3Reviews[item.signId].decision !== 'PENDING').length;
  const pending = Math.max(phase3SampleItems.length - reviewed, 0);
  progress.textContent = phase3SampleItems.length
    ? `${reviewed.toLocaleString()} revisadas · ${pending.toLocaleString()} pendientes`
    : `${Object.keys(phase3Reviews).length.toLocaleString()} guardadas`;
}

function loadPhase3Reviews() {
  try {
    const stored = localStorage.getItem(PHASE3_REVIEW_STORAGE_KEY);
    phase3Reviews = stored ? JSON.parse(stored) : {};
    if (!phase3Reviews || typeof phase3Reviews !== 'object' || Array.isArray(phase3Reviews)) phase3Reviews = {};
  } catch (e) {
    phase3Reviews = {};
    console.warn('No se pudieron cargar las revisiones de fase 3:', e);
  }
  updatePhase3Progress();
}

function renderPhase3SampleList() {
  const select = document.getElementById('phase3-sample-sign');
  const count = document.getElementById('phase3-sample-count');
  if (!select) return;
  select.replaceChildren();
  if (!phase3SampleItems.length) {
    select.add(new Option('No se pudo cargar la muestra oficial', ''));
    if (count) count.textContent = 'no disponible';
    updatePhase3Progress();
    return;
  }
  phase3SampleItems.forEach(item => {
    const review = phase3Reviews[item.signId];
    const decision = review?.decision && review.decision !== 'PENDING' ? review.decision : 'PENDIENTE';
    select.add(new Option(`${item.sampleId} · ${item.signId} · ${item.risk} · ${decision}`, item.signId));
  });
  if (currentSignName && phase3SampleItems.some(item => item.signId === currentSignName)) select.value = currentSignName;
  if (count) count.textContent = `${phase3SampleItems.length} señas`;
  updatePhase3Progress();
}

async function loadPhase3Sample() {
  try {
    const response = await fetch('/api/v1/phase3/sample');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    phase3SampleItems = Array.isArray(payload.items)
      ? payload.items.map(item => ({ ...item, signId: String(item.signId || '').normalize('NFC').trim() }))
        .filter(item => item.signId)
      : [];
  } catch (error) {
    phase3SampleItems = [];
    console.error('No se pudo cargar la muestra de fase 3:', error);
  }
  renderPhase3SampleList();
}

function updatePhase3ReviewForm(signName) {
  setPhase3Form(signName && phase3Reviews[signName] ? phase3Reviews[signName] : {});
  const status = document.getElementById('phase3-review-status');
  if (status) {
    status.textContent = signName
      ? (phase3Reviews[signName]
        ? `Ficha cargada para «${signName}». Puedes corregirla y guardar de nuevo.`
        : `Sin ficha guardada para «${signName}».`)
      : 'Selecciona una seña para comenzar.';
  }
}

function savePhase3Review() {
  if (!currentSignName) return;
  if (phase3SampleItems.length && !phase3SampleItems.some(item => item.signId === currentSignName)) {
    const status = document.getElementById('phase3-review-status');
    if (status) status.textContent = 'Selecciona una seña de la muestra oficial de fase 3 antes de guardar.';
    return;
  }
  phase3Reviews[currentSignName] = {
    ...getPhase3ReviewFromForm(),
    signId: currentSignName,
    savedAt: new Date().toISOString(),
    versionReviewed: preferredVersion,
  };
  try {
    localStorage.setItem(PHASE3_REVIEW_STORAGE_KEY, JSON.stringify(phase3Reviews));
  } catch (e) {
    console.error('No se pudo guardar la revisión de fase 3:', e);
    const status = document.getElementById('phase3-review-status');
    if (status) status.textContent = 'No se pudo guardar localmente. Revisa el almacenamiento del navegador.';
    return;
  }
  updatePhase3Progress();
  renderPhase3SampleList();
  const status = document.getElementById('phase3-review-status');
  if (status) status.textContent = `Ficha guardada para «${currentSignName}».`;
}

function goToNextPhase3Pending() {
  const list = phase3SampleItems.map(item => item.signId);
  const next = list.find(sign => !phase3Reviews[sign] || phase3Reviews[sign].decision === 'PENDING');
  if (!next) {
    const status = document.getElementById('phase3-review-status');
    if (status) status.textContent = 'No quedan señas pendientes en el filtro actual.';
    return;
  }
  const select = document.getElementById('select-avatar-clip');
  if (select) select.value = next;
  playSign(next);
}

function updateVerifyButtonState(signName) {
  const btn = document.getElementById('btn-verify-sign');
  const label = document.getElementById('verify-sign-label');
  if (!btn || !label) return;

  if (verifiedSigns.has(signName)) {
    btn.classList.add('btn-verify-active');
    label.textContent = '✓ Verificada (Conforme)';
  } else {
    btn.classList.remove('btn-verify-active');
    label.textContent = 'Marcar como Verificada';
  }
}

function openLightbox(src, title) {
  openLightboxModal(src || currentIllustrationUrl, title, currentSignName);
}

function closeLightbox() {
  closeLightboxModal();
}

function toggleUhdIllustration() {
  const overlay = document.getElementById('uhd-illustration-overlay');
  if (!overlay) return;
  isUhdIllustrationOpen = !isUhdIllustrationOpen;
  overlay.style.display = isUhdIllustrationOpen ? 'flex' : 'none';
}

function hideUhdIllustration() {
  const overlay = document.getElementById('uhd-illustration-overlay');
  if (overlay) {
    overlay.style.display = 'none';
    isUhdIllustrationOpen = false;
  }
}

function updateSignIllustration(signName, meta) {
  loadSignIllustrationPreview(signName, meta, (url) => { currentIllustrationUrl = url; }, hideUhdIllustration);
}

function updateActiveSignHandshapeCard(signName, info) {
  activeSignCmMeta = buildActiveSignHandshapeMeta(signName, info, allItems, handshapesById);
}

function renderCmExplorer() {
  const pillsContainer = document.getElementById('cm-pills-container');
  const drawer = document.getElementById('cm-variants-drawer');
  const drawerTitle = document.getElementById('cm-drawer-title');
  const variantsStrip = document.getElementById('cm-variants-strip');
  const resetBtn = document.getElementById('btn-reset-cm-filters');
  const alfaSelect = document.getElementById('select-filter-alfa');
  if (!pillsContainer) return;

  const hasAnyFilter = Boolean(activeCmFilter || activeVariantFilter || activeAlfaFilter);
  if (resetBtn) resetBtn.style.display = hasAnyFilter ? 'inline-flex' : 'none';

  const cfgs = (handshapesCatalog && handshapesCatalog.configurations) ? handshapesCatalog.configurations : [];
  pillsContainer.innerHTML = '';

  const allBtn = document.createElement('button');
  allBtn.type = 'button';
  allBtn.className = `cm-pill-btn ${activeCmFilter === '' ? 'active' : ''}`;
  allBtn.title = 'Mostrar todas las configuraciones manuales (4.142 señas)';
  allBtn.innerHTML = `
    <span class="cm-pill-roman">Todas</span>
    <span class="cm-pill-count">${allSigns.length.toLocaleString()}</span>
  `;
  allBtn.addEventListener('click', () => {
    activeCmFilter = '';
    activeVariantFilter = '';
    renderCmExplorer();
    applySignFilters(true);
  });
  pillsContainer.appendChild(allBtn);

  cfgs.forEach(cfg => {
    const isActive = activeCmFilter === cfg.id;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `cm-pill-btn ${isActive ? 'active' : ''}`;
    btn.title = `${cfg.name} (${cfg.total_signs} señas)`;
    if (isActive && cfg.color_hex) btn.style.borderColor = cfg.color_hex;
    btn.innerHTML = `
      <span class="cm-pill-roman">
        <span class="cm-pill-dot" style="background:${cfg.color_hex || '#64748B'};"></span>
        ${cfg.roman}
      </span>
      <span class="cm-pill-count">${cfg.total_signs}</span>
    `;
    btn.addEventListener('click', () => {
      if (activeCmFilter === cfg.id && !activeVariantFilter) {
        activeCmFilter = '';
      } else {
        activeCmFilter = cfg.id;
      }
      activeVariantFilter = '';
      renderCmExplorer();
      applySignFilters(true);
    });
    pillsContainer.appendChild(btn);
  });

  const selectedCfg = activeCmFilter ? handshapesById[activeCmFilter] : null;
  if (drawer && variantsStrip) {
    if (selectedCfg && selectedCfg.id !== 'configuracion_manual_*' && Array.isArray(selectedCfg.variants) && selectedCfg.variants.length > 0) {
      drawer.style.display = 'block';
      if (drawerTitle) {
        drawerTitle.textContent = `Lámina ${selectedCfg.roman} (${selectedCfg.total_signs} señas) — ${selectedCfg.variants.length} formas`;
      }
      variantsStrip.innerHTML = '';

      const allVarCard = document.createElement('div');
      allVarCard.className = `cm-variant-card ${activeVariantFilter === '' ? 'active' : ''}`;
      allVarCard.title = `Ver todas las ${selectedCfg.total_signs} señas de la Configuración Manual ${selectedCfg.roman}`;
      const baseImg = selectedCfg.variants[0]?.image_url || '';
      allVarCard.innerHTML = `
        ${baseImg ? `<img src="${baseImg}" class="cm-variant-thumb" alt="Todas ${selectedCfg.roman}" style="opacity:0.85;">` : ''}
        <span class="cm-variant-lbl">Todas (${selectedCfg.roman})</span>
        <span class="cm-variant-cnt">${selectedCfg.total_signs} señas</span>
      `;
      allVarCard.addEventListener('click', () => {
        activeVariantFilter = '';
        renderCmExplorer();
        applySignFilters(true);
      });
      variantsStrip.appendChild(allVarCard);

      selectedCfg.variants.forEach(v => {
        const isVarActive = activeVariantFilter === v.variant_id;
        const card = document.createElement('div');
        card.className = `cm-variant-card ${isVarActive ? 'active' : ''}`;
        card.title = `${v.description} (${v.total_signs} señas) — Clic para filtrar, doble clic para ampliar`;
        card.innerHTML = `
          ${v.image_url ? `<img src="${v.image_url}" class="cm-variant-thumb" alt="${v.label}">` : ''}
          <span class="cm-variant-lbl">${v.short_key === 'base' ? 'Base' : v.short_key.toUpperCase()}</span>
          <span class="cm-variant-cnt">${v.total_signs} señas</span>
        `;
        card.addEventListener('click', () => {
          activeVariantFilter = (activeVariantFilter === v.variant_id) ? '' : v.variant_id;
          renderCmExplorer();
          applySignFilters(true);
        });
        card.addEventListener('dblclick', (e) => {
          e.stopPropagation();
          if (v.image_url) openLightbox(v.image_url, `${selectedCfg.name} — ${v.description}`);
        });
        variantsStrip.appendChild(card);
      });
    } else {
      drawer.style.display = 'none';
    }
  }

  if (alfaSelect) {
    const alfaCounts = {};
    allItems.forEach(it => {
      if (activeCmFilter && it.hand_configuration !== activeCmFilter) return;
      if (activeVariantFilter && it.hand_variant !== activeVariantFilter) return;
      const al = it.alphabetical_group || '';
      if (al) alfaCounts[al] = (alfaCounts[al] || 0) + 1;
    });
    const sortedAlfas = Object.keys(alfaCounts).sort();
    const prevAlfa = activeAlfaFilter;
    alfaSelect.innerHTML = `<option value="">Todas las letras (${Object.values(alfaCounts).reduce((a, b) => a + b, 0)})</option>`;
    sortedAlfas.forEach(al => {
      const letter = al.replace('alfa-', '').toUpperCase();
      const opt = document.createElement('option');
      opt.value = al;
      opt.textContent = `Letra ${letter} (${al}) — ${alfaCounts[al]} señas`;
      if (al === prevAlfa) opt.selected = true;
      alfaSelect.appendChild(opt);
    });
  }
}

function applySignFilters(autoSelectFirst = false) {
  const searchInput = document.getElementById('input-search-sign');
  const term = searchInput ? searchInput.value.trim().toLowerCase() : '';

  const pairs = [];
  allSigns.forEach((s, idx) => {
    const it = allItems[idx] || { sign: s };
    if (activeCmFilter && it.hand_configuration !== activeCmFilter) return;
    if (activeVariantFilter && it.hand_variant !== activeVariantFilter && it.hand_variant_key !== activeVariantFilter) return;
    if (activeAlfaFilter && it.alphabetical_group !== activeAlfaFilter) return;

    if (term) {
      const matchesSign = s.toLowerCase().includes(term);
      const matchesPalabra = (it.palabra || '').toLowerCase().includes(term);
      const matchesSlug = (it.slug || '').toLowerCase().includes(term);
      const matchesIdx = String(it.catalog_index || (idx + 1)) === term;
      const matchesVar = (it.hand_variant_label || '').toLowerCase().includes(term);
      if (!matchesSign && !matchesPalabra && !matchesSlug && !matchesIdx && !matchesVar) return;
    }
    pairs.push({ sign: s, item: it });
  });

  if (activeSortOrder === 'hand_config') {
    pairs.sort((a, b) => {
      const cA = getCmSortKey(a.item.hand_configuration);
      const cB = getCmSortKey(b.item.hand_configuration);
      if (cA !== cB) return cA - cB;
      const vA = getVariantSortKey(a.item.hand_variant_key);
      const vB = getVariantSortKey(b.item.hand_variant_key);
      if (vA !== vB) return vA - vB;
      const alA = a.item.alphabetical_group || 'zzz';
      const alB = b.item.alphabetical_group || 'zzz';
      if (alA !== alB) return alA.localeCompare(alB);
      return (a.item.catalog_index || 999999) - (b.item.catalog_index || 999999);
    });
  } else if (activeSortOrder === 'alfa') {
    pairs.sort((a, b) => {
      const alA = a.item.alphabetical_group || 'zzz';
      const alB = b.item.alphabetical_group || 'zzz';
      if (alA !== alB) return alA.localeCompare(alB);
      return (a.item.catalog_index || 999999) - (b.item.catalog_index || 999999);
    });
  }

  displayedSigns = pairs.map(p => p.sign);
  displayedItems = pairs.map(p => p.item);
  renderSignOptions(displayedSigns, displayedItems);

  const selectEl = document.getElementById('select-avatar-clip');
  if (autoSelectFirst && displayedSigns.length > 0) {
    const nextSign = displayedSigns.includes(currentSignName) ? currentSignName : displayedSigns[0];
    if (selectEl) selectEl.value = nextSign;
    if (nextSign !== currentSignName) {
      playSign(nextSign);
    }
  }
}

async function playSign(signName) {
  if (!signName || !window.avatarController) return;
  currentSignName = signName;
  currentSignIndex = allSigns.findIndex(s => s === signName);

  const hudSign = document.getElementById('avatar-active-gloss-hud');
  if (hudSign) hudSign.textContent = signName.toUpperCase();

  const statusBadge = document.getElementById('avatar-playback-status-badge');
  if (statusBadge) statusBadge.textContent = 'Cargando...';

  updateVerifyButtonState(signName);
  updatePhase3ReviewForm(signName);
  updateActiveSignHandshapeCard(signName, null);

  const reTag = document.getElementById('reextracted-sign-tag');
  const isRe = isReextractedSign(signName);
  if (reTag) reTag.style.display = isRe ? 'inline-flex' : 'none';

  fetchSignInfo(signName).then(info => {
    if (info) {
      const posEl = document.getElementById('info-catalog-pos');
      const palEl = document.getElementById('info-catalog-palabra');
      const slugEl = document.getElementById('info-catalog-slug');
      const catEl = document.getElementById('info-catalog-categories');

      if (posEl) posEl.textContent = `#${info.catalog_index || '—'} de 4.252`;
      if (palEl) palEl.textContent = info.palabra || signName;
      if (slugEl) slugEl.textContent = info.slug || '—';
      if (catEl) {
        const cats = Array.isArray(info.categorias) ? info.categorias.join(', ') : (info.categorias || '—');
        catEl.textContent = cats;
      }
    }
    updateActiveSignHandshapeCard(signName, info);
    updateUHDVideoPlayer(signName, info);
    updateSignIllustration(signName, info);
  });

  fetchSignQA(signName, preferredVersion).then(qa => {
    if (qa) {
      const statusPill = document.getElementById('qa-status-pill');
      if (statusPill) {
        if (qa.needs_review === true || qa.needs_review === 'True') {
          const reasons = Array.isArray(qa.review_reasons) && qa.review_reasons.length > 0
            ? ` (${qa.review_reasons[0]})`
            : '';
          statusPill.textContent = `⚠️ Revisión${reasons}`;
          statusPill.style.color = '#b45309';
        } else {
          statusPill.textContent = '✓ Aprobada';
          statusPill.style.color = '#007a3d';
        }
      }
    }
  });

  try {
    const vParam = preferredVersion ? `?version=${preferredVersion}` : '';
    const res = await fetch(`/api/v1/animations/${encodeURIComponent(signName)}${vParam}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const animData = await res.json();
    await window.avatarController.importCustomClip(animData);

    const pipeVer = animData?.metadata?.pipelineVersion || (preferredVersion === '2.7' ? '2.7_Estandarizado' : (preferredVersion === '2.6' ? '2.6_Directo_1a1_corregido' : '2.5_Directo_1a1'));
    const handStd = animData?.metadata?.handStandardization || null;
    const isV27 = pipeVer.startsWith('2.7') || handStd?.version === '2.7' || preferredVersion === '2.7';
    const isV26 = !isV27 && pipeVer.startsWith('2.6');

    syncVersionUIElements(isV27 ? '2.7' : (isV26 ? '2.6' : '2.5'));
    const bannerText = document.getElementById('version-status-text');
    if (isV27 && bannerText) {
      const stdTag = handStd?.status === 'STANDARDIZED'
        ? `🖐️ ${handStd.template_id || handStd.template_variant || handStd.hand_configuration || 'CM'} (${handStd.frames_modified || 0} frames)`
        : (handStd?.status || 'CM Estandarizada');
      bannerText.textContent = `✓ Versión 2.7.3 Estabilizada: ${stdTag} + IK Anti-Penetración + 52 Blendshapes.`;
    }

    const selectEl = document.getElementById('select-avatar-clip');
    if (selectEl && selectEl.value !== signName) selectEl.value = signName;

    if (statusBadge) statusBadge.textContent = 'Reproduciendo';

    const syncChk = document.getElementById('chk-sync-playback');
    const videoEl = document.getElementById('avatar-uhd-video');
    if (syncChk && syncChk.checked && videoEl && videoEl.src) {
      videoEl.currentTime = 0;
      const speedSelect = document.getElementById('select-avatar-speed');
      if (speedSelect) videoEl.playbackRate = parseFloat(speedSelect.value);
      videoEl.play().catch(() => {});
    }
  } catch (err) {
    console.error(`Error reproduciendo seña "${signName}":`, err);
    if (statusBadge) statusBadge.textContent = 'Error';
  }
}

function renderSignOptions(signsList, itemsList = []) {
  renderSignSelectOptions(signsList, itemsList, currentSignName, verifiedSigns, activeVariantFilter, activeCmFilter);
}

function navigateSign(delta) {
  const activeList = (displayedSigns && displayedSigns.length > 0) ? displayedSigns : allSigns;
  if (activeList.length === 0) return;
  let idx = activeList.indexOf(currentSignName);
  if (idx === -1) idx = 0;
  let nextIndex = idx + delta;
  if (nextIndex < 0) nextIndex = activeList.length - 1;
  if (nextIndex >= activeList.length) nextIndex = 0;
  const targetSign = activeList[nextIndex];
  const selectEl = document.getElementById('select-avatar-clip');
  if (selectEl) selectEl.value = targetSign;
  playSign(targetSign);
}

async function initAvatarConfig() {
  try {
    loadPhase3Reviews();
    if (!window.avatarController) {
      window.avatarController = new AvatarPanelController('avatar-config-workspace');
      console.info('✓ AvatarPanelController activo en /avatarconfig');
    }

    window.avatarController.renderClipOptions = () => {};
    window.avatarController.categories = [];

    const toggleCompBtn = document.getElementById('btn-toggle-comparison-mode');
    const compLayout = document.getElementById('comparison-layout-wrap');
    toggleCompBtn?.addEventListener('click', () => {
      isComparisonMode = !isComparisonMode;
      if (isComparisonMode) {
        compLayout?.classList.remove('single-view');
        toggleCompBtn.style.color = 'var(--accent-primary)';
        toggleCompBtn.textContent = '🎥 Comparación: ON';
      } else {
        compLayout?.classList.add('single-view');
        toggleCompBtn.style.color = 'var(--text-muted)';
        toggleCompBtn.textContent = '🎥 Comparación: OFF';
      }
    });

    document.getElementById('btn-cam-face')?.addEventListener('click', () => window.avatarController?.setCameraPreset('face'));
    document.getElementById('btn-cam-medium')?.addEventListener('click', () => window.avatarController?.setCameraPreset('medium'));
    document.getElementById('btn-cam-full')?.addEventListener('click', () => window.avatarController?.setCameraPreset('full'));
    document.getElementById('btn-cam-hands')?.addEventListener('click', () => window.avatarController?.setCameraPreset('hands'));
    document.getElementById('btn-reload-default-vrm')?.addEventListener('click', () => window.avatarController?.loadVRMFromUrl('/avatar/LSEC-Interpreter-Female.vrm'));

    const selectEl = document.getElementById('select-avatar-clip');
    selectEl?.addEventListener('change', (e) => {
      const sign = e.target.value;
      if (sign) playSign(sign);
    });

    document.getElementById('btn-sign-prev')?.addEventListener('click', () => navigateSign(-1));
    document.getElementById('btn-sign-next')?.addEventListener('click', () => navigateSign(1));
    document.getElementById('btn-sign-random')?.addEventListener('click', () => {
      const activeList = (displayedSigns && displayedSigns.length > 0) ? displayedSigns : allSigns;
      if (activeList.length === 0) return;
      const randIdx = Math.floor(Math.random() * activeList.length);
      const targetSign = activeList[randIdx];
      if (selectEl) selectEl.value = targetSign;
      playSign(targetSign);
    });

    document.getElementById('phase3-save-review')?.addEventListener('click', savePhase3Review);
    document.getElementById('phase3-next-pending')?.addEventListener('click', goToNextPhase3Pending);
    document.getElementById('phase3-export-reviews')?.addEventListener('click', () => exportPhase3ReviewsData(phase3Reviews));
    document.getElementById('phase3-sample-sign')?.addEventListener('change', (event) => {
      const sign = event.target.value;
      if (sign) playSign(sign);
    });

    document.getElementById('btn-verify-sign')?.addEventListener('click', () => {
      if (!currentSignName) return;
      if (verifiedSigns.has(currentSignName)) verifiedSigns.delete(currentSignName);
      else verifiedSigns.add(currentSignName);
      try {
        localStorage.setItem('lsec_verified_signs_set', JSON.stringify(Array.from(verifiedSigns)));
      } catch (e) {
        console.warn(e);
      }
      updateVerifyButtonState(currentSignName);
      updateVerificationBadge();
      renderSignOptions(displayedSigns, displayedItems);
    });

    document.getElementById('nav-btn-v27')?.addEventListener('click', () => setPreferredVersion('2.7'));
    document.getElementById('nav-btn-v26')?.addEventListener('click', () => setPreferredVersion('2.6'));
    document.getElementById('nav-btn-v25')?.addEventListener('click', () => setPreferredVersion('2.5'));
    document.getElementById('nav-btn-toggle-version')?.addEventListener('click', () => setPreferredVersion(getNextVersion(preferredVersion)));
    document.getElementById('card-btn-v27')?.addEventListener('click', () => setPreferredVersion('2.7'));
    document.getElementById('card-btn-v26')?.addEventListener('click', () => setPreferredVersion('2.6'));
    document.getElementById('card-btn-v25')?.addEventListener('click', () => setPreferredVersion('2.5'));
    document.getElementById('btn-toggle-pipeline-version')?.addEventListener('click', () => setPreferredVersion(getNextVersion(preferredVersion)));
    document.getElementById('hud-pipeline-badge')?.addEventListener('click', () => setPreferredVersion(getNextVersion(preferredVersion)));

    document.getElementById('btn-reset-cm-filters')?.addEventListener('click', () => {
      activeCmFilter = '';
      activeVariantFilter = '';
      activeAlfaFilter = '';
      const alfaSel = document.getElementById('select-filter-alfa');
      if (alfaSel) alfaSel.value = '';
      renderCmExplorer();
      applySignFilters(true);
    });

    document.getElementById('select-filter-alfa')?.addEventListener('change', (e) => {
      activeAlfaFilter = e.target.value || '';
      renderCmExplorer();
      applySignFilters(true);
    });

    document.getElementById('select-sort-order')?.addEventListener('change', (e) => {
      activeSortOrder = e.target.value || 'catalog';
      applySignFilters(false);
    });

    document.getElementById('btn-open-cm-sheet-drawer')?.addEventListener('click', () => {
      const cfg = activeCmFilter ? handshapesById[activeCmFilter] : null;
      if (cfg && cfg.sheet_url) openLightbox(cfg.sheet_url, `${cfg.name} — Lámina Oficial Completa (${cfg.total_signs} señas)`);
    });

    document.getElementById('active-cm-thumb-box')?.addEventListener('click', () => {
      if (!activeSignCmMeta) return;
      if (activeSignCmMeta.variantImgUrl) {
        openLightbox(activeSignCmMeta.variantImgUrl, `${activeSignCmMeta.cmName} · Sub-variante ${activeSignCmMeta.variantLabel}`);
      } else if (activeSignCmMeta.sheetUrl) {
        openLightbox(activeSignCmMeta.sheetUrl, activeSignCmMeta.cmName);
      }
    });

    document.getElementById('btn-active-cm-open-sheet')?.addEventListener('click', () => {
      if (activeSignCmMeta?.sheetUrl) openLightbox(activeSignCmMeta.sheetUrl, `${activeSignCmMeta.cmName} — Lámina Oficial Completa`);
    });
    document.getElementById('btn-uhd-open-cm-sheet')?.addEventListener('click', () => {
      if (activeSignCmMeta?.sheetUrl) openLightbox(activeSignCmMeta.sheetUrl, `${activeSignCmMeta.cmName} — Lámina Oficial Completa`);
    });
    document.getElementById('btn-active-cm-filter-variant')?.addEventListener('click', () => {
      if (!activeSignCmMeta) return;
      activeCmFilter = activeSignCmMeta.cmId;
      activeVariantFilter = activeSignCmMeta.cmId.endsWith('*') ? '' : activeSignCmMeta.variantId;
      renderCmExplorer();
      applySignFilters(false);
    });

    const videoEl = document.getElementById('avatar-uhd-video');
    const btnUhdPlay = document.getElementById('btn-uhd-toggle-play');
    const playBtnText = document.getElementById('uhd-play-btn-text');

    btnUhdPlay?.addEventListener('click', () => {
      if (!videoEl) return;
      if (videoEl.paused) {
        videoEl.play();
        if (playBtnText) playBtnText.textContent = '⏸ Pausa';
      } else {
        videoEl.pause();
        if (playBtnText) playBtnText.textContent = '▶ Play';
      }
    });

    document.getElementById('btn-uhd-step-prev')?.addEventListener('click', () => {
      if (videoEl) {
        videoEl.pause();
        videoEl.currentTime = Math.max(0, videoEl.currentTime - (1 / 60));
        if (document.getElementById('chk-sync-playback')?.checked && window.avatarController) {
          window.avatarController.pause();
          window.avatarController.seek(videoEl.currentTime);
        }
      }
    });
    document.getElementById('btn-uhd-step-next')?.addEventListener('click', () => {
      if (videoEl) {
        videoEl.pause();
        videoEl.currentTime = Math.min(videoEl.duration || 10, videoEl.currentTime + (1 / 60));
        if (document.getElementById('chk-sync-playback')?.checked && window.avatarController) {
          window.avatarController.pause();
          window.avatarController.seek(videoEl.currentTime);
        }
      }
    });
    document.getElementById('btn-uhd-mute')?.addEventListener('click', () => {
      if (!videoEl) return;
      videoEl.muted = !videoEl.muted;
      const lbl = document.getElementById('uhd-mute-label');
      if (lbl) lbl.textContent = videoEl.muted ? '🔇' : '🔊';
    });
    document.getElementById('btn-uhd-fullscreen')?.addEventListener('click', () => {
      if (videoEl?.requestFullscreen) videoEl.requestFullscreen();
    });

    const illBox = document.getElementById('illustration-img-box');
    const overlayImg = document.getElementById('uhd-illustration-overlay-img');
    const btnToggleUhdIll = document.getElementById('btn-toggle-uhd-illustration');
    const btnCloseUhdIll = document.getElementById('btn-close-uhd-illustration');
    const btnExpandUhdIll = document.getElementById('btn-expand-uhd-illustration');
    const btnCloseLightbox = document.getElementById('btn-close-lightbox');
    const lightboxModal = document.getElementById('illustration-lightbox');

    illBox?.addEventListener('click', () => { if (currentIllustrationUrl) openLightbox(currentIllustrationUrl); });
    overlayImg?.addEventListener('click', () => { if (currentIllustrationUrl) openLightbox(currentIllustrationUrl); });
    btnExpandUhdIll?.addEventListener('click', () => { if (currentIllustrationUrl) openLightbox(currentIllustrationUrl); });
    btnToggleUhdIll?.addEventListener('click', toggleUhdIllustration);
    btnCloseUhdIll?.addEventListener('click', hideUhdIllustration);
    btnCloseLightbox?.addEventListener('click', closeLightbox);
    lightboxModal?.addEventListener('click', (e) => { if (e.target === lightboxModal) closeLightbox(); });

    const btnPlay = document.getElementById('btn-avatar-play');
    const btnPause = document.getElementById('btn-avatar-pause');
    const btnReset = document.getElementById('btn-avatar-reset');
    const speedSelect = document.getElementById('select-avatar-speed');
    const syncChk = document.getElementById('chk-sync-playback');

    btnPlay?.addEventListener('click', () => {
      if (syncChk?.checked && videoEl?.src) {
        videoEl.currentTime = 0;
        videoEl.playbackRate = parseFloat(speedSelect?.value || '1');
        videoEl.play().catch(() => {});
      }
    });
    btnPause?.addEventListener('click', () => { if (syncChk?.checked && videoEl) videoEl.pause(); });
    btnReset?.addEventListener('click', () => {
      if (syncChk?.checked && videoEl) {
        videoEl.pause();
        videoEl.currentTime = 0;
      }
    });
    speedSelect?.addEventListener('change', (e) => {
      if (videoEl) videoEl.playbackRate = parseFloat(e.target.value);
    });

    window.addEventListener('keydown', (e) => {
      const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
      if (activeTag === 'input' || activeTag === 'textarea') return;
      if (e.key === 'ArrowRight') { e.preventDefault(); navigateSign(1); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); navigateSign(-1); }
      else if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        if (videoEl && !videoEl.paused) btnPause?.click();
        else btnPlay?.click();
      } else if (e.key === 'r' || e.key === 'R') { e.preventDefault(); btnReset?.click(); }
      else if (e.key === 'v' || e.key === 'V') { e.preventDefault(); setPreferredVersion(getNextVersion(preferredVersion)); }
      else if (e.key === 'c' || e.key === 'C') { e.preventDefault(); toggleCompBtn?.click(); }
      else if (e.key === 'i' || e.key === 'I') { e.preventDefault(); toggleUhdIllustration(); }
      else if (e.key === 'Escape') { closeLightbox(); hideUhdIllustration(); }
    });

    const searchInput = document.getElementById('input-search-sign');
    searchInput?.addEventListener('input', () => {
      applySignFilters(false);
      if (displayedSigns.length > 0 && selectEl) selectEl.value = displayedSigns[0];
    });

    try {
      await loadPhase3Sample();
      const [listRes, hsRes] = await Promise.all([
        fetch('/api/v1/animations/list?limit=6000'),
        fetch('/api/v1/animations/handshapes'),
      ]);

      if (hsRes.ok) {
        handshapesCatalog = await hsRes.json();
        handshapesById = {};
        (handshapesCatalog.configurations || []).forEach(c => { handshapesById[c.id] = c; });
      }

      if (listRes.ok) {
        const data = await listRes.json();
        const rawSigns = data.signs || [];
        const rawItems = data.items || [];
        const seenInitNfc = new Set();
        allSigns = [];
        allItems = [];
        rawSigns.forEach((s, idx) => {
          if (!s) return;
          const nfcSign = String(s).normalize('NFC').trim();
          if (!nfcSign || seenInitNfc.has(nfcSign)) return;
          seenInitNfc.add(nfcSign);
          allSigns.push(nfcSign);
          const it = rawItems[idx] ? { ...rawItems[idx], sign: nfcSign } : { sign: nfcSign };
          if (it.palabra) it.palabra = String(it.palabra).normalize('NFC').trim();
          allItems.push(it);
        });
        displayedSigns = [...allSigns];
        displayedItems = [...allItems];

        const badge = document.getElementById('sign-count-badge');
        if (badge) badge.textContent = `${allSigns.length.toLocaleString()} Señas`;

        renderCmExplorer();
        updateVerificationBadge();
        renderSignOptions(allSigns, allItems);

        const defaultSign = allSigns.find(s => s === '¡Quieto!') ||
                            allSigns.find(s => s.toLowerCase() === '¡quieto!') ||
                            allSigns[0];
        if (defaultSign) {
          if (selectEl) selectEl.value = defaultSign;
          setTimeout(() => playSign(defaultSign), 1000);
        }
      }
    } catch (err) {
      console.error('Error al obtener lista de animaciones y configuraciones manuales:', err);
    }
  } catch (err) {
    console.error('Error inicializando /avatarconfig:', err);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAvatarConfig);
} else {
  initAvatarConfig();
}
