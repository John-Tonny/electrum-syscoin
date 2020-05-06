from weakref import ref
from decimal import Decimal
import re
import datetime
import traceback, sys

from kivy.app import App
from kivy.cache import Cache
from kivy.clock import Clock
from kivy.compat import string_types
from kivy.properties import (ObjectProperty, DictProperty, NumericProperty,
                             ListProperty, StringProperty, ReferenceListProperty)

from kivy.uix.recycleview import RecycleView
from kivy.uix.label import Label

from kivy.lang import Builder
from kivy.factory import Factory
from kivy.utils import platform

from electrum.util import profiler, parse_URI, format_time, InvalidPassword, NotEnoughFunds, Fiat, USE_COLLATERAL_DEFAULT, use_collateral_list
from electrum import bitcoin
from electrum.transaction import TxOutput, Transaction, tx_from_str
from electrum.util import send_exception_to_crash_reporter, parse_URI, InvalidBitcoinURI
from electrum.paymentrequest import PR_UNPAID, PR_PAID, PR_UNKNOWN, PR_EXPIRED
from electrum.plugin import run_hook
from electrum.wallet import InternalAddressCorruption
from electrum import simple_config

from .context_menu import ContextMenu

from electrum.gui.kivy.i18n import _

###john
import os
import base58
from electrum import ecc
from electrum.constants import COLLATERAL_COINS, AGGREGATION_INTERVAL_TIME
from electrum.masternode import MasternodeAnnounce, NetworkAddress, MasternodePing
from electrum.util import AlreadyHaveAddress, bfh, bh2u
from electrum.crypto import sha256d
from jnius import autoclass
from electrum.masternode_manager import MASTERNODE_MIN_CONFIRMATIONS


class HistoryRecycleView(RecycleView):
    pass

###john
class MasternodeRecycleView(RecycleView):
    pass

class CScreen(Factory.Screen):
    __events__ = ('on_activate', 'on_deactivate', 'on_enter', 'on_leave')
    action_view = ObjectProperty(None)
    loaded = False
    kvname = None
    context_menu = None
    menu_actions = []
    app = App.get_running_app()

    def _change_action_view(self):
        app = App.get_running_app()
        action_bar = app.root.manager.current_screen.ids.action_bar
        _action_view = self.action_view

        if (not _action_view) or _action_view.parent:
            return
        action_bar.clear_widgets()
        action_bar.add_widget(_action_view)

    def on_enter(self):
        # FIXME: use a proper event don't use animation time of screen
        Clock.schedule_once(lambda dt: self.dispatch('on_activate'), .25)
        pass

    def update(self):
        pass

    @profiler
    def load_screen(self):
        if self.kvname == 'masternode':
            self.app.check_register()
        self.screen = Builder.load_file('electrum/gui/kivy/uix/ui_screens/' + self.kvname + '.kv')
        self.add_widget(self.screen)
        self.loaded = True
        self.update()
        setattr(self.app, self.kvname + '_screen', self)

    def on_activate(self):
        if self.kvname and not self.loaded:
            self.load_screen()
        #Clock.schedule_once(lambda dt: self._change_action_view())

    def on_leave(self):
        self.dispatch('on_deactivate')

    def on_deactivate(self):
        self.hide_menu()

    def hide_menu(self):
        if self.context_menu is not None:
            self.remove_widget(self.context_menu)
            self.context_menu = None

    def show_menu(self, obj):
        self.hide_menu()
        self.context_menu = ContextMenu(obj, self.menu_actions)
        self.add_widget(self.context_menu)


# note: this list needs to be kept in sync with another in qt
TX_ICONS = [
    "unconfirmed",
    "close",
    "unconfirmed",
    "close",
    "clock1",
    "clock2",
    "clock3",
    "clock4",
    "clock5",
    "confirmed",
]

