const SAVED_KEY = "literature.saved";
const SEEN_KEY = "literature.seen";

const LECTURES = {
  "energy-systems": {
    label: "Energy systems",
    href: "../cycling-physiology/01-energy-systems.html",
  },
  mitochondria: {
    label: "Mitochondria",
    href: "../cycling-physiology/02-mitochondria.html",
  },
  "not-yet": { label: "Not in the notes yet", href: "" },
};

const KINDS = {
  cycling: "Cycling",
  endurance: "Endurance",
  physiology: "Physiology",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const papers = Array.isArray(window.PAPERS) ? window.PAPERS : [];
const latestRunId = Number.isInteger(window.LATEST_RUN_ID) ? window.LATEST_RUN_ID : null;
let descending = true;

const filters = document.getElementById("filters");
const list = document.getElementById("list");
const count = document.getElementById("count");
const empty = document.getElementById("empty");
const direction = document.getElementById("direction");

function loadSet(key) {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || "[]");
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch (error) {
    return new Set();
  }
}

function storeSet(key, values) {
  localStorage.setItem(key, JSON.stringify([...values]));
}

const saved = loadSet(SAVED_KEY);
const seen = loadSet(SEEN_KEY);

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
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!match) return iso || "";
  return `${Number(match[3])} ${MONTHS[Number(match[2]) - 1]} ${match[1]}`;
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

function haystack(paper) {
  return [paper.title, paper.authors, paper.journal, paper.sport, paper.why, paper.learn]
    .join(" ")
    .toLowerCase();
}

function matches(paper) {
  const query = document.getElementById("search").value.trim().toLowerCase();
  const kind = document.getElementById("kind").value;
  const sport = document.getElementById("sport").value;
  const journal = document.getElementById("journal").value;
  const lecture = document.getElementById("lecture").value;
  const from = document.getElementById("from").value;
  const to = document.getElementById("to").value;
  const minimum = Number(document.getElementById("score").value);
  if (query && !haystack(paper).includes(query)) return false;
  if (kind && paper.kind !== kind) return false;
  if (sport && paper.sport !== sport) return false;
  if (journal && paper.journal !== journal) return false;
  if (lecture && paper.lecture !== lecture) return false;
  if (document.getElementById("latest").checked && paper.run_id !== latestRunId) return false;
  if (document.getElementById("saved-only").checked && !saved.has(paper.id)) return false;
  if (document.getElementById("hide-seen").checked && seen.has(paper.id)) return false;
  if (Number(paper.score) < minimum) return false;
  if (from && (paper.published_on || "") < from) return false;
  if (to && (paper.published_on || "") > to) return false;
  return true;
}

function compare(left, right) {
  const field = document.getElementById("sort").value;
  let delta = 0;
  if (field === "score") delta = Number(left.score) - Number(right.score);
  else if (field === "journal" || field === "title") {
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

function renderCard(paper) {
  const card = element("article", "card");
  if (seen.has(paper.id)) card.classList.add("is-seen");

  const top = element("div", "card-top");
  top.append(element("p", "score", `${paper.score}/10`));
  const bits = [KINDS[paper.kind], paper.sport].filter(Boolean);
  if (bits.length) top.append(element("p", "meta", bits.join(" · ")));
  card.append(top);

  card.append(element("h2", "", paper.title));
  if (paper.authors) card.append(element("p", "authors", paper.authors));
  const place = [paper.journal, formatDate(paper.published_on)].filter(Boolean).join(" · ");
  if (place) card.append(element("p", "journal-line", place));
  if (paper.abstract_missing) {
    card.append(element("p", "missing", "The abstract was missing, so this was read from the title."));
  }

  if (paper.why) {
    const why = element("section", "section");
    why.append(element("h3", "", "Why it is here"));
    why.append(element("p", "", paper.why));
    card.append(why);
  }
  if (paper.learn) {
    const learn = element("section", "section");
    learn.append(element("h3", "", "What you could learn"));
    learn.append(element("p", "learn", paper.learn));
    card.append(learn);
  }

  const lecture = LECTURES[paper.lecture];
  if (lecture && lecture.href) {
    const link = element("a", "", lecture.label);
    link.href = lecture.href;
    const where = element("section", "section");
    where.append(element("h3", "", "Where it sits"));
    where.append(link);
    card.append(where);
  } else if (paper.lecture === "not-yet") {
    const where = element("section", "section");
    where.append(element("h3", "", "Where it sits"));
    where.append(element("p", "", "Not in the notes yet."));
    card.append(where);
  }

  const actions = element("div", "actions");
  const save = element("button", saved.has(paper.id) ? "is-on" : "", saved.has(paper.id) ? "Saved" : "Save");
  save.type = "button";
  save.setAttribute("aria-pressed", saved.has(paper.id) ? "true" : "false");
  save.dataset.action = "save";
  save.dataset.id = paper.id;

  const mark = element("button", seen.has(paper.id) ? "is-on" : "", seen.has(paper.id) ? "Seen" : "Mark seen");
  mark.type = "button";
  mark.setAttribute("aria-pressed", seen.has(paper.id) ? "true" : "false");
  mark.dataset.action = "seen";
  mark.dataset.id = paper.id;

  const copy = element("button", "", "Copy citation");
  copy.type = "button";
  copy.dataset.action = "copy";
  copy.dataset.id = paper.id;

  actions.append(save, mark, copy);
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

function render() {
  document.getElementById("score-value").textContent = document.getElementById("score").value;
  direction.textContent = directionLabel();
  const shown = papers.filter(matches).sort(compare);
  count.textContent = `Showing ${shown.length} of ${papers.length}.`;
  list.replaceChildren(...shown.map(renderCard));
  if (shown.length) {
    empty.hidden = true;
    return;
  }
  empty.hidden = false;
  empty.textContent = papers.length
    ? "Nothing matches these filters."
    : "No papers have been classified yet.";
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

fillSelect("sport", unique("sport"));
fillSelect("journal", unique("journal"));
if (latestRunId === null) {
  document.getElementById("latest").disabled = true;
} else {
  document.getElementById("latest").checked = true;
}

filters.addEventListener("input", render);
filters.addEventListener("change", render);
document.getElementById("sort").addEventListener("change", () => {
  const field = document.getElementById("sort").value;
  descending = field === "published_on" || field === "score";
});
direction.addEventListener("click", () => {
  descending = !descending;
  render();
});

list.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const id = button.dataset.id;
  if (button.dataset.action === "save") {
    if (saved.has(id)) saved.delete(id);
    else saved.add(id);
    storeSet(SAVED_KEY, saved);
    render();
  } else if (button.dataset.action === "seen") {
    if (seen.has(id)) seen.delete(id);
    else seen.add(id);
    storeSet(SEEN_KEY, seen);
    render();
  } else if (button.dataset.action === "copy") {
    const paper = papers.find((item) => item.id === id);
    if (!paper) return;
    await copyText(citation(paper));
    button.textContent = "Copied";
    window.setTimeout(() => {
      button.textContent = "Copy citation";
    }, 1500);
  }
});

render();
