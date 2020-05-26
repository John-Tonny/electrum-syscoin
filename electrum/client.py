
import hashlib
import aiohttp
import asyncio
import queue
import json
import time
import threading
from electrum.constants import MASTERNODE_PORTS
from electrum import constants
import random

POST_TIMEOUT = 500
GET_TIMEOUT = 1000

class Client:

    def __init__(self, wallet):
        self.wallet = wallet
        self.loop = self.wallet.network.asyncio_loop
        self.money_queue = queue.Queue()    
                
        self.conversion_account = {}
        self.conversion_list = []
        self.conversion_total = 0
        self.conversion_cur_page = 1
        self.conversion_page_size = 20
        
        self.money_ratio = 0
        timer = threading.Timer(0.5, self.get_money_ratio)
        timer.start()    

    def get_header_auth(self):
        m = hashlib.md5()
        name = constants.API_NAME
        password = constants.API_PASSWORD
        privkey = constants.API_PRIVKEY
        m.update(str.encode(name + password + privkey))
        return m.hexdigest()

    def post_req(self, url, data, rqueue):
        async def _post_req(url, data, rqueue):
            async with aiohttp.ClientSession() as session:
                headers = {'Auth': self.get_header_auth()}                
                method = constants.API_URL + url
                try:
                    async with session.post(method, headers=headers, data=data) as resp:
                        resp = await resp.text(encoding='utf-8')
                        rqueue.put(resp)
                except Exception as e:
                    resp = {}
                    resp['code'] = '-1000'
                    rqueue.put(resp)
                    print(str(e))
                    
        asyncio.run_coroutine_threadsafe(_post_req(url, data, rqueue), self.loop)
        
    def post_async_req(self, url, data, queue:asyncio.Queue):
        async def _post_req(url, data, queue):
            async with aiohttp.ClientSession() as session:
                headers = {'Auth': self.get_header_auth()}                
                method = constants.API_URL + url
                #with aiohttp.Timeout(POST_TIMEOUT):
                async with session.post(method, headers=headers, data=data) as resp:
                    resp = await resp.text(encoding='utf-8')
                    queue.put(resp)
                    
        asyncio.run_coroutine_threadsafe(_post_req(url, data, queue), self.loop)

    def get_req(self, url, data, rqueue):
        async def _get_req(url, data, rqueue):
            async with aiohttp.ClientSession() as session:
                headers = {'Auth': self.get_header_auth()}                
                method = constants.API_URL + url
                try:
                    async with session.get(method, headers=headers, data=data) as resp:
                        resp = await resp.text(encoding='utf-8')
                        rqueue.put(resp)
                except Exception as e:
                    resp = {}
                    resp['code'] = '-1000'
                    rqueue.put(resp)
                    print(str(e))
                
        asyncio.run_coroutine_threadsafe(_get_req(url, data, rqueue), self.loop)

    def post_register(self, mobilephone, address, password=''):
        url = 'useracocunt/accpet'
        data = {'phone': mobilephone, 'userAccount': address, 'code': password}
        register_queue = queue.Queue()        
        self.post_req(url, data, register_queue)
        resp = register_queue.get()
        try:
            ret  = json.loads(resp, strict=False)
            if ret["code"] == 200:
                return True
            return False
        except Exception as e:
            return False
    
    
    def get_money_ratio(self):
        url = 'fundValue/latest'
        self.get_req(url, None, self.money_queue)
        try:
            resp = json.loads(self.money_queue.get(), strict=False)
            if resp['code'] == 200:
                self.money_ratio = resp['data']['fundValue']
        except Exception as e:
            pass
        
        
        timer = threading.Timer(10 + random.randrange(1,10), self.get_money_ratio)
        timer.start()        
                
    def post_conversion(self, txid, amount, fee, dstAccount, srcAccount, payWay, payName, payAccount, payBank, payBankSub, remark):
        phone = self.get_phone()        
        url = 'cashpool/output/apply'
        data = {}
        data['phone'] = phone
        data['txid'] = txid
        data['amount'] = amount
        data['fee'] = fee
        data['dstAccount'] = dstAccount
        data['srcAccount'] = srcAccount
        data['payWay'] = payWay
        data['payName'] = payName
        data['payAccount'] = payAccount
        data['payBank'] = payBank
        data['payBankSub'] = payBankSub
        data['remark'] = remark
        conversion_queue = queue.Queue()        
        self.post_req(url, data, conversion_queue)
        resp = conversion_queue.get()
        return json.loads(resp, strict=False)
        
    def get_masternodes(self):
        phone = self.get_phone()
        url = 'nodes/getPhoneNode?phone=%s' % phone
        masternode_queue = queue.Queue()        
        self.get_req(url, None, masternode_queue)
        resp = masternode_queue.get()
        resp = json.loads(resp, strict=False)
        if False:
            resp = {}
            data = [{'ip':'52.82.14.25:9069', 'genkey': '5KTbFcwYns3QmTuzFMEoSbqxoF3u1a2DneNKbsuRAJoAJoLMhAw'},
                    {'ip':'47.104.25.28:9069', 'genkey': '5JcP6XZBngpgXkUAYXb3i9B2X3cYymANr7o1danBthigsnGp5Qc'},
                    {'ip':'120.24.96.245:9080', 'genkey': '5JcP6XZBngpgXkUAYXb3i9B2X3cYymANr7o1danBthigsnGp5Qc'},
                    {'ip':'1.2.3.6:9069', 'genkey': '5KMmZ1jWDntnYdunmJDRze2xuBRRZxTeoTbf37eJt8ZrP6NVGMV'}]
            
            for mn in data:
                key = mn['ip']
                resp[key] = mn['genkey']
            return resp
        if resp['code'] == 200:
            try:
                data = resp['data']
                ret = {}
                if isinstance(data, dict):
                    ip = data['ip'] + ":" + str(MASTERNODE_PORTS)
                    ret[ip] = data['genkey']
                elif isinstance(data, list):                
                    for mn in data:
                        ip = mn['ip'] + ":" + str(MASTERNODE_PORTS)
                        ret[ip] = mn['genkey']
            finally:
                pass
            return ret
        return {}
        
    def get_account(self):
        phone = self.get_phone()
        url = 'useracocunt/info?phone=%s' % phone
        account_queue = queue.Queue()        
        self.get_req(url, None, account_queue)
        resp = account_queue.get()
        return json.loads(resp, strict=False)
    
    def get_conversion(self, pageNo=1, pageSize=20):
        phone = self.get_phone()        
        url = 'cashpool/output/list?phone=%s&pageNo=%d&pageSize=%d' % (phone, pageNo, pageSize)
        conversion_queue = queue.Queue()        
        self.get_req(url, None, conversion_queue)
        resp = conversion_queue.get()
        resp = json.loads(resp, strict=False)
        if resp['code'] == 200:
            data = resp['data']
            self.conversion_total = data['total']
            self.conversion_list += data['records']
            return
        return []
        
    def post_mobilephone_checkcode(self, mobilephone):
        url = 'sms/sendCode'
        data = {'phone': mobilephone, 'action': 'wallet'}
        register_queue = queue.Queue()        
        self.post_req(url, data, register_queue)
        resp = register_queue.get()
        try:
            ret  = json.loads(resp, strict=False)
            if ret["code"] == 200:
                return True, ''
            return False, ret['pagePrompt']
        except Exception as e:
            return False, str(e) + '-' + resp
        
        
    def do_search_conversion(self):
        self.conversion_cur_page = 1
        self.conversion_list = []
        
        return self.get_conversion(self.conversion_cur_page, self.conversion_page_size)
        
    def do_back_conversion(self):                
        if self.conversion_cur_page ==1:
            return
        self.conversion_cur_page -= 1
        
        cur_total_page = (len(self.conversion_list) + (self.conversion_page_size -1))//self.conversion_page_size
        total_page = (self.conversion_total + (self.conversion_page_size -1))//self.conversion_page_size        
        if total_page > cur_total_page:
            return self.get_conversion(self.conversion_cur_page, self.conversion_page_size)

    def do_next_conversion(self):
        total_page = (self.conversion_total + (self.conversion_page_size-1))//self.conversion_page_size
        if self.conversion_cur_page >= total_page:
            return
        self.conversion_cur_page += 1
        
        cur_total_page = (len(self.conversion_list) + (self.conversion_page_size -1))//self.conversion_page_size
        if total_page > cur_total_page:
            return self.get_conversion(self.conversion_cur_page, self.conversion_page_size)

    def get_profit_address(self):
        register_info = self.wallet.storage.get('user_register')        
        if register_info is None:        
            return ''
        for key in register_info.keys():
            password, profit_address = register_info[key]
            return profit_address
    
    def get_phone(self):
        register_info = self.wallet.storage.get('user_register')        
        if register_info is None:        
            return ''
        for key in register_info.keys():
            return key
        
    def get_current_time(self):
        time_stamp = time.time() 
        local_time = time.localtime(time_stamp)  
        str_time = time.strftime('%Y-%m-%d %H:%M:%S', local_time)
        return str_time
        
    def get_conversion_commit(self):
        conversion_data = self.wallet.storage.get('conversion_masternode')
        if (not conversion_data is None) or (conversion_data):
            if conversion_data.get('txFlag') == '-100':
                return True, conversion_data
        return False, {}
                
    
    def payaccount_add(self, name, account, bank, mode, save=True):
        if self.wallet is None:
            return
        if self.conversion_account.get(account) is None:
            self.conversion_account[account] = (name, bank, mode)        
        
        if save:
            self.wallet.storage.put('conversion_account', self.conversion_account )
           
    def payaccount_load(self):
        if not self.wallet is None:
            self.conversion_account = self.wallet.storage.get('conversion_account', {})
        
        
    def conversion_commit_send(self, data):
        if not isinstance(data, dict):
            return
        
        ll = {}
        txId = data['txId']
        for l in self.conversion_list:
            if l['txId'] == txId:
                return
        
        self.conversion_list.append(data)
        
        
        
            
        
        
        