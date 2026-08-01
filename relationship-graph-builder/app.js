/* UFO Files Graph Builder — dependency-free, GitHub Pages compatible. */

const NS = "http://www.w3.org/2000/svg";
const LABELS = {
  person: "People", government_agency: "Government agencies", organization: "Organizations",
  location: "Locations", program: "Programs", subject: "Subjects", date: "Dates",
  mentions: "Mentions", documentCount: "Documents", sourceCount: "Collections",
  classificationConfidence: "Classification confidence", extractionConfidence: "Extraction confidence",
  words: "Words", documents: "Documents", segments: "Segments", bytes: "Source bytes",
  createdAt: "Cataloged at", durationMs: "Duration", source: "Collection", format: "Format",
  entity: "Entities", document: "Transcript files", name: "Name", title: "Title",
  category: "Entity type", reviewStatus: "Review status", engine: "Engine", path: "Path",
  table: "Table", collection: "Collections", shared_entities: "Shared entities"
};
const TABLE_FIELDS = {
  entity: ["name", "category", "mentions", "documentCount", "sourceCount", "classificationConfidence", "extractionConfidence", "reviewStatus"],
  document: ["title", "source", "format", "words", "segments", "bytes", "createdAt", "engine", "durationMs", "path"],
  source: ["name", "documents", "words"]
};
const TYPES = [
  { id: "network", label: "Network", icon: "<circle cx='6' cy='8' r='3'/><circle cx='24' cy='4' r='3'/><circle cx='22' cy='16' r='3'/><path d='M9 7l12-2M9 10l10 5M23 7l-1 6'/>" },
  { id: "scatter", label: "Scatter", icon: "<path d='M3 2v16h25'/><circle cx='9' cy='13' r='2'/><circle cx='15' cy='9' r='2'/><circle cx='22' cy='5' r='2'/>" },
  { id: "bars", label: "Bars", icon: "<path d='M3 2v16h26M7 15h4V8H7zm8 0h4V4h-4zm8 0h4v-9h-4z'/>" },
  { id: "timeline", label: "Timeline", icon: "<path d='M3 10h25M8 5v10m7-7v7m8-12v12'/><circle cx='8' cy='10' r='2'/><circle cx='15' cy='10' r='2'/><circle cx='23' cy='10' r='2'/>" },
  { id: "matrix", label: "Matrix", icon: "<path d='M4 3h22v15H4zM11 3v15m8-15v15M4 8h22m-22 5h22'/>" },
  { id: "table", label: "Table", icon: "<path d='M3 3h25v15H3zM3 8h25M3 13h25M12 3v15'/>" }
];
const DEFAULT = {
  type: "scatter", x: "entity", y: "mentions", size: "sourceCount", color: "category",
  categories: ["person", "government_agency", "organization"], sources: [], relation: "all",
  minEvidence: 2, minConfidence: 0.65, limit: 50, labels: "top", aggregation: "source",
  nodeRole: "entity", timelineRole: "document", matrixColumns: "category",
  tableRole: "entity", tableColumns: ["name", "category", "mentions", "documentCount", "sourceCount"],
  tableSort: "mentions", tableDirection: "desc", tableSearch: "",
  labelSize: 12, zoom: 1, title: "Evidence map"
};
const state = { catalog: null, config: loadConfig(), selected: null, documentById: new Map() };
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

function loadConfig() {
  try {
    const param = new URLSearchParams(location.hash.slice(1)).get("config");
    if (param) return { ...DEFAULT, ...JSON.parse(decodeURIComponent(escape(atob(param)))) };
  } catch (_) {}
  return { ...DEFAULT };
}

function persistHash() {
  const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(state.config))));
  history.replaceState(null, "", `#config=${encodeURIComponent(encoded)}`);
}

function el(name, attrs = {}, text = "") {
  const node = document.createElementNS(NS, name);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  if (text) node.textContent = text;
  return node;
}

function formatNumber(value) {
  if (value == null) return "—";
  if (typeof value === "string" && value.trim() !== "" && Number.isNaN(Number(value))) return value;
  if (Number.isNaN(Number(value))) return "—";
  if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(1)}m`;
  if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(1)}k`;
  return Number(value).toLocaleString();
}

function label(value) {
  return LABELS[value] || String(value).replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
}

function escapeHTML(value = "") {
  return String(value).replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 1800);
}

function controlSelect(key, title, options) {
  const choices = options.map(option => {
    const value = typeof option === "string" ? option : option.value;
    const text = typeof option === "string" ? label(option) : option.label;
    return `<option value="${escapeHTML(value)}" ${state.config[key] === value ? "selected" : ""}>${escapeHTML(text)}</option>`;
  }).join("");
  return `<div class="control"><label for="control-${key}">${escapeHTML(title)}</label><select id="control-${key}" data-config="${key}">${choices}</select></div>`;
}

function renderTypeGrid() {
  $("#typeGrid").innerHTML = TYPES.map(type => `
    <button class="type-card ${state.config.type === type.id ? "active" : ""}" data-type="${type.id}">
      <svg viewBox="0 0 31 20" fill="none" stroke="currentColor" stroke-width="1.5">${type.icon}</svg><span>${type.label}</span>
    </button>`).join("");
}

