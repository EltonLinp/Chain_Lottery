(() => {
  const walletButton = document.getElementById("wallet-button");
  const walletAddressLabel = document.getElementById("wallet-address");
  const purchaseForm = document.getElementById("purchase-form");
  const messageBox = document.getElementById("purchase-message");
  const ticketsList = document.getElementById("tickets-list");
  const ticketsEmpty = document.getElementById("tickets-empty");
  const statusIndicator = document.getElementById("status-indicator");
  const numberInputsContainer = document.getElementById("number-inputs");

  if (!walletButton || !purchaseForm || !ticketsList || !ticketsEmpty || !numberInputsContainer) {
    console.warn("Ticket UI not found on this page.");
    return;
  }

  let walletAddress = null;
  let tickets = [];
  let appConfig = null;
  let provider = null;
  let signer = null;
  let contract = null;
  let ticketPriceWei = null;

  const shortenAddress = (addr) => (addr ? `${addr.slice(0, 6)}...${addr.slice(-4)}` : "N/A");

  const setMessage = (text, type = "info") => {
    if (!messageBox) return;
    messageBox.textContent = text || "";
    const cls = type === "error" ? "error" : "success";
    messageBox.className = `message ${cls}`;
  };

  const updateWalletUI = () => {
    if (walletAddressLabel) {
      walletAddressLabel.textContent = walletAddress ? `Wallet: ${shortenAddress(walletAddress)}` : "Not connected";
    }
    walletButton.textContent = walletAddress ? "Disconnect" : "Connect Wallet";
  };

  const ensureConfigLoaded = async () => {
    if (appConfig) return appConfig;
    const resp = await fetch("/config");
    if (!resp.ok) throw new Error("Failed to load contract configuration.");
    appConfig = await resp.json();
    if (appConfig?.ticket_price_wei) {
      try {
        ticketPriceWei = BigInt(appConfig.ticket_price_wei);
      } catch (err) {
        console.warn("Ticket price is not a valid bigint:", err);
        ticketPriceWei = null;
      }
    }
    return appConfig;
  };

  const ensureContract = async () => {
    if (!window.ethers) throw new Error("ethers.js not loaded. Refresh the page once scripts finish loading.");
    await ensureConfigLoaded();
    if (!Array.isArray(appConfig?.abi) || !appConfig?.contract_address) {
      throw new Error("Contract ABI or address missing in backend configuration.");
    }
    if (!window.ethereum) throw new Error("Wallet provider not detected. Install MetaMask or a compatible wallet.");

    if (!provider) provider = new ethers.BrowserProvider(window.ethereum);
    if (!signer) signer = await provider.getSigner();
    if (!contract) contract = new ethers.Contract(appConfig.contract_address, appConfig.abi, signer);
    return contract;
  };

  const connectWallet = async () => {
    if (walletAddress) {
      walletAddress = null;
      provider = null;
      signer = null;
      contract = null;
      updateWalletUI();
      setMessage("Wallet disconnected.", "info");
      return;
    }

    if (!window.ethereum) {
      alert("MetaMask not detected. Please install a wallet extension first.");
      return;
    }

    try {
      await ensureConfigLoaded();
      provider = new ethers.BrowserProvider(window.ethereum);
      await provider.send("eth_requestAccounts", []);
      signer = await provider.getSigner();
      walletAddress = await signer.getAddress();
      contract = new ethers.Contract(appConfig.contract_address, appConfig.abi, signer);
      const network = await provider.getNetwork();
      if (appConfig?.chain_id && Number(network.chainId) !== Number(appConfig.chain_id)) {
        setMessage(`Connected to chain ${network.chainId}. Switch to ${appConfig.chain_id}.`, "error");
      } else {
        setMessage("Wallet connected.", "success");
      }
    } catch (err) {
      console.error(err);
      walletAddress = null;
      provider = null;
      signer = null;
      contract = null;
      const msg = err?.message || "Wallet connection failed.";
      setMessage(msg, "error");
    }

    updateWalletUI();
  };

  const validateNumbers = (values) => {
    if (!Array.isArray(values) || values.length !== 6) throw new Error("Please enter exactly six numbers.");
    const sorted = values.map((n) => Number(n)).sort((a, b) => a - b);
    if (sorted.some((n) => Number.isNaN(n) || n < 1 || n > 35)) {
      throw new Error("Numbers must be between 1 and 35.");
    }
    for (let i = 0; i < sorted.length - 1; i += 1) {
      if (sorted[i] === sorted[i + 1]) {
        throw new Error("Numbers must be unique and strictly ascending.");
      }
    }
    return sorted;
  };

  const ticketToHtml = (ticket) => {
    const matchesText = ticket.matches != null ? ticket.matches : "N/A";
    const payoutText = ticket.payout != null ? ticket.payout : 0;
    const buyerText = ticket.buyer ? shortenAddress(ticket.buyer) : "N/A";
    const status = ticket.status || "unknown";
    return `
      <div><strong>ID:</strong> ${ticket.ticket_id}</div>
      <div><strong>Period:</strong> ${ticket.period_id}</div>
      <div><strong>Numbers:</strong> ${Array.isArray(ticket.numbers) ? ticket.numbers.join(", ") : "N/A"}</div>
      <div><strong>Status:</strong> ${status}</div>
      <div><strong>Matches:</strong> ${matchesText}</div>
      <div><strong>Payout:</strong> ${payoutText}</div>
      <div><strong>Buyer:</strong> ${buyerText}</div>
      <div><strong>Tx Hash:</strong> ${ticket.tx_hash || "N/A"}</div>
    `;
  };

  const renderTickets = () => {
    ticketsList.innerHTML = "";
    if (!Array.isArray(tickets) || tickets.length === 0) {
      ticketsEmpty.style.display = "block";
      return;
    }

    ticketsEmpty.style.display = "none";

    tickets.forEach((ticket) => {
      const item = document.createElement("li");
      item.className = "ticket-item";

      const meta = document.createElement("div");
      meta.className = "ticket-meta";
      meta.innerHTML = ticketToHtml(ticket);

      const actions = document.createElement("div");
      actions.className = "ticket-actions";

      const refreshBtn = document.createElement("button");
      refreshBtn.textContent = "Sync";
      refreshBtn.addEventListener("click", () => refreshTicket(ticket.ticket_id));

      const claimBtn = document.createElement("button");
      claimBtn.textContent = "Claim";
      claimBtn.disabled = !(ticket.matches > 0 && !ticket.claimed);
      claimBtn.addEventListener("click", () => claimTicket(ticket.ticket_id));

      actions.appendChild(refreshBtn);
      actions.appendChild(claimBtn);

      item.appendChild(meta);
      item.appendChild(actions);
      ticketsList.appendChild(item);
    });
  };

  const fetchTickets = async () => {
    try {
      const resp = await fetch("/tickets");
      if (!resp.ok) throw new Error("Failed to load tickets from backend.");
      tickets = await resp.json();
      tickets = Array.isArray(tickets) ? tickets : [];
      renderTickets();
    } catch (err) {
      console.error(err);
      setMessage(err.message, "error");
    }
  };

  const syncTicketWithBackend = async (ticketId, txHash) => {
    const payload = { ticket_id: ticketId };
    if (txHash) payload.tx_hash = txHash;
    const resp = await fetch("/tickets/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const errPayload = await resp.json().catch(() => ({}));
      throw new Error(errPayload.error || "Failed to sync ticket with backend.");
    }
    return resp.json();
  };

  const refreshTicket = async (ticketId) => {
    try {
      const synced = await syncTicketWithBackend(ticketId);
      tickets = tickets.map((t) => (t.ticket_id === synced.ticket_id ? synced : t));
      renderTickets();
      setMessage(`Ticket ${ticketId} refreshed from blockchain.`, "success");
    } catch (err) {
      console.warn("Fallback to backend refresh:", err);
      try {
        const resp = await fetch(`/tickets/${ticketId}`);
        if (!resp.ok) throw new Error("Ticket not found.");
        const data = await resp.json();
        tickets = tickets.map((t) => (t.ticket_id === ticketId ? { ...t, ...data } : t));
        renderTickets();
      } catch (fallbackErr) {
        alert(`Refresh failed: ${fallbackErr.message}`);
      }
    }
  };

  const extractTokenId = (receipt) => {
    if (!contract || !receipt?.logs) return null;
    for (const log of receipt.logs) {
      try {
        const parsed = contract.interface.parseLog(log);
        if (parsed && parsed.name === "TicketPurchased") {
          const tokenId = parsed.args?.tokenId ?? parsed.args?.[2];
          return tokenId != null ? tokenId.toString() : null;
        }
      } catch (err) {
        // Ignore unrelated logs.
      }
    }
    return null;
  };

  const submitPurchase = async (event) => {
    event.preventDefault();
    if (!walletAddress) {
      setMessage("Connect wallet before purchasing.", "error");
      return;
    }

    const numbers = Array.from(numberInputsContainer.querySelectorAll("input")).map((input) => input.value);
    let sortedNumbers;
    try {
      sortedNumbers = validateNumbers(numbers);
    } catch (err) {
      setMessage(err.message, "error");
      return;
    }

    try {
      const activeContract = await ensureContract();
      const price = ticketPriceWei != null ? ticketPriceWei : BigInt(await activeContract.ticketPrice());
      const tx = await activeContract.buyTicket(sortedNumbers, "", { value: price });
      setMessage("Transaction submitted. Waiting for confirmation...", "info");
      const receipt = await tx.wait();
      const tokenId = extractTokenId(receipt);
      if (!tokenId) throw new Error("Unable to read ticket ID from transaction logs.");

      await syncTicketWithBackend(tokenId, receipt.hash);
      setMessage(`Ticket ${tokenId} purchased successfully. Tx: ${receipt.hash}`, "success");
      purchaseForm.reset();
      await fetchTickets();
    } catch (err) {
      console.error(err);
      const msg = err?.message || "Purchase failed.";
      setMessage(msg, "error");
    }
  };

  const claimTicket = async (ticketId) => {
    if (!walletAddress) {
      setMessage("Connect wallet before claiming.", "error");
      return;
    }

    try {
      const activeContract = await ensureContract();
      const tx = await activeContract.claimPrize(BigInt(ticketId));
      setMessage("Claim transaction sent. Waiting for confirmation...", "info");
      const receipt = await tx.wait();
      const resp = await fetch(`/tickets/${ticketId}/sync-claim`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tx_hash: receipt.hash }),
      });
      if (!resp.ok) {
        const errPayload = await resp.json().catch(() => ({}));
        throw new Error(errPayload.error || "Backend failed to record claim.");
      }
      const updated = await resp.json();
      tickets = tickets.map((t) => (t.ticket_id === updated.ticket_id ? updated : t));
      renderTickets();
      setMessage(`Ticket ${ticketId} claimed. Tx: ${receipt.hash}`, "success");
    } catch (err) {
      console.error(err);
      const msg = err?.message || "Claim failed.";
      setMessage(msg, "error");
    }
  };

  const createNumberInputs = () => {
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

  const checkHealth = async () => {
    try {
      const resp = await fetch("/health");
      if (statusIndicator) statusIndicator.textContent = resp.ok ? "Online" : "Service error";
    } catch (err) {
      if (statusIndicator) statusIndicator.textContent = "Backend unreachable";
    }
  };

  walletButton.addEventListener("click", connectWallet);
  purchaseForm.addEventListener("submit", submitPurchase);

  if (window.ethereum) {
    window.ethereum.on("accountsChanged", (accounts) => {
      if (!accounts || accounts.length === 0) {
        walletAddress = null;
        provider = null;
        signer = null;
        contract = null;
        updateWalletUI();
        setMessage("Wallet disconnected.", "info");
      } else {
        walletAddress = accounts[0];
        signer = null;
        contract = null;
        updateWalletUI();
      }
    });
    window.ethereum.on("chainChanged", () => window.location.reload());
  }

  createNumberInputs();
  updateWalletUI();
  fetchTickets();
  checkHealth();
  ensureConfigLoaded().catch((err) => {
    console.error(err);
    setMessage(err.message, "error");
  });
})();
