const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture } = require("@nomicfoundation/hardhat-network-helpers");

describe("LotteryCore", function () {
  async function deployFixture() {
    const [deployer, alice, bob] = await ethers.getSigners();

    const TicketNFT = await ethers.getContractFactory("TicketNFT");
    const ticketNFT = await TicketNFT.deploy("ChainLottery Ticket", "CLT", "https://example.com/tickets/");
    await ticketNFT.waitForDeployment();

    const ticketPrice = ethers.parseEther("0.01");

    const LotteryCore = await ethers.getContractFactory("LotteryCore");
    const lottery = await LotteryCore.deploy(await ticketNFT.getAddress(), ticketPrice);
    await lottery.waitForDeployment();

    const minterRole = await ticketNFT.MINTER_ROLE();
    await ticketNFT.grantRole(minterRole, await lottery.getAddress());

    return { deployer, alice, bob, ticketNFT, lottery, ticketPrice };
  }

  it("opens the first period automatically", async function () {
    const { lottery } = await loadFixture(deployFixture);

    const currentPeriodId = await lottery.currentPeriodId();
    expect(currentPeriodId).to.equal(1n);

    const period = await lottery.getPeriod(currentPeriodId);
    // status = Selling (enum value 0)
    expect(period.status).to.equal(0);
    expect(period.ticketCount).to.equal(0n);
  });

  it("mints an NFT and records ticket purchase data", async function () {
    const { lottery, ticketNFT, ticketPrice, alice } = await loadFixture(deployFixture);

    const numbers = [1, 6, 12, 20, 28, 35];
    const metadata = "ipfs://ticket-1";
    const tx = await lottery.connect(alice).buyTicket(numbers, metadata, { value: ticketPrice });
    await tx.wait();

    const tokenId = 1n;
    const balance = await ticketNFT.balanceOf(alice.address);
    expect(balance).to.equal(1n);
    expect(await ticketNFT.ownerOf(tokenId)).to.equal(alice.address);

    const ticket = await lottery.getTicket(tokenId);
    expect(ticket.buyer).to.equal(alice.address);
    expect(ticket.periodId).to.equal(await lottery.currentPeriodId());
    expect(ticket.stake).to.equal(ticketPrice);
    expect(ticket.claimed).to.equal(false);

    for (let i = 0; i < numbers.length; i += 1) {
      expect(ticket.numbers[i]).to.equal(numbers[i]);
    }
  });

  it("rejects invalid ticket combinations", async function () {
    const { lottery, ticketPrice, alice } = await loadFixture(deployFixture);

    await expect(
      lottery.connect(alice).buyTicket([1, 1, 2, 3, 4, 5], "", { value: ticketPrice }),
    ).to.be.revertedWithCustomError(lottery, "NumbersNotAscending");

    await expect(
      lottery.connect(alice).buyTicket([0, 2, 3, 4, 5, 6], "", { value: ticketPrice }),
    ).to.be.revertedWithCustomError(lottery, "NumbersOutOfRange");
  });

  it("pays out jackpot winners after oracle submission", async function () {
    const { lottery, ticketNFT, ticketPrice, alice, deployer } = await loadFixture(deployFixture);

    const winningNumbers = [3, 9, 14, 18, 23, 30];
    await lottery.connect(alice).buyTicket(winningNumbers, "", { value: ticketPrice });

    // Fund contract to cover potential jackpot payout.
    await deployer.sendTransaction({ to: await lottery.getAddress(), value: ethers.parseEther("15") });

    await lottery.closeCurrentPeriod();
    const currentPeriodId = await lottery.currentPeriodId();
    await lottery.submitResult(currentPeriodId, winningNumbers);

    const expectedPayout = ticketPrice * 1000n;
    await expect(() => lottery.connect(alice).claimPrize(1n)).to.changeEtherBalances(
      [lottery, alice],
      [-expectedPayout, expectedPayout],
    );

    const ticket = await lottery.getTicket(1n);
    expect(ticket.claimed).to.equal(true);
    const period = await lottery.getPeriod(currentPeriodId);
    expect(period.paidOut).to.equal(expectedPayout);
  });

  it("prevents prize claims before results are available", async function () {
    const { lottery, ticketPrice, alice } = await loadFixture(deployFixture);

    const numbers = [2, 5, 11, 19, 22, 26];
    await lottery.connect(alice).buyTicket(numbers, "", { value: ticketPrice });

    await expect(lottery.connect(alice).claimPrize(1n)).to.be.revertedWithCustomError(
      lottery,
      "PeriodNotResultReady",
    );
  });
});
