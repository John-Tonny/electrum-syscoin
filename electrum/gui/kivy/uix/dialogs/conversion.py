from kivy.app import App
from kivy.factory import Factory
from kivy.properties import ObjectProperty
from kivy.lang import Builder

from electrum.util import base_units_list, NotEnoughFunds

from electrum.i18n import languages
from electrum.gui.kivy.i18n import _
from electrum.plugin import run_hook
from electrum import coinchooser

from .choice_dialog import ChoiceDialog

from kivy.uix.recycleview import RecycleView
from electrum.gui.kivy.uix.context_menu import ContextMenu

from electrum.constants import DESTROY_ADDRESS
from electrum import bitcoin
from electrum.transaction import TxOutput, Transaction, tx_from_str
from electrum import simple_config

import copy
import traceback
import sys

Builder.load_string('''
#:import partial functools.partial
#:import _ electrum.gui.kivy.i18n._

<CardLabel@Label>
    color: 0.95, 0.95, 0.95, 1
    size_hint: 1, None
    text: ''
    text_size: self.width, None
    height: self.texture_size[1]
    halign: 'left'
    valign: 'top'

<ConversionItem@CardItem>
    icon: 'atlas://electrum/gui/kivy/theming/light/important'
    conversion_time: ''
    status: ''
    amount: ''
    alias: ''
    account: ''
    bank: ''
    mode: ''
    Image:
        id: icon
        source: root.icon
        size_hint: None, 1
        allow_stretch: True
        width: self.height*1.5
        mipmap: True
    BoxLayout:
        orientation: 'vertical'
        Widget
        CardLabel:
            text: root.status + '  ' +root.conversion_time 
            font_size: '15sp'
        CardLabel:
            color: .699, .699, .699, 1
            font_size: '14sp'
            shorten: True
            text: root.amount
        Widget

<ConversionRecycleView>:
    viewclass: 'ConversionItem'
    RecycleBoxLayout:
        default_size: None, dp(56)
        default_size_hint: 1, None
        size_hint: 1, None
        height: self.minimum_height
        orientation: 'vertical'

<ConversionDialog@Popup>
    id: s
    title: _('Conversion')
    amount: ''
    alias: ''
    account: ''
    bank: ''
    mode: _('weixin')
    is_pr: False
    next_pr: True
    back_pr: True
    disable_pin: False
    use_encryption: False
    BoxLayout
        padding: '12dp', '12dp', '12dp', '12dp'
        spacing: '12dp'
        orientation: 'vertical'
        SendReceiveBlueBottom:
            id: blue_bottom
            size_hint: 1, None
            height: self.minimum_height
            CardSeparator:
                opacity: int(not root.is_pr)
                color: blue_bottom.foreground_color                            
            BoxLayout:
                id: mode_selection
                size_hint: 1, None
                height: blue_bottom.item_height
                spacing: '5dp'
                Image:
                    source: 'atlas://electrum/gui/kivy/theming/light/paymode'
                    opacity: 0.7
                    size_hint: None, None
                    size: '22dp', '22dp'
                    pos_hint: {'center_y': .5}
                BlueButton:
                    id: mode_e
                    text: s.mode if s.mode else _('Payment Modes')
                    shorten: True
                    disabled: False
                    on_release: Clock.schedule_once(lambda dt: app.choose_payway_dialog(root))
            CardSeparator:
                opacity: int(not root.is_pr)
                color: blue_bottom.foreground_color                    
            BoxLayout:
                id: alias_selection
                size_hint: 1, None
                height: blue_bottom.item_height
                spacing: '5dp'
                Image:
                    source: 'atlas://electrum/gui/kivy/theming/light/contact'
                    opacity: 0.7
                    size_hint: None, None
                    size: '22dp', '22dp'
                    pos_hint: {'center_y': .5}
                BlueButton:
                    id: alias_e
                    text: s.alias if s.alias else _('Name')
                    shorten: True
                    disabled: False
                    on_release: Clock.schedule_once(lambda dt: app.masternode_dialog(_('Enter Name'), s))
            CardSeparator:
                opacity: int(not root.is_pr)
                color: blue_bottom.foreground_color            
            BoxLayout:
                id: account_selection
                size_hint: 1, None
                height: blue_bottom.item_height
                spacing: '5dp'
                Image:
                    source: 'atlas://electrum/gui/kivy/theming/light/globe'
                    opacity: 0.7
                    size_hint: None, None
                    size: '22dp', '22dp'
                    pos_hint: {'center_y': .5}
                BlueButton:
                    id: account_e
                    text: s.account if s.account else _('Account')
                    disabled: False
                    shorten: True                    
                    on_release: Clock.schedule_once(lambda dt: app.masternode_dialog(_('Enter Account'), s))
            CardSeparator:
                opacity: int(not root.is_pr)
                color: blue_bottom.foreground_color
            BoxLayout:
                id: bank_selection
                size_hint: 1, None
                height: blue_bottom.item_height
                spacing: '5dp'
                Image:
                    source: 'atlas://electrum/gui/kivy/theming/light/bank'
                    opacity: 0.7
                    size_hint: None, None
                    size: '22dp', '22dp'
                    pos_hint: {'center_y': .5}
                BlueButton:
                    id: bank_e
                    text: s.bank if s.bank else _('Bank')
                    shorten: True
                    disabled: root.disable_pin
                    on_release: Clock.schedule_once(lambda dt: app.masternode_dialog(_('Enter Bank'), s))
            BoxLayout:
                size_hint: 1, None
                height: blue_bottom.item_height
                spacing: '5dp'
                Image:
                    source: 'atlas://electrum/gui/kivy/theming/light/calculator'
                    opacity: 0.7
                    size_hint: None, None
                    size: '22dp', '22dp'
                    pos_hint: {'center_y': .5}
                BlueButton:
                    id: amount_e
                    default_text: _('Amount')
                    text: s.amount if s.amount else _('Amount')
                    disabled: root.is_pr
                    on_release: Clock.schedule_once(lambda dt: app.amount_dialog(s, True, 'conversion'))
            CardSeparator:
                opacity: int(not root.is_pr)
                color: blue_bottom.foreground_color
            BoxLayout:
                size_hint: 1, None
                height: blue_bottom.item_height
                spacing: '5dp'
                Image:
                    source: 'atlas://electrum/gui/kivy/theming/light/star_big_inactive'
                    opacity: 0.7
                    size_hint: None, None
                    size: '22dp', '22dp'
                    pos_hint: {'center_y': .5}
                BlueButton:
                    id: fee_e
                    default_text: _('Fee')
                    text: app.fee_status
                    on_release: Clock.schedule_once(lambda dt: app.fee_dialog(s, True))
        BoxLayout:
            size_hint: 1, None
            height: '48dp'
            IconButton:
                id: account
                size_hint: 0.6, 1
                disabled: root.is_pr
                icon: 'atlas://electrum/gui/kivy/theming/light/close'
                on_release: s.dismiss()
            IconButton:
                id: account
                size_hint: 0.6, 1
                disabled: root.is_pr
                icon: 'atlas://electrum/gui/kivy/theming/light/accounts'
                on_release: Clock.schedule_once(lambda dt: app.choose_payaccount_dialog(root))
            Button:
                text: _('Conversion')
                size_hint: 1, 1
                on_release: Clock.schedule_once(lambda dt: root.do_destroy())
            IconButton:
                id: back_page
                size_hint: 0.6, 1
                disabled: root.is_pr or root.back_pr
                icon: 'atlas://electrum/gui/kivy/theming/light/back_page'
                on_release: Clock.schedule_once(lambda dt: root.do_back_page())
            IconButton:
                id: search
                size_hint: 0.6, 1
                disabled: root.is_pr
                icon: 'atlas://electrum/gui/kivy/theming/light/search'
                on_release: Clock.schedule_once(lambda dt: root.do_search())
            IconButton:
                id: next_page
                size_hint: 0.6, 1
                disabled: root.is_pr or root.next_pr
                icon: 'atlas://electrum/gui/kivy/theming/light/next_page'
                on_release: Clock.schedule_once(lambda dt: root.do_next_page())
        ConversionRecycleView:
            id: conversion_container
            scroll_type: ['bars', 'content']
            bar_width: '25dp'                
''')


