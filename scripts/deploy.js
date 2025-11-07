const hre = require("hardhat");
require("dotenv").config();

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log(`Deploying with ${deployer.address} on ${hre.network.name}`);

  const ChainLottery = await hre.ethers.getContractFactory("ChainLottery");
  const contract = await ChainLottery.deploy();
  await contract.waitForDeployment();

  const contractAddress = await contract.getAddress();
  console.log(`ChainLottery deployed at ${contractAddress}`);

  const oracleRole = await contract.ORACLE_ROLE();
  const oracleAddress = process.env.ORACLE_ADDRESS;

  if (
    oracleAddress &&
    oracleAddress.toLowerCase() !== deployer.address.toLowerCase()
  ) {
    const tx = await contract.grantRole(oracleRole, oracleAddress);
    await tx.wait();
    console.log(`Granted ORACLE_ROLE to ${oracleAddress}`);
  } else {
    console.log(
      "No ORACLE_ADDRESS provided (or matches deployer). Deployer retains ORACLE_ROLE by default.",
    );
  }

  console.log(
    "Remember to record this address in deployed/<network>.json and .env files.",
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
