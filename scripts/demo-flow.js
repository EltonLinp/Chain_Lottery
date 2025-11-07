const fs = require("fs");
const path = require("path");
const hre = require("hardhat");
require("dotenv").config();

const { ethers } = hre;

function ensureEnv(name) {
  if (!process.env[name]) {
    throw new Error(`Missing env var: ${name}`);
  }
  return process.env[name];
}

function parseNumbers(csv) {
  return csv.split(",").map((n) => {
    const num = Number(n.trim());
    if (!Number.isInteger(num)) {
      throw new Error(`Invalid number in DEMO_WINNING_NUMBERS: ${n}`);
    }
    return num;
  });
}

async function main() {
  const CONTRACT_ADDRESS = ensureEnv("CONTRACT_ADDRESS");
  const OWNER_KEY = ensureEnv("PRIVATE_KEY");
  const ORACLE_KEY = ensureEnv("ORACLE_PRIVATE_KEY");
  const PLAYER_KEY = ensureEnv("PLAYER_PRIVATE_KEY");

  const ticketPrice = ethers.parseEther(
    process.env.DEMO_TICKET_PRICE_ETH || "0.01",
  );
  const salesWindow = Number(process.env.DEMO_SALES_WINDOW || 600);
  const numbers = parseNumbers(
    process.env.DEMO_WINNING_NUMBERS || "1,5,12,23,34,45",
  );

  const provider = hre.ethers.provider;
  const owner = new ethers.Wallet(OWNER_KEY, provider);
  const oracle = new ethers.Wallet(ORACLE_KEY, provider);
  const player = new ethers.Wallet(PLAYER_KEY, provider);

  const contract = await ethers.getContractAt(
    "ChainLottery",
    CONTRACT_ADDRESS,
    owner,
  );

  const now = Math.floor(Date.now() / 1000);
  const salesEnd = now + salesWindow;
  const logs = [];

  function pushLog(step, receipt) {
    logs.push({
      step,
      txHash: receipt?.hash || receipt?.transactionHash,
      blockNumber: receipt?.blockNumber,
      gasUsed: receipt?.gasUsed?.toString(),
    });
  }

  const currentRoundId = Number(await contract.currentRoundId());
  if (currentRoundId !== 0) {
    const round = await contract.getRound(currentRoundId);
    if (Number(round.status) !== 3) {
      throw new Error(
        `Active round ${currentRoundId} has status ${round.status}, please finish it before running demo`,
      );
    }
  }

  const openTx = await contract.connect(owner).openRound(salesEnd, ticketPrice);
  const openReceipt = await openTx.wait();
  pushLog("openRound", openReceipt);
  const roundId = Number(await contract.currentRoundId());

  const buyTx = await contract
    .connect(player)
    .buyTicket(roundId, numbers, { value: ticketPrice });
  const buyReceipt = await buyTx.wait();
  pushLog("buyTicket", buyReceipt);
  const ticketId = Number(await contract.nextTicketId());

  const closeTx = await contract.connect(owner).closeRound(roundId);
  const closeReceipt = await closeTx.wait();
  pushLog("closeRound", closeReceipt);

  const commitTx = await contract
    .connect(oracle)
    .commitResult(roundId, numbers);
  const commitReceipt = await commitTx.wait();
  pushLog("commitResult", commitReceipt);

  const prize = await contract.prizeOf(roundId, ticketId);
  const claimTx = await contract.connect(player).claim(roundId, ticketId);
  const claimReceipt = await claimTx.wait();
  pushLog("claim", claimReceipt);

  const summary = {
    network: hre.network.name,
    contract: CONTRACT_ADDRESS,
    roundId,
    ticketId,
    ticketPrice: ticketPrice.toString(),
    prize: prize.toString(),
    numbers,
    timestamps: {
      startedAt: now,
      salesEnd,
    },
    steps: logs,
  };

  const logDir = path.join(__dirname, "..", "logs");
  if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir);
  }
  const outPath = path.join(logDir, `demo-run-${Date.now()}.json`);
  fs.writeFileSync(outPath, JSON.stringify(summary, null, 2));
  console.log(`[demo] Flow completed. Results saved to ${outPath}`);
}

main().catch((error) => {
  console.error("[demo] script failed:", error);
  process.exitCode = 1;
});
