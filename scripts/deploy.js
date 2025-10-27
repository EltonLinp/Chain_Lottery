const fs = require("fs");
const path = require("path");
const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();

  console.log("Deploying contracts with:", await deployer.getAddress());

  const TicketNFT = await hre.ethers.getContractFactory("TicketNFT");
  const ticketNFT = await TicketNFT.deploy("ChainLottery Ticket", "CLT", "https://example.com/tickets/");
  await ticketNFT.waitForDeployment();

  const LotteryCore = await hre.ethers.getContractFactory("LotteryCore");
  const ticketPrice = hre.ethers.parseEther("0.01");
  const lotteryCore = await LotteryCore.deploy(await ticketNFT.getAddress(), ticketPrice);
  await lotteryCore.waitForDeployment();

  const minterRole = await ticketNFT.MINTER_ROLE();
  await (await ticketNFT.grantRole(minterRole, await lotteryCore.getAddress())).wait();

  console.log("TicketNFT deployed to:", await ticketNFT.getAddress());
  console.log("LotteryCore deployed to:", await lotteryCore.getAddress());

  const outputDir = path.join(__dirname, "..", "deployed");
  fs.mkdirSync(outputDir, { recursive: true });

  const deployment = {
    network: "localhost",
    ticketNFT: await ticketNFT.getAddress(),
    lotteryCore: await lotteryCore.getAddress(),
    ticketPrice: ticketPrice.toString(),
    timestamp: new Date().toISOString(),
  };

  fs.writeFileSync(path.join(outputDir, "localhost.json"), JSON.stringify(deployment, null, 2));
  console.log("Deployment saved to deployed/localhost.json");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
