<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useMapStore } from "@/stores/map.store";
import type { MapCountry } from "@/types";

const store = useMapStore();

// --- Controale ---
const model = ref("sir");
const language = ref("python");
const layer = ref<"observed" | "simulated" | "diff">("observed");
// Index zilnic, calculat din date.
const dayIdx = ref(0);

async function reload() {
  await store.fetch(model.value, language.value);
  dayIdx.value = Math.floor((nDays.value - 1) * 0.4); // poziție implicită
  refreshLayer();
}
onMounted(reload);
watch([model, language], reload);

// --- Bounds temporal ---
const minDate = computed(() => store.data?.global_min_day ?? null);
const maxDate = computed(() => store.data?.global_max_day ?? null);
function diffDays(a: string, b: string): number {
  return Math.round(
    (new Date(b).getTime() - new Date(a).getTime()) / (1000 * 60 * 60 * 24),
  );
}
const nDays = computed(() => {
  if (!minDate.value || !maxDate.value) return 0;
  return diffDays(minDate.value, maxDate.value) + 1;
});
const currentDate = computed(() => {
  if (!minDate.value) return "";
  const d = new Date(minDate.value);
  d.setDate(d.getDate() + dayIdx.value);
  return d.toISOString().slice(0, 10);
});

// Cate tari au simulated populat. Daca e 0, banner-ul de avertizare apare.
const simulatedCount = computed(() => {
  return store.data?.countries.filter((c) => c.simulated && c.simulated.values.length > 0).length ?? 0;
});

const observedCount = computed(() => store.data?.countries.length ?? 0);

const legend = computed(() => buildLegend(layer.value));

// Lista de simulări efectiv afișate, sortată alfabetic. Folosită în panoul
// „Simulări folosite". Click pe rând → pagina de detaliu a simulării.
const usedSims = computed(() => {
  return (store.data?.countries ?? [])
    .filter((c) => c.simulation)
    .map((c) => ({
      country: c.name || c.iso3,
      iso3: c.iso3,
      sim: c.simulation!,
    }))
    .sort((a, b) => a.country.localeCompare(b.country));
});

// Toate simulările folosesc același t_max? Dacă da, afișăm o singură valoare
// în titlul panoului în loc să o repetăm pe fiecare rând.
const commonTMax = computed(() => {
  const set = new Set(usedSims.value.map((s) => s.sim.t_max));
  return set.size === 1 ? [...set][0] : null;
});

function fmtDate(s: string): string {
  return new Date(s).toLocaleDateString("ro-RO", {
    day: "2-digit", month: "2-digit", year: "numeric",
  });
}

function fmtTime(s: string): string {
  return new Date(s).toLocaleTimeString("ro-RO", {
    hour: "2-digit", minute: "2-digit",
  });
}

// --- Lookup: valoare per țară la data curentă ---
function valueFor(c: MapCountry, kind: "observed" | "simulated"): number | null {
  const s = kind === "observed" ? c.observed : c.simulated;
  if (!s) return null;
  const idx = diffDays(s.start_date, currentDate.value);
  if (idx < 0 || idx >= s.values.length) return null;
  return s.values[idx];
}

function per100k(v: number, pop: number): number {
  return pop > 0 ? (v * 1e5) / pop : 0;
}

// --- Color scale ---
// Sequential pentru observed/simulated: YlOrRd (galben pal -> rosu inchis).
// Diverging pentru diff: albastru -> alb -> rosu.
// Transformare log pe rata (per 100k) pentru ca distributia e skewed.

const SEQ_STOPS: Array<[number, number, number]> = [
  [255, 255, 204], // #ffffcc galben pal
  [255, 237, 160], // #ffeda0
  [254, 217, 118], // #fed976
  [254, 178, 76],  // #feb24c
  [253, 141, 60],  // #fd8d3c
  [252, 78, 42],   // #fc4e2a
  [227, 26, 28],   // #e31a1c rosu
  [177, 0, 38],    // #b10026 rosu inchis
];

const DIV_NEG: [number, number, number] = [33, 102, 172];  // albastru saturat
const DIV_MID: [number, number, number] = [247, 247, 247]; // alb-gri
const DIV_POS: [number, number, number] = [178, 24, 43];   // rosu saturat

