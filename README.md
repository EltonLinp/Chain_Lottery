# ChainLottery 运行指南

> 建议使用 **Python 3.9**、**Node.js 20** 及 **Hardhat 2.26** 以上版本，确保所有依赖与脚本兼容。

## 项目依赖环境

| 类型 | 说明 |
| --- | --- |
| Python 解释器 | 建议 `3.9.x`，并使用 `venv` 创建隔离环境 |
| Node.js / npm | Node `20.x`（Hardhat 对 Node 18 存在警告） |
| 数据库 | PostgreSQL 14+（若未安装，可暂时使用 SQLite，数据库相关功能会降级） |
| 本地区块链 | Hardhat 内建节点 |

### Python 依赖（`requirements.txt`）

```
Flask==2.2.5
web3==6.11.3
requests==2.31.0
python-dotenv==1.0.1
SQLAlchemy==1.4.54
alembic==1.13.2
psycopg2-binary==2.9.9
gunicorn==20.1.0
pydantic==1.10.18
celery==5.3.6
pytest==7.4.4
pytest-asyncio==0.23.7
eth-typing==3.5.2
```

安装方式（建议在虚拟环境中）：

```powershell
python -m venv .venv（本人用的是python 3.9.8）
.venv\Scripts\activate
pip install -r requirements.txt
```

### Node 依赖

```powershell
npm install
```

## 准备本地区块链（Hardhat）

1. **启动节点** （终端 A）  
   ```powershell
   npx hardhat node --hostname 127.0.0.1
   ```
   终端会打印 20 个测试账号与私钥，请保留窗口不要关闭。

2. **编译 + 部署合约** （终端 B）  
   ```powershell
   npx hardhat compile
   npx hardhat run scripts/deploy.js --network localhost
   ```
   结束后会在 `deployed/localhost.json` 中写入 `ticketNFT`、`lotteryCore` 地址及票价。

## 配置环境变量（`.env`）

复制下列模板到项目根目录的 `.env` 并按实际替换：

```
RPC_URL=http://127.0.0.1:8545
LOTTERY_CONTRACT_ADDRESS=<deploy 输出的 lotteryCore 地址>
LOTTERY_ABI_PATH=artifacts/contracts/LotteryCore.sol/LotteryCore.json
DATABASE_URL=postgresql://chainlottery:密码@localhost:5432/chainlottery
FLASK_SECRET_KEY=change-me
ADMIN_API_KEY=<可选，留空则不校验>
ORACLE_SIGNER=<Hardhat 节点输出的私钥（带 0x，长度 66）>
```

- `ORACLE_SIGNER` 必须是部署者或已被授予 `MANAGER_ROLE`、`ORACLE_ROLE` 的账户私钥，否则后台无法在链上提交开奖交易。
- 如果还没有安装 PostgreSQL，可暂时把 `DATABASE_URL` 改为 `sqlite:///chainlottery.db`，功能会自动降级。

## 启动后端服务

每次修改 `.env` 后，需要重启 Flask：

```powershell
.venv\Scripts\activate
flask --app backend.app:create_app run
```

后台默认监听 `http://127.0.0.1:5000`。

## 启动前端 / 管理页面

- 用户界面：`http://127.0.0.1:5000/`
- 管理后台：`http://127.0.0.1:5000/admin`

使用提示：

1. 浏览器安装 MetaMask（或兼容钱包），新建网络：
   - RPC URL：`http://127.0.0.1:8545`
   - Chain ID：`31337`
   - 货币符号随意（如 ETH）。
2. 在管理页顶部输入 `ADMIN_API_KEY`（若 `.env` 中留空可忽略）。
3. 开奖流程会在链上自动执行：关闭售票 → 写入结果 → 结算 → 打开下一期，并同步数据库。若签名账户没权限，会返回授权错误。

## PostgreSQL 初始化（如需）

```powershell
createdb chainlottery
psql -d chainlottery -c "CREATE USER chainlottery WITH PASSWORD 'yourpassword';"
psql -d chainlottery -c "GRANT ALL PRIVILEGES ON DATABASE chainlottery TO chainlottery;"
psql -d chainlottery -c "GRANT ALL ON SCHEMA public TO chainlottery;"
```
把 `.env` 中的 `DATABASE_URL` 替换成对应的连接串即可。

## 常用调试命令

| 目的 | 命令 |
| --- | --- |
| 查看链上合约是否部署 | `npx hardhat console --network localhost` <br>`> await ethers.provider.getCode("<LOTTERY_CONTRACT_ADDRESS>");` 返回非 `"0x"` 即成功 |
| 重新部署合约 | `npx hardhat run scripts/deploy.js --network localhost` |
| 后端单元测试 | `python -m pytest backend/tests`（需要额外 mock 配置） |
| 清空数据库记录（慎用） | `DELETE FROM draws; DELETE FROM tickets; UPDATE system_state SET current_period = 1 WHERE id = 1;` |

## 全部启动流程快速回顾

```powershell
# 终端 A：本地区块链
npx hardhat node --hostname 127.0.0.1

# 终端 B：编译并部署
npx hardhat compile
npx hardhat run scripts/deploy.js --network localhost
（更新 .env 中的 LOTTERY_CONTRACT_ADDRESS、ORACLE_SIGNER 等）

# 终端 C：Flask 后端
.venv\Scripts\activate
flask --app backend.app:create_app run
```

浏览器访问 `http://127.0.0.1:5000` 体验购票、`http://127.0.0.1:5000/admin` 执行开奖即可。