function renderControls() {
  renderTypeGrid();
  const numericEntity = ["documentCount", "mentions", "sourceCount", "classificationConfidence", "extractionConfidence"];
  const numericDoc = ["words", "segments", "bytes", "durationMs"];
  let roles = "";
  if (state.config.type === "network") {
    const relationshipControl = state.config.nodeRole === "collection"
      ? `<div class="control"><label for="collectionRelationship">Relationship</label><select id="collectionRelationship" disabled><option>Shared published entities</option></select></div>`
      : controlSelect("relation", "Relationship", [{ value: "all", label: "Any published relationship" }, { value: "co_mentioned", label: "Repeated co-mention" }, { value: "affiliated_with", label: "Affiliation cue" }, { value: "investigated", label: "Investigation cue" }]);
    roles = controlSelect("nodeRole", "Nodes", [{ value: "entity", label: "Entities" }, { value: "collection", label: "Collections" }]) + relationshipControl;
  } else if (state.config.type === "scatter") {
    roles = controlSelect("x", "X axis", ["entity", ...numericEntity]) + controlSelect("y", "Y axis", numericEntity);
  } else if (state.config.type === "bars") {
    roles = controlSelect("aggregation", "Group by", [{ value: "entity", label: "Entities" }, { value: "source", label: "Collection" }, { value: "format", label: "Transcript format" }]) + controlSelect("y", "Measure", state.config.aggregation === "entity" ? numericEntity : ["words", "documents", "bytes"]);
  } else if (state.config.type === "timeline") {
    roles = controlSelect("timelineRole", "Marks", [{ value: "entity", label: "Entities" }, { value: "document", label: "Completed transcript files" }]) + controlSelect("x", "X axis", [{ value: "createdAt", label: "Transcription date" }]) + controlSelect("y", "Y axis", state.config.timelineRole === "entity" ? numericEntity : numericDoc);
  } else if (state.config.type === "matrix") {
    roles = `<div class="control"><div class="control-title">Rows</div><select disabled><option>Collections</option></select></div>` + controlSelect("matrixColumns", "Columns", [{ value: "entity", label: "Entities" }, { value: "category", label: "Entity categories" }]);
  } else {
    const fields = TABLE_FIELDS[state.config.tableRole];
    const columnChecks = fields.map(field => `<label class="check-chip"><input type="checkbox" data-table-column="${field}" ${state.config.tableColumns.includes(field) ? "checked" : ""}><span>${escapeHTML(label(field))}</span></label>`).join("");
    roles = controlSelect("tableRole", "Rows", [{ value: "entity", label: "Entities" }, { value: "document", label: "Transcript files" }, { value: "source", label: "Collections" }]) + `<div class="control"><div class="control-title">Columns <span>${state.config.tableColumns.length}</span></div><div class="check-grid">${columnChecks}</div></div>`;
  }
  $("#roleControls").innerHTML = roles;

  const sizeOptions = state.config.type === "network" && state.config.nodeRole === "collection"
    ? ["documents", "words"]
    : state.config.type === "timeline" && state.config.timelineRole !== "entity" ? numericDoc : numericEntity;
  const labelSizeControl = `<div class="control"><label>Label size <span>${state.config.labelSize}px</span></label><input type="range" min="11" max="18" step="1" value="${state.config.labelSize}" data-range="labelSize"></div>`;
  const zoomControl = state.config.type === "network" ? `<div class="control"><label>Zoom <span>${state.config.zoom.toFixed(1)}×</span></label><input type="range" min="0.5" max="2.5" step="0.1" value="${state.config.zoom}" data-range="zoom"></div>` : "";
  if (state.config.type === "table") {
    const sortOptions = TABLE_FIELDS[state.config.tableRole];
    $("#encodeControls").innerHTML = controlSelect("tableSort", "Sort by", sortOptions) + controlSelect("tableDirection", "Direction", [{ value: "desc", label: "Descending" }, { value: "asc", label: "Ascending" }]) + labelSizeControl;
  } else {
    $("#encodeControls").innerHTML = (["scatter", "network", "timeline"].includes(state.config.type)
      ? controlSelect("size", "Size + shade", sizeOptions) + `<div class="control"><div class="control-title">Shade scale</div><select disabled><option>Monochrome value scale</option></select></div>` + controlSelect("labels", "Labels", [{ value: "top", label: "Most important" }, { value: "all", label: "All" }, { value: "none", label: "None" }])
      : `<div class="control"><div class="control-title">Shade scale</div><select disabled><option>Monochrome value scale</option></select></div>`) + labelSizeControl + zoomControl;
  }

  const categories = [...new Set(state.catalog?.entities.map(item => item.category) || ["person", "government_agency", "organization", "location", "program", "subject", "date"] )];
  const categoryChecks = categories.map(category => `<label class="check-chip"><input type="checkbox" data-category="${category}" ${state.config.categories.includes(category) ? "checked" : ""}><span>${escapeHTML(label(category))}</span></label>`).join("");
  const sources = state.catalog?.sources || [];
  const sourceChecks = sources.map(source => `<label class="check-chip"><input type="checkbox" data-source="${escapeHTML(source.name)}" ${state.config.sources.includes(source.name) ? "checked" : ""}><span>${escapeHTML(source.name)}</span></label>`).join("");
  const usesEntities = state.config.type === "table" ? state.config.tableRole === "entity" : !["bars", "timeline"].includes(state.config.type) || state.config.aggregation === "entity" || state.config.timelineRole === "entity";
  $("#filterControls").innerHTML = `
    ${usesEntities ? `<div class="control"><div class="control-title">Entity categories</div><div class="check-grid">${categoryChecks}</div></div>` : ""}
    <div class="control"><div class="control-title">Collections <span>${state.config.sources.length || "all"}</span></div><div class="check-grid">${sourceChecks}</div></div>
    ${state.config.type === "table" ? `<div class="control"><label for="tableSearch">Search rows</label><input id="tableSearch" class="text-input" type="search" value="${escapeHTML(state.config.tableSearch)}" placeholder="Filter this list" data-table-search></div>` : ""}
    ${usesEntities ? `<div class="control"><label>Minimum confidence <span>${Math.round(state.config.minConfidence * 100)}%</span></label><input type="range" min="0.5" max="0.95" step="0.01" value="${state.config.minConfidence}" data-range="minConfidence"></div>` : ""}
    ${state.config.type === "network" ? `<div class="control"><label>${state.config.nodeRole === "collection" ? "Shared entities" : "Relationship evidence"} <span>${state.config.minEvidence}×</span></label><input type="range" min="1" max="12" step="1" value="${state.config.minEvidence}" data-range="minEvidence"></div>` : ""}
    <div class="control"><label>Maximum ${state.config.type === "table" ? "rows" : "marks"} <span>${state.config.limit}</span></label><input type="range" min="20" max="${state.config.type === "network" ? 120 : 250}" step="10" value="${state.config.limit}" data-range="limit"></div>`;

  $$('[data-config]').forEach(node => node.addEventListener("change", event => updateConfig(event.target.dataset.config, event.target.value)));
  $$('[data-range]').forEach(node => node.addEventListener("input", event => {
    const key = event.target.dataset.range;
    const value = Number(event.target.value);
    state.config[key] = value;
    const output = event.target.closest(".control")?.querySelector("label span");
    if (output) output.textContent = key === "minConfidence" ? `${Math.round(value * 100)}%` : key === "minEvidence" ? `${value}×` : key === "labelSize" ? `${value}px` : key === "zoom" ? `${value.toFixed(1)}×` : String(value);
    persistHash();
    renderGraph();
  }));
  $$('[data-category]').forEach(node => node.addEventListener("change", () => {
    state.config.categories = $$('[data-category]:checked').map(input => input.dataset.category);
    commitConfig();
  }));
  $$('[data-source]').forEach(node => node.addEventListener("change", () => {
    state.config.sources = $$('[data-source]:checked').map(input => input.dataset.source);
    commitConfig();
  }));
  $$('[data-table-column]').forEach(node => node.addEventListener("change", () => {
    const columns = $$('[data-table-column]:checked').map(input => input.dataset.tableColumn);
    if (!columns.length) { node.checked = true; return toast("Keep at least one column"); }
    state.config.tableColumns = columns;
    renderControls();
    commitConfig(false);
  }));
  $("[data-table-search]")?.addEventListener("input", event => {
    state.config.tableSearch = event.target.value;
    persistHash();
    renderGraph();
  });
  $$('[data-type]').forEach(node => node.addEventListener("click", () => setType(node.dataset.type)));
}