function lerp(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

function interpStops(stops: Array<[number, number, number]>, t: number): string {
  if (t <= 0) {
    const [r, g, b] = stops[0];
    return `rgb(${r},${g},${b})`;
  }
  if (t >= 1) {
    const [r, g, b] = stops[stops.length - 1];
    return `rgb(${r},${g},${b})`;
  }
  const pos = t * (stops.length - 1);
  const i = Math.floor(pos);
  const f = pos - i;
  const a = stops[i];
  const b = stops[i + 1];
  return `rgb(${lerp(a[0], b[0], f)},${lerp(a[1], b[1], f)},${lerp(a[2], b[2], f)})`;
}

// Scară log10 cu plafon la 5×10^4 per 100k. Astfel:
//   1/100k    → ~0.06 (galben foarte pal)
//   100/100k  → ~0.43 (portocaliu deschis)
//   1000/100k → ~0.64 (portocaliu)
//   10000/100k → ~0.85 (roșu)
//   50000/100k → 1.0 (roșu închis)
// Modelele SIR fără intervenție pot atinge 30-80k/100k la peak, deci avem
// nevoie de 5×10^4 ca să discriminăm în zona peak.
const LOG_PLAFON = 4.7; // log10(5×10^4) ≈ 4.7

function colorForRate(rate: number | null, kind: "observed" | "simulated" | "diff"): string {
  if (rate === null || isNaN(rate)) return "#e8e8e8";
  if (kind === "diff") {
    if (rate === 0) {
      const [r, g, b] = DIV_MID;
      return `rgb(${r},${g},${b})`;
    }
    const t = Math.min(Math.log10(Math.abs(rate) + 1) / LOG_PLAFON, 1);
    const target = rate > 0 ? DIV_POS : DIV_NEG;
    return `rgb(${lerp(DIV_MID[0], target[0], t)},${lerp(DIV_MID[1], target[1], t)},${lerp(DIV_MID[2], target[2], t)})`;
  }
  if (rate <= 0) return interpStops(SEQ_STOPS, 0);
  const t = Math.min(Math.log10(rate + 1) / LOG_PLAFON, 1);
  return interpStops(SEQ_STOPS, t);
}

// Generam legenda: 6-7 puncte intre 0 si 5×10^4 per 100k.
type LegendEntry = { color: string; label: string };
function buildLegend(kind: "observed" | "simulated" | "diff"): LegendEntry[] {
  if (kind === "diff") {
    const ticks = [-50000, -1000, -10, 0, 10, 1000, 50000];
    return ticks.map((v) => ({
      color: colorForRate(v, "diff"),
      label: v === 0 ? "0" : (v > 0 ? "+" : "") + formatRate(v),
    }));
  }
  const ticks = [0, 10, 100, 1000, 10000, 50000];
  return ticks.map((v) => ({
    color: colorForRate(v, "observed"),
    label: v === 0 ? "0" : formatRate(v),
  }));
}

function formatRate(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1000) return (v / 1000).toFixed(0) + "k";
  if (abs >= 1) return v.toFixed(0);
  return v.toFixed(1);
}

// --- Leaflet ---
let map: L.Map | null = null;
let geoLayer: L.GeoJSON | null = null;

// Maparea prefix ISO 3166-2 (ex "RO", "US") → geojson sub-național
// disponibil. Țările listate aici au datasets cu rezoluție sub-națională.
const SUBNATIONAL_GEOJSONS: Record<string, string> = {
  RO: "/geo/romania-counties.geojson",
  US: "/geo/usa-subnational.geojson",
  CN: "/geo/china-subnational.geojson",
  CA: "/geo/canada-subnational.geojson",
  AU: "/geo/australia-subnational.geojson",
};