class ConversionRecycleView(RecycleView):
    pass

class ConversionDialog(Factory.Popup):

    def __init__(self, app):
        self.app = app
        self.plugins = self.app.plugins
        self.config = self.app.electrum_config
        Factory.Popup.__init__(self)
        
        # cached dialogs
        self._conversion_payway_dialog = None
        self._conversion_payaccount_dialog = None
        
        self.context_menu = None
        self.menu_actions = [('Details', self.show_conversion)]
        
        self.payment_request = None
        self.conversion_data ={}
        
        self.disable_pin = True
        
    def show_conversion(self):
        self.app.show_info("show convert")
        pass
    
    def update(self):
        conversion_card = self.ids.conversion_container        
        cards = []
        
        if self.app.client is None:
            conversion_card = cards
            return

        self.search_state_update()
        
        conversion_txid = ''
        is_commit, conversion_data = self.app.client.get_conversion_commit()        
        if is_commit:
            conversion_txid = str(conversion_data.get('txId')) if not conversion_data.get('txId') is None else ''
                
        conversion_list = self.app.client.conversion_list
        if len(conversion_list) > 0:
            start = (self.app.client.conversion_cur_page-1) * self.app.client.conversion_page_size 
            stop = start + self.app.client.conversion_page_size
            conversion_list = conversion_list[start:stop]
        for data in conversion_list:
            status = data.get('txFlag') if not data.get('txFlag') is None else ''
            sdate = data.get('createTime') if not data.get('createTime') is None else ''
            amount = str(data.get('amount')/bitcoin.COIN) if not data.get('amount') is None else ''
            payWay = data.get('payWay') if not data.get('payWay') is None else '1'
            payWay = self.get_pay_mode_from_num(payWay)
            payName = data.get('payName') if not data.get('payName') is None else ''
            payAccount = data.get('payAccount') if not data.get('payAccount') is None else ''
            payBank = data.get('payBank') if not data.get('payBank') is None else ''
            
            txid = str(data.get('txId')) if not data.get('txId') is None else ''
            if is_commit:
                if txid == conversion_txid:
                    is_commit = False
                    self.app.wallet.storage.put('conversion_masternode', {})
            
            ci = self.get_card(status, amount, sdate, payName, payAccount, payBank, payWay)
            cards.append(ci)
            
        if is_commit:
            status = conversion_data.get('txFlag') if not conversion_data.get('txFlag') is None else ''
            sdate = conversion_data.get('createTime') if not conversion_data.get('createTime') is None else ''
            amount = str(conversion_data.get('amount')/bitcoin.COIN) if not conversion_data.get('amount') is None else ''
            
            if conversion_data.get('payWay') is None:
                payWay = _('weixin')
            else:
                payWay = conversion_data.get('payWay') if not conversion_data.get('payWay') is None else '1'
                payWay = self.get_pay_mode_from_num(payWay)
            payName = conversion_data.get('payName') if not conversion_data.get('payName') is None else ''
            payAccount = conversion_data.get('payAccount') if not conversion_data.get('payAccount') is None else ''
            payBank = conversion_data.get('payBank') if not conversion_data.get('payBank') is None else ''
            ci = self.get_card(status, amount, sdate, payName, payAccount, payBank, payWay)
            cards.append(ci)            
        
        conversion_card.data = cards
        
    def get_card(self, status, amount, conversion_time, alias, account, bank, mode):
        icon = "atlas://electrum/gui/kivy/theming/light/important" 
        icon_announced = "atlas://electrum/gui/kivy/theming/light/instantsend_locked" 
        ri = {}
        ri['screen'] = self
        if status == '1':
            ri['icon'] = icon_announced
        else:
            ri['icon'] = icon 
        ri['amount'] = str(amount)
        if status == '0':
            status = _('Verifing')
        elif status == '1':
            status = _('Verified')
        elif status == '-1':
            status = _('Verify failed')
        elif status == '-100':
            status = _('Submit failed')
        else:
            status = _('unknown')
        ri['status'] = status
        ri['alias'] = alias
        ri['account'] = account
        ri['bank'] = bank
        ri['mode'] = mode
        ri['conversion_time'] = conversion_time.replace('T', ' ')
        return ri

    def hide_menu(self):
        pass
    
    def show_menu(self, obj):
        #self.hide_menu()
        #self.context_menu = ContextMenu(obj, self.menu_actions)
        #self.add_widget(self.context_menu)
        #self.show_masternode(obj)
        #self.alias = obj.alias
        pass
    
    def do_destroy(self):     
        if self.app.client is None:
            return
        if self.app.client.money_ratio == 0:
            self.app.show_info(_('Value not yet determined, please wait!'))
            return
        
        is_commit, data = self.app.client.get_conversion_commit()        
        if is_commit: 
            tx = self.app.wallet.db.get_transaction(data['txId'])                
            self.destroy_commit(tx)
            return
        
        try:
            self.check_conversion()
        except Exception as e:
            self.app.show_error(str(e))
            return
        
        self.conversion_data = {}
        self.conversion_data['createTime'] = self.app.client.get_current_time()             
        self.conversion_data['payWay'] = self.get_pay_mode()
        self.conversion_data['payName'] = self.alias
        self.conversion_data['payAccount'] = self.account
        self.conversion_data['payBank'] = self.bank
        self.conversion_data['payBankSub'] = 'sub'
        
        address = str(DESTROY_ADDRESS)
        if not address:
            self.app.show_error(_('Recipient not specified.'))
            return
        if not bitcoin.is_address(address):
            self.app.show_error(_('Invalid Bitcoin Address') + ':\n' + address)
            return
        try:
            amount = self.app.get_amount(self.amount)
        except:
            self.app.show_error(_('Invalid amount') + ':\n' + self.amount)
            return
        outputs = [TxOutput(bitcoin.TYPE_ADDRESS, address, amount)]

        message = ''
        amount = sum(map(lambda x:x[2], outputs))
        if self.app.electrum_config.get('use_rbf'):
            from electrum.gui.kivy.uix.dialogs.question import Question
            d = Question(_('Should this transaction be replaceable?'), lambda b: self._do_send(amount, message, outputs, b))
            d.open()
        else:
            self._do_send(amount, message, outputs, False)
        pass
    
    def _do_send(self, amount, message, outputs, rbf):
        # make unsigned transaction
        config = self.app.electrum_config
        coins = self.app.wallet.get_spendable_coins(None, config)
        try:
            tx = self.app.wallet.make_unsigned_transaction(coins, outputs, config, None)
        except NotEnoughFunds:
            self.app.show_error(_("Not enough funds"))
            return
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            self.app.show_error(str(e))
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
        self.app.protected('\n'.join(msg), self.send_tx, (tx, message))

    def send_tx(self, tx, message, password):
        if self.app.wallet.has_password() and password is None:
            return
        def on_success(tx):
            if tx.is_complete():
                self.broadcast(tx, self.payment_request)
                self.app.wallet.set_label(tx.txid(), message)
            else:
                self.app.tx_dialog(tx)
            return
        def on_failure(error):
            self.app.show_error(error)
            return
        if self.app.wallet.can_sign(tx):
            self.app.show_info(_("Signing transaction..."))
            self.app.sign_tx(tx, password, on_success, on_failure)
        else:
            self.app.tx_dialog(tx)

    def broadcast(self, tx, pr=None):
        def on_complete(ok, tx):
            if ok:
                self.app.show_info(_("broadcast successful!"))
                self.amount = ''
                self.destroy_commit(tx)
            else:
                self.app.show_error(_("broadcast failed!"))
                return 
                
        self.app.broadcast_conversion(tx, on_complete, pr)

    def do_search(self):
        self.app.client.do_search_conversion()
        self.update()
    
    def do_back_page(self):
        self.app.client.do_back_conversion()
        self.update()
    
    def do_next_page(self):
        self.app.client.do_next_conversion()
        self.update()
    
    def destroy_commit(self, tx):        
        self.app.show_info(_("Convert..."))
        tx = copy.deepcopy(tx)  # type: Transaction
        try:
            tx.deserialize()
        except BaseException as e:
            self.app.show_error(str(e))
            return
            #raise SerializationError(e)    
                
        format_amount = self.app.format_amount_and_units
        tx_details = self.app.wallet.get_tx_info(tx)
        amount, fee = tx_details.amount, tx_details.fee
        txid = tx.txid()
        destroy_address = DESTROY_ADDRESS        
        is_destroy = False
        amount = 0
        for output in tx.outputs():
            if output.address == destroy_address:
                amount = output.value 
                is_destroy = True
        if not is_destroy: 
            return        
        
        for item in tx.inputs():
            input_address = item['address']
            break
                
        payWay = self.conversion_data['payWay']
        payName = self.conversion_data['payName']
        payAccount = self.conversion_data['payAccount']
        payBank = self.conversion_data['payBank']
        payBankSub = self.conversion_data['payBankSub']
        remark = ''
                
        response = self.app.client.post_conversion(txid, amount, fee, destroy_address, input_address, payWay, payName, payAccount, payBank, payBankSub, remark)
        if response['code'] == 200:    
            self.app.client.payaccount_add(payName, payAccount, payBank, payWay)
            #self.app.client.conversion_commit_send(response['data'])
            self.update()
            self.app.show_info(_('Conversion successful!'))
        elif response['code'] == 901:    
            self.app.client.payaccount_add(payName, payAccount, payBank, payWay)
            self.app.show_info(_('Conversion successful!'))
        else:          
            self.conversion_data['txFlag'] = '-100'
            self.conversion_data['createTime'] = self.app.client.get_current_time()             
            self.conversion_data['txId'] = txid
            self.conversion_data['amount'] = amount
            self.conversion_data['fee'] = fee        
            
            self.app.wallet.storage.put('conversion_masternode', self.conversion_data)            
            self.update()
            self.app.show_error(_('Conversion failed!'))
            
    def set_pay_mode(self, mode):
        if self.mode == _('bank'):
            self.bank.setReadOnly(True)
        else:
            self.bank.setReadOnly(False)
    
    def get_pay_mode(self):
        if self.mode == _('bank'):
            return '1'
        
        if self.mode == _('weixin'):
            return '2'
        
        if self.mode == _('zhifubao'):
            return '3'
    
    def get_pay_mode_from_num(self, num):
        if self.mode == '1':
            return _('bank')
        
        if self.mode == '2':
            return _('weixin')
        
        if self.mode == '3':
            return _('zhifubao')
        return _('bank')

    def check_conversion(self):
        if len(self.alias) == 0:
            raise Exception(_("Name is not specified."))
        if len(self.account) == 0:            
            raise Exception(_("Account is not specified."))
        if self.get_pay_mode() == '1' :
            if len(self.bank) == 0:            
                raise Exception(_("Bank is not specified."))
        if len(self.amount) == 0:
            raise Exception(_("Amount is not specified."))
            

    def search_state_update(self):
        if self.app.client is None:
            self.next_pr = True
            self.back_pr = True
        else:
            total_page = (self.app.client.conversion_total + (self.app.client.conversion_page_size -1))//self.app.client.conversion_page_size
            if total_page <= 1 :
                self.next_pr = True
                self.back_pr = True   
            elif self.app.client.conversion_cur_page == 1:
                self.next_pr = False
                self.back_pr = True
            elif self.app.client.conversion_cur_page == total_page:
                self.next_pr = True
                self.back_pr = False
            elif self.app.client.conversion_cur_page < total_page:
                self.next_pr = False
                self.back_pr = False
