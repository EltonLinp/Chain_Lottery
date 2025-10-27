# ChainLottery Backend

Flask ��˸���Ʊ���������콱��ҵ��ӿڣ��������ݳ־û������ݿ⣨Ĭ�� PostgreSQL���ɻ��˵� SQLite����

## ģ��ṹ

| �ļ� | ˵�� |
| ---- | ---- |
| pp.py | Flask Ӧ����ڣ�ע����ͼ��������ʱ��ʼ�����ݿ⡣ |
| config.py | ͳһ���� Flask/Web3/���ݿ�/��������á� |
| db.py | SQLAlchemy ������ Session ���� |
| models.py | ORM ģ�ͣ����� Ticket �� Draw�� |
| services/blockchain.py | ��ȡ Hardhat ABI����װ���Ͻ���������ʧ��ʱ�Զ�����Ϊ��ʾģʽ���� |
| services/tickets.py / services/draws.py | Ʊ���뿪���ִ��߼��� |
| outes/ | health��	ickets��dmin ������ͼ�� |
| schemas.py | Pydantic ����/��Ӧģ�͡� |
| 	ests/ | ��Ԫ���ԣ�Ĭ��ʹ�� SQLite �ڴ�Ⲣ Mock Web3�� |

## ��������

.env ʾ����

`env
RPC_URL=http://127.0.0.1:8545
LOTTERY_CONTRACT_ADDRESS=0x0000000000000000000000000000000000000000
LOTTERY_ABI_PATH=artifacts/contracts/LotteryCore.sol/LotteryCore.json
DATABASE_URL=postgresql://chainlottery:yourpassword@localhost:5432/chainlottery
FLASK_SECRET_KEY=change-me
ADMIN_API_KEY=changeme   # ��ѡ��������У������ Token
`

δ���� DATABASE_URL ʱĬ��д�� sqlite:///chainlottery.db���״����� Flask ���Զ�����ȱʧ�ı�

## ���з���

`ash
python -m unittest discover backend/tests     # ��ѡ�����е���
export FLASK_APP=backend.app:create_app
flask run --reload
`

> Windows PowerShell��
>
> `powershell
> setx FLASK_APP "backend.app:create_app"
> flask run --reload
> `

## API ����

| ���� | ·�� | ˵�� |
| ---- | ---- | ---- |
| GET /health | ������� |
| POST /tickets | ��Ʊ���������ɵ�Ʊ�� ID |
| GET /tickets/<ticket_id> | ��ѯƱ��״̬��������Ϣ |
| POST /tickets/<ticket_id>/claim | �콱����ǰΪʾ���߼�����������ʱ�ᷢ����ʵ���ף� |
| GET /admin/api/periods | ����˻�ȡ�ڴ��б��� X-Admin-Token�� |
| POST /admin/api/draws | ������ֶ��ύ�������루�� X-Admin-Token�� |

## ǰ��ҳ��

- /��λ�� rontend/index.html��������ͨ�û�����Ǯ������ʾ����ѡ�Ź�Ʊ��ˢ�����콱��
- /admin��λ�� rontend/admin.html��������Ӫ���ֶ��ύ�������鿴���ڴι�Ʊ������������� ADMIN_API_KEY������ҳ�����ϽǱ��� Token ����ܵ��ýӿڡ�
- ���о�̬��Դλ�� /assets��

## �ֶ���������

1. �û���Ʊ�󣬿��� /admin ҳ��鿴�����ڴΣ�������� /admin/api/periods����
2. ��Ӫ���ڡ��ֶ��ύ�������������д�������벢�ύ��
3. ��˻᣺
   - ����������д�� draws ��
   - Ϊ��Ӧ�ڴε�ÿ��Ʊ���������������������
   - �����н�Ʊ����ǰ��ˢ���ڴμ��ɿ����������롣
4. �û���ǰ��ˢ��Ʊ�ݺ󣬿�ִ���콱�������� RPC ��ͨ����᳢�Է�����ʵ claimPrize ���ס�

## �Խ� Hardhat ������

1. �����ڵ��벿���Լ��
   `ash
   npm install
   npx hardhat compile
   npm run node            # �ն� A������ Hardhat �ڵ�
   npm run deploy:local    # �ն� B������ TicketNFT �� LotteryCore
   `
   ���������¼�� deployed/localhost.json��ABI λ�� rtifacts/contracts/LotteryCore.sol/LotteryCore.json��

2. ���� .env��
   `
   LOTTERY_CONTRACT_ADDRESS=<deploy ����� LotteryCore ��ַ>
   RPC_URL=http://127.0.0.1:8545
   LOTTERY_ABI_PATH=artifacts/contracts/LotteryCore.sol/LotteryCore.json
   DATABASE_URL=postgresql://chainlottery:yourpassword@localhost:5432/chainlottery
   ADMIN_API_KEY=changeme
   `

3. ���� Flask ����
   `ash
   flask --app backend.app:create_app run --reload
   `

�� RPC �޷���ͨ������δ���� Hardhat������ص��û��¼ WARNING �����˵���ʾģʽ���ڴ�Ϊ -1���콱����ģ�⽻�׹�ϣ����

## PostgreSQL �ٲ�

`ash
createdb chainlottery
psql -d chainlottery -c "CREATE USER chainlottery WITH PASSWORD 'yourpassword';"
psql -d chainlottery -c "GRANT ALL PRIVILEGES ON DATABASE chainlottery TO chainlottery;"
psql -d chainlottery -c "GRANT ALL ON SCHEMA public TO chainlottery;"
`

��� .env �� DATABASE_URL �ĳ� postgresql://chainlottery:yourpassword@localhost:5432/chainlottery�����ʹ�������˺ţ�����Ӧ������
