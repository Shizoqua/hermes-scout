/* The "Try it" playground on the home page. Every result below is copied from the recorded session
   in docs/demo.cast (hermes-scout with nomic-embed-text on the benchmark project); nothing is made up. */
(function () {
  const QUESTIONS = [
    {
      cmd: 'hermes-scout search "how do we keep a copy of the database in case it gets lost"',
      results: [
        ["0.63", "docs/backups.md:1-15", "# Backups and restores", true],
        ["0.57", "src/storage/cache.py:1-19", "Read-through cache in front of the primary store."],
        ["0.54", "notes/meeting-2026-05-12.md:1-15", "# Platform meeting, 12 May"],
      ],
      note: "The question shares no words with docs/backups.md, and it still comes first.",
      keyword: [
        ["src/uploads/images.py:1-16", "Processing for pictures people attach to tasks."],
        ["src/storage/cache.py:1-19", "Read-through cache in front of the primary store."],
        ["notes/hiring.md:1-8", "# Backend engineer interview loop"],
      ],
      keywordNote: "Keyword search alone: docs/backups.md is not in the results at all.",
    },
    {
      cmd: "hermes-scout search E4021",
      results: [
        ["0.56", "src/billing/errors.py:1-17", "Error codes shown to customers on the billing pages.", true],
        ["0.46", "docs/incident-2026-03.md:1-17", "# Postmortem: 14 March outage"],
      ],
      note: "A code name on its own: exact matches come first.",
    },
    {
      cmd: "hermes-scout similar src/auth/tokens.py",
      results: [
        ["0.63", "docs/security.md:1-12", "# Security policy", true],
        ["0.63", "docs/incident-2026-03.md:1-17", "# Postmortem: 14 March outage"],
        ["0.61", "src/client/backoff.py:1-19", "HTTP client helpers: wait and try again when the server pushes back."],
      ],
      note: "Files most related to a file: one result per file, closest first.",
    },
  ];

  function row(score, path, line, best, missed) {
    const li = document.createElement("li");
    if (best) li.className = "sc-best";
    if (missed) li.className = "sc-miss";
    li.innerHTML = '<span class="sc-score"></span><span class="sc-path"></span><span class="sc-line"></span>';
    li.children[0].textContent = score;
    li.children[1].textContent = path;
    li.children[2].textContent = line;
    return li;
  }

  function setup(root) {
    if (root.dataset.ready) return;
    root.dataset.ready = "1";
    const chips = root.querySelectorAll(".sc-chip");
    const cmd = root.querySelector("[data-cmd]");
    const list = root.querySelector("[data-results]");
    const note = root.querySelector("[data-note]");
    const compare = root.querySelector("[data-compare]");
    const compareWrap = root.querySelector("[data-compare-wrap]");
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let current = 0;
    let timers = [];

    function clear() {
      timers.forEach(clearTimeout);
      timers = [];
    }

    function show(index) {
      clear();
      current = index;
      const q = QUESTIONS[index];
      const keyword = compare.checked && q.keyword;
      chips.forEach((c, i) => c.setAttribute("aria-selected", String(i === index)));
      compareWrap.hidden = !q.keyword;
      list.innerHTML = "";
      note.textContent = "";
      note.className = "sc-note";
      const text = keyword ? q.cmd + " --ranking keyword" : q.cmd;
      const rows = keyword
        ? q.keyword.map(([path, line]) => row("  -", path, line, false, true))
        : q.results.map(([score, path, line, best]) => row(score, path, line, best, false));
      if (still) {
        cmd.textContent = text;
        rows.forEach((r) => list.appendChild(r));
        note.textContent = keyword ? q.keywordNote : q.note;
        return;
      }
      cmd.textContent = "";
      let typed = 0;
      const step = Math.max(8, Math.min(22, 900 / text.length));
      (function type() {
        cmd.textContent = text.slice(0, ++typed);
        if (typed < text.length) {
          timers.push(setTimeout(type, step));
          return;
        }
        rows.forEach((r, i) => timers.push(setTimeout(() => list.appendChild(r), 250 + i * 220)));
        timers.push(
          setTimeout(() => {
            note.textContent = keyword ? q.keywordNote : q.note;
            if (keyword) note.className = "sc-note sc-warn";
          }, 300 + rows.length * 220)
        );
      })();
    }

    chips.forEach((chip, i) => chip.addEventListener("click", () => show(i)));
    compare.addEventListener("change", () => show(current));
    show(0);
  }

  function bars() {
    const block = document.querySelector("[data-bars]");
    if (!block || !("IntersectionObserver" in window)) {
      if (block) block.classList.add("sc-on");
      return;
    }
    const seen = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        block.classList.add("sc-on");
        seen.disconnect();
      }
    });
    seen.observe(block);
  }

  function init() {
    document.querySelectorAll("[data-playground]").forEach(setup);
    bars();
  }

  if (window.document$ && typeof window.document$.subscribe === "function") {
    window.document$.subscribe(init);
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
