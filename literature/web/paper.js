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

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const papers = Array.isArray(window.PAPERS) ? window.PAPERS : [];
const paperId = new URLSearchParams(window.location.search).get("id") || "";
const paper = papers.find((item) => item.id === paperId) || null;
const root = document.getElementById("paper");

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function formatDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
  if (!match) return value || "";
  return `${Number(match[3])} ${MONTHS[Number(match[2]) - 1]} ${match[1]}`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inline(text) {
  let line = escapeHtml(text);
  line = line.replace(/`([^`]+)`/g, "<code>$1</code>");
  line = line.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noreferrer">$1</a>',
  );
  line = line.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  line = line.replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  return line;
}

function renderMarkdown(source) {
  const fences = [];
  const text = String(source || "").replace(/\r\n/g, "\n").replace(/```[^\n]*\n([\s\S]*?)```/g, (_, code) => {
    const token = `\u0000FENCE${fences.length}\u0000`;
    fences.push(code.replace(/\n$/, ""));
    return `\n\n${token}\n\n`;
  });
  return text
    .split(/\n{2,}/)
    .map((block) => renderBlock(block.trim(), fences))
    .filter(Boolean)
    .join("\n");
}

function renderBlock(block, fences) {
  const fence = /^\u0000FENCE(\d+)\u0000$/.exec(block);
  if (fence) return `<pre><code>${escapeHtml(fences[Number(fence[1])] || "")}</code></pre>`;
  const lines = block.split("\n");
  if (lines.every((line) => /^#{1,3} /.test(line))) {
    return lines
      .map((line) => {
        const level = /^#+/.exec(line)[0].length;
        return `<h${level}>${inline(line.replace(/^#{1,3} /, ""))}</h${level}>`;
      })
      .join("");
  }
  if (lines.every((line) => /^[-*] /.test(line))) {
    return `<ul>${lines.map((line) => `<li>${inline(line.slice(2))}</li>`).join("")}</ul>`;
  }
  if (lines.every((line) => /^\d+\. /.test(line))) {
    return `<ol>${lines.map((line) => `<li>${inline(line.replace(/^\d+\. /, ""))}</li>`).join("")}</ol>`;
  }
  return `<p>${lines.map((line) => inline(line)).join("<br>")}</p>`;
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

function section(title, text, className) {
  const node = element("section", "section");
  node.append(element("h3", "", title));
  node.append(element("p", className || "", text));
  return node;
}

function addDescription(record) {
  if (paper.why) {
    const title = paper.status === "discarded" ? "Why it was dropped" : "Why it is here";
    root.append(section(title, paper.why));
  }
  if (paper.learn) root.append(section("What the team could use", paper.learn, "learn"));
  if (!record) return;
  if (record.abstract) root.append(section("Abstract", record.abstract));
  else if (record.abstract_missing || paper.abstract_missing) {
    root.append(element("p", "missing", "The abstract was missing, so this was read from the title."));
  }
}

function addSummary(markdown, editable) {
  const block = element("section", "section");
  const head = element("div", "summary-head");
  head.append(element("h2", "", "Your summary"));
  const actions = element("div", "summary-actions");
  head.append(actions);
  const preview = element("div", "markdown");
  const editor = element("div", "summary-edit");
  const input = document.createElement("textarea");
  input.id = "summary";
  input.setAttribute("aria-label", "Your summary, in markdown");
  editor.append(input);
  const state = element("p", "save-state", "");
  let saved = (markdown || "").trim();

  const paint = (text) => {
    preview.innerHTML = text.trim()
      ? renderMarkdown(text)
      : "<p class=\"missing\">Nothing written yet.</p>";
  };
  const showReading = () => {
    editor.hidden = true;
    preview.hidden = false;
    actions.replaceChildren();
    if (editable) actions.append(editButton);
    state.textContent = "";
  };
  const showEditing = () => {
    input.value = saved;
    preview.hidden = true;
    editor.hidden = false;
    saveButton.disabled = false;
    cancelButton.disabled = false;
    actions.replaceChildren(saveButton, cancelButton);
    state.textContent = "";
    input.focus();
  };
  const editButton = element("button", "", "Edit");
  editButton.type = "button";
  editButton.addEventListener("click", showEditing);
  const cancelButton = element("button", "", "Cancel");
  cancelButton.type = "button";
  cancelButton.addEventListener("click", () => {
    input.value = saved;
    paint(saved);
    showReading();
  });
  const saveButton = element("button", "", "Save");
  saveButton.type = "button";
  saveButton.addEventListener("click", async () => {
    if (input.value.trim() === saved) {
      paint(saved);
      showReading();
      return;
    }
    saveButton.disabled = true;
    cancelButton.disabled = true;
    state.textContent = "Saving…";
    try {
      const response = await fetch("api/summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: paper.id, markdown: input.value }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Could not save.");
      saved = body.summary || "";
      paint(saved);
      showReading();
    } catch (error) {
      state.textContent = error.message;
      saveButton.disabled = false;
      cancelButton.disabled = false;
    }
  });

  paint(saved);
  block.append(head);
  if (!editable) {
    block.append(element(
      "p",
      "missing",
      "This page is read-only. Write the summary in the local app, then it is published with the library.",
    ));
  }
  block.append(preview, editor, state);
  showReading();
  root.append(block);
}

