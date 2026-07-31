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

  // --- Count-up animation for elements with .count[data-to] ---------------
  function animateCount(el) {
    const to = parseFloat(el.dataset.to || "0");
    const decimals = parseInt(el.dataset.decimals || "0", 10);
    const duration = 900;
    const start = performance.now();
    function frame(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      el.textContent = (to * eased).toFixed(decimals);
      if (t < 1) requestAnimationFrame(frame);
      else el.textContent = to.toFixed(decimals);
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
            plugins: { legend: { display: false } },
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
            plugins: { legend: { position: "bottom" } },
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
            plugins: { legend: { position: "bottom" } },
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
    const toggle = document.getElementById("themeToggle");
    if (toggle) toggle.addEventListener("click", toggleTheme);
  });
})();
