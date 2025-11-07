const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("ChainLottery", function () {
  let owner;
  let oracle;
  let alice;
  let bob;
  let eve;
  let lottery;
  const ticketPrice = ethers.parseEther("0.1");
  const winningNumbers = [1, 5, 12, 23, 34, 45];
  const losingNumbers = [2, 6, 13, 24, 35, 46];

  beforeEach(async function () {
    [owner, oracle, alice, bob, eve] = await ethers.getSigners();
    const ChainLottery = await ethers.getContractFactory("ChainLottery");
    lottery = await ChainLottery.connect(owner).deploy();
    await lottery.waitForDeployment();
    const ORACLE_ROLE = await lottery.ORACLE_ROLE();
    await lottery.connect(owner).grantRole(ORACLE_ROLE, oracle.address);
  });

  async function openDefaultRound(duration = 3600n) {
    const salesEnd = BigInt(await time.latest()) + duration;
    await lottery.connect(owner).openRound(salesEnd, ticketPrice);
    return { roundId: 1, salesEnd };
  }

  function toUint32Array(nums) {
    return nums.map((v) => BigInt(v));
  }

  describe("openRound", function () {
    it("allows owner to open a round", async function () {
      const salesEnd = BigInt(await time.latest()) + 600n;
      await expect(lottery.connect(owner).openRound(salesEnd, ticketPrice))
        .to.emit(lottery, "RoundOpened")
        .withArgs(1, salesEnd, ticketPrice);
      const round = await lottery.getRound(1);
      expect(round.ticketPrice).to.equal(ticketPrice);
      expect(round.salesEnd).to.equal(BigInt(salesEnd));
      expect(round.status).to.equal(1); // RoundStatus.Open
    });

    it("rejects non-owner attempts", async function () {
      const salesEnd = BigInt(await time.latest()) + 600n;
      await expect(
        lottery.connect(alice).openRound(salesEnd, ticketPrice),
      ).to.be.revertedWithCustomError(
        lottery,
        "AccessControlUnauthorizedAccount",
      );
    });

    it("prevents overlapping rounds", async function () {
      const salesEnd = BigInt(await time.latest()) + 600n;
      await lottery.connect(owner).openRound(salesEnd, ticketPrice);
      await expect(
        lottery.connect(owner).openRound(salesEnd + 1000n, ticketPrice),
      ).to.be.revertedWithCustomError(lottery, "ActiveRoundExists");
    });
  });

  describe("ticket purchases", function () {
    it("sells tickets while round open", async function () {
      await openDefaultRound();
      await expect(
        lottery.connect(alice).buyTicket(1, toUint32Array(winningNumbers), {
          value: ticketPrice,
        }),
      )
        .to.emit(lottery, "TicketPurchased")
        .withArgs(1, 1, alice.address, toUint32Array(winningNumbers));

      const ticket = await lottery.getTicket(1);
      expect(ticket.player).to.equal(alice.address);
      expect(ticket.roundId).to.equal(1);
      expect(ticket.numbers.map((n) => Number(n))).to.deep.equal(
        winningNumbers,
      );

      const round = await lottery.getRound(1);
      expect(round.jackpot).to.equal(ticketPrice);
      expect(round.ticketCount).to.equal(1);
    });

    it("rejects purchases after sales end", async function () {
      const { salesEnd } = await openDefaultRound(10n);
      await time.increaseTo(Number(salesEnd));
      await expect(
        lottery
          .connect(alice)
          .buyTicket(1, toUint32Array(winningNumbers), { value: ticketPrice }),
      ).to.be.revertedWithCustomError(lottery, "SalesClosed");
    });

    it("requires exact ticket price", async function () {
      await openDefaultRound();
      await expect(
        lottery.connect(alice).buyTicket(1, toUint32Array(winningNumbers), {
          value: ticketPrice - 1n,
        }),
      ).to.be.revertedWithCustomError(lottery, "InvalidTicketPrice");
    });

    it("validates number ranges and ordering", async function () {
      await openDefaultRound();
      await expect(
        lottery
          .connect(alice)
          .buyTicket(1, toUint32Array([0, 5, 12, 23, 34, 45]), {
            value: ticketPrice,
          }),
      ).to.be.revertedWithCustomError(lottery, "NumbersOutOfRange");

      await expect(
        lottery
          .connect(alice)
          .buyTicket(1, toUint32Array([1, 5, 5, 23, 34, 45]), {
            value: ticketPrice,
          }),
      ).to.be.revertedWithCustomError(lottery, "NumbersNotIncreasing");
    });
  });

  describe("commit and claim flow", function () {
    beforeEach(async function () {
      await openDefaultRound();
      await lottery.connect(alice).buyTicket(1, toUint32Array(winningNumbers), {
        value: ticketPrice,
      });
      await lottery.connect(bob).buyTicket(1, toUint32Array(winningNumbers), {
        value: ticketPrice,
      });
      await lottery.connect(eve).buyTicket(1, toUint32Array(losingNumbers), {
        value: ticketPrice,
      });
    });

    it("prevents commit before round is closed", async function () {
      await expect(
        lottery.connect(oracle).commitResult(1, toUint32Array(winningNumbers)),
      ).to.be.revertedWithCustomError(lottery, "RoundNotClosed");
    });

    it("returns zero prize before result commitment", async function () {
      expect(await lottery.prizeOf(1, 1)).to.equal(0);
    });

    it("allows oracle to commit result after close", async function () {
      await lottery.connect(owner).closeRound(1);
      await expect(
        lottery.connect(oracle).commitResult(1, toUint32Array(winningNumbers)),
      )
        .to.emit(lottery, "ResultCommitted")
        .withArgs(1, toUint32Array(winningNumbers), 2);
      const round = await lottery.getRound(1);
      expect(round.winnersCount).to.equal(2);
      expect(round.status).to.equal(3); // ResultCommitted
    });

    it("splits jackpot equally among winners", async function () {
      await lottery.connect(owner).closeRound(1);
      await lottery
        .connect(oracle)
        .commitResult(1, toUint32Array(winningNumbers));

      const round = await lottery.getRound(1);
      const expectedPrize = round.jackpot / round.winnersCount;
      expect(await lottery.prizeOf(1, 1)).to.equal(expectedPrize);
      expect(await lottery.prizeOf(1, 2)).to.equal(expectedPrize);
      expect(await lottery.prizeOf(1, 3)).to.equal(0);
    });

    it("allows winners to claim once and transfers prize", async function () {
      await lottery.connect(owner).closeRound(1);
      await lottery
        .connect(oracle)
        .commitResult(1, toUint32Array(winningNumbers));
      const round = await lottery.getRound(1);
      const expectedPrize = round.jackpot / round.winnersCount;

      await expect(() =>
        lottery.connect(alice).claim(1, 1),
      ).to.changeEtherBalances(
        [alice, lottery],
        [expectedPrize, -expectedPrize],
      );

      await expect(
        lottery.connect(alice).claim(1, 1),
      ).to.be.revertedWithCustomError(lottery, "TicketAlreadyClaimed");
    });

    it("rejects non-winners or unauthorized claimers", async function () {
      await lottery.connect(owner).closeRound(1);
      await lottery
        .connect(oracle)
        .commitResult(1, toUint32Array(winningNumbers));

      await expect(
        lottery.connect(eve).claim(1, 3),
      ).to.be.revertedWithCustomError(lottery, "TicketNotWinner");

      await expect(
        lottery.connect(bob).claim(1, 1),
      ).to.be.revertedWithCustomError(lottery, "UnauthorizedClaimer");
    });
  });
});