function setType(type) {
  state.config.type = type;
  if (type === "bars") Object.assign(state.config, { aggregation: "source", y: "words", color: "intensity", title: "Collection coverage" });
  if (type === "scatter") Object.assign(state.config, { x: "entity", y: "mentions", size: "sourceCount", color: "category", limit: 50, title: "Evidence map" });
  if (type === "network") Object.assign(state.config, { nodeRole: "entity", size: "mentions", color: "category", title: "People and institutions" });
  if (type === "timeline") Object.assign(state.config, { timelineRole: "document", x: "createdAt", y: "words", size: "words", color: "source", title: "Transcription activity" });
  if (type === "matrix") Object.assign(state.config, { matrixColumns: "category", color: "intensity", title: "Collections × entity types" });
  if (type === "table") Object.assign(state.config, { tableRole: "entity", tableColumns: ["name", "category", "mentions", "documentCount", "sourceCount"], tableSort: "mentions", tableDirection: "desc", tableSearch: "", limit: 60, title: "Archive entities" });
  state.selected = null;
  renderControls();
  commitConfig();
}

function updateConfig(key, value, rerenderControls = false) {
  state.config[key] = value;
  if (key === "aggregation") {
    state.config.y = value === "entity" ? "mentions" : "words";
    state.config.color = "intensity";
  }
  if (key === "timelineRole") {
    state.config.y = value === "entity" ? "mentions" : "words";
    state.config.size = value === "entity" ? "sourceCount" : "words";
    state.config.color = value === "entity" ? "category" : "source";
  }
  if (key === "nodeRole") {
    state.config.size = value === "collection" ? "documents" : "mentions";
    state.config.title = value === "collection" ? "Collection relationships" : "People and institutions";
    $("#graphTitle").textContent = state.config.title;
  }
  if (key === "tableRole") {
    const defaults = {
      entity: { tableColumns: ["name", "category", "mentions", "documentCount", "sourceCount"], tableSort: "mentions" },
      document: { tableColumns: ["title", "source", "format", "words", "createdAt"], tableSort: "createdAt" },
      source: { tableColumns: ["name", "documents", "words"], tableSort: "documents" }
    };
    Object.assign(state.config, defaults[value]);
  }
  if (rerenderControls) renderControls();
  if (["aggregation", "timelineRole", "matrixColumns", "tableRole", "nodeRole"].includes(key)) renderControls();
  commitConfig(false);
}

function commitConfig(updateTitle = true) {
  if (updateTitle) $("#graphTitle").textContent = state.config.title;
  persistHash();
  renderGraph();
}

function dimensions() {
  const box = $("#chartWrap").getBoundingClientRect();
  return { width: Math.max(460, box.width), height: Math.max(420, box.height) };
}

function clearChart() {
  const svg = $("#chart");
  svg.removeAttribute("hidden");
  $("#tableView").hidden = true;
  $("#chartWrap").classList.remove("table-mode");
  svg.replaceChildren();
  svg.style.setProperty("--graph-label-size", `${state.config.labelSize}px`);
  const { width, height } = dimensions();
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  $("#legend").innerHTML = "";
  return { svg, width, height };
}

function selectedSources() {
  return new Set(state.config.sources);
}

function entityMatches(entity) {
  if (!state.config.categories.includes(entity.category)) return false;
  if (entity.classificationConfidence < state.config.minConfidence) return false;
  const sources = selectedSources();
  if (!sources.size) return true;
  return entity.documentIds.some(id => sources.has(state.documentById.get(id)?.source));
}

function valueExtent(data, key) {
  const values = data.map(item => Number(item[key]) || 0);
  return [Math.min(...values, 0), Math.max(...values, 1)];
}

function scale(value, extent, range) {
  const span = extent[1] - extent[0] || 1;
  return range[0] + ((Number(value) || 0) - extent[0]) / span * (range[1] - range[0]);
}

function drawIntensityLegend() {
  $("#legend").innerHTML = `<span class="legend-item"><i style="background:#111;opacity:.14"></i>Lower</span><span class="legend-item"><i style="background:#111;opacity:.48"></i>Medium</span><span class="legend-item"><i style="background:#111"></i>Higher</span>`;
}

function addTitle(node, text) {
  node.append(el("title", {}, text));
}

function drawAxes(svg, width, height, xKey, yKey, xExtent, yExtent) {
  const margin = { left: 58, right: 28, top: 22, bottom: 48 };
  for (let i = 0; i <= 4; i++) {
    const y = margin.top + i * (height - margin.top - margin.bottom) / 4;
    svg.append(el("line", { x1: margin.left, y1: y, x2: width - margin.right, y2: y, class: "grid-line" }));
    const value = yExtent[1] - i * (yExtent[1] - yExtent[0]) / 4;
    svg.append(el("text", { x: margin.left - 8, y: y + 3, "text-anchor": "end", class: "axis-label" }, formatNumber(value)));
  }
  svg.append(el("text", { x: (margin.left + width - margin.right) / 2, y: height - 13, "text-anchor": "middle", class: "axis-label" }, label(xKey)));
  const yLabel = el("text", { x: 15, y: height / 2, transform: `rotate(-90 15 ${height / 2})`, "text-anchor": "middle", class: "axis-label" }, label(yKey));
  svg.append(yLabel);
  return margin;
}