class HistoryScreen(CScreen):

    tab = ObjectProperty(None)
    kvname = 'history'
    cards = {}

    def __init__(self, **kwargs):
        self.ra_dialog = None
        super(HistoryScreen, self).__init__(**kwargs)
        self.menu_actions = [ ('Label', self.label_dialog), ('Details', self.show_tx)]

    def show_tx(self, obj):
        tx_hash = obj.tx_hash
        tx = self.app.wallet.db.get_transaction(tx_hash)
        if not tx:
            return
        self.app.tx_dialog(tx)

    def label_dialog(self, obj):
        from .dialogs.label_dialog import LabelDialog
        key = obj.tx_hash
        text = self.app.wallet.get_label(key)
        def callback(title, text):
            self.app.wallet.set_label(key, text)
            self.update()
        d = LabelDialog(_('Enter Transaction Label'), text, callback)
        d.open()

    def get_card(self, tx_hash, tx_mined_status, value, balance):
        status, status_str = self.app.wallet.get_tx_status(tx_hash, tx_mined_status)
        icon = "atlas://electrum/gui/kivy/theming/light/" + TX_ICONS[status]
        label = self.app.wallet.get_label(tx_hash) if tx_hash else _('Pruned transaction outputs')
        ri = {}
        ri['screen'] = self
        ri['tx_hash'] = tx_hash
        ri['icon'] = icon
        ri['date'] = status_str
        ri['message'] = label
        ri['confirmations'] = tx_mined_status.conf
        if value is not None:
            ri['is_mine'] = value < 0
            if value < 0: value = - value
            ri['amount'] = self.app.format_amount_and_units(value)
            if self.app.fiat_unit:
                fx = self.app.fx
                fiat_value = value / Decimal(bitcoin.COIN) * self.app.wallet.price_at_timestamp(tx_hash, fx.timestamp_rate)
                fiat_value = Fiat(fiat_value, fx.ccy)
                ri['quote_text'] = fiat_value.to_ui_string()
        return ri

    def update(self, see_all=False):
        if self.app.wallet is None:
            return
        history = reversed(self.app.wallet.get_history())
        history_card = self.screen.ids.history_container
        history_card.data = [self.get_card(*item) for item in history]


