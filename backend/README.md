# ChainLottery Backend

Flask 后端负责购票、开奖、领奖等业务接口，并将数据持久化到数据库（默认 PostgreSQL，可回退到 SQLite）。

## 模块结构

| 文件 | 说明 |
| ---- | ---- |
| pp.py | Flask 应用入口，注册蓝图并在启动时初始化数据库。 |
| config.py | 统一加载 Flask/Web3/数据库/管理端配置。 |
| db.py | SQLAlchemy 引擎与 Session 管理。 |
| models.py | ORM 模型，包含 Ticket 与 Draw。 |
| services/blockchain.py | 读取 Hardhat ABI，封装链上交互（连接失败时自动降级为演示模式）。 |
| services/tickets.py / services/draws.py | 票据与开奖仓储逻辑。 |
| outes/ | health、	ickets、dmin 三个蓝图。 |
| schemas.py | Pydantic 请求/响应模型。 |
| 	ests/ | 单元测试，默认使用 SQLite 内存库并 Mock Web3。 |

## 环境配置

.env 示例：

`env
RPC_URL=http://127.0.0.1:8545
LOTTERY_CONTRACT_ADDRESS=0x0000000000000000000000000000000000000000
LOTTERY_ABI_PATH=artifacts/contracts/LotteryCore.sol/LotteryCore.json
DATABASE_URL=postgresql://chainlottery:yourpassword@localhost:5432/chainlottery
FLASK_SECRET_KEY=change-me
ADMIN_API_KEY=changeme   # 可选，留空则不校验管理端 Token
`

未设置 DATABASE_URL 时默认写入 sqlite:///chainlottery.db。首次启动 Flask 会自动创建缺失的表。

## 运行服务

`ash
python -m unittest discover backend/tests     # 可选，运行单测
export FLASK_APP=backend.app:create_app
flask run --reload
`

> Windows PowerShell：
>
> `powershell
> setx FLASK_APP "backend.app:create_app"
> flask run --reload
> `

## API 概览

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| GET /health | 健康检查 |
| POST /tickets | 购票，返回生成的票据 ID |
| GET /tickets/<ticket_id> | 查询票据状态、命中信息 |
| POST /tickets/<ticket_id>/claim | 领奖（当前为示例逻辑，连接链上时会发送真实交易） |
| GET /admin/api/periods | 管理端获取期次列表（需 X-Admin-Token） |
| POST /admin/api/draws | 管理端手动提交开奖号码（需 X-Admin-Token） |

## 前端页面

- /：位于 rontend/index.html，用于普通用户连接钱包（演示）、选号购票、刷新与领奖。
- /admin：位于 rontend/admin.html，用于运营方手动提交开奖、查看各期次购票情况。若配置了 ADMIN_API_KEY，需在页面右上角保存 Token 后才能调用接口。
- 所有静态资源位于 /assets。

## 手动开奖流程

1. 用户购票后，可在 /admin 页面查看最新期次（表格来自 /admin/api/periods）。
2. 运营方在“手动提交开奖结果”中填写六个号码并提交。
3. 后端会：
   - 将开奖号码写入 draws 表；
   - 为对应期次的每张票计算命中数及奖金基数；
   - 返回中奖票数，前端刷新期次即可看到开奖号码。
4. 用户在前端刷新票据后，可执行领奖；若链上 RPC 连通，则会尝试发送真实 claimPrize 交易。

## 对接 Hardhat 本地链

1. 启动节点与部署合约：
   `ash
   npm install
   npx hardhat compile
   npm run node            # 终端 A：启动 Hardhat 节点
   npm run deploy:local    # 终端 B：部署 TicketNFT 与 LotteryCore
   `
   部署输出记录在 deployed/localhost.json，ABI 位于 rtifacts/contracts/LotteryCore.sol/LotteryCore.json。

2. 更新 .env：
   `
   LOTTERY_CONTRACT_ADDRESS=<deploy 输出的 LotteryCore 地址>
   RPC_URL=http://127.0.0.1:8545
   LOTTERY_ABI_PATH=artifacts/contracts/LotteryCore.sol/LotteryCore.json
   DATABASE_URL=postgresql://chainlottery:yourpassword@localhost:5432/chainlottery
   ADMIN_API_KEY=changeme
   `

3. 启动 Flask 服务：
   `ash
   flask --app backend.app:create_app run --reload
   `

若 RPC 无法连通（例如未运行 Hardhat），相关调用会记录 WARNING 并回退到演示模式（期次为 -1，领奖返回模拟交易哈希）。

## PostgreSQL 速查

`ash
createdb chainlottery
psql -d chainlottery -c "CREATE USER chainlottery WITH PASSWORD 'yourpassword';"
psql -d chainlottery -c "GRANT ALL PRIVILEGES ON DATABASE chainlottery TO chainlottery;"
psql -d chainlottery -c "GRANT ALL ON SCHEMA public TO chainlottery;"
`

随后将 .env 中 DATABASE_URL 改成 postgresql://chainlottery:yourpassword@localhost:5432/chainlottery。如果使用其它账号，请相应调整。