function addStored(url, editable) {
  const block = element("section", "section");
  const head = element("div", "summary-head");
  head.append(element("h2", "", "Stored copy"));
  const actions = element("div", "summary-actions");
  head.append(actions);
  const preview = element("p", "stored-link");
  const editor = element("div", "stored-edit");
  const input = document.createElement("input");
  input.type = "url";
  input.id = "file-url";
  input.placeholder = "https://";
  input.setAttribute("aria-label", "URL where this paper is stored");
  editor.append(input);
  const state = element("p", "save-state", "");
  let saved = (url || "").trim();

  const paint = (value) => {
    const href = safeUrl(value);
    preview.replaceChildren();
    if (!href) {
      preview.append(element("span", "missing", "No link yet."));
      return;
    }
    const link = element("a", "", href);
    link.href = href;
    link.target = "_blank";
    link.rel = "noreferrer";
    preview.append(link);
  };
  const showReading = () => {
    editor.hidden = true;
    preview.hidden = false;
    actions.replaceChildren();
    if (editable) actions.append(editButton);
    state.textContent = "";
  };
  const showEditing = () => {
    input.value = saved;
    preview.hidden = true;
    editor.hidden = false;
    saveButton.disabled = false;
    cancelButton.disabled = false;
    actions.replaceChildren(saveButton, cancelButton);
    state.textContent = "";
    input.focus();
  };
  const editButton = element("button", "", "Edit");
  editButton.type = "button";
  editButton.addEventListener("click", showEditing);
  const cancelButton = element("button", "", "Cancel");
  cancelButton.type = "button";
  cancelButton.addEventListener("click", () => {
    input.value = saved;
    paint(saved);
    showReading();
  });
  const saveButton = element("button", "", "Save");
  saveButton.type = "button";
  saveButton.addEventListener("click", async () => {
    if (input.value.trim() === saved) {
      paint(saved);
      showReading();
      return;
    }
    saveButton.disabled = true;
    cancelButton.disabled = true;
    state.textContent = "Saving…";
    try {
      const response = await fetch("api/file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: paper.id, url: input.value }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Could not save.");
      saved = body.url || "";
      paint(saved);
      showReading();
    } catch (error) {
      state.textContent = error.message;
      saveButton.disabled = false;
      cancelButton.disabled = false;
    }
  });

  paint(saved);
  block.append(head);
  if (!editable) {
    block.append(element("p", "missing", "Add the link in the local app."));
  }
  block.append(preview, editor, state);
  showReading();
  root.append(block);
}

function renderHeader() {
  const top = element("p", "badges");
  if (paper.score !== null && paper.score !== undefined) {
    top.append(element("span", "score", `${paper.score}/10`));
  }
  top.append(element("span", `status status-${paper.status}`, STATUSES[paper.status] || paper.status));
  root.append(top);
  const bits = [KINDS[paper.kind], paper.sport].filter(Boolean);
  if (bits.length) root.append(element("p", "meta", bits.join(" · ")));
  root.append(element("h1", "", paper.title));
  document.title = paper.title;
  if (paper.authors) root.append(element("p", "authors", paper.authors));
  const place = [paper.journal, formatDate(paper.published_on)].filter(Boolean).join(" · ");
  if (place) root.append(element("p", "journal-line", place));
  const doi = safeUrl(paper.doi);
  if (doi) {
    const link = element("a", "notes-link", "DOI");
    link.href = doi;
    link.target = "_blank";
    link.rel = "noreferrer";
    root.append(link);
  }
}

async function localRecord() {
  try {
    const status = await fetch("api/status", { cache: "no-store" });
    if (!status.ok) return null;
    const body = await status.json();
    if (!body || body.mode !== "local") return null;
    const response = await fetch(`api/paper?id=${encodeURIComponent(paper.id)}`, { cache: "no-store" });
    if (!response.ok) return { local: true, abstract: "", abstract_missing: true, summary: paper.summary || "" };
    const record = await response.json();
    return { local: true, ...record };
  } catch (error) {
    return null;
  }
}

function showMissing() {
  root.append(element("h1", "", "This paper is not in the library."));
}

async function start() {
  if (!paper) {
    showMissing();
    return;
  }
  renderHeader();
  const record = await localRecord();
  addDescription(record);
  const markdown = (record && record.summary) || paper.summary || "";
  addSummary(markdown, Boolean(record && record.local));
  const fileUrl = (record && record.file_url) || paper.file_url || "";
  addStored(fileUrl, Boolean(record && record.local));
}

start();
