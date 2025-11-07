# 前端对接指南（简版）

## 依赖信息
- 合约地址（Sepolia）：`0xb802F2035C334dB3Ac10bB630Fb731A8496e7644`
- ABI 路径：`artifacts/contracts/ChainLottery.sol/ChainLottery.json`
- 唯一在售期，可通过合约 `currentRoundId` 获取最新期号。

## 直接连链（前端使用 ethers.js）
```ts
import { ethers } from "ethers";
import abi from "./ChainLottery.json";

const provider = new ethers.JsonRpcProvider(import.meta.env.VITE_RPC_URL);
const contract = new ethers.Contract(
  "0xb802F2035C334dB3Ac10bB630Fb731A8496e7644",
  abi.abi,
  provider,
);

// 查询当前轮次
const roundId = await contract.currentRoundId();
const round = await contract.getRound(roundId);

// 监听事件
contract.on("TicketPurchased", (roundId, ticketId, player, numbers) => {
  console.log({ roundId, ticketId, player, numbers });
});
```

## 调用合约（用户签名）
- 购票：`contract.connect(signer).buyTicket(roundId, numbers, { value: ticketPrice })`
- 查询奖金：`contract.prizeOf(roundId, ticketId)`
- 兑奖：`contract.connect(signer).claim(roundId, ticketId)`
> `numbers` 必须是 6 个严格递增的 1–49 整数；`ticketPrice` 可从 `round.ticketPrice` 读取。

## 只读 BFF（可选）
后端已提供快速查询 API，避免前端自己扫事件：

| Endpoint | 描述 |
| --- | --- |
| `GET http://localhost:4100/healthz` | 服务状态 + 网络信息 |
| `GET http://localhost:4100/periods` | 当前轮次详情（销售窗口、奖池、开奖号码等） |
| `GET http://localhost:4100/tickets?user=0x...` | 指定地址的购票列表与实时可兑金额 |

部署时可把 BFF 暴露在自己的域名下，前端只需调 REST 接口即可。

## 通用注意事项
- 只有在 `round.status === ResultCommitted (3)` 时，`prizeOf` 才会返回非零金额。
- 新一期开始前需确保上一期 `commitResult` 和 `claim` 已完成。
- 所有金额均为 Wei，前端显示前记得转换为 ETH。