// Detectăm prefixul comun al codurilor de regiune din datele studiului.
// Dacă toate au formă <CC>-<...> și <CC> e în lista cu sub-național,
// folosim geojson-ul țării. Altfel, harta lume.
const subdivisionLevel = computed<string>(() => {
  const list = store.data?.countries ?? [];
  if (list.length === 0) return "national";
  const prefixes = new Set<string>();
  for (const c of list) {
    const m = c.iso3.match(/^([A-Z]{2})-[A-Z0-9]{1,3}$/);
    if (!m) return "national"; // există coduri care nu sunt sub-naționale
    prefixes.add(m[1]);
  }
  if (prefixes.size !== 1) return "national";
  const cc = [...prefixes][0];
  return SUBNATIONAL_GEOJSONS[cc] ? `sub-${cc.toLowerCase()}` : "national";
});

const geoFilePath = computed(() => {
  const level = subdivisionLevel.value;
  if (level.startsWith("sub-")) {
    const cc = level.slice(4).toUpperCase();
    return SUBNATIONAL_GEOJSONS[cc] ?? "/geo/world-110m.geojson";
  }
  return "/geo/world-110m.geojson";
});

// Returnează true dacă suntem pe orice nivel sub-național (oricare țară).
const isSubnational = computed(() => subdivisionLevel.value.startsWith("sub-"));

// Codurile ISO3 (țări) sau ISO 3166-2 (județe) — citim din proprietățile
// feature-ului. NaturalEarth folosește ISO_A3, fișierul de județe COUNTY_CODE.
function isoFromFeature(feature?: GeoJSON.Feature): string | undefined {
  const props = feature?.properties as Record<string, unknown> | undefined;
  if (!props) return undefined;
  // Întâi căutăm coduri sub-naționale (RO-XX) și apoi naționale.
  const candidates = ["COUNTY_CODE", "ISO_A3", "ISO_A3_EH", "ADM0_A3", "iso_a3", "iso3"];
  for (const k of candidates) {
    const v = props[k];
    if (typeof v !== "string") continue;
    const s = v.trim();
    if (s === "-99" || s.length === 0) continue;
    // RO-XX format (sub-national) sau 3 litere (ISO3)
    if (/^[A-Z]{2,3}-[A-Z0-9]{1,3}$/.test(s.toUpperCase()) || s.length === 3) {
      return s.toUpperCase();
    }
  }
  return undefined;
}

// Lookup-ul e un computed — se reactualizeaza automat cand store.data se schimba.
const countryByISO = computed<Map<string, MapCountry>>(() => {
  const m = new Map<string, MapCountry>();
  for (const c of store.data?.countries ?? []) {
    m.set(c.iso3.toUpperCase(), c);
  }
  return m;
});

async function loadGeo(path: string): Promise<GeoJSON.FeatureCollection> {
  const r = await fetch(path);
  return r.json();
}

function styleFn(feature?: GeoJSON.Feature) {
  const iso = isoFromFeature(feature);
  const c = iso ? countryByISO.value.get(iso) : undefined;
  let fill = "#dddddd";
  if (c) {
    if (layer.value === "diff") {
      const obs = valueFor(c, "observed");
      const sim = valueFor(c, "simulated");
      if (obs !== null && sim !== null) {
        const rate = per100k(sim - obs, c.population);
        fill = colorForRate(rate, "diff");
      }
    } else {
      const v = valueFor(c, layer.value);
      if (v !== null) fill = colorForRate(per100k(v, c.population), layer.value);
    }
  }
  return {
    fillColor: fill,
    weight: 0.6,
    color: "#666",
    opacity: 1,
    fillOpacity: c ? 0.85 : 0.25,
  };
}

function onEachCountry(feature: GeoJSON.Feature, lyr: L.Layer) {
  const iso = isoFromFeature(feature);
  // Numele afișat fallback: NAME (județe) sau ADMIN (țări) sau ISO.
  const props = (feature.properties as Record<string, unknown>) ?? {};
  const fallbackName =
    (props.NAME as string | undefined) ||
    (props.ADMIN as string | undefined) ||
    (props.name as string | undefined) ||
    iso || "?";
  lyr.on({
    mouseover: () => (lyr as L.Path).setStyle({ weight: 1.6, color: "#000" }),
    mouseout: () => geoLayer?.resetStyle(lyr as L.Path),
  });
  (lyr as L.Path).bindTooltip(
    () => tooltipHtml(iso ? countryByISO.value.get(iso) : undefined, iso, fallbackName),
    { sticky: true },
  );
}

