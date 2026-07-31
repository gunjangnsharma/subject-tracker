/* Subject Tracker — client-side enhancements: count-up, reveal, charts. */
(function () {
  "use strict";

  const palette = {
    green: "#16a34a",
    blue: "#3b6cf6",
    amber: "#f59e0b",
    violet: "#7c3aed",
    track: "rgba(148,163,184,0.25)",
    ink: "#1f2430",
  };

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
  function renderDashboard(data) {
    if (typeof Chart === "undefined") return;
    Chart.defaults.font.family =
      "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
    Chart.defaults.color = "#6b7280";

    const overall = document.getElementById("overallChart");
    if (overall && data.overall) {
      new Chart(overall, {
        type: "doughnut",
        data: {
          labels: ["Done", "Left"],
          datasets: [
            {
              data: [data.overall.completed, data.overall.remaining],
              backgroundColor: [palette.green, palette.track],
              borderWidth: 0,
            },
          ],
        },
        options: {
          cutout: "72%",
          plugins: { legend: { display: false } },
          animation: { animateRotate: true, duration: 1000 },
        },
      });
    }

    const subjects = document.getElementById("subjectsChart");
    if (subjects && data.subjects) {
      new Chart(subjects, {
        type: "bar",
        data: {
          labels: data.subjects.labels,
          datasets: [
            {
              label: "Done",
              data: data.subjects.completed,
              backgroundColor: palette.blue,
              borderRadius: 6,
            },
            {
              label: "Left",
              data: data.subjects.remaining,
              backgroundColor: palette.track,
              borderRadius: 6,
            },
          ],
        },
        options: {
          scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
          plugins: { legend: { position: "bottom" } },
          animation: { duration: 900 },
        },
      });
    }

    const week = document.getElementById("weekChart");
    if (week && data.week) {
      new Chart(week, {
        type: "bar",
        data: {
          labels: data.week.labels,
          datasets: [
            {
              label: "Studied",
              data: data.week.studied,
              backgroundColor: palette.violet,
              borderRadius: 6,
            },
            {
              label: "Planned",
              data: data.week.planned,
              backgroundColor: palette.amber,
              borderRadius: 6,
            },
          ],
        },
        options: {
          scales: { y: { beginAtZero: true } },
          plugins: { legend: { position: "bottom" } },
          animation: { duration: 900 },
        },
      });
    }
  }

  window.SubjectTracker = { renderDashboard: renderDashboard };

  document.addEventListener("DOMContentLoaded", function () {
    setupReveal();
    runCounts();
  });
})();
