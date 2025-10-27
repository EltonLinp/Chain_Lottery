import os
os.environ['RPC_URL']='http://localhost:8545'
os.environ['LOTTERY_CONTRACT_ADDRESS']='0x'+'0'*40
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['ADMIN_API_KEY']='test-admin'

from backend.app import create_app
app = create_app()
client = app.test_client()
headers={'X-Admin-Token':'test-admin'}
print('periods', client.get('/admin/api/periods', headers=headers).json)
resp = client.post('/tickets', json={'numbers':[1,2,3,4,5,6]})
print('purchase', resp.status_code, resp.json)
resp = client.post('/admin/api/draws', headers=headers, json={'period_id':1, 'winning_numbers':[1,2,3,4,30,31]})
print('draw', resp.status_code, resp.json)