class SendScreen(CScreen):

    kvname = 'send'
    payment_request = None
    payment_request_queued = None

    def set_URI(self, text):
        if not self.app.wallet:
            self.payment_request_queued = text
            return
        try:
            uri = parse_URI(text, self.app.on_pr, loop=self.app.asyncio_loop)
        except InvalidBitcoinURI as e:
            self.app.show_info(_("Error parsing URI") + f":\n{e}")
            return
        amount = uri.get('amount')
        self.screen.address = uri.get('address', '')
        self.screen.message = uri.get('message', '')
        self.screen.amount = self.app.format_amount_and_units(amount) if amount else ''
        self.payment_request = None
        self.screen.is_pr = False

    def update(self):
        if self.app.wallet and self.payment_request_queued:
            self.set_URI(self.payment_request_queued)
            self.payment_request_queued = None

    def do_clear(self):
        self.screen.amount = ''
        self.screen.message = ''
        self.screen.address = ''
        self.payment_request = None
        self.screen.is_pr = False
        self.screen.info = ''

    def set_request(self, pr):
        self.screen.address = pr.get_requestor()
        amount = pr.get_amount()
        self.screen.amount = self.app.format_amount_and_units(amount) if amount else ''
        self.screen.message = pr.get_memo()
        if pr.is_pr():
            self.screen.is_pr = True
            self.payment_request = pr
        else:
            self.screen.is_pr = False
            self.payment_request = None

    def do_save(self):
        if not self.screen.address:
            return
        if self.screen.is_pr:
            # it should be already saved
            return
        # save address as invoice
        from electrum.paymentrequest import make_unsigned_request, PaymentRequest
        req = {'address':self.screen.address, 'memo':self.screen.message}
        amount = self.app.get_amount(self.screen.amount) if self.screen.amount else 0
        req['amount'] = amount
        pr = make_unsigned_request(req).SerializeToString()
        pr = PaymentRequest(pr)
        self.app.wallet.invoices.add(pr)
        self.app.show_info(_("Invoice saved"))
        if pr.is_pr():
            self.screen.is_pr = True
            self.payment_request = pr
        else:
            self.screen.is_pr = False
            self.payment_request = None

    def do_paste(self):
        data = self.app._clipboard.paste()
        if not data:
            self.app.show_info(_("Clipboard is empty"))
            return
        # try to decode as transaction
        try:
            raw_tx = tx_from_str(data)
            tx = Transaction(raw_tx)
            tx.deserialize()
        except:
            tx = None
        if tx:
            self.app.tx_dialog(tx)
            return
        # try to decode as URI/address
        self.set_URI(data)

    def do_send(self): 
        self.screen.info = _('Please wait') + '...'
        Clock.schedule_once(lambda dt: self.do_send1(), 0.5)
        
    def do_send1(self):    
        if self.screen.is_pr:
            if self.payment_request.has_expired():
                self.screen.info = ''
                self.app.show_error(_('Payment request has expired'))
                return
            outputs = self.payment_request.get_outputs()
        else:
            address = str(self.screen.address)
            if not address:
                self.screen.info = ''
                self.app.show_error(_('Recipient not specified.') + ' ' + _('Please scan a Bitcoin address or a payment request'))
                return
            if not bitcoin.is_address(address):
                self.screen.info = ''
                self.app.show_error(_('Invalid Bitcoin Address') + ':\n' + address)
                return
            try:
                amount = self.app.get_amount(self.screen.amount)
            except:
                self.screen.info = ''
                self.app.show_error(_('Invalid amount') + ':\n' + self.screen.amount)
                return
            outputs = [TxOutput(bitcoin.TYPE_ADDRESS, address, amount)]
        message = self.screen.message
        amount = sum(map(lambda x:x[2], outputs))
        if self.app.electrum_config.get('use_rbf'):
            self.screen.info = ''
            from .dialogs.question import Question
            d = Question(_('Should this transaction be replaceable?'), lambda b: self._do_send(amount, message, outputs, b))
            d.open()
        else:
            self._do_send(amount, message, outputs, False)
        
    def _do_send(self, amount, message, outputs, rbf):
        # make unsigned transaction
        config = self.app.electrum_config
        coins = self.app.wallet.get_spendable_coins(None, config)   
        
        try:
            tx = self.app.wallet.make_unsigned_transaction(coins, outputs, config, None)
        except NotEnoughFunds:
            self.screen.info = ''
            self.app.show_error(_("Not enough funds"))
            return
        except Exception as e:
            self.screen.info = ''
            traceback.print_exc(file=sys.stdout)
            self.app.show_error(str(e))
            return
        
        ###john
        bmasternode = False
        for in1 in tx.inputs():
            if in1['value'] == COLLATERAL_COINS * bitcoin.COIN:
                bmasternode = True
                break
        
        if bmasternode:
            from .dialogs.question import Question
            self.screen.info = ''
            d = Question(_('Are you sure to spend the collateral coins of masternode?'), lambda b: self.__do_send(tx, amount, message, outputs, rbf, b))
            d.open()
        else:
            self.__do_send(tx, amount, message, outputs, rbf, True)
                                    
    def __do_send(self, tx, amount, message, outputs, rbf, b):
        if not b:
            self.screen.info = ''
            return
        
        if rbf:
            tx.set_rbf(True)
            
        fee = tx.get_fee()
        msg = [
            _("Amount to be sent") + ": " + self.app.format_amount_and_units(amount),
            _("Mining fee") + ": " + self.app.format_amount_and_units(fee),
        ]
        x_fee = run_hook('get_tx_extra_fee', self.app.wallet, tx)
        if x_fee:
            x_fee_address, x_fee_amount = x_fee
            msg.append(_("Additional fees") + ": " + self.app.format_amount_and_units(x_fee_amount))

        feerate_warning = simple_config.FEERATE_WARNING_HIGH_FEE
        if fee > feerate_warning * tx.estimated_size() / 1000:
            msg.append(_('Warning') + ': ' + _("The fee for this transaction seems unusually high."))
        msg.append(_("Enter your PIN code to proceed"))
        self.screen.info = ''        
        self.app.protected('\n'.join(msg), self.send_tx, (tx, message))

    def send_tx(self, tx, message, password):
        if self.app.wallet.has_password() and password is None:
            self.app.show_info("password:" + 'exit')
            return
        def on_success(tx):
            if tx.is_complete():
                self.app.broadcast(tx, self.payment_request)
                self.app.wallet.set_label(tx.txid(), message)
            else:
                self.app.hide_info()
                self.app.tx_dialog(tx)
        def on_failure(error):
            self.app.show_error(error)
        if self.app.wallet.can_sign(tx):
            if self.app.aggregation_password is None:
                self.app.show_info(_("Signing transaction...")) # + "-" + str(len(tx.inputs())))
            self.app.sign_tx(tx, password, on_success, on_failure)
        else:
            self.app.tx_dialog(tx)

    def do_load_transaction(self):
        self.app.load_transaction()
    
    def do_aggregation(self):
        from .dialogs.question import Question
        def _do_start_aggregation(ok):
            if ok:
                msg = []
                msg.append(_("Enter your PIN code to proceed"))
                self.app.protected('\n'.join(msg), __do_start_aggregation, ())                
                
        def __do_start_aggregation(password):
            if self.app.wallet.has_password() and password is None:
                return
            self.app.aggregation_password = password
            self.screen.show_aggregation = (self.screen.show_aggregation + 1) % 2
            self.app.aggregation_nums = AGGREGATION_INTERVAL_TIME - 2               
                
        def _do_stop_aggregation(ok):
            if ok:
                self.screen.show_aggregation = (self.screen.show_aggregation + 1) % 2
                self.app.aggregation_password = None
                
        if self.screen.show_aggregation == 0:
            d = Question(_('Are you sure you want to start aggregation?'), _do_start_aggregation)
        else:
            d = Question(_('Are you sure you want to stop aggregation?'), _do_stop_aggregation)
        d.open()
            
    def do_aggregation_send(self, coins):
        address = self.app.get_app_new_address()
        if address == '':
            self.app.show_error(_('Failed to get address!'))
            return
        amount = self.app.get_aggregation_max_amount(address, coins) + ' ' + self.app.base_unit
        amount = self.app.get_amount(amount)
        outputs = [TxOutput(bitcoin.TYPE_ADDRESS, address, amount)]
        message = _('Aggregation')
        amount = sum(map(lambda x:x[2], outputs))            
        self._do_aggregation_send(coins, amount, message, outputs, False)            

    def _do_aggregation_send(self, coins, amount, message, outputs, rbf):
        config = self.app.electrum_config
        try:
            tx = self.app.wallet.make_unsigned_transaction(coins, outputs, config, None)
        except NotEnoughFunds:
            self.app.show_error(_("Not enough funds"))
            return
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            self.app.show_error(str(e))
            return 
        self.send_tx(tx, message, self.app.aggregation_password)
        
        
