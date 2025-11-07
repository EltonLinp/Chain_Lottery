const fs = require("fs");
const path = require("path");
const { ethers } = require("ethers");
require("dotenv").config({ path: path.resolve(__dirname, ".env") });

const REQUIRED_ENV = ["RPC_URL", "ORACLE_PRIVATE_KEY", "CONTRACT_ADDRESS"];
for (const key of REQUIRED_ENV) {
  if (!process.env[key]) {
    throw new Error(`Missing required env var: ${key}`);
  }
}

const RPC_URL = process.env.RPC_URL;
const ORACLE_PRIVATE_KEY = process.env.ORACLE_PRIVATE_KEY;
const CONTRACT_ADDRESS = process.env.CONTRACT_ADDRESS;
const RESULTS_PATH =
  process.env.RESULTS_PATH || path.join(__dirname, "results.json");
const ABI_PATH =
  process.env.CONTRACT_ABI_PATH ||
  path.join(
    __dirname,
    "..",
    "artifacts",
    "contracts",
    "ChainLottery.sol",
    "ChainLottery.json",
  );
const MAX_RETRIES = Number(process.env.ORACLE_MAX_RETRIES || 3);
const RETRY_DELAY_MS = Number(process.env.ORACLE_RETRY_DELAY_MS || 5000);

function readJson(filePath) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`File not found: ${filePath}`);
  }
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function validateNumbers(numbers) {
  if (!Array.isArray(numbers) || numbers.length !== 6) {
    throw new Error("winningNumbers must contain 6 integers");
  }
  let prev = 0;
  numbers.forEach((num, idx) => {
    if (!Number.isInteger(num)) {
      throw new Error(`Index ${idx} is not an integer: ${num}`);
    }
    if (num < 1 || num > 49) {
      throw new Error(`Index ${idx} out of range 1-49: ${num}`);
    }
    if (idx > 0 && num <= prev) {
      throw new Error("Numbers must be strictly increasing");
    }
    prev = num;
  });
}

function loadAbi(abiPath) {
  if (!fs.existsSync(abiPath)) {
    throw new Error(
      `ABI not found: ${abiPath}. Run npm run build in project root to generate artifacts.`,
    );
  }
  return readJson(abiPath).abi;
}

async function alreadyCommitted(contract, roundId) {
  const round = await contract.getRound(roundId);
  return Number(round.status) === 3; // RoundStatus.ResultCommitted
}

async function submitResult(contract, roundId, numbers) {
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      const tx = await contract.commitResult(roundId, numbers);
      console.log(`[oracle] commitResult sent: ${tx.hash}`);
      await tx.wait();
      console.log("[oracle] transaction confirmed");
      return;
    } catch (err) {
      console.error(
        `[oracle] submit failed (attempt ${attempt}/${MAX_RETRIES}): ${err.reason || err.message}`,
      );
      if (attempt === MAX_RETRIES) {
        throw err;
      }
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS));
    }
  }
}

async function main() {
  const { roundId, winningNumbers } = readJson(RESULTS_PATH);
  if (typeof roundId !== "number" || roundId < 0) {
    throw new Error("roundId must be a non-negative number");
  }
  validateNumbers(winningNumbers);

  const provider = new ethers.JsonRpcProvider(RPC_URL);
  const wallet = new ethers.Wallet(ORACLE_PRIVATE_KEY, provider);
  const abi = loadAbi(ABI_PATH);
  const contract = new ethers.Contract(CONTRACT_ADDRESS, abi, wallet);

  console.log(
    `[oracle] roundId=${roundId}, numbers=${winningNumbers.join(",")}`,
  );
  console.log(`[oracle] oracle address=${await wallet.getAddress()}`);

  if (await alreadyCommitted(contract, roundId)) {
    console.log("[oracle] round already has committed result, skipping");
    return;
  }

  await submitResult(contract, roundId, winningNumbers);

  const round = await contract.getRound(roundId);
  console.log(
    `[oracle] winnersCount=${round.winnersCount}, status=${round.status}`,
  );
}

main().catch((error) => {
  console.error("[oracle] script failed:", error);
  process.exitCode = 1;
});