function collectionNetworkData() {
  const sourceFilter = selectedSources();
  const documentsBySource = new Map();
  state.catalog.documents.forEach(document => {
    if (!documentsBySource.has(document.source)) documentsBySource.set(document.source, []);
    documentsBySource.get(document.source).push(document);
  });
  const candidates = state.catalog.sources
    .filter(source => !sourceFilter.size || sourceFilter.has(source.name))
    .map(source => {
      const documents = documentsBySource.get(source.name) || [];
      return {
        ...source,
        category: "collection",
        bytes: documents.reduce((sum, document) => sum + (document.bytes || 0), 0),
        documentIds: documents.map(document => document.id)
      };
    });
  const sourceByName = new Map(candidates.map(source => [source.name, source]));
  const pairs = new Map();
  state.catalog.entities.filter(entityMatches).forEach(entity => {
    const names = [...new Set(entity.documentIds.map(id => state.documentById.get(id)?.source).filter(name => sourceByName.has(name)))].sort();
    for (let leftIndex = 0; leftIndex < names.length; leftIndex++) for (let rightIndex = leftIndex + 1; rightIndex < names.length; rightIndex++) {
      const left = sourceByName.get(names[leftIndex]), right = sourceByName.get(names[rightIndex]);
      const key = `${left.id}|${right.id}`;
      if (!pairs.has(key)) pairs.set(key, { id: `shared-${key}`, source: left.id, target: right.id, relationship: "shared_entities", sharedEntities: [] });
      pairs.get(key).sharedEntities.push(entity);
    }
  });
  const edges = [...pairs.values()].map(edge => {
    const names = new Set([candidates.find(source => source.id === edge.source)?.name, candidates.find(source => source.id === edge.target)?.name]);
    const documentIds = new Set(edge.sharedEntities.flatMap(entity => entity.documentIds.filter(id => names.has(state.documentById.get(id)?.source))));
    const evidence = edge.sharedEntities.flatMap(entity => entity.evidence.filter(item => documentIds.has(item.documentId)).slice(0, 1).map(item => ({ ...item, excerpt: `${entity.name}: ${item.excerpt}` }))).slice(0, 8);
    return { ...edge, evidenceCount: edge.sharedEntities.length, documentCount: documentIds.size, confidence: edge.sharedEntities.reduce((sum, entity) => sum + entity.classificationConfidence, 0) / edge.sharedEntities.length, evidence };
  }).filter(edge => edge.evidenceCount >= state.config.minEvidence);
  return { candidates, edges };
}

function renderNetwork() {
  const { svg, width, height } = clearChart();
  const zoom = Math.max(.5, Math.min(2.5, Number(state.config.zoom) || 1));
  const labelSize = state.config.labelSize / zoom;
  const collectionMode = state.config.nodeRole === "collection";
  let candidates, edges;
  if (collectionMode) {
    ({ candidates, edges } = collectionNetworkData());
  } else {
    candidates = state.catalog.entities.filter(entityMatches);
    const candidateIds = new Set(candidates.map(item => item.id));
    edges = state.catalog.edges.filter(edge => candidateIds.has(edge.source) && candidateIds.has(edge.target) && edge.evidenceCount >= state.config.minEvidence && (state.config.relation === "all" || edge.relationship === state.config.relation));
  }
  const degree = new Map();
  edges.forEach(edge => { degree.set(edge.source, (degree.get(edge.source) || 0) + edge.evidenceCount); degree.set(edge.target, (degree.get(edge.target) || 0) + edge.evidenceCount); });
  const nodes = candidates.filter(node => degree.has(node.id)).sort((a, b) => (degree.get(b.id) || 0) - (degree.get(a.id) || 0)).slice(0, state.config.limit);
  const ids = new Set(nodes.map(node => node.id));
  edges = edges.filter(edge => ids.has(edge.source) && ids.has(edge.target));
  if (!nodes.length) return showEmpty();
  const cx = width / 2, cy = height / 2;
  const positions = new Map();
  nodes.forEach((node, index) => {
    const angle = index * 2.399963 + ((node.category || node.name).charCodeAt(0) % 5) * .25;
    const radius = collectionMode ? Math.min(width, height) * .3 : 38 + Math.sqrt(index / nodes.length) * Math.min(width, height) * .38;
    positions.set(node.id, { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius });
  });
  for (let round = 0; round < (collectionMode ? 0 : 35); round++) {
    edges.forEach(edge => {
      const a = positions.get(edge.source), b = positions.get(edge.target);
      const dx = b.x - a.x, dy = b.y - a.y, distance = Math.hypot(dx, dy) || 1;
      const pull = (distance - 90) * .008;
      a.x += dx / distance * pull; a.y += dy / distance * pull;
      b.x -= dx / distance * pull; b.y -= dy / distance * pull;
    });
    for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
      const a = positions.get(nodes[i].id), b = positions.get(nodes[j].id);
      const dx = b.x - a.x, dy = b.y - a.y, distance = Math.hypot(dx, dy) || 1;
      if (distance < 42) { const push = (42 - distance) * .02; a.x -= dx / distance * push; a.y -= dy / distance * push; b.x += dx / distance * push; b.y += dy / distance * push; }
    }
  }
  const sizeExtent = valueExtent(nodes, state.config.size);
  const radii = new Map(nodes.map(node => [node.id, scale(node[state.config.size], sizeExtent, [5, 17])]));
  nodes.forEach(node => {
    const point = positions.get(node.id), radius = radii.get(node.id);
    point.x = Math.max(radius + 3, Math.min(width - radius - 3, point.x));
    point.y = Math.max(radius + 3, Math.min(height - radius - 3, point.y));
  });
  const bounds = nodes.reduce((box, node) => {
    const point = positions.get(node.id), radius = radii.get(node.id);
    return {
      left: Math.min(box.left, point.x - radius), right: Math.max(box.right, point.x + radius),
      top: Math.min(box.top, point.y - radius), bottom: Math.max(box.bottom, point.y + radius)
    };
  }, { left: Infinity, right: -Infinity, top: Infinity, bottom: -Infinity });
  const networkCenterX = (bounds.left + bounds.right) / 2;
  const networkCenterY = (bounds.top + bounds.bottom) / 2;
  svg.setAttribute("viewBox", `${networkCenterX - width / (2 * zoom)} ${networkCenterY - height / (2 * zoom)} ${width / zoom} ${height / zoom}`);
  const edgeGroup = el("g");
  edges.forEach(edge => {
    const a = positions.get(edge.source), b = positions.get(edge.target);
    const line = el("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "edge mark", "stroke-width": Math.min(4, .5 + Math.sqrt(edge.evidenceCount) * .35) });
    addTitle(line, `${label(edge.relationship)} · ${edge.evidenceCount} ${collectionMode ? "entities" : "evidence segments"}`);
    line.addEventListener("click", () => collectionMode ? inspectCollectionEdge(edge, nodes) : inspectEdge(edge));
    edgeGroup.append(line);
  });
  svg.append(edgeGroup);
  nodes.forEach((node, index) => {
    const point = positions.get(node.id);
    const radius = radii.get(node.id);
    const shade = scale(node[state.config.size], sizeExtent, [.18, .96]);
    const circle = el("circle", { cx: point.x, cy: point.y, r: radius, fill: "#111", "fill-opacity": shade, stroke: "#111", "stroke-width": 1, class: "mark" });
    addTitle(circle, `${node.name} · ${collectionMode ? `${node.documents} documents` : `${node.mentions} mentions`}`);
    circle.addEventListener("click", () => collectionMode ? inspectGroup(node) : inspectEntity(node));
    svg.append(circle);
    if (state.config.labels === "all" || (state.config.labels === "top" && index < 16)) {
      svg.append(el("text", {
        x: point.x,
        y: point.y + radius + labelSize,
        "text-anchor": "middle",
        class: "chart-label node-label",
        style: `font-size:${labelSize}px`,
        "vector-effect": "non-scaling-stroke",
      }, node.name.slice(0, 28)));
    }
  });
  drawIntensityLegend();
  setSummary(`${nodes.length} ${collectionMode ? "collections" : "entities"} · ${edges.length} relationships`, "network");
}

