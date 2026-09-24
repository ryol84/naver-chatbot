(() => {
  const state = {
    lat: null,
    lng: null,
    label: null,
    symptom: null,
    need24h: false,
    needEmergency: false,
    careLevels: new Set(["university", "secondary", "primary", "neighborhood"]),
    radiusKm: 8,
    busy: false,
    hospitals: [],
    featured: [],
    selectedId: null,
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const locStatus = $("#loc-status");
  const resultsList = $("#results-list");
  const featuredWrap = $("#featured-wrap");
  const featuredList = $("#featured-list");
  const countLabel = $("#count-label");
  const mapHint = $("#map-hint");
  const radiusInput = $("#radius");
  const radiusLabel = $("#radius-label");

  let map = null;
  let userMarker = null;
  let hospitalLayer = null;
  let markersById = new Map();

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  function initMap() {
    map = L.map("map", {
      zoomControl: true,
      attributionControl: true,
    }).setView([37.5665, 126.978], 12);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    }).addTo(map);

    hospitalLayer = L.layerGroup().addTo(map);

    map.on("click", (e) => {
      setLocation(e.latlng.lat, e.latlng.lng, "지도에서 지정");
      setActive(".chip.city", null);
      if (mapHint) mapHint.classList.add("hidden");
    });

    setTimeout(() => map.invalidateSize(), 80);
  }

  function userIcon() {
    return L.divIcon({
      className: "pin-user",
      html: '<div class="user-pin"></div>',
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    });
  }

  function hospitalIcon(h) {
    const hot = h.is_24h || h.is_emergency || h.is_emergency_surgery;
    const letter = hot ? "!" : "H";
    return L.divIcon({
      className: "pin-user",
      html: `<div class="hospital-pin${hot ? " hot" : ""}"><span>${letter}</span></div>`,
      iconSize: hot ? [32, 32] : [28, 28],
      iconAnchor: hot ? [16, 28] : [14, 24],
      popupAnchor: [0, -22],
    });
  }

  function setActive(groupSel, el) {
    $$(groupSel).forEach((n) => n.classList.remove("active"));
    if (el) el.classList.add("active");
  }

  function setLocation(lat, lng, label) {
    state.lat = lat;
    state.lng = lng;
    state.label = label;
    locStatus.textContent = label
      ? `${label} · ${lat.toFixed(4)}, ${lng.toFixed(4)}`
      : `${lat.toFixed(4)}, ${lng.toFixed(4)}`;

    if (userMarker) {
      userMarker.setLatLng([lat, lng]);
    } else {
      userMarker = L.marker([lat, lng], { icon: userIcon(), zIndexOffset: 1000 }).addTo(map);
      userMarker.bindPopup("기준 위치");
    }
    map.setView([lat, lng], Math.max(map.getZoom(), 12), { animate: true });
    maybeSearch();
  }

  function useGeolocation() {
    if (!navigator.geolocation) {
      locStatus.textContent = "GPS를 쓸 수 없어요. 지도를 클릭하거나 지역을 골라 주세요.";
      return;
    }
    locStatus.textContent = "GPS 확인 중…";
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocation(pos.coords.latitude, pos.coords.longitude, "내 위치");
        setActive(".chip.city", null);
        if (mapHint) mapHint.classList.add("hidden");
      },
      () => {
        locStatus.textContent = "위치를 얻지 못했어요. 지도를 클릭하거나 지역을 골라 주세요.";
      },
      { enableHighAccuracy: true, timeout: 12000 }
    );
  }

  async function maybeSearch() {
    if (state.lat == null || state.lng == null) return;
    if (state.busy) return;
    state.busy = true;
    resultsList.innerHTML = `<p class="loading">근처 병원을 찾는 중…</p>`;
    if (countLabel) countLabel.textContent = "";

    const params = new URLSearchParams({
      lat: String(state.lat),
      lng: String(state.lng),
      need_24h: String(state.need24h),
      need_emergency: String(state.needEmergency),
      radius_km: String(state.radiusKm),
      limit: "50",
    });
    if (state.careLevels.size && state.careLevels.size < 4) {
      params.set("care_levels", Array.from(state.careLevels).join(","));
    }
    if (state.symptom) params.set("symptom", state.symptom);

    try {
      const res = await fetch(`/api/hospitals/nearby?${params.toString()}`);
      const data = await res.json();
      state.hospitals = data.hospitals || [];
      state.featured = data.featured || [];
      renderResults(data);
      renderMarkers(state.hospitals);
    } catch (err) {
      resultsList.innerHTML = `<p class="empty">검색에 실패했어요. 잠시 후 다시 시도해 주세요.</p>`;
      featuredWrap.hidden = true;
    } finally {
      state.busy = false;
    }
  }

  function badgeHtml(h) {
    const badges = [];
    if (h.care_level_short || h.care_level_ko) {
      badges.push(`<span class="badge">${escapeHtml(h.care_level_short || h.care_level_ko)}</span>`);
    }
    if (h.is_24h) badges.push(`<span class="badge hot">24시</span>`);
    if (h.is_emergency_surgery) badges.push(`<span class="badge hot">응급수술</span>`);
    else if (h.is_emergency) badges.push(`<span class="badge hot">응급</span>`);
    (h.equipment || []).slice(0, 4).forEach((e) => {
      badges.push(`<span class="badge equip">${escapeHtml(e)}</span>`);
    });
    return badges.join("");
  }

  function deptsLine(h) {
    const deps = (h.departments || []).slice(0, 6);
    if (!deps.length) return "";
    return `<p class="hospital-meta">진료: ${escapeHtml(deps.join(" · "))}</p>`;
  }

  function equipLine(h) {
    const eq = h.equipment || [];
    if (!eq.length) return "";
    return `<p class="hospital-meta">장비: ${escapeHtml(eq.slice(0, 5).join(", "))}</p>`;
  }

  function hoursBlock(h) {
    const hours = h.hours;
    if (hours && Array.isArray(hours.lines) && hours.lines.length) {
      const cls = hours.is_24h ? "hours-block hot" : hours.unknown ? "hours-block muted" : "hours-block";
      const rows = hours.lines
        .map((line) => `<li>${escapeHtml(line)}</li>`)
        .join("");
      return `<div class="${cls}"><p class="hours-label">영업시간</p><ul>${rows}</ul></div>`;
    }
    // fallback for older payloads
    if (h.is_24h || h.hours_24h === "yes") {
      return `<div class="hours-block hot"><p class="hours-label">영업시간</p><ul><li>24시간 영업</li></ul></div>`;
    }
    const parts = [];
    if (h.weekday_hours) parts.push(`평일 ${h.weekday_hours}`);
    if (h.weekend_hours) parts.push(h.weekend_hours);
    if (!parts.length) {
      return `<div class="hours-block muted"><p class="hours-label">영업시간</p><ul><li>정보 없음</li></ul></div>`;
    }
    return `<div class="hours-block"><p class="hours-label">영업시간</p><ul>${parts
      .map((p) => `<li>${escapeHtml(p)}</li>`)
      .join("")}</ul></div>`;
  }

  function actionsHtml(h) {
    const phone = h.phone
      ? `<a class="call" href="tel:${escapeAttr(h.phone)}" onclick="event.stopPropagation()">전화</a>`
      : "";
    const mapUrl =
      h.daum_map_url ||
      `https://map.kakao.com/link/map/${encodeURIComponent(h.name)},${h.lat},${h.lng}`;
    return `
      <div class="hospital-actions">
        ${phone}
        <a href="${escapeAttr(mapUrl)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">길찾기</a>
      </div>`;
  }

  function cardHtml(h, i, { priority = false } = {}) {
    return `
      <button type="button" class="hospital${priority ? " priority" : ""}${state.selectedId === h.id ? " selected" : ""}" data-id="${escapeAttr(h.id)}" style="animation-delay:${i * 35}ms">
        <div class="hospital-top">
          <h3 class="hospital-name">${escapeHtml(h.name)}</h3>
          <span class="hospital-dist">${h.distance_km} km</span>
        </div>
        <div class="badges">${badgeHtml(h)}</div>
        <p class="hospital-addr">${escapeHtml(h.address || "")}</p>
        ${hoursBlock(h)}
        ${deptsLine(h)}
        ${equipLine(h)}
        ${actionsHtml(h)}
      </button>`;
  }

  function bindCardClicks(root) {
    root.querySelectorAll(".hospital").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.dataset.id;
        selectHospital(id);
      });
    });
  }

  function renderResults(data) {
    const featured = data.featured || [];
    const hospitals = data.hospitals || [];
    const f = data.filters || {};
    const featuredIds = new Set(featured.map((h) => String(h.id)));
    // 24시만 위 블록 — 그 외는 아래 섹션 (응급 포함, 중복 없음)
    const rest = hospitals.filter((h) => !featuredIds.has(String(h.id)));
    const restWrap = $("#rest-wrap");

    if (countLabel) {
      const bits = [`${rest.length}곳`];
      if (featured.length) bits.unshift(`24시 ${featured.length}`);
      bits.push(`반경 ${f.radius_km}km`);
      if (f.relaxed) bits.push("조건 완화");
      countLabel.textContent = `· ${bits.join(" · ")}`;
    }

    if (featured.length) {
      featuredWrap.hidden = false;
      featuredList.innerHTML = featured.map((h, i) => cardHtml(h, i, { priority: true })).join("");
      bindCardClicks(featuredList);
    } else {
      featuredWrap.hidden = true;
      featuredList.innerHTML = "";
    }

    if (!hospitals.length) {
      if (restWrap) restWrap.hidden = false;
      resultsList.innerHTML = `<p class="empty">이 반경에 병원이 없어요. 지도를 옮기거나 반경을 넓혀 보세요.</p>`;
      return;
    }

    if (!rest.length) {
      if (restWrap) restWrap.hidden = true;
      resultsList.innerHTML = "";
      return;
    }

    if (restWrap) restWrap.hidden = false;
    resultsList.innerHTML = rest.map((h, i) => cardHtml(h, i)).join("");
    bindCardClicks(resultsList);
  }
  function renderMarkers(hospitals) {
    hospitalLayer.clearLayers();
    markersById = new Map();
    if (!hospitals.length) return;

    const bounds = [];
    if (state.lat != null) bounds.push([state.lat, state.lng]);

    hospitals.forEach((h) => {
      if (h.lat == null || h.lng == null) return;
      const m = L.marker([h.lat, h.lng], {
        icon: hospitalIcon(h),
        zIndexOffset: h.is_24h || h.is_emergency ? 400 : 200,
      });
      const popup = `
        <div class="popup-card">
          <h3>${escapeHtml(h.name)}</h3>
          <div class="badges">${badgeHtml(h)}</div>
          <p>${escapeHtml(h.address || "")}</p>
          ${hoursBlock(h)}
          ${deptsLine(h)}
          ${equipLine(h)}
          <p>${h.distance_km} km</p>
        </div>`;
      m.bindPopup(popup, { maxWidth: 280 });
      m.on("click", () => selectHospital(h.id, { fromMap: true }));
      m.addTo(hospitalLayer);
      markersById.set(h.id, m);
      bounds.push([h.lat, h.lng]);
    });

    if (bounds.length > 1) {
      try {
        map.fitBounds(bounds, { padding: [36, 36], maxZoom: 14 });
      } catch (_) {
        /* ignore */
      }
    }
  }

  function selectHospital(id, { fromMap = false } = {}) {
    state.selectedId = id;
    $$(".hospital").forEach((el) => {
      el.classList.toggle("selected", el.dataset.id === id);
    });
    const marker = markersById.get(id);
    if (marker) {
      if (!fromMap) {
        map.panTo(marker.getLatLng(), { animate: true });
      }
      marker.openPopup();
    }
    const card = document.querySelector(`.hospital[data-id="${CSS.escape(id)}"]`);
    if (card && !fromMap) {
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function hydrate(options) {
    const cityWrap = $("#city-chips");
    cityWrap.innerHTML = (options.cities || [])
      .map(
        (c) =>
          `<button type="button" class="chip city" data-lat="${c.lat}" data-lng="${c.lng}" data-label="${escapeAttr(c.label)}">${escapeHtml(c.label)}</button>`
      )
      .join("");

    const careWrap = $("#care-chips");
    careWrap.innerHTML = (options.care_levels || [])
      .map(
        (c) =>
          `<button type="button" class="chip care active" data-care="${escapeAttr(c.id)}" aria-pressed="true">${escapeHtml(c.label)}</button>`
      )
      .join("");

    const symptomWrap = $("#symptom-chips");
    symptomWrap.innerHTML =
      `<button type="button" class="chip symptom active" data-symptom="" aria-pressed="true">전체</button>` +
      (options.symptoms || [])
        .filter((s) => s.id !== "unknown")
        .map(
          (s) =>
            `<button type="button" class="chip symptom" data-symptom="${escapeAttr(s.id)}" aria-pressed="false">${escapeHtml(s.label)}</button>`
        )
        .join("");

    $$(".chip.city").forEach((btn) => {
      btn.addEventListener("click", () => {
        setActive(".chip.city", btn);
        setLocation(Number(btn.dataset.lat), Number(btn.dataset.lng), btn.dataset.label);
        if (mapHint) mapHint.classList.add("hidden");
      });
    });

    $$(".chip.care").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.dataset.care;
        const on = btn.getAttribute("aria-pressed") !== "true";
        btn.setAttribute("aria-pressed", String(on));
        btn.classList.toggle("active", on);
        if (on) state.careLevels.add(id);
        else state.careLevels.delete(id);
        if (state.careLevels.size === 0) {
          // keep at least one so results aren't empty by accident
          state.careLevels.add(id);
          btn.setAttribute("aria-pressed", "true");
          btn.classList.add("active");
        }
        maybeSearch();
      });
    });

    $$(".chip.symptom").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$(".chip.symptom").forEach((n) => {
          n.classList.remove("active");
          n.setAttribute("aria-pressed", "false");
        });
        btn.classList.add("active");
        btn.setAttribute("aria-pressed", "true");
        state.symptom = btn.dataset.symptom || null;
        maybeSearch();
      });
    });
  }

  $("#btn-geo")?.addEventListener("click", useGeolocation);

  const careGuide = $("#care-guide");
  const btnCareHelp = $("#btn-care-help");
  btnCareHelp?.addEventListener("click", () => {
    if (!careGuide) return;
    const open = careGuide.hasAttribute("hidden");
    if (open) careGuide.removeAttribute("hidden");
    else careGuide.setAttribute("hidden", "");
    btnCareHelp.setAttribute("aria-expanded", String(open));
    btnCareHelp.textContent = open ? "등급 안내 닫기" : "등급 안내";
  });

  const btn24 = $("#btn-24h");
  btn24?.addEventListener("click", () => {
    state.need24h = !state.need24h;
    btn24.setAttribute("aria-pressed", String(state.need24h));
    btn24.classList.toggle("active", state.need24h);
    maybeSearch();
  });

  const btnEr = $("#btn-er");
  btnEr?.addEventListener("click", () => {
    state.needEmergency = !state.needEmergency;
    btnEr.setAttribute("aria-pressed", String(state.needEmergency));
    btnEr.classList.toggle("active", state.needEmergency);
    maybeSearch();
  });

  radiusInput?.addEventListener("input", () => {
    state.radiusKm = Number(radiusInput.value);
    if (radiusLabel) radiusLabel.textContent = String(state.radiusKm);
  });
  radiusInput?.addEventListener("change", () => {
    state.radiusKm = Number(radiusInput.value);
    maybeSearch();
  });

  initMap();

  fetch("/api/triage/options")
    .then((r) => r.json())
    .then((options) => {
      hydrate(options);
      // Default: Seoul City Hall so map isn't empty before GPS
      const seoul = (options.cities || []).find((c) => /서울/.test(c.label));
      if (seoul) {
        setLocation(seoul.lat, seoul.lng, seoul.label);
        const chip = $(`.chip.city[data-label="${CSS.escape(seoul.label)}"]`);
        if (chip) setActive(".chip.city", chip);
      }
    })
    .catch(() => {
      locStatus.textContent = "옵션을 불러오지 못했어요. 새로고침 해 주세요.";
    });
})();
