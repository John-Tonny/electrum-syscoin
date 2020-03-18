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

class MasternodeManager1(object):
    """Masternode manager.

    Keeps track of masternodes and helps with signing broadcasts.
    """
    def __init__(self, wallet, config):
        self.network_event = threading.Event()
        self.wallet = wallet
        self.config = config
        # Subscribed masternode statuses.
        self.masternode_statuses = {}
        self.height = 0
        self.load()

    def load(self):
        """Load masternodes from wallet storage."""
        ###john
        self.masternode_statuses1 = self.wallet.storage.get('masternode_statuses', {})        
        self.add_masternode('49cb679443456d0e6813a154bacff0dfd84c5ec49b5c93f5aba87fd1a4fa0ddd-0', '')
        #self.add_masternode('f4c6c1c0f6677715b314292516f2e5b829f4d3475e1fa7c529efd670c6b60747-0', '')
        #self.add_masternode('c802e16e482ff783245856f2c56c9833635d31dda2c1ed9ad015c7d2161c4196-0', '')
        #self.add_masternode('65b35f6e3080cc66c12bca883d3d9445bf0880f379a684b85881cc4629fd892f-0', '')
        #self.add_masternode('91cc02b84d76f801d9a8d5b6ad4d852178dbab5a89df3427d1343feacfe6576a-0', '')
        #self.add_masternode('b7e5e09e0f4b2d6268b0b2fbf4ccca5fd1bbffffdea6ff7acf30454a8810d194-0', '')
            
    def add_masternode(self, collateral, status, save = True):  
        try:
            if self.masternode_statuses.get(collateral) is None:
                self.masternode_statuses[collateral] = status            
            if save:
                self.save()
        except Exception as e:
            self.app.show_err(str(e))
    
    def save(self):
        """Save masternodes status."""
        self.wallet.storage.put('masternode_statuses', self.masternode_statuses)

    def send_subscriptions(self):
        if not self.wallet.network.is_connected():
            return
        
        def on_success():
            pass
        
        def on_failure():
            pass
        
        try:
            pass
            #if self.height < self.wallet.network.interface.tip - 5 :
            #    self.height = self.wallet.network.interface.tip
            #    self.app.subscribe_to_masternode_start(on_success, on_failure)            
        except Exception as e:
            self.app.show_err("k8:" + str(e))
        #self.subscribe_to_masternodes()
                    