function renderScatter() {
  const { svg, width, height } = clearChart();
  const data = state.catalog.entities.filter(entityMatches).sort((a, b) => b[state.config.y] - a[state.config.y]).slice(0, state.config.limit);
  if (!data.length) return showEmpty();
  const categoricalX = state.config.x === "entity";
  const xExtent = categoricalX ? [0, Math.max(1, data.length - 1)] : valueExtent(data, state.config.x);
  const yExtent = valueExtent(data, state.config.y), sizeExtent = valueExtent(data, state.config.size);
  let margin;
  if (categoricalX) {
    margin = { left: 58, right: 28, top: 22, bottom: 55 };
    for (let i = 0; i <= 4; i++) {
      const y = margin.top + i * (height - margin.top - margin.bottom) / 4;
      svg.append(el("line", { x1: margin.left, y1: y, x2: width - margin.right, y2: y, class: "grid-line" }));
      const value = yExtent[1] - i * (yExtent[1] - yExtent[0]) / 4;
      svg.append(el("text", { x: margin.left - 8, y: y + 3, "text-anchor": "end", class: "axis-label" }, formatNumber(value)));
    }
    svg.append(el("text", { x: (margin.left + width - margin.right) / 2, y: height - 12, "text-anchor": "middle", class: "axis-label" }, label("entity")));
    svg.append(el("text", { x: 15, y: height / 2, transform: `rotate(-90 15 ${height / 2})`, "text-anchor": "middle", class: "axis-label" }, label(state.config.y)));
  } else {
    margin = drawAxes(svg, width, height, state.config.x, state.config.y, xExtent, yExtent);
  }
  const plotWidth = width - margin.left - margin.right;
  const tickEvery = Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor(plotWidth / 62))));
  data.forEach((item, index) => {
    const x = categoricalX
      ? margin.left + (index + .5) * plotWidth / data.length
      : scale(item[state.config.x], xExtent, [margin.left, width - margin.right]);
    const y = scale(item[state.config.y], yExtent, [height - margin.bottom, margin.top]);
    const radius = scale(item[state.config.size], sizeExtent, [4, 15]);
    const shade = scale(item[state.config.size], sizeExtent, [.18, .96]);
    const dot = el("circle", { cx: x, cy: y, r: radius, fill: "#111", "fill-opacity": shade, stroke: "#111", "stroke-width": 1, class: "mark" });
    addTitle(dot, `${item.name} · ${label(state.config.x)}: ${formatNumber(item[state.config.x])}`);
    dot.addEventListener("click", () => inspectEntity(item)); svg.append(dot);
    if (categoricalX && state.config.labels !== "none" && (state.config.labels === "all" || index % tickEvery === 0)) {
      svg.append(el("text", { x, y: Math.min(height - 25, y + radius + state.config.labelSize), "text-anchor": "middle", class: "chart-label node-label" }, item.name.slice(0, 20)));
    } else if (!categoricalX && (state.config.labels === "all" || (state.config.labels === "top" && index < 12))) {
      svg.append(el("text", { x, y: Math.min(height - margin.bottom + 18, y + radius + state.config.labelSize), "text-anchor": "middle", class: "chart-label node-label" }, item.name.slice(0, 26)));
    }
  });
  drawIntensityLegend();
  setSummary(`${data.length} entities`, "scatter");
}

function aggregateDocuments() {
  const sourceFilter = selectedSources();
  const docs = state.catalog.documents.filter(doc => !sourceFilter.size || sourceFilter.has(doc.source));
  if (state.config.aggregation === "entity") {
    return state.catalog.entities.filter(entityMatches).map(entity => ({ ...entity, source: entity.category }));
  }
  if (state.config.aggregation === "format") {
    return [...new Set(docs.map(doc => doc.format))].map(format => {
      const items = docs.filter(doc => doc.format === format);
      return { name: label(format), source: format, documents: items.length, words: items.reduce((sum, item) => sum + item.words, 0), bytes: items.reduce((sum, item) => sum + item.bytes, 0), documentIds: items.map(item => item.id) };
    });
  }
  return state.catalog.sources.filter(source => !sourceFilter.size || sourceFilter.has(source.name)).map(source => {
    const items = docs.filter(doc => doc.source === source.name);
    return { name: source.name, source: source.name, documents: items.length, words: items.reduce((sum, item) => sum + item.words, 0), bytes: items.reduce((sum, item) => sum + item.bytes, 0), documentIds: items.map(item => item.id) };
  });
}

