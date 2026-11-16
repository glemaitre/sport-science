const LEGACY_SAVED_KEY = "literature.saved";
const LEGACY_SEEN_KEY = "literature.seen";
const PENDING_KEY = "literature.pending";
const LIST_KEY = "literature.list";
const PAGE_SIZE = 10;

const KINDS = {
  cycling: "Cycling",
  endurance: "Endurance",
  physiology: "Physiology",
};

const STATUSES = {
  "of-interest": "Of interest",
  discarded: "Discarded",
  unclassified: "Unclassified",
};

const TRIAGE = {
  "to-read": "To read",
  read: "Read",
  useful: "Useful",
  "not-relevant": "Not relevant",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const papers = Array.isArray(window.PAPERS) ? window.PAPERS : [];
const byId = new Map(papers.map((paper) => [paper.id, paper]));
const latestRunId = Number.isInteger(window.LATEST_RUN_ID) ? window.LATEST_RUN_ID : null;
let library = window.LIBRARY || {};
let local = false;
let descending = true;
let page = 1;

const filters = document.getElementById("filters");
const list = document.getElementById("list");
const count = document.getElementById("count");
const empty = document.getElementById("empty");
const pagers = ["pager-top", "pager-bottom"].map((id) => document.getElementById(id));
const direction = document.getElementById("direction");

function loadJson(key, fallback) {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || "null");
    return parsed === null ? fallback : parsed;
  } catch (error) {
    return fallback;
  }
}

const pending = loadJson(PENDING_KEY, {});

function storePending() {
  localStorage.setItem(PENDING_KEY, JSON.stringify(pending));
}

function triageOf(paper) {
  if (!local && Object.prototype.hasOwnProperty.call(pending, paper.id)) return pending[paper.id];
  return paper.triage || "";
}

function unique(field) {
  return [...new Set(papers.map((paper) => paper[field]).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, undefined, { sensitivity: "base" })
  );
}

function fillSelect(id, values) {
  const select = document.getElementById(id);
  const current = select.value;
  select.replaceChildren(new Option("Any", ""));
  values.forEach((value) => select.append(new Option(value, value)));
  if (values.includes(current)) select.value = current;
}

function formatDate(iso) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  if (!match) return iso || "";
  return `${Number(match[3])} ${MONTHS[Number(match[2]) - 1]} ${match[1]}`;
}

function formatCount(value) {
  return Number(value || 0).toLocaleString("en-GB");
}

function directionLabel() {
  const field = document.getElementById("sort").value;
  if (field === "score") return descending ? "Highest first" : "Lowest first";
  if (field === "published_on") return descending ? "Newest first" : "Oldest first";
  return descending ? "Z to A" : "A to Z";
}

function citation(paper) {
  const parts = [];
  if (paper.authors && paper.year) parts.push(`${paper.authors} (${paper.year}).`);
  else if (paper.authors) parts.push(`${paper.authors}.`);
  else if (paper.year) parts.push(`(${paper.year}).`);
  if (paper.title) parts.push(`${paper.title}.`);
  if (paper.doi) parts.push(paper.doi);
  return parts.join(" ");
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol === "https:" || url.protocol === "http:") return url.href;
  } catch (error) {
    return "";
  }
  return "";
}

function paperHref(id) {
  const url = new URL("paper.html", "http://local/");
  url.searchParams.set("id", id);
  return `paper.html${url.search}`;
}

function haystack(paper) {
  return [paper.title, paper.authors, paper.journal, paper.sport, paper.why, paper.learn, paper.summary, paper.file_url]
    .join(" ")
    .toLowerCase();
}