function tooltipHtml(c: MapCountry | undefined, iso: string | undefined, fallbackName: string): string {
  if (!c) return `<strong>${fallbackName}</strong> (${iso ?? "?"})<br/>nu e în studiu`;
  const obs = valueFor(c, "observed");
  const sim = valueFor(c, "simulated");
  const fmt = (v: number | null) =>
    v === null ? "—" : Math.round(v).toLocaleString("ro-RO");
  const rate100 = (v: number | null) =>
    v === null ? "—" : per100k(v, c.population).toFixed(1);
  const displayName = c.name || fallbackName;
  let simInfo = "";
  if (c.simulation) {
    const d = new Date(c.simulation.created_at).toLocaleDateString("ro-RO", {
      day: "2-digit", month: "2-digit", year: "numeric",
    });
    const idShort = c.simulation.id.slice(0, 8);
    simInfo = `<br/><small style="color:#666">sim ${idShort} · ${d} · t_max=${c.simulation.t_max}` +
      (c.simulation.total_runs > 1 ? ` · cea mai recentă din ${c.simulation.total_runs}` : "") +
      `</small>`;
  }
  return `
    <strong>${displayName}</strong> (${c.iso3})<br/>
    <small>pop ${c.population.toLocaleString("ro-RO")}</small><br/>
    observat: <b>${fmt(obs)}</b> (${rate100(obs)}/100k)<br/>
    simulat:  <b>${fmt(sim)}</b> (${rate100(sim)}/100k)${simInfo}
  `;
}

async function initMap() {
  if (map) return;
  const el = document.getElementById("epi-map");
  if (!el) return;
  map = L.map(el, { center: [25, 10], zoom: 2, worldCopyJump: true });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap",
    maxZoom: 9,
  }).addTo(map);
  await rebuildGeoLayer();
}

// Înlocuim layer-ul GeoJSON când nivelul (țări vs județe) se schimbă.
let currentGeoPath = "";
async function rebuildGeoLayer() {
  if (!map) return;
  const path = geoFilePath.value;
  if (path === currentGeoPath && geoLayer) return;
  currentGeoPath = path;
  if (geoLayer) {
    geoLayer.remove();
    geoLayer = null;
  }
  const geo = await loadGeo(path);
  geoLayer = L.geoJSON(geo as any, {
    style: styleFn,
    onEachFeature: onEachCountry,
  }).addTo(map);
  fitToStudyBounds();
}

// Auto-fit:
//  • dacă suntem pe nivel județe → fit la întregul geojson (Romania)
//  • dacă suntem pe nivel național cu 1-3 țări → fit la acele țări
//  • altfel rămâne vederea globală
function fitToStudyBounds() {
  if (!map || !geoLayer) return;
  if (isSubnational.value) {
    const bounds = geoLayer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [20, 20], maxZoom: 8 });
    }
    return;
  }
  const ids = new Set([...countryByISO.value.keys()]);
  if (ids.size === 0 || ids.size > 3) return;
  const matchLayers: L.Layer[] = [];
  geoLayer.eachLayer((lyr) => {
    const f = (lyr as any).feature as GeoJSON.Feature | undefined;
    const iso = isoFromFeature(f);
    if (iso && ids.has(iso)) matchLayers.push(lyr);
  });
  if (matchLayers.length === 0) return;
  const group = L.featureGroup(matchLayers);
  map.fitBounds(group.getBounds(), { padding: [20, 20], maxZoom: 6 });
}

function refreshLayer() {
  if (!geoLayer) return;
  geoLayer.setStyle(styleFn);
}

// Re-randam stilurile la orice schimbare relevanta (lookup, ziua, stratul).
watch([dayIdx, layer, countryByISO], refreshLayer);

// La primul fetch initializam harta; ulterior refreshLayer se ocupa.
watch(
  () => store.data,
  async () => {
    if (!map) {
      await initMap();
    } else {
      // Daca s-a schimbat nivelul (tari ↔ judete), reconstruim layer-ul.
      await rebuildGeoLayer();
    }
    refreshLayer();
    fitToStudyBounds();
  },
);

