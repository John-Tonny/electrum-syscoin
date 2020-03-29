
import hashlib
import aiohttp
import asyncio
import queue
import json
import time
import threading

class Client:

    def __init__(self, wallet):
        self.wallet = wallet
        self.loop = self.wallet.network.asyncio_loop
        self.money_queue = queue.Queue()    
                
        self.conversion_list = []
        self.conversion_total = 0
        self.conversion_cur_page = 1
        self.conversion_page_size = 3 #20
        
        self.money_ratio = 0
        timer = threading.Timer(2, self.get_money_ratio)
        timer.start()                

    def get_header_auth(self):
        m = hashlib.md5()
        name = 'admin'
        password = '999000'
        privkey = 'jlw999000'
        m.update(str.encode(name + password + privkey))
        return m.hexdigest()

    def post_req(self, url, data, rqueue):
        async def _post_req(url, data, rqueue):
            async with aiohttp.ClientSession() as session:
                headers = {'Auth': self.get_header_auth()}                
                method = 'http://52.82.33.173:8080/' + url
                async with session.post(method, headers=headers, data=data) as resp:
                    resp = await resp.text(encoding='utf-8')
                    rqueue.put(resp)
                    
        asyncio.run_coroutine_threadsafe(_post_req(url, data, rqueue), self.loop)
        
    def post_async_req(self, url, data, queue:asyncio.Queue):
        async def _post_req(url, data, queue):
            async with aiohttp.ClientSession() as session:
                headers = {'Auth': self.get_header_auth()}                
                method = 'http://52.82.33.173:8080/' + url
                async with session.post(method, headers=headers, data=data) as resp:
                    resp = await resp.text(encoding='utf-8')
                    queue.put(resp)
                    
        asyncio.run_coroutine_threadsafe(_post_req(url, data, queue), self.loop)

    def get_req(self, url, data, rqueue):
        async def _get_req(url, data, rqueue):
            async with aiohttp.ClientSession() as session:
                headers = {'Auth': self.get_header_auth()}                
                method = 'http://52.82.33.173:8080/' + url
                async with session.get(method, headers=headers, data=data) as resp:
                    resp = await resp.text(encoding='utf-8')
                    rqueue.put(resp)
                    
        asyncio.run_coroutine_threadsafe(_get_req(url, data, rqueue), self.loop)


    def post_register(self, mobilephone, address):
        url = 'useracocunt/accpet'
        data = {'phone': mobilephone, 'userAccount': address}
        register_queue = queue.Queue()        
        self.post_req(url, data, register_queue)
        resp = register_queue.get()
        return json.loads(resp)
    
    def get_money_ratio(self):
        url = 'fundValue/latest'
        self.get_req(url, None, self.money_queue)
        resp = json.loads(self.money_queue.get())
        if resp['code'] == 200:
            self.money_ratio = resp['data']['fundValue']
            print(self.money_ratio)
        
        timer = threading.Timer(2,self.get_money_ratio)
        timer.start()        
        
    def post_conversion(self, txid, amount, fee, dstAddress, srcAddress):
        phone = self.get_phone()        
        url = 'cashpool/output/apply'
        data = {}
        data['phone'] = phone
        data['txid'] = txid
        data['amount'] = amount
        data['fee'] = fee
        data['dstAccount'] = dstAddress
        data['srcAccount'] = srcAddress
        conversion_queue = queue.Queue()        
        self.post_req(url, data, conversion_queue)
        resp = conversion_queue.get()
        return json.loads(resp)
        
    def get_maternodes(self):
        phone = self.get_phone()
        url = 'nodes/getPhoneNode?phone=%s' % phone
        masternode_queue = queue.Queue()        
        self.get_req(url, None, masternode_queue)
        resp = masternode_queue.get()
        resp = json.loads(resp)
        #if resp['code'] == 200:
        resp = {}
        data = [{'ip':'52.82.14.25:9069', 'genkey': '5KTbFcwYns3QmTuzFMEoSbqxoF3u1a2DneNKbsuRAJoAJoLMhAw'},
                {'ip':'47.104.25.28:9069', 'genkey': '5JcP6XZBngpgXkUAYXb3i9B2X3cYymANr7o1danBthigsnGp5Qc'},
                {'ip':'1.2.3.6:9069', 'genkey': '5KMmZ1jWDntnYdunmJDRze2xuBRRZxTeoTbf37eJt8ZrP6NVGMV'}]
        for mn in data:
            key = mn['ip']
            resp[key] = mn['genkey']
        return resp
        #    return {}
        
    def get_account(self):
        phone = self.get_phone()
        url = 'useracocunt/info?phone=%s' % phone
        account_queue = queue.Queue()        
        self.get_req(url, None, account_queue)
        resp = account_queue.get()
        return json.loads(resp)
    
    def get_conversion(self, pageNo=1, pageSize=20):
        phone = self.get_phone()        
        url = 'cashpool/output/list?phone=%s&pageNo=%d&pageSize=%d' % (phone, pageNo, pageSize)
        conversion_queue = queue.Queue()        
        self.get_req(url, None, conversion_queue)
        resp = conversion_queue.get()
        resp = json.loads(resp)
        if resp['code'] == 200:
            data = resp['data']
            self.conversion_total = data['total']
            self.conversion_list += data['records']
            return
        return []
        
    def do_search_conversion(self):
        self.conversion_cur_page = 1
        self.conversion_list = []
        
        self.get_conversion(self.conversion_cur_page, self.conversion_page_size)
        
    def do_back_conversion(self):                
        if self.conversion_cur_page ==1:
            return
        self.conversion_cur_page -= 1
        
        cur_total_page = (len(self.conversion_list) + (self.conversion_page_size -1))//self.conversion_page_size
        total_page = (self.conversion_total + (self.conversion_page_size -1))//self.conversion_page_size        
        if total_page > cur_total_page:
            self.get_conversion(self.conversion_cur_page, self.conversion_page_size)

    def do_next_conversion(self):
        total_page = (self.conversion_total + (self.conversion_page_size-1))//self.conversion_page_size
        if self.conversion_cur_page >= total_page:
            return
        self.conversion_cur_page += 1
        
        cur_total_page = (len(self.conversion_list) + (self.conversion_page_size -1))//self.conversion_page_size
        if total_page > cur_total_page:
            self.get_conversion(self.conversion_cur_page, self.conversion_page_size)

    def get_profit_address(self):
        register_info = self.wallet.storage.get('masternoderegister')        
        if register_info is None:        
            return ''
        for key in register_info.keys():
            password, profit_address = register_info[key]
            return profit_address
    
    def get_phone(self):
        register_info = self.wallet.storage.get('masternoderegister')        
        if register_info is None:        
            return ''
        for key in register_info.keys():
            return key
        
        
        
    
        
        
        
        