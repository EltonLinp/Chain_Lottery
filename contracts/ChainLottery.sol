// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Address.sol";

/**
 * @title ChainLottery
 * @notice Single-round 6/49 lottery covering buy -> close -> oracle draw -> claim.
 *         Only one round can be active at a time and jackpots are split among 6/6 winners.
 */
contract ChainLottery is AccessControl, ReentrancyGuard {
    using Address for address payable;

    uint8 public constant NUMBERS_COUNT = 6;
    uint32 public constant MIN_NUMBER = 1;
    uint32 public constant MAX_NUMBER = 49;

    bytes32 public constant OWNER_ROLE = keccak256("OWNER_ROLE");
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");

    enum RoundStatus {
        None,
        Open,
        Closed,
        ResultCommitted
    }

    struct Round {
        uint256 roundId;
        uint64 salesStart;
        uint64 salesEnd;
        uint256 ticketPrice;
        uint256 jackpot;
        uint256 claimedJackpot;
        RoundStatus status;
        uint32 ticketCount;
        uint32 winnersCount;
        uint32[NUMBERS_COUNT] winningNumbers;
    }

    struct Ticket {
        uint256 roundId;
        address player;
        uint64 purchasedAt;
        bool paidOut;
        uint32[NUMBERS_COUNT] numbers;
    }

    /// roundId => Round state
    mapping(uint256 => Round) private _rounds;
    /// ticketId => Ticket data
    mapping(uint256 => Ticket) private _tickets;
    /// roundId => combination hash => count
    mapping(uint256 => mapping(bytes32 => uint256)) private _combinationCounts;

    uint256 public currentRoundId;
    uint256 public nextTicketId;

    event RoundOpened(uint256 indexed roundId, uint64 salesEnd, uint256 ticketPrice);
    event RoundClosed(uint256 indexed roundId);
    event TicketPurchased(
        uint256 indexed roundId,
        uint256 indexed ticketId,
        address indexed player,
        uint32[NUMBERS_COUNT] numbers
    );
    event ResultCommitted(
        uint256 indexed roundId,
        uint32[NUMBERS_COUNT] winningNumbers,
        uint32 winnersCount
    );
    event PrizePaid(
        uint256 indexed roundId,
        uint256 indexed ticketId,
        address indexed player,
        uint256 amount
    );

    error ActiveRoundExists();
    error InvalidSalesEnd();
    error InvalidTicketPrice();
    error RoundNotOpen();
    error RoundNotClosed();
    error ResultAlreadyCommitted();
    error ResultNotCommitted();
    error SalesClosed();
    error TicketNotFound();
    error RoundNotFound();
    error TicketAlreadyClaimed();
    error UnauthorizedClaimer();
    error TicketNotWinner();
    error NumbersOutOfRange();
    error NumbersNotIncreasing();
    error WinnersOverflow();

    constructor() {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(OWNER_ROLE, msg.sender);
        _grantRole(ORACLE_ROLE, msg.sender);
    }

    // ========= View helpers =========

    function getRound(uint256 roundId) external view returns (Round memory) {
        Round memory round = _rounds[roundId];
        if (round.roundId == 0) revert RoundNotFound();
        return round;
    }

    function getTicket(uint256 ticketId) external view returns (Ticket memory) {
        Ticket memory ticket = _tickets[ticketId];
        if (ticket.roundId == 0) revert TicketNotFound();
        return ticket;
    }

    function prizeOf(uint256 roundId, uint256 ticketId) external view returns (uint256) {
        Round storage round = _requireRound(roundId);
        if (round.status != RoundStatus.ResultCommitted) {
            return 0;
        }

        Ticket storage ticket = _requireTicket(ticketId);
        if (ticket.roundId != roundId) revert TicketNotFound();

        return _calculatePrize(round, ticket);
    }

    // ========= Core lifecycle =========

    function openRound(uint64 salesEnd, uint256 ticketPrice) external onlyRole(OWNER_ROLE) {
        if (ticketPrice == 0) revert InvalidTicketPrice();
        if (salesEnd <= block.timestamp) revert InvalidSalesEnd();

        if (currentRoundId != 0) {
            Round storage current = _rounds[currentRoundId];
            if (current.status != RoundStatus.ResultCommitted) revert ActiveRoundExists();
        }

        currentRoundId += 1;
        Round storage round = _rounds[currentRoundId];
        round.roundId = currentRoundId;
        round.salesStart = uint64(block.timestamp);
        round.salesEnd = salesEnd;
        round.ticketPrice = ticketPrice;
        round.status = RoundStatus.Open;

        emit RoundOpened(currentRoundId, salesEnd, ticketPrice);
    }

    function closeRound(uint256 roundId) external onlyRole(OWNER_ROLE) {
        Round storage round = _requireRound(roundId);
        if (round.status != RoundStatus.Open) revert RoundNotOpen();
        round.status = RoundStatus.Closed;
        emit RoundClosed(roundId);
    }

    function buyTicket(
        uint256 roundId,
        uint32[NUMBERS_COUNT] calldata numbers
    ) external payable returns (uint256 ticketId) {
        Round storage round = _requireRound(roundId);
        if (round.status != RoundStatus.Open) revert RoundNotOpen();
        if (block.timestamp >= round.salesEnd) revert SalesClosed();
        if (msg.value != round.ticketPrice) revert InvalidTicketPrice();

        uint32[NUMBERS_COUNT] memory nums = numbers;
        bytes32 key = _validateNumbers(nums);

        ticketId = ++nextTicketId;
        Ticket storage ticket = _tickets[ticketId];
        ticket.roundId = roundId;
        ticket.player = msg.sender;
        ticket.purchasedAt = uint64(block.timestamp);
        ticket.paidOut = false;
        ticket.numbers = nums;

        round.ticketCount += 1;
        round.jackpot += msg.value;
        _combinationCounts[roundId][key] += 1;

        emit TicketPurchased(roundId, ticketId, msg.sender, nums);
        return ticketId;
    }

    function commitResult(
        uint256 roundId,
        uint32[NUMBERS_COUNT] calldata winningNumbers
    ) external onlyRole(ORACLE_ROLE) {
        Round storage round = _requireRound(roundId);
        if (round.status == RoundStatus.ResultCommitted) revert ResultAlreadyCommitted();
        if (round.status != RoundStatus.Closed) revert RoundNotClosed();

        uint32[NUMBERS_COUNT] memory resultNumbers = winningNumbers;
        bytes32 key = _validateNumbers(resultNumbers);

        for (uint256 i = 0; i < NUMBERS_COUNT; i++) {
            round.winningNumbers[i] = resultNumbers[i];
        }
        uint256 winners = _combinationCounts[roundId][key];
        if (winners > type(uint32).max) revert WinnersOverflow();
        round.winnersCount = uint32(winners);
        round.status = RoundStatus.ResultCommitted;

        emit ResultCommitted(roundId, round.winningNumbers, round.winnersCount);
    }

    function claim(uint256 roundId, uint256 ticketId) external nonReentrant {
        Round storage round = _requireRound(roundId);
        if (round.status != RoundStatus.ResultCommitted) revert ResultNotCommitted();

        Ticket storage ticket = _requireTicket(ticketId);
        if (ticket.roundId != roundId) revert TicketNotFound();
        if (ticket.player != msg.sender) revert UnauthorizedClaimer();
        if (ticket.paidOut) revert TicketAlreadyClaimed();

        uint256 prize = _calculatePrize(round, ticket);
        if (prize == 0) revert TicketNotWinner();

        ticket.paidOut = true;
        round.claimedJackpot += prize;
        payable(ticket.player).sendValue(prize);

        emit PrizePaid(roundId, ticketId, ticket.player, prize);
    }

    // ========= Internal helpers =========

    function _requireRound(uint256 roundId) private view returns (Round storage) {
        Round storage round = _rounds[roundId];
        if (round.roundId == 0) revert RoundNotFound();
        return round;
    }

    function _requireTicket(uint256 ticketId) private view returns (Ticket storage) {
        Ticket storage ticket = _tickets[ticketId];
        if (ticket.roundId == 0) revert TicketNotFound();
        return ticket;
    }

    function _calculatePrize(
        Round storage round,
        Ticket storage ticket
    ) private view returns (uint256) {
        if (round.winnersCount == 0) {
            return 0;
        }
        if (!_numbersMatch(ticket.numbers, round.winningNumbers)) {
            return 0;
        }
        return round.jackpot / round.winnersCount;
    }

    function _validateNumbers(
        uint32[NUMBERS_COUNT] memory numbers
    ) private pure returns (bytes32) {
        uint32 previous = 0;
        for (uint256 i = 0; i < NUMBERS_COUNT; i++) {
            uint32 num = numbers[i];
            if (num < MIN_NUMBER || num > MAX_NUMBER) revert NumbersOutOfRange();
            if (i > 0 && num <= previous) revert NumbersNotIncreasing();
            previous = num;
        }
        return keccak256(abi.encode(numbers));
    }

    function _numbersMatch(
        uint32[NUMBERS_COUNT] storage a,
        uint32[NUMBERS_COUNT] storage b
    ) private view returns (bool) {
        for (uint256 i = 0; i < NUMBERS_COUNT; i++) {
            if (a[i] != b[i]) {
                return false;
            }
        }
        return true;
    }
}