class ReceiveScreen(CScreen):

    kvname = 'receive'

    def update(self):
        if not self.screen.address:
            self.get_new_address()
        else:
            status = self.app.wallet.get_request_status(self.screen.address)
            self.screen.status = _('Payment received') if status == PR_PAID else ''

    def clear(self):
        self.screen.address = ''
        self.screen.amount = ''
        self.screen.message = ''

    def get_new_address(self) -> bool:
        """Sets the address field, and returns whether the set address
        is unused."""
        if not self.app.wallet:
            return False
        self.clear()
        unused = True
        try:
            addr = self.app.wallet.get_unused_address()
            if addr is None:
                addr = self.app.wallet.get_receiving_address() or ''
                unused = False
        except InternalAddressCorruption as e:
            addr = ''
            self.app.show_error(str(e))
            send_exception_to_crash_reporter(e)
        self.screen.address = addr
        return unused

    def on_address(self, addr):
        req = self.app.wallet.get_payment_request(addr, self.app.electrum_config)
        self.screen.status = ''
        if req:
            self.screen.message = req.get('memo', '')
            amount = req.get('amount')
            self.screen.amount = self.app.format_amount_and_units(amount) if amount else ''
            status = req.get('status', PR_UNKNOWN)
            self.screen.status = _('Payment received') if status == PR_PAID else ''
        Clock.schedule_once(lambda dt: self.update_qr())

    def get_URI(self):
        from electrum.util import create_bip21_uri
        amount = self.screen.amount
        if amount:
            a, u = self.screen.amount.split()
            assert u == self.app.base_unit
            amount = Decimal(a) * pow(10, self.app.decimal_point())
        return create_bip21_uri(self.screen.address, amount, self.screen.message)

    @profiler
    def update_qr(self):
        uri = self.get_URI()
        qr = self.screen.ids.qr
        qr.set_data(uri)

    def do_share(self):
        uri = self.get_URI()
        self.app.do_share(uri, _("Share Bitcoin Request"))

    def do_copy(self):
        uri = self.get_URI()
        self.app._clipboard.copy(uri)
        self.app.show_info(_('Request copied to clipboard'))

    def save_request(self):
        addr = self.screen.address
        if not addr:
            return False
        amount = self.screen.amount
        message = self.screen.message
        amount = self.app.get_amount(amount) if amount else 0
        req = self.app.wallet.make_payment_request(addr, amount, message, None)
        try:
            self.app.wallet.add_payment_request(req, self.app.electrum_config)
            added_request = True
        except Exception as e:
            self.app.show_error(_('Error adding payment request') + ':\n' + str(e))
            added_request = False
        finally:
            self.app.update_tab('requests')
        return added_request

    def on_amount_or_message(self):
        Clock.schedule_once(lambda dt: self.update_qr())

    def do_new(self):
        is_unused = self.get_new_address()
        if not is_unused:
            self.app.show_info(_('Please use the existing requests first.'))

    def do_save(self):
        if self.save_request():
            self.app.show_info(_('Request was saved.'))


