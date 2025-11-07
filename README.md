# ChainLottery 后端指南

## 工具版本
| 工具 | 版本 |
| --- | --- |
| Node.js | 20.19.5 |
| npm | 10.8.2 |
| Hardhat | 2.26.5 |

## 目录速览
- `contracts/ChainLottery.sol`：6/49 合约（开期 → 购票 → 关期 → 官方开奖 → 兑奖）。
- `test/ChainLottery.test.js`：Hardhat 单测，覆盖生命周期、号码校验、开奖逻辑与兑奖。
- `scripts/deploy.js`：部署脚本，按 `.env` 自动设置 `ORACLE_ROLE`。
- `scripts/demo-flow.js`：无头脚本，串联开期→购票→关期→开奖→兑奖并输出日志。
- `oracle/`：Node.js 预言机，读取 `results.json` 校验号码并调用 `commitResult`，自带幂等和重试。
- `bff/`：Express 只读 API，提供 `/healthz`、`/periods`、`/tickets?user=0x...`。
- `deployed/`：各网络部署信息（如 `deployed/sepolia.json`）。
- `logs/demo-run-*.json`：无头脚本在 Sepolia 的演示日志。
- `PLAN.md`：三日执行计划（中文策划书版本）。

## 环境变量（根目录 `.env`）
```
RPC_URL=https://sepolia.infura.io/v3/XXXX
PRIVATE_KEY=0x...              # OWNER / 部署钱包
ETHERSCAN_API_KEY=XXXX
CONTRACT_ADDRESS=0x...         # 部署后更新
ORACLE_ADDRESS=0x...           # 预言机角色地址
ORACLE_PRIVATE_KEY=0x...       # 预言机钱包
PLAYER_PRIVATE_KEY=0x...       # demo-flow 用的购票/兑奖钱包
RESULTS_PATH=oracle/results.json
CONTRACT_ABI_PATH=artifacts/contracts/ChainLottery.sol/ChainLottery.json
ORACLE_MAX_RETRIES=3
ORACLE_RETRY_DELAY_MS=5000
DEMO_TICKET_PRICE_ETH=0.01
DEMO_SALES_WINDOW=600
DEMO_WINNING_NUMBERS=1,5,12,23,34,45
PORT=4100                      # BFF 监听端口
```
`oracle/.env` 与 `.env.example` 可以复用同样字段。

## 合约要点
- **单期走完再开新期**：`openRound`（OWNER）→ `closeRound` → `commitResult`（ORACLE）→ `claim`。
- **号码规则**：`uint32[6]`，范围 1–49 且严格递增；购票与开奖共用同一校验函数。
- **奖池均分**：所有购票金额累积进 `jackpot`，官方开奖后按组合哈希得到 `winnersCount`，兑奖金额 = `jackpot / winnersCount`。
- **事件**：`RoundOpened`、`RoundClosed`、`TicketPurchased`、`ResultCommitted`、`PrizePaid`，方便前端/后端监听。
- **安全**：基于 OpenZeppelin `AccessControl` 与 `ReentrancyGuard`，并校验票价、截止时间、幂等提交等边界。

## 开发与测试
```bash
npm install
npm run build
npm test
```

## 部署到 Sepolia
```bash
npm run deploy:sepolia
# 记得同步 deployed/sepolia.json 与 .env 中的地址
```

## 无头演示脚本
```bash
npx hardhat run scripts/demo-flow.js --network sepolia
```
脚本会读取 `.env` 中的三个钱包依次执行开期、购票、关期、开奖、兑奖，并把结果写入 `logs/demo-run-<timestamp>.json`。

## 预言机脚本
```bash
cd oracle
npm install        # 首次
npm run start      # 读取 results.json，校验号码并调用 commitResult
```
脚本会打印 roundId、号码与 oracle 地址；若目标期已开奖则自动跳过，否则按配置重试提交。

## BFF API
```bash
cd bff
npm install        # 首次
npm run dev        # 或 npm run start，默认监听 PORT=4100
```
接口：
- `GET /healthz` → `{ status, network, chainId, contract }`
- `GET /periods` → 当前轮次状态（销售时间、票价、奖池、开奖号码等）
- `GET /tickets?user=0x...` → 指定地址所有购票记录与实时 `prizeOf`（默认回溯 5000 区块）

## 交付清单与证据
- Sepolia 合约：`0xb802F2035C334dB3Ac10bB630Fb731A8496e7644`（详见 `deployed/sepolia.json`）。
- 预言机：`oracle/index.js`、`oracle/results.json`、`oracle/.env.example`。
- 闭环日志：`logs/demo-run-*.json`，记录 `openRound -> buyTicket -> closeRound -> commitResult -> claim` 的所有交易哈希。
- BFF API 文档与 `.env.example`，可供前端直接复现或验收。

