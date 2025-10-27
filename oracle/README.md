# Oracle Service Overview

The oracle layer bridges official ChainLottery draw data into the on-chain `LotteryCore` contract.

## Responsibilities

- Poll or receive draw results from trusted data sources (e.g., official lottery website API).
- Validate and normalize draw payloads (numbers sorted ascending, date/issue metadata present).
- Sign and broadcast a `submitResult` transaction with the oracle role key.
- Provide observability: structured logs, error notifications, and retry strategies.

## Components

| Module | Purpose |
| ------ | ------- |
| `config.py` | Load typed configuration from `.env`/environment variables. |
| `datasource/base.py` | Abstract interface for result providers. |
| `datasource/http_api.py` | Implementation fetching draw data from an HTTP JSON endpoint (extensible). |
| `lottery_client.py` | Thin wrapper around `web3.py` for encoding and sending contract calls. |
| `scheduler.py` | Polling loop with retry/backoff and idempotence guard. |
| `service.py` | CLI entrypoint to run the oracle pipeline end-to-end. |

## Data Flow

1. `scheduler` triggers a fetch cycle.
2. `datasource` fetches & parses the latest issue’s numbers.
3. `lottery_client` checks on-chain period status and sends `submitResult`.
4. Responses and errors are logged; failed attempts schedule retries.

## Verification

1. Export required environment variables (see `oracle/.env.example`).
2. Run Hardhat local node (`npx hardhat node`) and deploy the contracts with a manager/oracle signer.
3. Fund the oracle signer account and grant it the `ORACLE_ROLE` on `LotteryCore`.
4. Execute `python oracle/service.py --once` to push a single result.
5. Verify emitted events via Hardhat console or `hardhat test` extensions.

Unit tests for the oracle layer live under `oracle/tests/` and mock external dependencies to validate parsing, retries, and transaction submission logic. 运行本地测试：

```bash
python -m unittest discover oracle/tests
```
