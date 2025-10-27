(() => {
  const init = () => {
    const tokenInput = document.getElementById("admin-token");
    const saveTokenBtn = document.getElementById("save-token");
    const refreshBtn = document.getElementById("refresh-periods");
    const periodsTableBody = document.querySelector("#periods-table tbody");
    const periodSelect = document.getElementById("period-select");
    const numberInputsContainer = document.getElementById("draw-number-inputs");
    const messageBox = document.getElementById("draw-message");
    const drawForm = document.getElementById("draw-form");

    if (!numberInputsContainer) {
      console.error("draw-number-inputs container not found. Check admin.html.");
      return;
    }

    let drawStatusMap = new Map();
    const TOKEN_KEY = "chainlottery-admin-token";

    const setMessage = (text, type = "info") => {
      if (!messageBox) return;
      messageBox.textContent = text;
      messageBox.className = `message ${type === "error" ? "error" : "success"}`;
    };

    const loadToken = () => {
      const stored = localStorage.getItem(TOKEN_KEY);
      if (stored && tokenInput) tokenInput.value = stored;
    };

    const saveToken = () => {
      if (!tokenInput) return;
      const value = tokenInput.value.trim();
      if (value) localStorage.setItem(TOKEN_KEY, value);
      else localStorage.removeItem(TOKEN_KEY);
      setMessage("Admin token updated");
    };

    const getHeaders = () => {
      const headers = { "Content-Type": "application/json" };
      const token = tokenInput ? (tokenInput.value.trim() || localStorage.getItem(TOKEN_KEY)) : localStorage.getItem(TOKEN_KEY);
      if (token) headers["X-Admin-Token"] = token;
      return headers;
    };

    const clearNumberInputs = () => {
      numberInputsContainer.innerHTML = "";
      for (let i = 0; i < 6; i += 1) {
        const input = document.createElement("input");
        input.type = "number";
        input.min = "1";
        input.max = "35";
        input.required = true;
        input.className = "number-input";
        input.placeholder = `No.${i + 1}`;
        numberInputsContainer.appendChild(input);
      }
    };

    const renderPeriods = (periods) => {
      if (!periodsTableBody || !periodSelect) return;
      periodsTableBody.innerHTML = "";
      periodSelect.innerHTML = "";
      drawStatusMap.clear();

      if (!Array.isArray(periods) || periods.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 5;
        cell.textContent = "No period data yet";
        row.appendChild(cell);
        periodsTableBody.appendChild(row);
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No period";
        periodSelect.appendChild(option);
        return;
      }

      periods.forEach((period) => {
        const row = document.createElement("tr");
        const numbers = period.winning_numbers ? period.winning_numbers.join(", ") : "Not announced";
        const locked = Array.isArray(period.winning_numbers) && period.winning_numbers.length > 0;
        row.innerHTML = `
          <td>${period.period_id}</td>
          <td>${period.ticket_count}</td>
          <td>${period.settled_count}</td>
          <td>${period.claimed_count}</td>
          <td>${numbers}</td>
        `;
        periodsTableBody.appendChild(row);

        const option = document.createElement("option");
        option.value = period.period_id;
        option.textContent = locked ? `Period ${period.period_id} (locked)` : `Period ${period.period_id}`;
        option.dataset.locked = locked ? "true" : "false";
        periodSelect.appendChild(option);
        drawStatusMap.set(period.period_id, { locked, numbers: period.winning_numbers });
      });

      updateDrawFormState();
    };

    const updateDrawFormState = () => {
      if (!periodSelect) return;
      const selected = Number(periodSelect.value || 0);
      const status = drawStatusMap.get(selected);
      const inputs = numberInputsContainer.querySelectorAll("input");
      const submitBtn = drawForm?.querySelector('button[type="submit"]');

      if (status?.locked) {
        inputs.forEach((input, idx) => {
          input.value = status.numbers?.[idx] ?? "";
          input.disabled = true;
        });
        if (submitBtn) submitBtn.disabled = true;
        setMessage(`Period ${selected} already has a draw result.`, "info");
      } else {
        inputs.forEach((input) => {
          input.disabled = false;
          input.value = "";
        });
        if (submitBtn) submitBtn.disabled = false;
        setMessage("", "info");
      }
    };

    const fetchPeriods = async () => {
      try {
        const resp = await fetch("/admin/api/periods", { headers: getHeaders() });
        if (!resp.ok) throw new Error("Failed to load periods");
        const data = await resp.json();
        renderPeriods(data);
      } catch (err) {
        console.error(err);
        setMessage(err.message, "error");
      }
    };

    const validateNumbers = (numbers) => {
      if (numbers.length !== 6) throw new Error("Please enter exactly 6 numbers");
      const sorted = [...numbers].sort((a, b) => a - b);
      if (numbers.some((n) => Number.isNaN(n) || n < 1 || n > 35)) throw new Error("Numbers must be between 1 and 35");
      for (let i = 0; i < sorted.length - 1; i += 1) {
        if (sorted[i] === sorted[i + 1]) throw new Error("Numbers must be unique");
      }
      return sorted;
    };

    const submitDraw = async (event) => {
      event.preventDefault();
      try {
        const numbers = Array.from(numberInputsContainer.querySelectorAll("input")).map((input) => Number(input.value));
        const sortedNumbers = validateNumbers(numbers);
        const periodIdValue = periodSelect ? periodSelect.value : "";
        const payload = { winning_numbers: sortedNumbers };
        if (periodIdValue) payload.period_id = Number(periodIdValue);

        const resp = await fetch("/admin/api/draws", {
          method: "POST",
          headers: getHeaders(),
          body: JSON.stringify(payload)
        });
        if (!resp.ok) {
          const errPayload = await resp.json();
          throw new Error(errPayload.error || "Submit draw failed");
        }
        const data = await resp.json();
        if (data.already_set) {
          const numbersText = Array.isArray(data.winning_numbers) ? data.winning_numbers.join(", ") : "Already settled";
          setMessage(`Period ${data.period_id} already settled on chain. Numbers: ${numbersText}`, "info");
          await fetchPeriods();
          return;
        }
        const txEntries = data.transactions ? Object.entries(data.transactions) : [];
        const txSummary = txEntries.length
          ? txEntries.map(([label, hash]) => `${label}: ${hash}`).join(" | ")
          : "No chain transactions returned.";
        const warningSummary = Array.isArray(data.warnings) && data.warnings.length
          ? ` Warnings: ${data.warnings.join(" ; ")}`
          : "";
        const currentInfo = data.current_period ? `Current period: ${data.current_period}.` : "";
        setMessage(`Period ${data.period_id} settled on chain. ${currentInfo} ${txSummary}${warningSummary}`, "success");
        if (periodSelect && data.current_period) {
          periodSelect.value = String(data.current_period);
        }
        await fetchPeriods();
      } catch (err) {
        console.error(err);
        setMessage(err.message, "error");
      }
    };

    if (saveTokenBtn) saveTokenBtn.addEventListener("click", saveToken);
    if (refreshBtn) refreshBtn.addEventListener("click", fetchPeriods);
    if (drawForm) drawForm.addEventListener("submit", submitDraw);
    if (periodSelect) periodSelect.addEventListener("change", updateDrawFormState);

    loadToken();
    clearNumberInputs();
    fetchPeriods();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
