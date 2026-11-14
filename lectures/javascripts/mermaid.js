// Material loads Mermaid from unpkg and initializes it once. Mermaid 11 no longer
// matches the theme stylesheet Material injects, so diagrams keep dark text and
// disappear on the dark page. This patches initialize before that first call,
// and redraws a diagram when the palette changes.
(function () {
  function themeConfig() {
    var dark = document.body.getAttribute("data-md-color-scheme") === "slate";
    if (dark) {
      return {
        theme: "base",
        themeVariables: {
          darkMode: true,
          background: "transparent",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
          primaryColor: "#1f6f6a",
          primaryTextColor: "#f7f4ee",
          primaryBorderColor: "#9fd4cf",
          secondaryColor: "#3f3a34",
          secondaryTextColor: "#f7f4ee",
          tertiaryColor: "#243330",
          tertiaryTextColor: "#f7f4ee",
          lineColor: "#e7e5e4",
          textColor: "#f7f4ee",
          mainBkg: "#1f6f6a",
          nodeBorder: "#9fd4cf",
          clusterBkg: "#1a2422",
          clusterBorder: "#5eead4",
          titleColor: "#f7f4ee",
          edgeLabelBackground: "#121816",
          nodeTextColor: "#f7f4ee"
        }
      };
    }
    return {
      theme: "base",
      themeVariables: {
        darkMode: false,
        background: "transparent",
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
        primaryColor: "#e5f2f0",
        primaryTextColor: "#1e2930",
        primaryBorderColor: "#1f6f6a",
        secondaryColor: "#efe6d6",
        secondaryTextColor: "#1e2930",
        tertiaryColor: "#fffdf8",
        tertiaryTextColor: "#1e2930",
        lineColor: "#1e2930",
        textColor: "#1e2930",
        mainBkg: "#e5f2f0",
        nodeBorder: "#1f6f6a",
        clusterBkg: "#f7f4ee",
        clusterBorder: "#1f6f6a",
        titleColor: "#1e2930",
        edgeLabelBackground: "#f7f4ee",
        nodeTextColor: "#1e2930"
      }
    };
  }

  function patch(mermaid) {
    if (!mermaid || mermaid.__themed || typeof mermaid.initialize !== "function") return;
    var real = mermaid.initialize.bind(mermaid);
    mermaid.initialize = function (config) {
      real(Object.assign({}, config || {}, themeConfig(), { startOnLoad: false }));
    };
    mermaid.__themed = true;
  }

  var current = window.mermaid;
  try {
    Object.defineProperty(window, "mermaid", {
      configurable: true,
      enumerable: true,
      get: function () { return current; },
      set: function (value) {
        current = value;
        patch(value);
      }
    });
  } catch (err) {
    if (current) patch(current);
  }
  if (current) patch(current);

  function remember(pre) {
    if (pre && pre.dataset && !pre.dataset.diagram) pre.dataset.diagram = pre.textContent;
  }

  document.querySelectorAll("pre.mermaid").forEach(remember);

  new MutationObserver(function (records) {
    records.forEach(function (record) {
      record.addedNodes.forEach(function (node) {
        if (node.nodeType !== 1) return;
        if (node.matches && node.matches("pre.mermaid")) remember(node);
        if (node.querySelectorAll) node.querySelectorAll("pre.mermaid").forEach(remember);
      });
      record.removedNodes.forEach(function (node) {
        if (node.nodeType !== 1 || !node.dataset || !node.dataset.diagram) return;
        record.addedNodes.forEach(function (added) {
          if (added.nodeType === 1 && added.classList && added.classList.contains("mermaid")) {
            added.dataset.diagram = node.dataset.diagram;
          }
        });
      });
    });
  }).observe(document.body, { childList: true, subtree: true });

  var scheme = document.body.getAttribute("data-md-color-scheme");
  new MutationObserver(function () {
    var next = document.body.getAttribute("data-md-color-scheme");
    if (next === scheme || !window.mermaid) return;
    scheme = next;
    window.mermaid.initialize({ startOnLoad: false });
    document.querySelectorAll("[data-diagram]").forEach(function (el) {
      if (el.tagName === "PRE") return;
      var id = "mermaid_redraw_" + Math.random().toString(36).slice(2);
      window.mermaid.render(id, el.dataset.diagram).then(function (result) {
        var host = document.createElement("div");
        host.className = "mermaid";
        host.dataset.diagram = el.dataset.diagram;
        host.innerHTML = result.svg;
        el.replaceWith(host);
      }).catch(function (err) {
        console.error(err);
      });
    });
  }).observe(document.body, { attributes: true, attributeFilter: ["data-md-color-scheme"] });
})();