function renderBars() {
  const { svg, width, height } = clearChart();
  const data = aggregateDocuments().sort((a, b) => b[state.config.y] - a[state.config.y]).slice(0, state.config.limit);
  if (!data.length) return showEmpty();
  const margin = { left: Math.min(190, width * .28), right: 45, top: 20, bottom: 60 };
  const row = (height - margin.top - margin.bottom) / data.length;
  const max = Math.max(...data.map(item => item[state.config.y]), 1);
  data.forEach((item, index) => {
    const y = margin.top + index * row;
    const barWidth = (width - margin.left - margin.right) * item[state.config.y] / max;
    svg.append(el("text", { x: margin.left - 8, y: y + row * .62, "text-anchor": "end", class: "chart-label" }, item.name.slice(0, 27)));
    const opacity = .14 + item[state.config.y] / max * .86;
    const rect = el("rect", { x: margin.left, y: y + 2, width: Math.max(2, barWidth), height: Math.max(5, row - 5), rx: 1, fill: "#111", "fill-opacity": opacity, stroke: "#111", "stroke-width": 1, class: "mark" });
    addTitle(rect, `${item.name} · ${formatNumber(item[state.config.y])} ${label(state.config.y)}`);
    rect.addEventListener("click", () => state.config.aggregation === "entity" ? inspectEntity(item) : inspectGroup(item)); svg.append(rect);
    svg.append(el("text", { x: Math.min(width - 5, margin.left + barWidth + 6), y: y + row * .62, class: "axis-label" }, formatNumber(item[state.config.y])));
  });
  drawIntensityLegend();
  setSummary(`${data.length} ${state.config.aggregation === "entity" ? "entities" : state.config.aggregation === "source" ? "collections" : "formats"}`, "bars");
}

function renderTimeline() {
  const { svg, width, height } = clearChart();
  const sourceFilter = selectedSources();
  const data = (state.config.timelineRole === "entity"
    ? state.catalog.entities.filter(entityMatches).map(entity => {
        const documents = entity.documentIds.map(id => state.documentById.get(id)).filter(document => document?.createdAt && (!sourceFilter.size || sourceFilter.has(document.source))).sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
        return documents.length ? { ...entity, title: entity.name, createdAt: documents[0].createdAt, source: documents[0].source, format: documents[0].format, entityRecord: entity } : null;
      }).filter(Boolean)
    : state.catalog.documents.filter(item => item.createdAt && (!sourceFilter.size || sourceFilter.has(item.source))))
    .sort((a, b) => (b[state.config.y] || 0) - (a[state.config.y] || 0)).slice(0, state.config.limit);
  if (!data.length) return showEmpty();
  const dates = data.map(item => new Date(item.createdAt).getTime());
  const xExtent = [Math.min(...dates), Math.max(...dates) + 1], yExtent = valueExtent(data, state.config.y), sizeExtent = valueExtent(data, state.config.size);
  const margin = drawAxes(svg, width, height, "createdAt", state.config.y, xExtent, yExtent);
  data.forEach((item, index) => {
    const x = scale(new Date(item.createdAt).getTime(), xExtent, [margin.left, width - margin.right]);
    const y = scale(item[state.config.y], yExtent, [height - margin.bottom, margin.top]);
    const radius = scale(item[state.config.size], sizeExtent, [3, 12]);
    const shade = scale(item[state.config.size], sizeExtent, [.18, .96]);
    const dot = el("circle", { cx: x, cy: y, r: radius, fill: "#111", "fill-opacity": shade, stroke: "#111", "stroke-width": 1, class: "mark" });
    addTitle(dot, `${item.title} · ${new Date(item.createdAt).toLocaleDateString()}`); dot.addEventListener("click", () => item.entityRecord ? inspectEntity(item.entityRecord) : inspectDocument(item)); svg.append(dot);
    if (state.config.labels === "all" || (state.config.labels === "top" && index < 12)) {
      svg.append(el("text", { x, y: Math.min(height - margin.bottom + 18, y + radius + state.config.labelSize), "text-anchor": "middle", class: "chart-label node-label" }, item.title.slice(0, 22)));
    }
  });
  drawIntensityLegend();
  setSummary(`${data.length} ${state.config.timelineRole === "entity" ? "entities" : "completed transcripts"}`, "timeline");
}

function renderMatrix() {
  const { svg, width, height } = clearChart();
  const sources = state.catalog.sources.filter(item => !state.config.sources.length || state.config.sources.includes(item.name));
  const columns = state.config.matrixColumns === "entity"
    ? state.catalog.entities.filter(entityMatches).sort((a, b) => b.mentions - a.mentions).slice(0, Math.min(state.config.limit, 18)).map(entity => ({ id: entity.id, label: entity.name, category: entity.category, entity }))
    : state.config.categories.map(category => ({ id: category, label: label(category), category }));
  if (!sources.length || !columns.length) return showEmpty();
  const counts = [];
  sources.forEach(source => columns.forEach(column => {
    const value = column.entity
      ? column.entity.documentIds.filter(id => state.documentById.get(id)?.source === source.name).length
      : state.catalog.entities.filter(entity => entity.category === column.category && entity.classificationConfidence >= state.config.minConfidence && entity.documentIds.some(id => state.documentById.get(id)?.source === source.name)).length;
    counts.push({ source: source.name, category: column.category, columnId: column.id, columnLabel: column.label, entityId: column.entity?.id, value });
  }));
  const margin = { left: Math.min(175, width * .3), right: 25, top: 70, bottom: 25 };
  const cellW = (width - margin.left - margin.right) / columns.length, cellH = (height - margin.top - margin.bottom) / sources.length;
  const max = Math.max(...counts.map(item => item.value), 1);
  columns.forEach((column, index) => svg.append(el("text", { x: margin.left + (index + .5) * cellW, y: margin.top - 12, "text-anchor": "middle", class: "chart-label" }, column.label.slice(0, state.config.matrixColumns === "entity" ? 12 : 15))));
  sources.forEach((source, index) => svg.append(el("text", { x: margin.left - 8, y: margin.top + (index + .55) * cellH, "text-anchor": "end", class: "chart-label" }, source.name.slice(0, 24))));
  counts.forEach(item => {
    const row = sources.findIndex(source => source.name === item.source), column = columns.findIndex(candidate => candidate.id === item.columnId);
    const opacity = .08 + item.value / max * .92;
    const rect = el("rect", { x: margin.left + column * cellW + 1, y: margin.top + row * cellH + 1, width: Math.max(2, cellW - 2), height: Math.max(2, cellH - 2), fill: "#111", "fill-opacity": opacity, stroke: "none", class: "mark" });
    addTitle(rect, `${item.source} · ${item.columnLabel}: ${item.value}`); rect.addEventListener("click", () => inspectMatrix(item)); svg.append(rect);
  });
  drawIntensityLegend();
  setSummary(`${sources.length} collections × ${columns.length} ${state.config.matrixColumns === "entity" ? "entities" : "entity types"}`, "matrix");
}

