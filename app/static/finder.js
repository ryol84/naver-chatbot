(() => {
  const state = {
    lat: null,
    lng: null,
    label: null,
    symptom: null,
    severity: "moderate",
    need24h: false,
    busy: false,
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const locStatus = $("#loc-status");
  const resultsSub = $("#results-sub");
  const resultsList = $("#results-list");

  function setActive(groupSel, el) {
    $$(groupSel).forEach((n) => n.classList.remove("active"));
    if (el) el.classList.add("active");
  }

  function setLocation(lat, lng, label) {
    state.lat = lat;
    state.lng = lng;
    state.label = label;
    locStatus.textContent = label
      ? `기준 위치: ${label} (${lat.toFixed(4)}, ${lng.toFixed(4)})`
      : `기준 위치: ${lat.toFixed(4)}, ${lng.toFixed(4)}`;
    maybeSearch();
  }

  function useGeolocation() {
    if (!navigator.geolocation) {
      locStatus.textContent = "이 브라우저는 위치 정보를 지원하지 않아요. 아래 지역을 골라 주세요.";
      return;
    }
    locStatus.textContent = "위치를 확인하는 중…";
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocation(pos.coords.latitude, pos.coords.longitude, "현재 위치");
        setActive(".chip.city", null);
      },
      () => {
        locStatus.textContent = "위치를 얻지 못했어요. 주요 지역 버튼을 눌러 주세요.";
      },
      { enableHighAccuracy: true, timeout: 12000 }
    );
  }

  async function maybeSearch() {
    if (state.lat == null || state.lng == null) return;
    if (!state.symptom) {
      resultsSub.textContent = "아픈 부위를 고르면 검색을 시작합니다.";
      return;
    }
    if (state.busy) return;
    state.busy = true;
    resultsList.innerHTML = `<p class="loading">근처 병원을 찾는 중…</p>`;
    resultsSub.textContent = "조건에 맞는 병원을 정렬하고 있어요.";

    const params = new URLSearchParams({
      lat: String(state.lat),
      lng: String(state.lng),
      symptom: state.symptom,
      severity: state.severity || "moderate",
      need_24h: String(state.need24h),
      limit: "15",
    });

    try {
      const res = await fetch(`/api/hospitals/nearby?${params.toString()}`);
      const data = await res.json();
      renderResults(data);
    } catch (err) {
      resultsList.innerHTML = `<p class="empty">검색에 실패했어요. 잠시 후 다시 시도해 주세요.</p>`;
      resultsSub.textContent = String(err);
    } finally {
      state.busy = false;
    }
  }

  function renderResults(data) {
    const hospitals = data.hospitals || [];
    const f = data.filters || {};
    const bits = [];
    if (state.label) bits.push(state.label);
    bits.push(`반경 ${f.radius_km}km`);
    if (f.need_24h) bits.push("24시만");
    if (f.relaxed) bits.push("조건 완화 결과");
    resultsSub.textContent = hospitals.length
      ? `${hospitals.length}곳 · ${bits.join(" · ")}`
      : `조건에 맞는 병원이 없어요. 반경을 넓히거나 24시 조건을 풀어 보세요.`;

    if (!hospitals.length) {
      resultsList.innerHTML = `<p class="empty">결과가 없습니다.</p>`;
      return;
    }

    resultsList.innerHTML = hospitals
      .map((h, i) => {
        const badges = [
          h.care_level_ko ? `<span class="badge">${escapeHtml(h.care_level_ko)}</span>` : "",
          h.hours_24h === "yes" ? `<span class="badge hot">24시</span>` : "",
          (h.departments || []).includes("응급") ? `<span class="badge hot">응급</span>` : "",
          h.department_match ? `<span class="badge">증상 관련</span>` : "",
        ]
          .filter(Boolean)
          .join("");

        const phone = h.phone
          ? `<a class="call" href="tel:${escapeAttr(h.phone)}">전화 ${escapeHtml(h.phone)}</a>`
          : "";
        const map =
          h.daum_map_url ||
          `https://map.kakao.com/link/map/${encodeURIComponent(h.name)},${h.lat},${h.lng}`;
        const place = h.place_search_url
          ? `<a href="${escapeAttr(h.place_search_url)}" target="_blank" rel="noopener">검색</a>`
          : "";

        return `
          <article class="hospital" style="animation-delay:${i * 45}ms">
            <div class="hospital-top">
              <h3 class="hospital-name">${escapeHtml(h.name)}</h3>
              <span class="hospital-dist">${h.distance_km} km</span>
            </div>
            <div class="badges">${badges}</div>
            <p class="hospital-addr">${escapeHtml(h.address || "")}</p>
            <div class="hospital-actions">
              ${phone}
              <a href="${escapeAttr(map)}" target="_blank" rel="noopener">지도</a>
              ${place}
            </div>
          </article>
        `;
      })
      .join("");

    $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
  }

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

  function hydrate(options) {
    const stats = options.stats || {};
    $("#hero-meta").textContent =
      `전국 동반동물 병원 ${stats.total_with_coords ?? "—"}곳 · 24시 표기 ${stats.hours_24h_yes ?? "—"}곳`;

    const cityWrap = $("#city-chips");
    cityWrap.innerHTML = (options.cities || [])
      .map(
        (c) =>
          `<button type="button" class="chip city" data-lat="${c.lat}" data-lng="${c.lng}" data-label="${escapeAttr(c.label)}">${escapeHtml(c.label)}</button>`
      )
      .join("");

    const symptomWrap = $("#symptom-grid");
    symptomWrap.innerHTML = (options.symptoms || [])
      .map(
        (s) => `
        <button type="button" class="symptom" data-symptom="${escapeAttr(s.id)}">
          <span class="symptom-label">${escapeHtml(s.label)}</span>
          <span class="symptom-hint">${escapeHtml(s.hint)}</span>
        </button>`
      )
      .join("");

    const severityWrap = $("#severity-grid");
    severityWrap.innerHTML = (options.severities || [])
      .map(
        (s) => `
        <button type="button" class="severity" data-severity="${escapeAttr(s.id)}">
          <span class="severity-label">${escapeHtml(s.label)}</span>
          <span class="severity-hint">${escapeHtml(s.hint)}</span>
        </button>`
      )
      .join("");

    $$(".chip.city").forEach((btn) => {
      btn.addEventListener("click", () => {
        setActive(".chip.city", btn);
        setLocation(Number(btn.dataset.lat), Number(btn.dataset.lng), btn.dataset.label);
      });
    });

    $$(".symptom").forEach((btn) => {
      btn.addEventListener("click", () => {
        setActive(".symptom", btn);
        state.symptom = btn.dataset.symptom;
        maybeSearch();
      });
    });

    $$(".severity").forEach((btn) => {
      btn.addEventListener("click", () => {
        setActive(".severity", btn);
        state.severity = btn.dataset.severity;
        maybeSearch();
      });
    });

    const defaultSeverity = $(`.severity[data-severity="moderate"]`);
    if (defaultSeverity) defaultSeverity.classList.add("active");
  }

  $("#btn-geo")?.addEventListener("click", useGeolocation);
  $("#btn-geo-2")?.addEventListener("click", useGeolocation);
  $("#btn-scroll-triage")?.addEventListener("click", () => {
    $("#triage")?.scrollIntoView({ behavior: "smooth" });
  });

  const btn24 = $("#btn-24h");
  btn24?.addEventListener("click", () => {
    state.need24h = !state.need24h;
    btn24.setAttribute("aria-pressed", String(state.need24h));
    maybeSearch();
  });

  fetch("/api/triage/options")
    .then((r) => r.json())
    .then(hydrate)
    .catch(() => {
      $("#hero-meta").textContent = "옵션을 불러오지 못했어요. 새로고침 해 주세요.";
    });
})();