class TabbedCarousel(Factory.TabbedPanel):
    '''Custom TabbedPanel using a carousel used in the Main Screen
    '''

    carousel = ObjectProperty(None)

    def animate_tab_to_center(self, value):
        scrlv = self._tab_strip.parent
        if not scrlv:
            return
        idx = self.tab_list.index(value)
        n = len(self.tab_list)
        if idx in [0, 1]:
            scroll_x = 1
        elif idx in [n-1, n-2]:
            scroll_x = 0
        else:
            scroll_x = 1. * (n - idx - 1) / (n - 1)
        mation = Factory.Animation(scroll_x=scroll_x, d=.25)
        mation.cancel_all(scrlv)
        mation.start(scrlv)

    def on_current_tab(self, instance, value):
        self.animate_tab_to_center(value)

    def on_index(self, instance, value):
        current_slide = instance.current_slide
        if not hasattr(current_slide, 'tab'):
            return
        tab = current_slide.tab
        ct = self.current_tab
        try:
            if ct.text != tab.text:
                carousel = self.carousel
                carousel.slides[ct.slide].dispatch('on_leave')
                self.switch_to(tab)
                carousel.slides[tab.slide].dispatch('on_enter')
        except AttributeError:
            current_slide.dispatch('on_enter')

    def switch_to(self, header):
        # we have to replace the functionality of the original switch_to
        if not header:
            return
        if not hasattr(header, 'slide'):
            header.content = self.carousel
            super(TabbedCarousel, self).switch_to(header)
            try:
                tab = self.tab_list[-1]
            except IndexError:
                return
            self._current_tab = tab
            tab.state = 'down'
            return

        carousel = self.carousel
        self.current_tab.state = "normal"
        header.state = 'down'
        self._current_tab = header
        # set the carousel to load the appropriate slide
        # saved in the screen attribute of the tab head
        slide = carousel.slides[header.slide]
        if carousel.current_slide != slide:
            carousel.current_slide.dispatch('on_leave')
            carousel.load_slide(slide)
            slide.dispatch('on_enter')

    def add_widget(self, widget, index=0):
        if isinstance(widget, Factory.CScreen):
            self.carousel.add_widget(widget)
            return
        super(TabbedCarousel, self).add_widget(widget, index=index)