function matches(paper) {
  const query = document.getElementById("search").value.trim().toLowerCase();
  const status = document.getElementById("status").value;
  const triage = document.getElementById("triage").value;
  const kind = document.getElementById("kind").value;
  const sport = document.getElementById("sport").value;
  const journal = document.getElementById("journal").value;
  const from = document.getElementById("from").value;
  const to = document.getElementById("to").value;
  const minimum = Number(document.getElementById("score").value);
  const mark = triageOf(paper);
  if (status === "of-interest") {
    if (paper.status !== "of-interest" && mark !== "useful") return false;
  } else if (status && paper.status !== status) return false;
  if (triage === "none" && mark) return false;
  if (triage && triage !== "none" && mark !== triage) return false;
  if (document.getElementById("hide-done").checked && (mark === "read" || mark === "not-relevant")) {
    return false;
  }
  if (query && !haystack(paper).includes(query)) return false;
  if (kind && paper.kind !== kind) return false;
  if (sport && paper.sport !== sport) return false;
  if (journal && paper.journal !== journal) return false;
  if (status !== "unclassified" && document.getElementById("latest").checked && paper.run_id !== latestRunId) {
    return false;
  }
  if (minimum > 0 && (paper.score === null || Number(paper.score) < minimum)) return false;
  if (from && (paper.published_on || "") < from) return false;
  if (to && (paper.published_on || "") > to) return false;
  return true;
}

function compare(left, right) {
  const field = document.getElementById("sort").value;
  let delta = 0;
  if (field === "score") {
    delta = (left.score === null ? -1 : Number(left.score)) - (right.score === null ? -1 : Number(right.score));
  } else if (field === "journal" || field === "title") {
    delta = String(left[field] || "").localeCompare(String(right[field] || ""), undefined, {
      sensitivity: "base",
    });
  } else delta = String(left.published_on || "").localeCompare(String(right.published_on || ""));
  if (delta === 0) delta = String(left.title || "").localeCompare(String(right.title || ""));
  return descending ? -delta : delta;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function section(title, text, className) {
  const node = element("section", "section");
  node.append(element("h3", "", title));
  node.append(element("p", className || "", text));
  return node;
}

function renderCard(paper) {
  const mark = triageOf(paper);
  const card = element("article", "card");
  if (mark === "read" || mark === "not-relevant") card.classList.add("is-done");

  const top = element("div", "card-top");
  const badges = element("p", "badges");
  if (paper.score !== null && paper.score !== undefined) {
    badges.append(element("span", "score", `${paper.score}/10`));
  }
  badges.append(element("span", `status status-${paper.status}`, STATUSES[paper.status] || paper.status));
  if (mark) badges.append(element("span", "mark", TRIAGE[mark] || mark));
  top.append(badges);
  const bits = [KINDS[paper.kind], paper.sport].filter(Boolean);
  if (bits.length) top.append(element("p", "meta", bits.join(" · ")));
  card.append(top);

  const heading = element("h2");
  const title = element("a", "card-title", paper.title);
  title.href = paperHref(paper.id);
  heading.append(title);
  card.append(heading);
  card.addEventListener("click", (event) => {
    if (event.target.closest("button, a")) return;
    window.location.href = title.href;
  });
  if (paper.authors) card.append(element("p", "authors", paper.authors));
  const place = [paper.journal, formatDate(paper.published_on)].filter(Boolean).join(" · ");
  if (place) card.append(element("p", "journal-line", place));
  if (paper.status === "unclassified") {
    card.append(element("p", "missing", "Waiting for the model."));
  } else if (paper.abstract_missing) {
    card.append(element("p", "missing", "The abstract was missing, so this was read from the title."));
  }

  if (paper.why) {
    const title = paper.status === "discarded" ? "Why it was dropped" : "Why it is here";
    card.append(section(title, paper.why));
  }
  if (paper.learn) card.append(section("What the team could use", paper.learn, "learn"));

  const actions = element("div", "actions");
  const group = element("div", "triage");
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", "Your triage");
  Object.entries(TRIAGE).forEach(([value, label]) => {
    const on = mark === value;
    const button = element("button", on ? "is-on" : "", label);
    button.type = "button";
    button.setAttribute("aria-pressed", on ? "true" : "false");
    button.dataset.action = "triage";
    button.dataset.value = value;
    button.dataset.id = paper.id;
    group.append(button);
  });
  actions.append(group);

  const copy = element("button", "", "Copy citation");
  copy.type = "button";
  copy.dataset.action = "copy";
  copy.dataset.id = paper.id;
  actions.append(copy);
  const doi = safeUrl(paper.doi);
  if (doi) {
    const link = element("a", "", "DOI");
    link.href = doi;
    link.target = "_blank";
    link.rel = "noreferrer";
    actions.append(link);
  }
  card.append(actions);
  return card;
}

function renderLibrary() {
  const counts = library.counts || {};
  const parts = [
    `${formatCount(counts["of-interest"])} of interest`,
    `${formatCount(counts.discarded)} discarded`,
    `${formatCount(counts.unclassified)} waiting for the model`,
  ];
  let text = `${parts.join(" · ")}.`;
  if (library.covered_from && library.covered_through) {
    text += ` Every journal is read from ${formatDate(library.covered_from)} to ${formatDate(library.covered_through)}.`;
    if (library.start_date && library.covered_from > library.start_date) {
      text += ` Older months back to ${formatDate(library.start_date)} are still being read.`;
    }
  } else if (library.start_date) {
    text += ` Some journals have not been read yet. The start date is ${formatDate(library.start_date)}.`;
  }
  document.getElementById("backlog").textContent = text;
}

function renderPending() {
  const box = document.getElementById("pending");
  const size = Object.keys(pending).length;
  box.hidden = local || size === 0;
  document.getElementById("pending-count").textContent =
    `${size} triage ${size === 1 ? "mark is" : "marks are"} only in this browser. Export them, then run python -m literature triage PATH.`;
}

function pageWindow(current, pages) {
  const wanted = new Set([1, pages, current - 2, current - 1, current, current + 1, current + 2]);
  const items = [];
  let previous = 0;
  for (let number = 1; number <= pages; number += 1) {
    if (!wanted.has(number)) continue;
    if (previous && number - previous > 1) items.push("…");
    items.push(number);
    previous = number;
  }
  return items;
}

function pageButton(label, target, disabled) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.disabled = disabled;
  if (!disabled) {
    button.addEventListener("click", () => {
      page = target;
      render();
      count.scrollIntoView({ block: "start" });
    });
  }
  return button;
}