function tableRecords() {
  const sourceFilter = selectedSources();
  let records;
  if (state.config.tableRole === "document") {
    records = state.catalog.documents.filter(item => !sourceFilter.size || sourceFilter.has(item.source));
  } else if (state.config.tableRole === "source") {
    records = state.catalog.sources
      .filter(item => !sourceFilter.size || sourceFilter.has(item.name))
      .map(item => ({ ...item, documentIds: state.catalog.documents.filter(document => document.source === item.name).map(document => document.id) }));
  } else {
    records = state.catalog.entities.filter(entityMatches);
  }
  const query = state.config.tableSearch.trim().toLocaleLowerCase();
  if (query) records = records.filter(item => TABLE_FIELDS[state.config.tableRole].some(field => String(item[field] ?? "").toLocaleLowerCase().includes(query)));
  const sortField = TABLE_FIELDS[state.config.tableRole].includes(state.config.tableSort) ? state.config.tableSort : TABLE_FIELDS[state.config.tableRole][0];
  const direction = state.config.tableDirection === "asc" ? 1 : -1;
  return records.sort((a, b) => {
    const left = a[sortField] ?? "", right = b[sortField] ?? "";
    if (typeof left === "number" && typeof right === "number") return (left - right) * direction;
    return String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" }) * direction;
  }).slice(0, state.config.limit);
}

function tableDisplayValue(item, field) {
  const value = item[field];
  if (value == null || value === "") return "—";
  if (["classificationConfidence", "extractionConfidence"].includes(field)) return `${Math.round(value * 100)}%`;
  if (field === "createdAt") return new Date(value).toLocaleString();
  if (field === "durationMs") return `${Number(value).toLocaleString()} ms`;
  if (["category", "reviewStatus", "format"].includes(field)) return label(value);
  if (typeof value === "number") return value.toLocaleString();
  return String(value);
}

