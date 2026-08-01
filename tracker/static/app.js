/* Subject Tracker — client-side enhancements: theme, count-up, reveal, charts. */
(function () {
  "use strict";

  // --- Theme ---------------------------------------------------------------
  const root = document.documentElement;

  function currentTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function setTheme(theme) {
    root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("theme", theme);
    } catch (e) {}
    redrawCharts(); // recolor charts to match the new theme
  }

  function toggleTheme() {
    setTheme(currentTheme() === "dark" ? "light" : "dark");
  }

  // Read a CSS custom property so charts always match the active theme.
  function cssVar(name) {
    return getComputedStyle(root).getPropertyValue(name).trim();
  }

  function themeColors() {
    return {
      done: cssVar("--accent-2") || "#16a34a",
      blue: cssVar("--accent") || "#3b6cf6",
      amber: cssVar("--amber") || "#f59e0b",
      violet: cssVar("--violet") || "#7c3aed",
      track: cssVar("--chart-track") || "rgba(148,163,184,0.25)",
      grid: cssVar("--chart-grid") || "rgba(148,163,184,0.2)",
      text: cssVar("--muted") || "#6b7280",
    };
  }

  // --- Format minutes as "Xh Ym" (130 -> "2h 10m", 30 -> "30m", 0 -> "0m") -
  function formatHM(minutes) {
    const total = Math.round(minutes);
    const h = Math.floor(total / 60);
    const m = total - h * 60;
    if (h && m) return h + "h " + m + "m";
    if (h) return h + "h";
    return m + "m";
  }

  // --- Count-up animation for elements with .count[data-to] ---------------
  // data-format="hm": interpret data-to as MINUTES and render as "Xh Ym".
  function animateCount(el) {
    const to = parseFloat(el.dataset.to || "0");
    const decimals = parseInt(el.dataset.decimals || "0", 10);
    const asHM = el.dataset.format === "hm";
    const render = (v) => (asHM ? formatHM(v) : v.toFixed(decimals));
    const duration = 900;
    const start = performance.now();
    function frame(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      el.textContent = render(to * eased);
      if (t < 1) requestAnimationFrame(frame);
      else el.textContent = render(to);
    }
    requestAnimationFrame(frame);
  }

  // --- Reveal-on-scroll for .reveal elements ------------------------------
  function setupReveal() {
    const items = document.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window)) {
      items.forEach((el) => el.classList.add("is-visible"));
      return;
    }
    const obs = new IntersectionObserver(
      (entries, observer) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 }
    );
    items.forEach((el) => obs.observe(el));
  }

  function runCounts() {
    document.querySelectorAll(".count").forEach(animateCount);
  }

  // --- Date inputs: open the native picker on click anywhere in the field --
  // Natively only the small calendar icon opens the popup; this makes the
  // whole field clickable, which is what users expect.
  function setupDatePickers() {
    document.addEventListener("click", function (event) {
      const el = event.target;
      if (el && el.matches && el.matches('input[type="date"]')) {
        if (typeof el.showPicker === "function") {
          try {
            el.showPicker();
          } catch (e) {
            /* not user-activated / unsupported — ignore, native focus still works */
          }
        }
      }
    });
  }

  // Chart tooltip: values are in hours; show them as "Xh Ym".
  function hmTooltip(context) {
    const parsed = context.parsed;
    const hours = parsed && typeof parsed === "object" ? parsed.y : parsed;
    const name = context.dataset.label || context.label || "";
    const text = formatHM(hours * 60);
    return name ? name + ": " + text : text;
  }
  const hmTooltipPlugin = { callbacks: { label: hmTooltip } };

  // --- Completed-time controls (plan pages) -------------------------------
  // Inline validation (no popups): minutes 0-59, and hours*60 + minutes must not
  // exceed the chapter length. Valid changes auto-save on blur via AJAX; the
  // "Done" checkbox instantly completes (or clears) the chapter. The UI updates
  // in place — no page reload. A <noscript> Save button is the no-JS fallback.
  function setupCompletionForms() {
    document.querySelectorAll(".completion-form").forEach(function (form) {
      const hEl = form.querySelector('input[name="completed_hours"]');
      const mEl = form.querySelector('input[name="completed_minutes"]');
      const err = form.querySelector(".field-error");
      const checkbox = form.querySelector(".done-toggle");
      if (!hEl || !mEl || !err) return;
      const duration = parseInt(form.dataset.duration || "0", 10);
      let lastTotal = clampInt(hEl.value) * 60 + clampInt(mEl.value);

      function setInvalid(el, on) {
        el.classList.toggle("input-invalid", on);
        el.setAttribute("aria-invalid", on ? "true" : "false");
      }

      function validate() {
        const h = parseInt(hEl.value || "0", 10);
        const m = parseInt(mEl.value || "0", 10);
        let message = "";
        let badH = false;
        let badM = false;
        if (isNaN(h) || isNaN(m) || h < 0 || m < 0) {
          message = "Enter valid numbers";
          badH = isNaN(h) || h < 0;
          badM = isNaN(m) || m < 0;
        } else if (m > 59) {
          message = "Minutes must be 0–59";
          badM = true;
        } else if (h * 60 + m > duration) {
          message = "Can't exceed " + formatHM(duration);
          badH = true;
          badM = true;
        }
        err.textContent = message;
        err.hidden = !message;
        setInvalid(hEl, badH);
        setInvalid(mEl, badM);
        return !message;
      }

      function applyResult(data) {
        lastTotal = data.completed_minutes;
        hEl.value = data.completed_h;
        mEl.value = data.completed_m;
        if (checkbox) checkbox.checked = data.is_done;
        const item = form.closest(".plan-item");
        if (item) {
          item.classList.toggle("done", data.is_done);
          const label = item.querySelector(".item-progress");
          if (label) {
            label.textContent =
              data.completed_hm + " / " + data.total_hm + " (" + data.percent + "%)";
          }
        }
      }

      function save() {
        if (!validate()) return;
        const body = new FormData();
        body.append("completed_hours", hEl.value || "0");
        body.append("completed_minutes", mEl.value || "0");
        fetch(form.action, {
          method: "POST",
          headers: { "X-Requested-With": "XMLHttpRequest" },
          body: body,
        })
          .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
          .then(applyResult)
          .catch(function () {
            /* network error — leave inputs as-is; user can retry */
          });
      }

      function saveIfChanged() {
        if (validate() && clampInt(hEl.value) * 60 + clampInt(mEl.value) !== lastTotal) {
          save();
        }
      }

      hEl.addEventListener("input", validate);
      mEl.addEventListener("input", validate);
      hEl.addEventListener("blur", saveIfChanged);
      mEl.addEventListener("blur", saveIfChanged);

      if (checkbox) {
        checkbox.addEventListener("change", function () {
          const target = checkbox.checked ? duration : 0;
          hEl.value = Math.floor(target / 60);
          mEl.value = target % 60;
          save();
        });
      }

      // No-JS fallback: the noscript button submits normally, so block only when
      // scripted validation fails (the visible form has no Save button).
      form.addEventListener("submit", function (e) {
        if (!validate()) e.preventDefault();
      });
    });
  }

  // Reorder chapters within a module. The ▲/▼ buttons are plain forms, so this
  // works without JS (POST -> redirect); here we intercept them, reorder the rows
  // in place from the ids the server returns, and re-disable the end buttons.
  function setupReorderControls() {
    document.querySelectorAll("table.chapters").forEach(function (table) {
      const body = table.tBodies[0];
      if (!body) return;

      table.querySelectorAll(".reorder").forEach(function (control) {
        const chapterId = control.getAttribute("data-chapter-id");
        control.querySelectorAll("form").forEach(function (form) {
          form.addEventListener("submit", function (event) {
            event.preventDefault();
            const button = form.querySelector("button");
            if (button && button.disabled) return;

            fetch(form.action, {
              method: "POST",
              headers: { "X-Requested-With": "XMLHttpRequest" },
              body: new FormData(form),
            })
              .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
              .then(function (data) {
                if (data.moved) applyOrder(body, data.chapter_ids, chapterId);
              })
              .catch(function () {
                // Network/server error — fall back to a normal submit so the
                // user still gets the move (and any flash message).
                form.submit();
              });
          });
        });
      });
    });
  }

  // Re-append rows to match `ids`, then refresh which end buttons are disabled
  // and briefly highlight the row that moved.
  function applyOrder(body, ids, movedId) {
    const rows = [];
    ids.forEach(function (id) {
      const row = body.querySelector('[data-chapter-row="' + id + '"]');
      if (row) {
        body.appendChild(row);   // appending in order re-sorts the table
        rows.push(row);
      }
    });

    rows.forEach(function (row, index) {
      const up = row.querySelector('.reorder button[data-direction="up"]');
      const down = row.querySelector('.reorder button[data-direction="down"]');
      if (up) up.disabled = index === 0;
      if (down) down.disabled = index === rows.length - 1;
    });

    const moved = body.querySelector('[data-chapter-row="' + movedId + '"]');
    if (moved) {
      moved.classList.remove("just-moved");
      // Force a reflow so re-adding the class restarts the animation.
      void moved.offsetWidth;
      moved.classList.add("just-moved");
      // Keep focus on the button the user pressed, which now sits in a new row.
      const still = moved.querySelector(".reorder button:not([disabled])");
      if (still) still.focus();
    }
  }

  function clampInt(value) {
    const n = parseInt(value || "0", 10);
    return isNaN(n) || n < 0 ? 0 : n;
  }

  // --- Plan forms: only assign on an explicit "Plan" click ----------------
  // The chapter must never be planned just by picking a date. We disable the
  // Plan button until a date is chosen, and swallow Enter in the date field so
  // the native picker can't implicitly submit the form.
  function setupPlanForms() {
    document.querySelectorAll(".plan-form").forEach(function (form) {
      const dateEl = form.querySelector('input[type="date"]');
      const btn = form.querySelector('button[type="submit"]');
      if (!dateEl || !btn) return;

      const today = new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD, local
      // The field may arrive pre-filled with the date this chapter is already
      // planned for. If that date is in the past (an overdue/backlog item), do
      // NOT set `min` to today — the browser would mark the field invalid and
      // the user could not simply reopen the picker. Only constrain the picker
      // when there is nothing to preserve.
      const initial = dateEl.value;
      if (!initial || initial >= today) {
        // No back-dating: the picker can't select earlier than today.
        dateEl.min = today;
      }

      function sync() {
        // Unchanged value is a no-op; nothing to submit.
        const empty = !dateEl.value;
        const tooEarly = dateEl.min && dateEl.value < dateEl.min;
        btn.disabled = empty || tooEarly || dateEl.value === initial;
      }
      sync();
      dateEl.addEventListener("input", sync);
      dateEl.addEventListener("change", sync);
      dateEl.addEventListener("keydown", function (e) {
        if (e.key === "Enter") e.preventDefault(); // no implicit submit
      });
    });
  }

  // --- Dashboard charts (Chart.js) ----------------------------------------
  let dashboardData = null; // remembered so we can redraw on theme change
  let charts = [];

  function buildCharts() {
    if (typeof Chart === "undefined" || !dashboardData) return;
    const data = dashboardData;
    const c = themeColors();

    Chart.defaults.font.family =
      "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
    Chart.defaults.color = c.text;

    const overall = document.getElementById("overallChart");
    if (overall && data.overall) {
      charts.push(
        new Chart(overall, {
          type: "doughnut",
          data: {
            labels: ["Done", "Left"],
            datasets: [
              {
                data: [data.overall.completed, data.overall.remaining],
                backgroundColor: [c.done, c.track],
                borderWidth: 0,
              },
            ],
          },
          options: {
            cutout: "72%",
            plugins: { legend: { display: false }, tooltip: hmTooltipPlugin },
            animation: { animateRotate: true, duration: 1000 },
          },
        })
      );
    }

    const subjects = document.getElementById("subjectsChart");
    if (subjects && data.subjects) {
      charts.push(
        new Chart(subjects, {
          type: "bar",
          data: {
            labels: data.subjects.labels,
            datasets: [
              { label: "Done", data: data.subjects.completed, backgroundColor: c.blue, borderRadius: 6 },
              { label: "Left", data: data.subjects.remaining, backgroundColor: c.track, borderRadius: 6 },
            ],
          },
          options: {
            scales: {
              x: { stacked: true, grid: { color: c.grid }, ticks: { color: c.text } },
              y: { stacked: true, beginAtZero: true, grid: { color: c.grid }, ticks: { color: c.text } },
            },
            plugins: { legend: { position: "bottom" }, tooltip: hmTooltipPlugin },
            animation: { duration: 900 },
          },
        })
      );
    }

    const week = document.getElementById("weekChart");
    if (week && data.week) {
      charts.push(
        new Chart(week, {
          type: "bar",
          data: {
            labels: data.week.labels,
            datasets: [
              { label: "Studied", data: data.week.studied, backgroundColor: c.violet, borderRadius: 6 },
              { label: "Planned", data: data.week.planned, backgroundColor: c.amber, borderRadius: 6 },
            ],
          },
          options: {
            scales: {
              x: { grid: { color: c.grid }, ticks: { color: c.text } },
              y: { beginAtZero: true, grid: { color: c.grid }, ticks: { color: c.text } },
            },
            plugins: { legend: { position: "bottom" }, tooltip: hmTooltipPlugin },
            animation: { duration: 900 },
          },
        })
      );
    }
  }

  function redrawCharts() {
    if (!charts.length) return;
    charts.forEach((ch) => ch.destroy());
    charts = [];
    buildCharts();
  }

  function renderDashboard(data) {
    dashboardData = data;
    buildCharts();
  }

  window.SubjectTracker = { renderDashboard: renderDashboard, toggleTheme: toggleTheme };

  document.addEventListener("DOMContentLoaded", function () {
    setupReveal();
    runCounts();
    setupDatePickers();
    setupCompletionForms();
    setupPlanForms();
    setupReorderControls();
    const toggle = document.getElementById("themeToggle");
    if (toggle) toggle.addEventListener("click", toggleTheme);
  });
})();
