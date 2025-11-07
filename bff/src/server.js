import fs from "fs";
import path from "path";
import express from "express";
import cors from "cors";
import { ethers } from "ethers";
import dotenv from "dotenv";

dotenv.config({ path: path.resolve(process.cwd(), "../.env") });

const REQUIRED_ENV = ["RPC_URL", "CONTRACT_ADDRESS"];
for (const key of REQUIRED_ENV) {
  if (!process.env[key]) {
    throw new Error(`Missing env var: ${key}`);
  }
}

const ABI_RELATIVE = process.env.CONTRACT_ABI_PATH || "artifacts/contracts/ChainLottery.sol/ChainLottery.json";
const provider = new ethers.JsonRpcProvider(process.env.RPC_URL);
const ABI = await loadAbi();
const CONTRACT_ADDRESS = process.env.CONTRACT_ADDRESS;
const contract = new ethers.Contract(CONTRACT_ADDRESS, ABI, provider);

const app = express();
app.use(cors());
const PORT = process.env.PORT || 4000;

app.get("/healthz", async (_req, res) => {
  try {
    const network = await provider.getNetwork();
    res.json({
      status: "ok",
      network: network.name,
      chainId: Number(network.chainId),
      contract: CONTRACT_ADDRESS,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get("/periods", async (_req, res) => {
  try {
    const currentRoundId = Number(await contract.currentRoundId());
    if (currentRoundId === 0) {
      return res.json({ currentRoundId: 0 });
    }
    const round = await contract.getRound(currentRoundId);
    res.json({
      roundId: Number(round.roundId),
      salesStart: Number(round.salesStart),
      salesEnd: Number(round.salesEnd),
      ticketPrice: round.ticketPrice.toString(),
      jackpot: round.jackpot.toString(),
      winnersCount: Number(round.winnersCount),
      status: Number(round.status),
      ticketCount: Number(round.ticketCount),
      winningNumbers: round.winningNumbers.map((n) => Number(n)),
    });
  } catch (err) {
    console.error("[/periods] error", err);
    res.status(500).json({ error: err.message });
  }
});

app.get("/tickets", async (req, res) => {
  const { user } = req.query;
  if (!user || !ethers.isAddress(user)) {
    return res.status(400).json({ error: "Invalid user address" });
  }
  try {
    const normalized = ethers.getAddress(user);
    const latestBlock = await provider.getBlockNumber();
    const fromBlock = Math.max(0, latestBlock - 5000);
    const filter = contract.filters.TicketPurchased(null, null, normalized);
    const events = await contract.queryFilter(filter, fromBlock, latestBlock);
    const tickets = await Promise.all(
      events.map(async (event) => {
        const { roundId, ticketId, numbers } = event.args;
        const prize = await contract.prizeOf(roundId, ticketId);
        return {
          roundId: Number(roundId),
          ticketId: Number(ticketId),
          numbers: numbers.map((n) => Number(n)),
          prize: prize.toString(),
          txHash: event.transactionHash,
        };
      }),
    );
    res.json({ user: normalized, tickets });
  } catch (err) {
    console.error("[/tickets] error", err);
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`BFF listening on port ${PORT}`);
});

async function loadAbi() {
  const abiFullPath = path.resolve(process.cwd(), "..", ABI_RELATIVE);
  const raw = await fs.promises.readFile(abiFullPath, "utf8");
  return JSON.parse(raw).abi;
}