###john
class MasternodeScreen(CScreen):

    kvname = 'masternode'

    def __init__(self, **kwargs):
        super(MasternodeScreen, self).__init__(**kwargs)
        self.menu_actions = [ ('Remove', self.do_remove), ('Freeze', self.do_freeze), ('Unfreeze', self.do_unfreeze), ('Activate', self.do_activate)]
                
        self.blue_bottom_pos = 0
        self.column_1_pos = 0
        self.column_2_pos = 0
        self.masternode_container_pos = 0
        self.x = 0
                
        self.test = True
        
    def do_clear(self):
        self.screen.alias =''
        self.screen.collateral = ''
        self.screen.utxo = ''
        self.screen.delegate = ''
        self.screen.ip = ''
        self.screen.is_pr = False
            
    
    def do_hide(self):
        if self.test:
            
            self.blue_bottom_pos = self.screen.ids.blue_bottom.y
            self.column_1_pos = self.screen.ids.column_1.y
            self.column_2_pos = self.screen.ids.column_2.y
            self.masternode_container_pos = self.screen.ids.masternode_container.y
            #self.x = self.screen.ids.blue_buttom.x
            
            self.screen.alias = str(self.blue_bottom_pos)
            self.screen.collateral = str(self.column_1_pos)
            self.screen.utxo = str(self.column_2_pos)
            self.screen.delegate = str(self.masternode_container_pos)   
            self.screen.ip = str(self.screen.ids.blue_bottom.height)
            
            try:
                self.test = False            
                self.screen.ids.blue_buttom.pos = ReferenceListProperty(10000, 10000)            
                self.screen.ids.column_1.pos = ReferenceListProperty(10000, 10000)
                self.screen.ids.masternode_container.pos = ReferenceListProperty(10000, 10000)
            except Exception as e:
                self.app.show_error(str(e))
            '''
            y1 = self.column_1_pos - self.column_2_pos
            y2 = self.masternode_container_pos - self.column_2_pos
            self.screen.ids.column_1.y = self.blue_bottom_pos
            self.screen.ids.column_2.y = self.screen.ids.column_1.y + y1
            self.screen.ids.masternode_container.y = self.screen.ids.column_2.y + y2
            '''
        else:
            self.test = True
            self.screen.ids.blue_bottom.y = self.blue_bottom_pos
            self.screen.ids.column_1.y = self.column_1_pos
            self.screen.ids.column_2.y = self.column_2_pos
            self.screen.ids.masternode_container.y = self.masternode_container_pos        
    
    def do_remove(self, obj):        
        from .dialogs.question import Question        
        def _do_remove(obj, b):
            try:
                if not b:
                    return
                key = obj.txid + '-' + str(obj.index)
                self.set_frozen_masternode(obj.txid, str(obj.index), False)                
                self.app.masternode_manager.remove_masternode(key)
                self.do_clear()
                self.update()
                return
            except Exception as e:
                self.app.show_error(str(e))
        
        if obj.status == 'ENABLED':
            self.app.show_info(_('Masternode has already been activated,cannot be deleted!'))
            return
        
        d = Question(_('Are you sure you want to remove it?'), lambda b: _do_remove(obj, b))
        d.open()
    
    def do_removeall(self):   
        if len(self.app.masternode_manager.masternodes) == 0:
            return
        from .dialogs.question import Question
        def _do_removeall(ok):
            try:
                if not ok:
                    return
                self.do_unfreezeall(info=False)
                self.app.masternode_manager.masternodes = {}
                self.app.masternode_manager.save()
                self.do_clear()
                self.update()
                return
            except Exception as e:
                self.app.show_error(str(e))
                
        d = Question(_('Are you sure you want to remove all of them?'), _do_removeall)
        d.open()

    def do_unfreeze(self, obj):        
        from .dialogs.question import Question        
        def _do_unfreeze(obj, b):
            try:
                if not b:
                    return
                self.set_frozen_masternode(obj.txid, str(obj.index), False)                
                self.update()
                return
            except Exception as e:
                self.app.show_error(str(e))
        
        d = Question(_('Are you sure you want to unfreeze it?'), lambda b: _do_unfreeze(obj, b))
        d.open()

    def do_unfreezeall(self, info=True):   
        if len(self.app.masternode_manager.masternodes) == 0:
            return        
        from .dialogs.question import Question
        def _do_unfreezeall(ok):
            try:
                if not ok:
                    return
                
                for key in self.app.masternode_manager.masternodes.keys():                
                    mn = self.app.masternode_manager.masternodes[key]
                    self.set_frozen_masternode(mn.vin['prevout_hash'], str(mn.vin['prevout_n']), False)                
                self.update()
                return
            except Exception as e:
                self.app.show_error(str(e))
        if info:
            d = Question(_('Are you sure you want to unfreeze all of them?'), _do_unfreezeall)
            d.open()
        else:
            _do_unfreezeall(True)
                
    def do_freeze(self, obj):        
        from .dialogs.question import Question        
        def _do_freeze(obj, b):
            try:
                if not b:
                    return
                self.set_frozen_masternode(obj.txid, str(obj.index), True)                
                self.update()
                return
            except Exception as e:
                self.app.show_error(str(e))
        
        d = Question(_('Are you sure you want to freeze it?'), lambda b: _do_freeze(obj, b))
        d.open()
                
    def do_save(self):
        key = self.screen.utxo
        mn = self.app.masternode_manager.get_masternode(key)
        if mn is None:
            key = None
            
        try:
            self.check_save(key)
        except Exception as e:
            self.app.show_error(str(e))
            return
        
        try:
            delegate_pub = self.app.masternode_manager.import_masternode_delegate(self.screen.delegate)
        except Exception as e:
            self.app.show_error(str(e))
            pass
                
        try:
            txin_type, txin_key, is_compressed = bitcoin.deserialize_privkey(self.screen.delegate)
            delegate_pub = ecc.ECPrivkey(txin_key).get_public_key_hex(compressed=is_compressed)
        except Exception as e:
            self.app.show_error(_('Invalid Masternode Private Key'))
            return
                       
        try:
            collateral_pub = self.app.wallet.get_public_keys(self.screen.collateral)[0]            
        except Exception as e:
            self.app.show_error(_("InValid Collateral Key"))
            return 
        
        try:
            if mn is None:
                self.app.show_info("bbbbb1:" + str(key) + '-' + str(type(key)))
                return
            mn.alias = self.screen.alias
            mn.delegate_key = delegate_pub
            mn.collateral_key = collateral_pub
            ipaddress , port = self.screen.ip.split(":")
            mn.addr.ip = ipaddress
            mn.addr.port = int(port)
            self.app.masternode_manager.save()
            self.update()
            self.app.show_info(_('Masternode saved'))
        except Exception as e:
            self.app.show_error(str(e))
        
    def do_scan(self):
        try:
            exclude_frozen = True
            coins = self.app.masternode_manager.get_masternode_outputs(exclude_frozen=exclude_frozen)
            for coin in coins:
                if self.app.masternode_manager.is_used_masternode_from_coin(coin):
                    continue
                
                vin = {'prevout_hash': coin['prevout_hash'], 'prevout_n': coin['prevout_n']}                        
                try:
                    collateral = self.app.wallet.get_public_keys(coin['address'])[0]       
                except Exception as e:
                    self.app.show_error(str(e))
                
                alias = self.app.masternode_manager.get_default_alias()      
                mn = MasternodeAnnounce(alias=alias, vin=vin, addr=NetworkAddress(),
                                        collateral_key=collateral, delegate_key='', sig='', sig_time=0,
                                        last_ping=MasternodePing(),announced=False)             
                self.app.masternode_manager.add_masternode(mn, save=False)
                
                try:
                    self.set_frozen_masternode(coin['prevout_hash'], coin['prevout_n'], True)
                except Exception as e:
                    self.app.show_error("pppp:" + str(e))
                
            self.app.masternode_manager.save()
            self.update()            
        except Exception as e:
            self.app.show_error(str(e))
            return 
        
    def do_activate(self, obj):
        if self.check_status(obj):
            self.app.show_info(_('Masternode has already been activated'))
            return        

        if len(obj.alias) == 0:                
            self.app.show_error(_('Alias is not specified'))        
            return
        if len(obj.collateral) == 0:
            self.app.show_error(_('Collateral payment is not specified'))
            return
        if len(obj.delegate) == 0:
            self.app.show_error(_('Masternode delegate key is not specified'))
            return
        if len(obj.ipaddress) == 0:
            self.app.show_error(_('Masternode has no IP address'))
            return        
        
        tx_height = self.app.wallet.get_tx_height(obj.txid)
        if tx_height.conf < MASTERNODE_MIN_CONFIRMATIONS:
            self.app.show_error(_('Collateral payment must have at least %d confirmations (current: %d)') %(MASTERNODE_MIN_CONFIRMATIONS, tx_height.conf)) 
            return                    
                    
        msg=[]        
        msg.append(_("Enter your PIN code to proceed"))
        key = obj.txid + '-' + str(obj.index)
        self.app.protected('\n'.join(msg), self.sign_announce, (key,))   
                                
    def sign_announce(self, key, password):
        if self.app.wallet.has_password() and password is None:
            return
        def on_success(key):
            self.app.show_info("Successfully signed Masternode Announce.")
            self.send_announce(key)
            
        def on_failure(error):
            self.app.show_error(_('Error signing MasternodeAnnounce:'))
        
        self.app.sign_announce(key, password, on_success, on_failure)
            
    def send_announce(self, key):
        def on_success(errmsg, was_announced):
            if len(errmsg) > 0 :
                self.app.show_error(errmsg)
            elif was_announced:
                self.app.show_info(_('Masternode was activated successfully.'))
            self.update()
            
        def on_failure(error):
            self.app.show_error(error)
            self.update()
        
        self.app.send_announce(key, on_success, on_failure)

    def get_card(self, utxo, collateral, delegate, status, announced, alias, ip):
        icon = "atlas://electrum/gui/kivy/theming/light/important_dis" 
        icon_announced = "atlas://electrum/gui/kivy/theming/light/instantsend_locked_dis" 
        ri = {}
        ri['screen'] = self
        if status == 'ENABLED' or status == 'PRE_ENABLED':
            ri['icon'] = icon_announced
        else:
            ri['icon'] = icon 
        ri['txid'], ri['index'] = utxo.split('-')
        ri['collateral'] = collateral
        ri['delegate'] = delegate
        ri['status'] = status
        ri['announced'] = announced
        ri['alias'] = alias
        ri['ipaddress'], ri['port'] = ip.split(":")
        
        uxtos = {'prevout_hash': ri['txid'], 'prevout_n': int(ri['index'])}
        if self.app.wallet.is_frozen_coin(uxtos):   
            pos = ri['icon'].find('_dis')
            ri['icon'] = ri['icon'][:pos]        
        return ri

    def update(self, see_all=False):
        if self.app.wallet is None:
            return
        
        self.register_status()
        try:
            masternode_card = self.screen.ids.masternode_container
            cards = []
            if len(self.app.masternode_manager.masternodes) == 0:
                self.hide_menu()
            
            for key in self.app.masternode_manager.masternodes.keys():                
                try:
                    mn = self.app.masternode_manager.masternodes[key]
                    collateral = mn.get_collateral_str()
                    status = mn.status 
                    utxo = str(mn.vin['prevout_hash']) + '-' + str(mn.vin['prevout_n'])
                    ip = mn.addr.ip + ":" + str(mn.addr.port)
                    ci = self.get_card(utxo, str(mn.collateral_key), mn.delegate_key, str(status), mn.announced, mn.alias, ip)
                    cards.append(ci)
                        
                except Exception as e:
                    #self.app.show_error(str(e))
                    continue
            
            masternode_card.data = cards
        except Exception as e:
            self.app.show_error(str(e))
         
    def show_masternode(self, obj):
        self.screen.alias = obj.alias
        self.screen.collateral = bitcoin.public_key_to_p2pkh(bfh(obj.collateral))
        self.screen.utxo = obj.txid + '-' + str(obj.index)
        self.screen.delegate = self.app.wallet.get_delegate_private_key(obj.delegate)
        if len(obj.ipaddress) > 0:
            self.screen.ip = obj.ipaddress + ":" + str(obj.port)
        else:
            self.screen.ip = ''
                    
    def show_menu(self, obj):
        self.hide_menu()
        
        if obj.icon.find('_dis') < 0:            
            self.menu_actions = [ ('Unfreeze', self.do_unfreeze), ('Activate', self.do_activate)]
        else:
            self.menu_actions = [ ('Freeze', self.do_freeze), ('Activate', self.do_activate)]
            
        #if obj.status != 'ENABLED' :            
        self.menu_actions = [('Remove', self.do_remove)] + self.menu_actions
            
        self.context_menu = ContextMenu(obj, self.menu_actions)
        self.add_widget(self.context_menu)
        self.show_masternode(obj)
        
    def do_paste(self):
        data = self.app._clipboard.paste()
        if not data:
            self.app.show_info(_("Clipboard is empty"))
            return
        # try to decode as delegate key
        try:
            txin_type, key, is_compressed = bitcoin.deserialize_privkey(data)
            pubkey = ecc.ECPrivkey(key).get_public_key_hex(compressed=is_compressed)
            self.screen.delegate = data
        except Exception as e:
            self.app.show_error(_("Invalid Delegate Key"))
        
    def do_generate(self):
        private_key = b'\x80' + os.urandom(32)
        checksum = sha256d(private_key)[0:4]
        wif = base58.b58encode(private_key + checksum)        
        self.screen.delegate= str(wif, encoding='utf-8')
    
    def on_qr_delegate(self, data):
        try:
            txin_type, key, is_compressed = bitcoin.deserialize_privkey(data)
            pubkey = ecc.ECPrivkey(key).get_public_key_hex(compressed=is_compressed)
            self.screen.delegate = data
        except Exception as e:
            self.show_error("Unable to decode Delegate Key data")            

    def check_status(self, obj):
        if obj.status == 'ENABLED' or obj.status == 'PRE_ENABLED':
            return True
        return False                
    
    def check_save(self, collateral=None):
        if (self.screen.alias is None) or len(self.screen.alias) == 0:                
            raise Exception(_('Alias is not specified'))        
        if (self.screen.collateral is None) or len(self.screen.collateral) == 0:
            raise Exception(_('Collateral payment is not specified'))
        if (self.screen.delegate is None) or len(self.screen.delegate) == 0:
            raise Exception(_('Masternode delegate key is not specified'))
        if (self.screen.ip is None) or len(self.screen.ip) == 0:
            raise Exception(_('Masternode has no IP address'))
                
        for key in self.app.masternode_manager.masternodes.keys():
            if not (collateral is None):
                if key == collateral:
                    continue
            mn = self.app.masternode_manager.masternodes[key]
            if mn.alias == self.screen.alias:
                raise Exception(_('A masternode with alias "%s" already exists') % self.screen.alias)
            delegate = self.app.wallet.get_delegate_private_key(mn.delegate_key)            
            if delegate == self.screen.delegate:
                raise Exception(_('A masternode with private key "%s" already exists') % self.screen.delegate)
            ipaddress, port = self.screen.ip.split(":")
            if mn.addr.ip == ipaddress:
                raise Exception(_('A masternode with ip address "%s" already exists') % self.screen.ip)
        return True
    
    def register_status(self):
        self.screen.is_pr = True
        
        address = self.app.wallet.get_unused_address()
        if address[0] != 'S':
            return
        
        if not (self.app.wallet.storage.get('user_register') is None):
            self.screen.is_pr = False
         
    def do_import(self):
        from jnius import autoclass  # SDcard Android        
        # Get path to SD card Android
        try:
            Environment = autoclass('android.os.Environment')
            sdpath = Environment.get_running_app().getExternalStorageDirectory()
            self.app.show_info(sdpath)
        # Not on Android
        except Exception as e:
            self.app.show_error(str(e))
            return
            
    def set_frozen_masternode(self, txid , index, frozen=True):         
        utxos = {'prevout_hash': txid, 'prevout_n': int(index)}
        self.app.wallet.set_frozen_state_of_coins([utxos], frozen)  
            
        