onBeforeUnmount(() => {
  map?.remove();
  map = null;
});
</script>

<template>
  <h1>Harta răspândirii</h1>
  <p class="muted">
    Compară pentru fiecare țară din studiul curent valoarea
    <strong>observată</strong> (din OWID) cu valoarea
    <strong>simulată</strong> de modelul ales, la o dată calendaristică
    selectabilă din slider.
  </p>

  <div class="card controls">
    <div class="row">
      <label>
        Model:
        <select v-model="model">
          <option value="sir">SIR</option>
          <option value="seir">SEIR</option>
          <option value="sirs">SIRS</option>
          <option value="sidarthe">SIDARTHE</option>
        </select>
      </label>
      <label>
        Limbaj:
        <select v-model="language">
          <option value="python">Python</option>
          <option value="julia">Julia</option>
          <option value="r">R</option>
        </select>
      </label>
      <label>
        Strat:
        <select v-model="layer">
          <option value="observed">Observat (OWID)</option>
          <option value="simulated">Simulat (model)</option>
          <option value="diff">Diferență (sim − obs)</option>
        </select>
      </label>
    </div>

    <div v-if="store.error" class="alert error">{{ store.error }}</div>
    <p v-if="store.loading" class="muted">Se încarcă…</p>

    <div
      v-if="!store.loading && (layer === 'simulated' || layer === 'diff') && simulatedCount === 0 && observedCount > 0"
      class="alert warn"
    >
      Nu există simulări <strong>{{ model.toUpperCase() }}</strong> în
      <strong>{{ language }}</strong> finalizate pentru țările din studiul curent.
      Lansează o simulare din pagina „Simulare nouă” sau alege altă combinație model/limbaj.
    </div>

    <div v-if="nDays > 0" class="row" style="align-items: center;">
      <input
        type="range"
        :min="0"
        :max="nDays - 1"
        v-model.number="dayIdx"
        style="flex: 1;"
      />
      <strong style="min-width: 8.5rem; text-align: right;">{{ currentDate }}</strong>
    </div>
  </div>

  <div id="epi-map" class="map-area"></div>

  <div class="card sims-used" v-if="usedSims.length > 0">
    <h3>
      Simulări afișate pe hartă
      <span class="muted">
        ({{ usedSims.length }} {{ isSubnational ? "regiuni" : "țări" }}<span
          v-if="commonTMax !== null">, t_max = {{ commonTMax }}</span>)
      </span>
    </h3>
    <p class="small">
      Pentru fiecare {{ isSubnational ? "regiune" : "țară" }}, harta folosește
      <strong>cea mai recentă</strong> simulare <code>{{ model }}</code>/<code>{{ language }}</code>
      din studiul curent. Click pe un rând pentru detaliul simulării.
    </p>
    <div class="sims-table">
      <div class="sims-row sims-head">
        <span>{{ isSubnational ? "Regiune" : "Țară" }}</span>
        <span>ID simulare</span>
        <span>Data rulării</span>
        <span v-if="commonTMax === null">t_max</span>
        <span>Versiuni</span>
      </div>
      <router-link
        v-for="entry in usedSims"
        :key="entry.sim.id"
        :to="{ name: 'simulation-detail', params: { id: entry.sim.id } }"
        class="sims-row sims-data"
      >
        <span class="country-name">
          <span class="iso-pill">{{ entry.iso3 }}</span>
          {{ entry.country }}
        </span>
        <code class="sim-id" :title="entry.sim.id">{{ entry.sim.id.slice(0, 8) }}…</code>
        <span class="muted">
          {{ fmtDate(entry.sim.created_at) }} <span class="mini">{{ fmtTime(entry.sim.created_at) }}</span>
        </span>
        <span class="muted" v-if="commonTMax === null">{{ entry.sim.t_max }}</span>
        <span class="versions">
          {{ entry.sim.total_runs === 1 ? "unică" : `1 din ${entry.sim.total_runs}` }}
        </span>
      </router-link>
    </div>
  </div>

  <div class="card legend">
    <h3>
      Legendă —
      <span v-if="layer === 'observed'">cazuri observate la 100.000 locuitori</span>
      <span v-else-if="layer === 'simulated'">cazuri simulate la 100.000 locuitori</span>
      <span v-else>simulat − observat (per 100k)</span>
    </h3>

    <div class="legend-scale">
      <div
        class="legend-stop"
        v-for="(entry, i) in legend"
        :key="i"
      >
        <span class="swatch" :style="{ background: entry.color }"></span>
        <span class="lbl">{{ entry.label }}</span>
      </div>
    </div>

    <p v-if="layer === 'diff'" class="small">
      Albastru = modelul <em>subestimează</em>, roșu = <em>supraestimează</em>.
      Scală log<sub>10</sub> pe |diferență| per 100.000 locuitori.
    </p>
    <p v-else class="small">
      Scală log<sub>10</sub>(rată+1) cu plafon la 50.000 cazuri / 100k
      (pentru a discrimina între peak-urile SIR ale județelor/țărilor).
      {{ isSubnational
          ? "Regiunile gri nu au date în studiul curent."
          : "Țările gri nu fac parte din studiul curent." }}
    </p>
  </div>
