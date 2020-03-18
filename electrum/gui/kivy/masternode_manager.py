from collections import namedtuple, OrderedDict
import base64
import threading
from decimal import Decimal

from electrum_dash.constants import COLLATERAL_COINS
from electrum_dash import bitcoin
from electrum_dash import ecc
from electrum_dash.blockchain import hash_header
from electrum_dash.masternode import MasternodeAnnounce, NetworkAddress
from electrum_dash.util import AlreadyHaveAddress, bfh, bh2u
from electrum_dash.util import format_satoshis_plain

from kivy.app import App
from kivy.logger import Logger
from electrum_dash.plugin import run_hook
import traceback


# From masternode.h
MASTERNODE_MIN_CONFIRMATIONS = 15

class MasternodeManager(object):
    """Masternode manager.

    Keeps track of masternodes and helps with signing broadcasts.
    """
    def __init__(self, wallet, config):
        try:
            self.network_event = threading.Event()
            self.wallet = wallet
            self.config = config
            # Subscribed masternode statuses.        
            self.masternode_statuses = {}
            self.load()
        except Exception as e:
            self.app.show_info("berror:" + str(e))

    def load(self):
        """Load masternodes from wallet storage."""
        masternodes = self.wallet.storage.get('masternodes', {})
        self.masternodes = [MasternodeAnnounce.from_dict(d) for d in masternodes.values()]

        ###john        
        #self.masternode_statuses1 = self.wallet.storage.get('masternode_statuses', {})        
        #self.add_masternode_status('49cb679443456d0e6813a154bacff0dfd84c5ec49b5c93f5aba87fd1a4fa0ddd-0', '')
        #self.add_masternode_status('f4c6c1c0f6677715b314292516f2e5b829f4d3475e1fa7c529efd670c6b60747-0', '')
        #self.add_masternode_status('c802e16e482ff783245856f2c56c9833635d31dda2c1ed9ad015c7d2161c4196-0', '')
        #self.add_masternode_status('65b35f6e3080cc66c12bca883d3d9445bf0880f379a684b85881cc4629fd892f-0', '')
        #self.add_masternode_status('91cc02b84d76f801d9a8d5b6ad4d852178dbab5a89df3427d1343feacfe6576a-0', '')
        #self.add_masternode_status('b7e5e09e0f4b2d6268b0b2fbf4ccca5fd1bbffffdea6ff7acf30454a8810d194-0', '')
        

    def send_subscriptions(self):
        if not self.wallet.network.is_connected():
            return
        self.subscribe_to_masternodes()

    def subscribe_to_masternodes(self):
        for mn in self.masternodes:
            collateral = mn.get_collateral_str()
            if not '-' in collateral or len(collateral.split('-')[0]) != 64:
                continue
            if self.masternode_statuses.get(collateral) is None:
                network = self.wallet.network
                method = network.interface.session.send_request
                request = ('masternode.subscribe', [collateral])
                async def update_collateral_status():
                    self.masternode_statuses[collateral] = ''
                    try:
                        res = await method(*request)
                        response = {'params': request[1], 'result': res}
                        self.masternode_subscription_response(response)
                    except Exception as e:
                        Logger.info('subscribe_to_masternodes: {0}'.format(repr(e)))
                network.run_from_another_thread(update_collateral_status())
                
    ###john
    def is_unused_masternode(self, coin):
        for mn in self.masternodes:
            if (mn.vin.get('prevout_hash') == coin.get('prevout_hash') and mn.vin.get('prevout_n') == coin.get('prevout_n')):
                return False
        
        if coin.get('value') == COLLATERAL_COINS *bitcoin.COIN:           
            return True        
        return False
                                  
    def get_masternode(self, alias):
        """Get the masternode labelled as alias."""
        for mn in self.masternodes:
            if mn.alias == alias:
                return mn

    def get_masternode_by_hash(self, hash_):
        for mn in self.masternodes:
            if mn.get_hash() == hash_:
                return mn

    def add_masternode(self, mn, save = True):
        """Add a new masternode."""
        if any(i.alias == mn.alias for i in self.masternodes):
            raise Exception('A masternode with alias "%s" already exists' % mn.alias)
        if any((i.vin['prevout_hash'] == mn.vin['prevout_hash'] and i.vin['prevout_n'] == mn.vin['prevout_n']) for i in self.masternodes):
            raise Exception('A masternode with txid "%s" already exists' % mn.vin['prevout_hash'])        
        self.masternodes.append(mn)
        if save:
            self.save()
            
    ###john
    def rename_masternode(self, mn):
        for i in self.masternodes:
            if (i.vin['prevout_hash'] == mn.vin['prevout_hash'] and i.vin['prevout_n'] == mn.vin['prevout_n']):
                if i.alias != mn.alias:
                    i.alias = mn.alias
                    self.save()                         
        
    def remove_masternode(self, alias, save = True):
        """Remove the masternode labelled as alias."""
        mn = self.get_masternode(alias)
        if not mn:
            raise Exception('Nonexistent masternode')
        # Don't delete the delegate key if another masternode uses it too.
        if not any(i.alias != mn.alias and i.delegate_key == mn.delegate_key for i in self.masternodes):
            self.wallet.delete_masternode_delegate(mn.delegate_key)

        self.masternodes.remove(mn)
        if save:
            self.save()

    def populate_masternode_output(self, alias):
        """Attempt to populate the masternode's data using its output."""
        mn = self.get_masternode(alias)
        if not mn:
            return
        if mn.announced:
            return
        txid = mn.vin.get('prevout_hash')
        prevout_n = mn.vin.get('prevout_n')
        if not txid or prevout_n is None:
            return
        # Return if it already has the information.
        if mn.collateral_key and mn.vin.get('address') and mn.vin.get('value') == COLLATERAL_COINS * bitcoin.COIN:
            return
        
        tx = self.wallet.db.get_transaction(txid)
        if not tx:
            return
        if len(tx.outputs()) <= prevout_n:
            return
        _, addr, value, _, _ = tx.outputs()[prevout_n]
        
        mn.collateral_key = self.wallet.get_public_keys(addr)[0]
        self.save()
        return True
    
    def get_masternode_outputs(self, domain = None, exclude_frozen = True):        
        """Get spendable coins that can be used as masternode collateral."""
        excluded = self.wallet.frozen_addresses if exclude_frozen else None
        coins = self.wallet.get_utxos(domain, excluded_addresses=excluded,
                                      mature_only=True, confirmed_only=True)
        ###john        
        rcoins = []
        for coin in coins:
            if self.is_unused_masternode(coin):
                rcoins.append(coin)
        
        return rcoins

    def get_delegate_privkey(self, pubkey):
        """Return the private delegate key for pubkey (if we have it)."""
        return self.wallet.get_delegate_private_key(pubkey)

    def check_can_sign_masternode(self, alias):
        """Raise an exception if alias can't be signed and announced to the network."""
        mn = self.get_masternode(alias)
        if not mn:
            raise Exception('Nonexistent masternode')
        if not mn.vin.get('prevout_hash'):
            raise Exception('Collateral payment is not specified')
        if not mn.collateral_key:
            raise Exception('Collateral key is not specified')
        if not mn.delegate_key:
            raise Exception('Masternode delegate key is not specified')

        # Ensure that the collateral payment has >= MASTERNODE_MIN_CONFIRMATIONS.
        tx_height = self.wallet.get_tx_height(mn.vin['prevout_hash'])
        if tx_height.conf < MASTERNODE_MIN_CONFIRMATIONS:
            raise Exception('Collateral payment must have at least %d '
                            'confirmations (current: %d)' %
                            (MASTERNODE_MIN_CONFIRMATIONS, tx_height.conf))
        # Ensure that the masternode's vin is valid.
        if mn.vin.get('value', 0) != bitcoin.COIN * COLLATERAL_COINS:
            raise Exception('Masternode requires a collateral 10000 VOLLAR output.')

        # If the masternode has been announced, it can be announced again if it has been disabled.
        if mn.announced:
            status = self.masternode_statuses.get(mn.get_collateral_str())
            if status in ['PRE_ENABLED', 'ENABLED']:
                raise Exception('Masternode has already been activated')

    def save(self):
        """Save masternodes."""
        masternodes = {}
        for mn in self.masternodes:
            masternodes[mn.alias] = mn.dump()

        self.wallet.storage.put('masternodes', masternodes)

    def sign_announce(self, alias, password):
        """Sign a Masternode Announce message for alias."""
        #self.check_can_sign_masternode(alias)
        mn = self.get_masternode(alias)
        # Ensure that the masternode's vin is valid.
        if mn.vin.get('scriptSig') is None:
            mn.vin['scriptSig'] = ''
        if mn.vin.get('sequence') is None:
            mn.vin['sequence'] = 0xffffffff
        # Ensure that the masternode's last_ping is current.
        height = self.wallet.get_local_height() - 12
        blockchain = self.wallet.network.blockchain()
        header = blockchain.read_header(height)
        mn.last_ping.block_hash = hash_header(header)
        mn.last_ping.vin = mn.vin

        # Sign ping with delegate key.
        self.wallet.sign_masternode_ping(mn.last_ping, mn.delegate_key)

        # After creating the Masternode Ping, sign the Masternode Announce.
        address = bitcoin.public_key_to_p2pkh(bfh(mn.collateral_key))
        mn.sig = self.wallet.sign_message(address, mn.serialize_for_sig(update_time=True), password)
        return mn            

    def send_announce(self, alias):
        """Broadcast a Masternode Announce message for alias to the network.

        Returns a 2-tuple of (error_message, was_announced).
        """
        if not self.wallet.network.is_connected():
            raise Exception('Not connected')

        mn = self.get_masternode(alias)
        # Vector-serialize the masternode.
        serialized = '01' + mn.serialize()
        errmsg = []
        
        self.network_event.clear()
        network = self.wallet.network
        method = network.interface.session.send_request
        request = ('masternode.announce.broadcast', [serialized])        
        async def masternode_announce_broadcast():
            try:
                r = {}
                r['result'] = await method(*request)
            except Exception as e:
                r['result'] = {}
                r['error'] = str(e)
            try:
                self.on_broadcast_announce(alias, r)
            except Exception as e:
                errmsg.append(str(e))
            finally:
                self.save()
                self.network_event.set()
        network.run_from_another_thread(masternode_announce_broadcast())
        self.network_event.wait()
        self.subscribe_to_masternodes()
        if errmsg:
            errmsg = errmsg[0]
        return (errmsg, mn.announced)
        
    def on_broadcast_announce(self, alias, r):
        """Validate the server response."""
        err = r.get('error')
        if err:
            raise Exception('Error response: %s' % str(err))

        result = r.get('result')

        mn = self.get_masternode(alias)
        mn_hash = mn.get_hash()
        mn_dict = result.get(mn_hash)
        if not mn_dict:
            raise Exception('No result for expected Masternode Hash. Got %s' % result)

        if mn_dict.get('errorMessage'):
            raise Exception('Announce was rejected: %s' % mn_dict['errorMessage'])
        if mn_dict.get(mn_hash) != 'successful':
            raise Exception('Announce was rejected (no error message specified)')

        mn.announced = True

    def import_masternode_delegate(self, sec):
        """Import a WIF delegate key.

        An exception will not be raised if the key is already imported.
        """
        try:
            pubkey = self.wallet.import_masternode_delegate(sec)
        except AlreadyHaveAddress:
            txin_type, key, is_compressed = bitcoin.deserialize_privkey(sec)
            pubkey = ecc.ECPrivkey(key)\
                .get_public_key_hex(compressed=is_compressed)
        return pubkey

    def masternode_subscription_response(self, response):
        """Callback for when a masternode's status changes."""
        collateral = response['params'][0]
        mn = None
        for masternode in self.masternodes:
            if masternode.get_collateral_str() == collateral:
                mn = masternode
                break

        if not mn:
            return

        if not 'result' in response:
            return

        status = response['result']
        if status is None:
            status = False
            
        Logger.info('Received updated status for masternode {0}: {1}'.format(mn.alias, status))
        self.masternode_statuses[collateral] = status
    
    '''
    def add_masternode_status(self, collateral, status, save = True):        
        if self.masternode_statuses1.get(collateral) is None:
            self.masternode_statuses1[collateral] = status            
        if save:
            self.save_status()
    
    def save_status(self):
        """Save masternodes status."""
        self.wallet.storage.put('masternode_statuses', self.masternode_statuses1)

    def send_subscriptions1(self):
        if not self.wallet.network.is_connected():
            return
        self.subscribe_to_masternodes1()
    
    def subscribe_to_masternodes1(self):
        try:
            network = self.wallet.network
            self.app.masternode_status_screen.alias = 'kkk' #str(network.interface.tip)
        except Exception as e:
            self.app.show_info("kkkk:" + str(e))
            
        
        try:
            for collateral in self.masternode_statuses1.keys():
                if not '-' in collateral or len(collateral.split('-')[0]) != 64:
                    continue
                network = self.wallet.network
                method = network.interface.session.send_request
                request = ('masternode.subscribe', [collateral])
                async def update_collateral_status():
                    self.masternode_statuses1[collateral] = ''
                    try:
                        res = await method(*request)
                        response = {'params': request[1], 'result': res}
                        self.masternode_statuses1[collateral] = res
                    except Exception as e:
                        Logger.info('subscribe_to_masternodes: {0}'.format(repr(e)))
                network.run_from_another_thread(update_collateral_status())        
            self.save_status()        
            self.app.masternode_status_screen.update()
        except Exception as e:
            self.app.show_info("kkkk:" + str(e))
    '''