function renderPager(pages) {
  for (const nav of pagers) {
    nav.replaceChildren();
    nav.hidden = pages <= 1;
    if (pages <= 1) continue;
    nav.append(pageButton("Previous", page - 1, page === 1));
    for (const item of pageWindow(page, pages)) {
      if (item === "…") {
        const gap = document.createElement("span");
        gap.className = "pager-gap";
        gap.textContent = "…";
        nav.append(gap);
        continue;
      }
      const button = pageButton(String(item), item, item === page);
      if (item === page) {
        button.classList.add("is-on");
        button.setAttribute("aria-current", "page");
      }
      nav.append(button);
    }
    nav.append(pageButton("Next", page + 1, page === pages));
  }
}

function render() {
  document.getElementById("latest").disabled =
    latestRunId === null || document.getElementById("status").value === "unclassified";
  document.getElementById("score-value").textContent = document.getElementById("score").value;
  direction.textContent = directionLabel();
  const shown = papers.filter(matches).sort(compare);
  const pages = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  if (page > pages) page = pages;
  if (page < 1) page = 1;
  const start = (page - 1) * PAGE_SIZE;
  const visible = shown.slice(start, start + PAGE_SIZE);
  count.textContent = shown.length
    ? `Showing ${formatCount(start + 1)}–${formatCount(start + visible.length)} of ${formatCount(shown.length)}.`
    : `Showing 0 of ${formatCount(papers.length)}.`;
  list.replaceChildren(...visible.map(renderCard));
  renderPager(shown.length ? pages : 0);
  renderPending();
  saveListState();
  if (shown.length) {
    empty.hidden = true;
    return;
  }
  empty.hidden = false;
  empty.textContent = papers.length ? "Nothing matches these filters." : "No papers have been fetched yet.";
}

async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch (error) {
    // The page falls back to selecting a text field when the clipboard is blocked.
  }
  const area = document.createElement("textarea");
  area.value = text;
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `The app answered ${response.status}.`);
  return data;
}

async function setMark(paper, value) {
  if (local) {
    await postJson("api/triage", { id: paper.id, status: value });
    paper.triage = value;
    return;
  }
  if (value === (paper.triage || "")) delete pending[paper.id];
  else pending[paper.id] = value;
  storePending();
}

function legacyMarks() {
  const saved = loadJson(LEGACY_SAVED_KEY, []);
  const seen = loadJson(LEGACY_SEEN_KEY, []);
  const marks = {};
  (Array.isArray(saved) ? saved : []).forEach((id) => {
    marks[id] = "to-read";
  });
  (Array.isArray(seen) ? seen : []).forEach((id) => {
    marks[id] = "read";
  });
  return Object.fromEntries(Object.entries(marks).filter(([id]) => byId.has(id)));
}