</template>

<style scoped>
.controls .row { gap: 1rem; flex-wrap: wrap; margin-bottom: 0.6rem; }
.map-area {
  height: 70vh;
  min-height: 480px;
  border: 1px solid var(--c-border, #cbd5e1);
  margin-bottom: 1rem;
}
.legend .small { color: var(--c-text-soft, #475569); font-size: 0.85rem; margin-top: 0.5rem; }
.legend-scale {
  display: flex;
  gap: 0;
  align-items: stretch;
  flex-wrap: wrap;
}
.legend-stop {
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 11px;
  color: var(--c-text);
}
.swatch {
  display: block;
  width: 56px;
  height: 18px;
  border: 1px solid var(--c-border-dark);
  border-right: none;
}
.legend-stop:last-child .swatch {
  border-right: 1px solid var(--c-border-dark);
}
.lbl {
  padding-top: 2px;
  color: var(--c-text);
}
.alert.warn {
  background: #fff4d6;
  border: 1px solid #c9a13a;
  padding: 6px 10px;
  font-size: 13px;
  margin: 8px 0;
  color: #533a00;
}
[data-theme="dark"] .alert.warn {
  background: #4a3a00;
  border-color: #fbbf24;
  color: #fde68a;
}

/* Panoul „Simulări afișate pe hartă" */
.sims-used h3 .muted { font-weight: 400; font-size: 11px; }
.sims-used .small {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--c-text-muted);
}
.sims-table {
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid var(--c-border);
  background: var(--c-surface-soft);
}
.sims-row {
  display: grid;
  grid-template-columns: 2fr 1.3fr 1.5fr 0.6fr 0.8fr;
  gap: 10px;
  padding: 5px 10px;
  align-items: center;
  font-size: 12px;
  border-bottom: 1px solid var(--c-border);
  text-decoration: none;
  color: var(--c-text);
}
.sims-row:last-child { border-bottom: none; }
.sims-head {
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-size: 10px;
  color: var(--c-text-strong);
  background: linear-gradient(180deg, var(--btn-bg-1) 0%, var(--btn-bg-2) 100%);
  position: sticky;
  top: 0;
  z-index: 1;
  cursor: default;
}
.sims-data {
  transition: background var(--t-fast) var(--easing);
  cursor: pointer;
}
.sims-data:hover {
  background: var(--table-row-hover);
  color: var(--c-text-strong);
}
.country-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}
.iso-pill {
  display: inline-block;
  font-size: 10px;
  background: var(--c-surface);
  color: var(--c-text);
  border: 1px solid var(--c-border);
  padding: 1px 5px;
  font-family: var(--font-mono);
  min-width: 38px;
  text-align: center;
}
.sim-id {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--c-link);
}
.mini { color: var(--c-text-muted); font-size: 10px; }
.versions {
  font-size: 11px;
  font-weight: 600;
  text-align: right;
}

@media (max-width: 720px) {
  .sims-row {
    grid-template-columns: 1.5fr 1fr 1fr;
    font-size: 11px;
  }
  .sims-row > :nth-child(4),
  .sims-row > :nth-child(5) { display: none; }
}
</style>
