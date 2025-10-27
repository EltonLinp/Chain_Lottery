// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {TicketNFT} from "./TicketNFT.sol";

/**
 * @title LotteryCore
 * @notice Manages ChainLottery periods, ticket sales, oracle result ingestion and prize settlements.
 *         The contract is designed to mirror an off-chain official lottery draw while ensuring the
 *         on-chain state machine remains transparent and auditable.
 */
contract LotteryCore is AccessControl, ReentrancyGuard {

    /// @notice Lifecycle of a lottery period.
    enum PeriodStatus {
        Selling,
        Closed,
        ResultIn,
        Settled
    }

    /// @notice Operational roles.
    bytes32 public constant MANAGER_ROLE = keccak256("MANAGER_ROLE");
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");
    bytes32 public constant CASHIER_ROLE = keccak256("CASHIER_ROLE");

    /// @notice Ticket schema constants.
    uint8 public constant NUMBERS_REQUIRED = 6;
    uint8 public constant MIN_NUMBER = 1;
    uint8 public constant MAX_NUMBER = 35;

    struct Period {
        PeriodStatus status;
        bool resultSet;
        uint8[NUMBERS_REQUIRED] winningNumbers;
        uint64 winningMask;
        uint256 ticketCount;
        uint256 totalSales;
        uint256 paidOut;
    }

    struct Ticket {
        uint256 periodId;
        address buyer;
        uint8[NUMBERS_REQUIRED] numbers;
        uint64 numberMask;
        uint256 stake;
        bool claimed;
    }

    TicketNFT public immutable ticketNFT;
    uint256 public ticketPrice;

    uint256 private _nextPeriodId = 1;
    uint256 public currentPeriodId;

    mapping(uint256 => Period) private _periods;
    mapping(uint256 => Ticket) private _tickets;
    mapping(uint8 => uint256) public prizeMultipliers;

    event PeriodOpened(uint256 indexed periodId);
    event PeriodClosed(uint256 indexed periodId);
    event ResultSubmitted(uint256 indexed periodId, uint8[NUMBERS_REQUIRED] winningNumbers);
    event PeriodSettled(uint256 indexed periodId);
    event TicketPurchased(address indexed buyer, uint256 indexed periodId, uint256 indexed tokenId, uint8[NUMBERS_REQUIRED] numbers);
    event PrizeClaimed(address indexed winner, uint256 indexed tokenId, uint256 indexed periodId, uint8 matches, uint256 payout);
    event TicketPriceUpdated(uint256 newPrice);
    event PrizeMultiplierUpdated(uint8 matches, uint256 multiplier);
    event FundsWithdrawn(address indexed to, uint256 amount);
    event FundsDeposited(address indexed from, uint256 amount);

    error InvalidPeriod(uint256 periodId);
    error PeriodNotSelling(uint256 periodId);
    error PeriodNotClosed(uint256 periodId);
    error PeriodNotSettled(uint256 periodId);
    error PeriodNotResultReady(uint256 periodId);
    error TicketHasNoPrize(uint256 tokenId);
    error TicketAlreadyClaimed(uint256 tokenId);
    error TicketNotOwned(uint256 tokenId);
    error TicketNotFound(uint256 tokenId);
    error IncorrectPayment(uint256 expected, uint256 received);
    error NumbersOutOfRange(uint8 number);
    error NumbersNotAscending();
    error InvalidMatches(uint8 matches);
    error InsufficientPrizePool(uint256 required, uint256 available);

    constructor(address ticketNFTAddress, uint256 ticketPriceWei) {
        require(ticketNFTAddress != address(0), "TicketNFT address empty");
        require(ticketPriceWei > 0, "Ticket price zero");

        ticketNFT = TicketNFT(ticketNFTAddress);
        ticketPrice = ticketPriceWei;

        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(MANAGER_ROLE, msg.sender);
        _grantRole(ORACLE_ROLE, msg.sender);
        _grantRole(CASHIER_ROLE, msg.sender);

        prizeMultipliers[6] = 1000;
        prizeMultipliers[5] = 50;
        prizeMultipliers[4] = 5;

        _openNextPeriod();
    }

    /**
     * @notice Open the next lottery period. Callable once the current period is settled (or never opened).
     */
    function openNextPeriod() external onlyRole(MANAGER_ROLE) {
        if (currentPeriodId != 0) {
            Period storage currentPeriod = _periods[currentPeriodId];
            if (currentPeriod.status != PeriodStatus.Settled) {
                revert PeriodNotSettled(currentPeriodId);
            }
        }
        _openNextPeriod();
    }

    /**
     * @notice Close ticket sales for the active period.
     */
    function closeCurrentPeriod() external onlyRole(MANAGER_ROLE) {
        if (currentPeriodId == 0) revert InvalidPeriod(currentPeriodId);
        Period storage period = _periods[currentPeriodId];
        if (period.status != PeriodStatus.Selling) revert PeriodNotSelling(currentPeriodId);
        period.status = PeriodStatus.Closed;
        emit PeriodClosed(currentPeriodId);
    }

    /**
     * @notice Submit official winning numbers for a closed period.
     */
    function submitResult(uint256 periodId, uint8[NUMBERS_REQUIRED] calldata winningNumbers)
        external
        onlyRole(ORACLE_ROLE)
    {
        Period storage period = _periods[periodId];
        if (period.status != PeriodStatus.Closed) revert PeriodNotClosed(periodId);

        uint64 mask = _validateAndMask(winningNumbers);
        period.status = PeriodStatus.ResultIn;
        period.resultSet = true;
        period.winningMask = mask;
        for (uint256 i = 0; i < NUMBERS_REQUIRED; i++) {
            period.winningNumbers[i] = winningNumbers[i];
        }

        emit ResultSubmitted(periodId, winningNumbers);
    }

    /**
     * @notice Marks a period as settled after payout reconciliation is complete.
     */
    function settlePeriod(uint256 periodId) external onlyRole(MANAGER_ROLE) {
        Period storage period = _periods[periodId];
        if (period.status != PeriodStatus.ResultIn) revert PeriodNotResultReady(periodId);
        period.status = PeriodStatus.Settled;
        emit PeriodSettled(periodId);
    }

    /**
     * @notice Purchase a single ticket for the current selling period.
     */
    function buyTicket(uint8[NUMBERS_REQUIRED] calldata numbers, string calldata tokenURI)
        external
        payable
        nonReentrant
        returns (uint256 tokenId)
    {
        if (currentPeriodId == 0) revert InvalidPeriod(currentPeriodId);
        if (msg.value != ticketPrice) revert IncorrectPayment(ticketPrice, msg.value);

        Period storage period = _periods[currentPeriodId];
        if (period.status != PeriodStatus.Selling) revert PeriodNotSelling(currentPeriodId);

        uint64 mask = _validateAndMask(numbers);

        tokenId = ticketNFT.mintTicket(msg.sender, tokenURI);

        Ticket storage ticket = _tickets[tokenId];
        ticket.periodId = currentPeriodId;
        ticket.buyer = msg.sender;
        ticket.numberMask = mask;
        ticket.stake = msg.value;
        for (uint256 i = 0; i < NUMBERS_REQUIRED; i++) {
            ticket.numbers[i] = numbers[i];
        }

        period.ticketCount += 1;
        period.totalSales += msg.value;

        emit TicketPurchased(msg.sender, currentPeriodId, tokenId, numbers);
    }

    /**
     * @notice Claims the prize for a winning ticket. Callable by the ticket holder.
     */
    function claimPrize(uint256 tokenId) external nonReentrant returns (uint256 payout) {
        Ticket storage ticket = _tickets[tokenId];
        if (ticket.buyer == address(0)) revert TicketNotFound(tokenId);
        if (ticket.buyer != msg.sender) revert TicketNotOwned(tokenId);
        if (ticket.claimed) revert TicketAlreadyClaimed(tokenId);

        Period storage period = _periods[ticket.periodId];
        if (!(period.status == PeriodStatus.ResultIn || period.status == PeriodStatus.Settled)) {
            revert PeriodNotResultReady(ticket.periodId);
        }
        if (!period.resultSet) revert PeriodNotResultReady(ticket.periodId);

        uint8 matches = _countMatches(ticket.numberMask, period.winningMask);
        uint256 multiplier = prizeMultipliers[matches];
        if (multiplier == 0) revert TicketHasNoPrize(tokenId);

        payout = ticket.stake * multiplier;
        uint256 balance = address(this).balance;
        if (payout > balance) revert InsufficientPrizePool(payout, balance);

        ticket.claimed = true;
        period.paidOut += payout;

        (bool sent, ) = payable(ticket.buyer).call{value: payout}("");
        require(sent, "Prize transfer failed");

        emit PrizeClaimed(ticket.buyer, tokenId, ticket.periodId, matches, payout);
    }

    /**
     * @notice Update ticket price (applies to subsequent purchases).
     */
    function setTicketPrice(uint256 newPrice) external onlyRole(MANAGER_ROLE) {
        require(newPrice > 0, "Ticket price zero");
        ticketPrice = newPrice;
        emit TicketPriceUpdated(newPrice);
    }

    /**
     * @notice Adjust prize multiplier for a given match count.
     */
    function setPrizeMultiplier(uint8 matches, uint256 multiplier) external onlyRole(MANAGER_ROLE) {
        if (matches > NUMBERS_REQUIRED) revert InvalidMatches(matches);
        prizeMultipliers[matches] = multiplier;
        emit PrizeMultiplierUpdated(matches, multiplier);
    }

    /**
     * @notice Allows the cashier to withdraw excess funds (e.g. unused jackpot reserves).
     */
    function withdraw(address payable to, uint256 amount) external onlyRole(CASHIER_ROLE) nonReentrant {
        require(to != address(0), "Withdraw to zero address");
        require(amount <= address(this).balance, "Withdraw exceeds balance");
        (bool sent, ) = to.call{value: amount}("");
        require(sent, "Withdraw transfer failed");
        emit FundsWithdrawn(to, amount);
    }

    /**
     * @notice View helper returning period data.
     */
    function getPeriod(uint256 periodId)
        external
        view
        returns (
            PeriodStatus status,
            bool resultSet,
            uint8[NUMBERS_REQUIRED] memory winningNumbers,
            uint64 winningMask,
            uint256 ticketCount,
            uint256 totalSales,
            uint256 paidOut
        )
    {
        Period storage period = _periods[periodId];
        status = period.status;
        resultSet = period.resultSet;
        winningNumbers = period.winningNumbers;
        winningMask = period.winningMask;
        ticketCount = period.ticketCount;
        totalSales = period.totalSales;
        paidOut = period.paidOut;
    }

    /**
     * @notice Returns stored ticket information.
     */
    function getTicket(uint256 tokenId) external view returns (Ticket memory) {
        return _tickets[tokenId];
    }

    /**
     * @dev Internal helper to open a new period.
     */
    function _openNextPeriod() private {
        uint256 periodId = _nextPeriodId;
        currentPeriodId = periodId;
        _nextPeriodId += 1;

        Period storage period = _periods[periodId];
        period.status = PeriodStatus.Selling;

        emit PeriodOpened(periodId);
    }

    /**
     * @dev Validates and converts an array of numbers into a bitmask representation.
     */
    function _validateAndMask(uint8[NUMBERS_REQUIRED] calldata numbers) private pure returns (uint64 mask) {
        uint8 previousNumber = 0;
        for (uint256 i = 0; i < NUMBERS_REQUIRED; i++) {
            uint8 number = numbers[i];
            if (number < MIN_NUMBER || number > MAX_NUMBER) revert NumbersOutOfRange(number);
            if (number <= previousNumber) revert NumbersNotAscending();
            uint64 bit = uint64(1) << (number - 1);
            if ((mask & bit) != 0) revert NumbersNotAscending(); // duplicates imply unsorted input
            mask |= bit;
            previousNumber = number;
        }
    }

    /**
     * @dev Counts matching numbers based on bitmask intersection.
     */
    function _countMatches(uint64 ticketMask, uint64 winningMask) private pure returns (uint8 count) {
        uint64 value = ticketMask & winningMask;
        while (value != 0) {
            value &= (value - 1);
            count += 1;
        }
    }

    receive() external payable {
        emit FundsDeposited(msg.sender, msg.value);
    }
}