function renderLegacy() {
  const marks = legacyMarks();
  const size = Object.keys(marks).length;
  document.getElementById("legacy").hidden = size === 0;
  document.getElementById("legacy-count").textContent =
    `This browser has ${size} Saved or Seen ${size === 1 ? "mark" : "marks"} from the old page. Saved becomes To read and Seen becomes Read.`;
}

async function importLegacy() {
  const marks = legacyMarks();
  for (const [id, value] of Object.entries(marks)) {
    const paper = byId.get(id);
    if (!paper || triageOf(paper)) continue;
    await setMark(paper, value);
  }
  localStorage.removeItem(LEGACY_SAVED_KEY);
  localStorage.removeItem(LEGACY_SEEN_KEY);
  renderLegacy();
  render();
}

function exportPending() {
  const blob = new Blob([JSON.stringify({ triage: pending }, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "triage.json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

function monthBefore(today) {
  const year = today.getMonth() === 0 ? today.getFullYear() - 1 : today.getFullYear();
  const monthIndex = today.getMonth() === 0 ? 11 : today.getMonth() - 1;
  const lastDay = new Date(year, monthIndex + 1, 0).getDate();
  return new Date(year, monthIndex, Math.min(today.getDate(), lastDay));
}

function isoDate(value) {
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}

function waitingCount() {
  return Number((library.counts || {}).unclassified) || 0;
}

function updateWaiting() {
  const waiting = waitingCount();
  const line = document.getElementById("waiting");
  line.textContent = waiting === 1
    ? "1 paper needs classification."
    : `${formatCount(waiting)} papers need classification.`;
  const classify = document.getElementById("classify-start");
  if (classify && !classify.dataset.busy) classify.disabled = waiting === 0;
}

function setJobButtons(running) {
  const fetchButton = document.getElementById("fetch-start");
  const classifyButton = document.getElementById("classify-start");
  if (running) {
    fetchButton.disabled = true;
    classifyButton.disabled = true;
    classifyButton.dataset.busy = "1";
    return;
  }
  delete classifyButton.dataset.busy;
  fetchButton.disabled = false;
  classifyButton.disabled = waitingCount() === 0;
}

function showJob(job) {
  const line = document.getElementById("job");
  if (!job) {
    line.hidden = true;
    setJobButtons(false);
    return;
  }
  const last = (job.log || []).filter(Boolean).slice(-1)[0] || "Starting.";
  const kind = job.kind || "backfill";
  line.hidden = false;
  if (job.state === "running") {
    line.textContent = kind === "fetch"
      ? `Fetching papers from ${formatDate(job.since)}. ${last}`
      : `Classifying papers that are waiting. ${last}`;
    setJobButtons(true);
  } else if (job.state === "done") {
    line.textContent = `Finished. ${last}`;
    setJobButtons(false);
  } else {
    const step = kind === "fetch" ? "fetch" : "classification";
    line.textContent = `The ${step} stopped with an error. ${last}`;
    setJobButtons(false);
  }
}

async function pollJob(id) {
  const response = await fetch(`api/jobs/${id}`, { cache: "no-store" });
  if (!response.ok) return;
  const job = await response.json();
  showJob(job);
  if (job.state === "running") {
    window.setTimeout(() => pollJob(id), 2000);
  } else if (job.state === "done") {
    window.setTimeout(() => window.location.reload(), 1200);
  }
}

async function detectApp() {
  try {
    const response = await fetch("api/status", { cache: "no-store" });
    if (!response.ok) return null;
    const data = await response.json();
    return data && data.mode === "local" ? data : null;
  } catch (error) {
    return null;
  }
}

function setUpLocal(status) {
  local = true;
  library = status.library || library;
  document.getElementById("notes-link").hidden = true;
  document.getElementById("published").hidden = true;
  const since = document.getElementById("backfill-since");
  const today = new Date();
  since.min = isoDate(monthBefore(today));
  since.max = isoDate(today);
  since.value = since.min;
  document.getElementById("backfill").hidden = false;
  updateWaiting();
  if (status.job) {
    showJob(status.job);
    if (status.job.state === "running") pollJob(status.job.id);
  }
}

function fieldValue(id) {
  const node = document.getElementById(id);
  return node ? node.value : "";
}

function saveListState() {
  try {
    sessionStorage.setItem(
      LIST_KEY,
      JSON.stringify({
        search: fieldValue("search"),
        status: fieldValue("status"),
        triage: fieldValue("triage"),
        hideDone: document.getElementById("hide-done").checked,
        kind: fieldValue("kind"),
        sport: fieldValue("sport"),
        journal: fieldValue("journal"),
        latest: document.getElementById("latest").checked,
        score: fieldValue("score"),
        from: fieldValue("from"),
        to: fieldValue("to"),
        sort: fieldValue("sort"),
        descending,
        page,
      }),
    );
  } catch (error) {
    // A blocked session store still leaves the list usable.
  }
}

function restoreListState() {
  let state = null;
  try {
    state = JSON.parse(sessionStorage.getItem(LIST_KEY) || "null");
  } catch (error) {
    state = null;
  }
  if (!state || typeof state !== "object") return;
  ["search", "status", "triage", "kind", "sport", "journal", "score", "from", "to", "sort"].forEach((id) => {
    const node = document.getElementById(id);
    if (node && typeof state[id] === "string") node.value = state[id];
  });
  if (typeof state.hideDone === "boolean") document.getElementById("hide-done").checked = state.hideDone;
  if (typeof state.latest === "boolean") document.getElementById("latest").checked = state.latest;
  if (typeof state.descending === "boolean") descending = state.descending;
  if (Number.isInteger(state.page) && state.page > 0) page = state.page;
}

fillSelect("sport", unique("sport"));
fillSelect("journal", unique("journal"));
if (latestRunId !== null) document.getElementById("latest").checked = true;
restoreListState();

filters.addEventListener("input", () => {
  page = 1;
  render();
});
filters.addEventListener("change", () => {
  page = 1;
  render();
});
document.getElementById("sort").addEventListener("change", () => {
  const field = document.getElementById("sort").value;
  descending = field === "published_on" || field === "score";
});
direction.addEventListener("click", () => {
  descending = !descending;
  page = 1;
  render();
});
document.getElementById("export").addEventListener("click", exportPending);
document.getElementById("clear-pending").addEventListener("click", () => {
  Object.keys(pending).forEach((id) => delete pending[id]);
  storePending();
  render();
});
document.getElementById("legacy-import").addEventListener("click", () => {
  importLegacy().catch((error) => window.alert(error.message));
});
document.getElementById("stats-toggle").addEventListener("click", () => {
  const backlog = document.getElementById("backlog");
  const toggle = document.getElementById("stats-toggle");
  const open = backlog.hidden;
  backlog.hidden = !open;
  toggle.textContent = open ? "Less" : "More";
  toggle.setAttribute("aria-expanded", open ? "true" : "false");
});

async function startFetch() {
  const since = document.getElementById("backfill-since").value;
  if (!since) return;
  try {
    const job = await postJson("api/fetch", { since });
    showJob({ ...job, log: [], kind: "fetch" });
    pollJob(job.id);
  } catch (error) {
    const line = document.getElementById("job");
    line.hidden = false;
    line.textContent = error.message;
  }
}

document.getElementById("backfill").addEventListener("submit", (event) => {
  event.preventDefault();
  startFetch();
});
document.getElementById("classify-start").addEventListener("click", async () => {
  try {
    const job = await postJson("api/classify", {});
    showJob({ ...job, log: [], kind: "classify" });
    pollJob(job.id);
  } catch (error) {
    const line = document.getElementById("job");
    line.hidden = false;
    line.textContent = error.message;
  }
});

list.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const paper = byId.get(button.dataset.id);
  if (!paper) return;
  if (button.dataset.action === "triage") {
    const value = triageOf(paper) === button.dataset.value ? "" : button.dataset.value;
    try {
      await setMark(paper, value);
    } catch (error) {
      window.alert(error.message);
      return;
    }
    render();
  } else if (button.dataset.action === "copy") {
    await copyText(citation(paper));
    button.textContent = "Copied";
    window.setTimeout(() => {
      button.textContent = "Copy citation";
    }, 1500);
  }
});

renderLibrary();
render();
detectApp().then((status) => {
  if (status) setUpLocal(status);
  else document.getElementById("published").hidden = false;
  renderLibrary();
  renderLegacy();
  render();
});