function renderTable() {
  const svg = $("#chart"), tableView = $("#tableView");
  svg.setAttribute("hidden", "");
  svg.replaceChildren();
  tableView.hidden = false;
  $("#chartWrap").classList.add("table-mode");
  $("#legend").innerHTML = "";
  const fields = state.config.tableColumns.filter(field => TABLE_FIELDS[state.config.tableRole].includes(field));
  const records = tableRecords();
  if (!fields.length || !records.length) {
    tableView.replaceChildren();
    return showEmpty();
  }
  tableView.style.setProperty("--table-font-size", `${state.config.labelSize}px`);
  tableView.innerHTML = `<table class="builder-table"><thead><tr>${fields.map(field => `<th scope="col">${escapeHTML(label(field))}</th>`).join("")}</tr></thead><tbody>${records.map((item, index) => `<tr tabindex="0" data-table-row="${index}">${fields.map(field => `<td>${escapeHTML(tableDisplayValue(item, field))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  $$('[data-table-row]').forEach(row => {
    const inspect = () => {
      const item = records[Number(row.dataset.tableRow)];
      if (state.config.tableRole === "entity") inspectEntity(item);
      else if (state.config.tableRole === "document") inspectDocument(item);
      else inspectGroup(item);
    };
    row.addEventListener("click", inspect);
    row.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); inspect(); } });
  });
  const rowLabel = state.config.tableRole === "entity" ? "entities" : state.config.tableRole === "document" ? "transcript files" : "collections";
  setSummary(`${records.length} ${rowLabel} · ${fields.length} columns`, "table");
}

function showEmpty() {
  $("#emptyState").hidden = false;
  setSummary("No matching records", state.config.type);
}

function setSummary(text, type) {
  $("#resultSummary").textContent = text;
  $("#graphKicker").textContent = label(type === "bars" ? "bar chart" : type);
  $("#policySummary").textContent = type === "network"
    ? state.config.nodeRole === "collection" ? `Links require ${state.config.minEvidence} shared published entities` : `Co-mentions require ${state.config.minEvidence} evidence segments · dense OCR sections excluded`
    : `${formatNumber(state.catalog.counts.documents)} source files · transcript text unchanged`;
}

function renderGraph() {
  if (!state.catalog) return;
  $("#emptyState").hidden = true;
  $("#graphTitle").textContent = state.config.title;
  $("#resetZoom").hidden = state.config.type !== "network";
  $("#exportButton").textContent = state.config.type === "table" ? "Export CSV" : "Export SVG";
  const descriptions = {
    network: state.config.nodeRole === "collection" ? "Collections connected by shared published entities." : "Evidence-backed connections across the local archive.", scatter: `${label(state.config.x)} compared with ${label(state.config.y)}.`,
    bars: `${label(state.config.y)} grouped by ${label(state.config.aggregation)}.`,
    timeline: `${state.config.timelineRole === "entity" ? "Entities" : "Completed transcript files"} by cataloging time.`,
    matrix: `${state.config.matrixColumns === "entity" ? "Entity" : "Entity-type"} coverage across completed collections.`,
    table: `A custom list of ${state.config.tableRole === "entity" ? "entities" : state.config.tableRole === "document" ? "transcript files" : "collections"}.`
  };
  $("#graphSubtitle").textContent = descriptions[state.config.type];
  ({ network: renderNetwork, scatter: renderScatter, bars: renderBars, timeline: renderTimeline, matrix: renderMatrix, table: renderTable })[state.config.type]();
}

function evidenceHTML(evidence = []) {
  if (!evidence.length) return "<p>No excerpt stored for this derived summary.</p>";
  return evidence.map(item => {
    const doc = state.documentById.get(item.documentId);
    return `<div class="evidence-card"><p>“${escapeHTML(item.excerpt)}”</p><small>${escapeHTML(doc?.path || item.documentId)}</small></div>`;
  }).join("");
}

function showInspector(category, title, metrics, evidence, note = "") {
  const inspector = $("#inspector");
  inspector.classList.add("has-selection");
  inspector.innerHTML = `<p class="inspect-category">${escapeHTML(label(category))}</p><h3>${escapeHTML(title)}</h3>${note ? `<p>${escapeHTML(note)}</p>` : ""}<div class="metric-row">${metrics.map(([value, name]) => `<div class="metric"><strong>${escapeHTML(formatNumber(value))}</strong><small>${escapeHTML(name)}</small></div>`).join("")}</div><div class="evidence-list"><h4>Evidence</h4>${evidenceHTML(evidence)}</div>`;
}

function inspectEntity(item) {
  state.selected = item;
  showInspector(item.category, item.name, [[item.mentions, "mentions"], [item.documentCount, "documents"], [item.sourceCount, "collections"], [`${Math.round(item.classificationConfidence * 100)}%`, "classification"]], item.evidence, `${label(item.reviewStatus)} · ${item.variants.length} observed name variant${item.variants.length === 1 ? "" : "s"}`);
}

function inspectEdge(edge) {
  const left = state.catalog.entities.find(item => item.id === edge.source), right = state.catalog.entities.find(item => item.id === edge.target);
  showInspector(edge.relationship, `${left?.name || "Entity"} ↔ ${right?.name || "Entity"}`, [[edge.evidenceCount, "segments"], [edge.documentCount, "documents"], [`${Math.round(edge.confidence * 100)}%`, "confidence"]], edge.evidence, "A typed edge requires same-segment relation language; a co-mention requires repeat evidence.");
}

function inspectCollectionEdge(edge, nodes) {
  const left = nodes.find(item => item.id === edge.source), right = nodes.find(item => item.id === edge.target);
  const names = edge.sharedEntities.slice(0, 8).map(entity => entity.name).join(", ");
  const remainder = Math.max(0, edge.sharedEntities.length - 8);
  showInspector("shared_entities", `${left?.name || "Collection"} ↔ ${right?.name || "Collection"}`, [[edge.evidenceCount, "shared entities"], [edge.documentCount, "documents"], [`${Math.round(edge.confidence * 100)}%`, "avg. classification"]], edge.evidence, `${names}${remainder ? `, and ${remainder} more` : ""}`);
}

function inspectGroup(item) {
  const docs = item.documentIds.map(id => state.documentById.get(id)).filter(Boolean);
  showInspector("collection", item.name, [[item.documents, "documents"], [item.words, "words"], [item.bytes, "source bytes"]], docs.slice(0, 4).map(doc => ({ documentId: doc.id, excerpt: doc.title })), "An aggregate of completed transcript files; it does not alter source content.");
}

function inspectDocument(item) {
  showInspector(item.format, item.title, [[item.words, "words"], [item.segments, "segments"], [item.bytes, "source bytes"]], [{ documentId: item.id, excerpt: `Completed ${new Date(item.createdAt).toLocaleString()}` }], item.source);
}

function inspectMatrix(item) {
  if (item.entityId) {
    const entity = state.catalog.entities.find(candidate => candidate.id === item.entityId);
    const documentIds = entity.documentIds.filter(id => state.documentById.get(id)?.source === item.source);
    showInspector(entity.category, `${item.source} × ${entity.name}`, [[item.value, "documents"], [entity.mentions, "total mentions"], [entity.sourceCount, "collections"]], entity.evidence.filter(evidence => documentIds.includes(evidence.documentId)), "This cell measures documents containing the entity in this collection.");
    return;
  }
  const entities = state.catalog.entities.filter(entity => entity.category === item.category && entity.documentIds.some(id => state.documentById.get(id)?.source === item.source));
  showInspector(item.category, `${item.source} × ${label(item.category)}`, [[item.value, "entities"], [new Set(entities.flatMap(entity => entity.documentIds)).size, "documents"]], entities.slice(0, 4).flatMap(entity => entity.evidence.slice(0, 1)), "Distinct published entities with evidence in this collection.");
}

function exportSVG() {
  const svg = $("#chart").cloneNode(true);
  svg.setAttribute("xmlns", NS);
  svg.insertAdjacentHTML("afterbegin", `<style>.chart-label{fill:#111;font-family:"SF Mono","IBM Plex Mono",ui-monospace,monospace;font-size:var(--graph-label-size,12px);font-weight:650;paint-order:stroke;stroke:#f6f5ef;stroke-width:3px;stroke-linejoin:round}.axis-label{fill:#555;font:11px "SF Mono",ui-monospace,monospace}.grid-line{stroke:#111;stroke-opacity:.12}.edge{stroke:#111;stroke-opacity:.28}</style>`);
  const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: "image/svg+xml" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `${state.config.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.svg`; link.click(); URL.revokeObjectURL(link.href);
}

function exportCSV() {
  const fields = state.config.tableColumns.filter(field => TABLE_FIELDS[state.config.tableRole].includes(field));
  const quote = value => `"${String(value).replaceAll('"', '""')}"`;
  const csv = [fields.map(field => quote(label(field))).join(","), ...tableRecords().map(item => fields.map(field => quote(tableDisplayValue(item, field))).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `${state.config.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.csv`; link.click(); URL.revokeObjectURL(link.href);
}

function exportCurrent() {
  if (state.config.type === "table") exportCSV();
  else exportSVG();
}

async function init() {
  try {
    const response = await fetch("data/catalog.json");
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    state.catalog = await response.json();
    state.catalog.documents.forEach(item => state.documentById.set(item.id, item));
    $("#loadingState").remove();
    renderControls(); renderGraph();
  } catch (error) {
    $("#loadingState").innerHTML = `<strong>Catalog unavailable</strong><br><small>${escapeHTML(error.message)}. Serve this folder over HTTP.</small>`;
  }
}

$$('.step-heading').forEach(button => button.addEventListener("click", () => {
  const step = button.closest(".step"); step.classList.toggle("open"); button.setAttribute("aria-expanded", String(step.classList.contains("open")));
}));
$("#graphTitle").addEventListener("blur", event => { state.config.title = event.target.textContent.trim() || "Untitled graph"; persistHash(); });
$("#saveButton").addEventListener("click", () => { localStorage.setItem("ufo-files-graph-view", JSON.stringify(state.config)); toast("View saved in this browser"); });
$("#shareButton").addEventListener("click", async () => { persistHash(); try { await navigator.clipboard.writeText(location.href); toast("Builder link copied"); } catch (_) { toast("Copy the URL from your browser"); } });
$("#exportButton").addEventListener("click", exportCurrent);
$("#resetZoom").addEventListener("click", () => {
  state.config.zoom = 1;
  renderControls();
  commitConfig(false);
});
window.addEventListener("resize", () => { clearTimeout(window.resizeTimer); window.resizeTimer = setTimeout(renderGraph, 120); });

init();
