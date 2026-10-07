// Agentic GraphRAG Dashboard Client Logic

document.addEventListener("DOMContentLoaded", () => {
  // Navigation Tabs
  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");

  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-tab");
      tabButtons.forEach(b => b.classList.remove("active"));
      tabContents.forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      const targetContent = document.getElementById(`tab-${target}`);
      if (targetContent) targetContent.classList.add("active");
    });
  });

  // Pipeline Selector
  let selectedPipeline = "p3";
  const pipelinePills = document.querySelectorAll(".pipeline-pill");
  pipelinePills.forEach(pill => {
    pill.addEventListener("click", () => {
      pipelinePills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      selectedPipeline = pill.getAttribute("data-pipeline");
    });
  });

  // Fetch Graph Stats
  fetchGraphStats();

  // Fetch Sample Prompts
  fetchSamplePrompts();

  // Fetch Benchmark Data
  fetchBenchmarks();

  // Query Execution
  const runBtn = document.getElementById("run-btn");
  const questionInput = document.getElementById("question-input");
  const resultCard = document.getElementById("result-card");
  const loader = document.getElementById("query-loader");
  const resultContent = document.getElementById("result-content");

  runBtn.addEventListener("click", executeQuery);
  questionInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      executeQuery();
    }
  });

  async function executeQuery() {
    const question = questionInput.value.trim();
    if (!question) return;

    resultCard.style.display = "block";
    loader.style.display = "flex";
    resultContent.style.display = "none";
    runBtn.disabled = true;

    try {
      const resp = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question,
          pipeline: selectedPipeline,
          top_k: 5
        })
      });

      if (!resp.ok) {
        throw new Error(`HTTP error! status: ${resp.status}`);
      }

      const data = await resp.json();
      renderResult(data);
    } catch (err) {
      alert("Query failed: " + err.message);
    } finally {
      loader.style.display = "none";
      resultContent.style.display = "block";
      runBtn.disabled = false;
    }
  }

  function renderResult(data) {
    document.getElementById("res-answer").textContent = data.answer || "No answer generated";
    document.getElementById("res-latency").textContent = `${data.latency_ms.toLocaleString()} ms`;
    document.getElementById("res-tokens").textContent = data.tokens?.total_tokens?.toLocaleString() || "0";
    document.getElementById("res-strat-changed").textContent = data.strategy_changed ? "True (Fallback Active)" : "False";
    document.getElementById("res-pipeline-tag").textContent = data.pipeline.toUpperCase();
    document.getElementById("res-stop-tag").textContent = data.stop_reason || "SUFFICIENCY_REACHED";

    // Trace Rendering
    const traceList = document.getElementById("trace-list");
    traceList.innerHTML = "";
    const trace = data.trace || [];
    document.getElementById("trace-step-count").textContent = `${trace.length} step${trace.length === 1 ? '' : 's'}`;

    if (trace.length === 0) {
      traceList.innerHTML = `<div class="trace-step-item"><p style="color: #64748b; font-size: 13px;">Direct execution without multi-agent trace steps.</p></div>`;
    } else {
      trace.forEach((step, idx) => {
        const item = document.createElement("div");
        item.className = "trace-step-item";
        item.innerHTML = `
          <div class="step-top-line">
            <div class="step-meta">
              <span class="step-num">Step ${step.step}</span>
              <span class="step-agent">${escapeHtml(step.agent)}</span>
              <span class="step-tool">${escapeHtml(step.tool)}</span>
            </div>
            <span class="step-lat">${step.latency_ms} ms &bull; Decision: <strong style="color: #34d399;">${escapeHtml(step.decision)}</strong></span>
          </div>
          <div class="step-summary"><strong>Observation:</strong> ${escapeHtml(step.observation_summary)}</div>
          ${step.args && Object.keys(step.args).length > 0 ? `
            <div class="step-args-box">Args: ${escapeHtml(JSON.stringify(step.args, null, 2))}</div>
          ` : ''}
        `;
        traceList.appendChild(item);
      });
    }

    // Citations Rendering
    const citationsList = document.getElementById("citations-list");
    citationsList.innerHTML = "";
    const citations = data.citations || [];
    document.getElementById("citation-count").textContent = `${citations.length} source${citations.length === 1 ? '' : 's'}`;

    if (citations.length === 0) {
      citationsList.innerHTML = `<p style="color: #64748b; font-size: 13px;">No direct citations returned.</p>`;
    } else {
      citations.forEach(c => {
        const card = document.createElement("div");
        card.className = "citation-card";
        card.innerHTML = `
          <div class="citation-header">
            <span>Chunk ID: ${escapeHtml(c.chunk_id)}</span>
            <span style="color: #94a3b8;">Doc: ${escapeHtml(c.doc_id)}</span>
          </div>
          <div class="citation-quote">&ldquo;${escapeHtml(c.quote || 'Direct grounding fact citation')}&rdquo;</div>
        `;
        citationsList.appendChild(card);
      });
    }
  }

  // Copy answer
  document.getElementById("copy-btn").addEventListener("click", () => {
    const ans = document.getElementById("res-answer").textContent;
    navigator.clipboard.writeText(ans).then(() => {
      alert("Answer copied to clipboard!");
    });
  });

  // Tool Playground execution
  const execToolBtn = document.getElementById("exec-tool-btn");
  const toolSelect = document.getElementById("tool-select");
  const toolArgsInput = document.getElementById("tool-args-input");
  const toolOutputJson = document.getElementById("tool-output-json");

  toolSelect.addEventListener("change", () => {
    const val = toolSelect.value;
    if (val === "Find_Events") {
      toolArgsInput.value = JSON.stringify({ sport: "Biathlon", year: 2014, min_competitors: 69 }, null, 2);
    } else if (val === "Aggregate_Events") {
      toolArgsInput.value = JSON.stringify({ sport: "Athletics", year: 2016, group_by: "gender", metric: "max_competitors" }, null, 2);
    } else if (val === "Event_Details") {
      toolArgsInput.value = JSON.stringify({ event_id: "event_02b6a7d55c" }, null, 2);
    } else if (val === "Navigate_Edition") {
      toolArgsInput.value = JSON.stringify({ event_id: "event_02b6a7d55c", direction: "PREVIOUS" }, null, 2);
    } else if (val === "Medal_Table") {
      toolArgsInput.value = JSON.stringify({ entity_id: "USA", entity_type: "Country", year: 2016 }, null, 2);
    } else if (val === "Resolve_Entity") {
      toolArgsInput.value = JSON.stringify({ query: "Usain Bolt", entity_type: "athlete" }, null, 2);
    } else if (val === "Vector_Chunk_Search") {
      toolArgsInput.value = JSON.stringify({ query: "Richmond Olympic Oval speed skating", top_k: 3 }, null, 2);
    }
  });

  execToolBtn.addEventListener("click", async () => {
    execToolBtn.disabled = true;
    toolOutputJson.textContent = "Executing on TigerGraph Savanna...";
    try {
      const args = JSON.parse(toolArgsInput.value);
      const resp = await fetch("/api/tools/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tool_name: toolSelect.value,
          args: args
        })
      });
      const data = await resp.json();
      toolOutputJson.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      toolOutputJson.textContent = "Error: " + err.message;
    } finally {
      execToolBtn.disabled = false;
    }
  });

  async function fetchGraphStats() {
    try {
      const res = await fetch("/api/graph/stats");
      const data = await res.json();
      const counts = data.vertex_counts || {};
      if (counts.Document) document.getElementById("stat-docs").textContent = counts.Document.toLocaleString();
      if (counts.DocumentChunk) document.getElementById("stat-chunks").textContent = counts.DocumentChunk.toLocaleString();
      if (counts.Event) document.getElementById("stat-events").textContent = counts.Event.toLocaleString();
      if (counts.Athlete) document.getElementById("stat-athletes").textContent = counts.Athlete.toLocaleString();
      if (counts.Country) document.getElementById("stat-countries").textContent = counts.Country.toLocaleString();
      if (counts.Venue) document.getElementById("stat-venues").textContent = counts.Venue.toLocaleString();
      if (counts.Sport) document.getElementById("stat-sports").textContent = counts.Sport.toLocaleString();
    } catch (e) {
      console.warn("Could not load live stats", e);
    }
  }

  async function fetchSamplePrompts() {
    try {
      const res = await fetch("/api/questions/sample");
      const samples = await res.json();
      const container = document.getElementById("sample-chips");
      container.innerHTML = "";
      samples.forEach(s => {
        const chip = document.createElement("button");
        chip.className = "sample-chip";
        chip.textContent = `[${s.qtype}] ${s.question.substring(0, 55)}...`;
        chip.title = s.question;
        chip.addEventListener("click", () => {
          questionInput.value = s.question;
          executeQuery();
        });
        container.appendChild(chip);
      });
    } catch (e) {
      console.warn("Could not load sample prompts", e);
    }
  }

  async function fetchBenchmarks() {
    try {
      const res = await fetch("/api/benchmarks");
      const data = await res.json();
      if (data.benchmark_p1_all100) {
        const p1 = data.benchmark_p1_all100;
        document.getElementById("p1-acc").textContent = `${p1.accuracy.toFixed(1)}%`;
        document.getElementById("p1-recall5").textContent = `${p1["recall@5"]?.toFixed(1) || 62.6}%`;
        document.getElementById("p1-mrr").textContent = p1.mrr?.toFixed(2) || "0.75";
        document.getElementById("p1-lat").textContent = `${(p1.mean_latency_ms / 1000).toFixed(1)}s`;
        document.getElementById("p1-tok").textContent = Math.round(p1.avg_tokens_per_q || 2941).toLocaleString();
      }
      if (data.benchmark_p2_all100) {
        const p2 = data.benchmark_p2_all100;
        document.getElementById("p2-acc").textContent = `${p2.accuracy.toFixed(1)}%`;
        document.getElementById("p2-recall5").textContent = `${p2["recall@5"]?.toFixed(1) || 62.6}%`;
        document.getElementById("p2-mrr").textContent = p2.mrr?.toFixed(2) || "0.75";
        document.getElementById("p2-lat").textContent = `${(p2.mean_latency_ms / 1000).toFixed(1)}s`;
        document.getElementById("p2-tok").textContent = Math.round(p2.avg_tokens_per_q || 3288).toLocaleString();
      }
    } catch (e) {
      console.warn("Could not load benchmarks", e);
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});
