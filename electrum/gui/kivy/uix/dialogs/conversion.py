from kivy.app import App
from kivy.factory import Factory
from kivy.properties import ObjectProperty
from kivy.lang import Builder

from electrum.util import base_units_list
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
    coins: ''
    moneys: ''
    submission_time: ''
    conversion_time: ''
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
            text: root.coins + '-' + root.moneys
            font_size: '15sp'
        CardLabel:
            color: .699, .699, .699, 1
            font_size: '14sp'
            shorten: True
            text: root.conversion_time if root.conversion_time != '' else root.submission_time
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
    title: _('Electrum Conversion')
    amount: ''
    alias: ''
    account: ''
    bank: ''
    mode: ''
    is_pr: False    
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
            CardSeparator:
                opacity: int(not root.is_pr)
                color: blue_bottom.foreground_color                            
            BoxLayout:
                id: mode_selection
                size_hint: 1, None
                height: blue_bottom.item_height
                spacing: '5dp'
                Image:
                    source: 'atlas://electrum/gui/kivy/theming/light/dip3_op'
                    size_hint: None, None
                    size: '22dp', '22dp'
                    pos_hint: {'center_y': .5}
                BlueButton:
                    id: mode_e
                    text: s.mode if s.mode else _('Payment Mode')
                    font_size: '13sp'
                    shorten: True
                    disabled: False
                    on_release: app.choose_payment_dialog(root)
            CardSeparator:
                opacity: int(not root.is_pr)
                color: blue_bottom.foreground_color                    
            BoxLayout:
                id: alias_selection
                size_hint: 1, None
                height: blue_bottom.item_height
                spacing: '5dp'
                Image:
                    source: 'atlas://electrum/gui/kivy/theming/light/star_big_inactive'
                    size_hint: None, None
                    size: '22dp', '22dp'
                    pos_hint: {'center_y': .5}
                BlueButton:
                    id: alias_e
                    text: s.alias if s.alias else _('Name')
                    font_size: '13sp'
                    shorten: True
                    disabled: False
                    on_release: Clock.schedule_once(lambda dt: app.masternode_dialog(_('Enter Alias'), s))
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
                    font_size: '13sp'
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
                    source: 'atlas://electrum/gui/kivy/theming/light/pen'
                    size_hint: None, None
                    size: '22dp', '22dp'
                    pos_hint: {'center_y': .5}
                BlueButton:
                    id: bank_e
                    text: s.bank if s.bank else _('Bank')
                    font_size: '13sp'
                    shorten: True
                    disabled: False
                    on_release: Clock.schedule_once(lambda dt: app.masternode_dialog(_('Enter Bank'), s))
        BoxLayout:
            size_hint: 1, None
            height: '48dp'
            Button:
                text: _('Select')
                size_hint: 1, 1
                on_release: root.do_select()
            Widget:
                size_hint: 1, 1
            Button:
                text: _('Destory')
                size_hint: 1, 1
                on_release: root.do_destroy()
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
        
        #layout = self.ids.scrollviewlayout
        #layout.bind(minimum_height=layout.setter('height'))
        # cached dialogs
        self._conversion_select_dialog = None
        
        self.context_menu = None
        self.menu_actions = [('Details', self.show_conversion)]
        
        self.payment_request = None
        
    def show_conversion(self):
        pass
    
    def update(self):
        conversion_card = self.ids.conversion_container        
        cards = []
        
        ci = self.get_card(100.11, 234.55, '2020-03-25 11:12:13', '2020-03-26 09:10:11')
        cards.append(ci)

        ci = self.get_card(200.11, 456.66, '2020-03-21 21:12:13', '2020-03-24 19:10:11')
        cards.append(ci)
        
        conversion_card.data = cards
        
    def get_card(self, coins, moneys, submission_time, conversion_time):
        icon = "atlas://electrum/gui/kivy/theming/light/important" 
        icon_announced = "atlas://electrum/gui/kivy/theming/light/instantsend_locked" 
        ri = {}
        ri['screen'] = self
        if moneys > 0:
            ri['icon'] = icon_announced
        else:
            ri['icon'] = icon 
        ri['coins'] = str(coins)
        ri['moneys'] = str(moneys)
        ri['submission_time'] = submission_time
        ri['conversion_time'] = conversion_time
        return ri

    def conversion_select_dialog(self, item, dt):
        if self._conversion_select_dialog is None:
            def cb(text):
                self.config.set_key('coin_chooser', text)
                item.status = text
            #self._conversion_select_dialog = ChoiceDialog(_('Payment selection'), choosers, chooser_name, cb)
        self._conversion_select_dialog.open()

    def hide_menu(self):
        pass
    
    def show_menu(self, obj):
        pass

    def do_select(self):
        pass
    
    def do_destroy(self):
        address = str(DESTROY_ADDRESS)
        if not address:
            self.app.show_error(_('Recipient not specified.') + ' ' + _('Please scan a Bitcoin address or a payment request'))
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
        def on_failure(error):
            self.app.show_error(error)
        if self.app.wallet.can_sign(tx):
            self.app.show_info("Signing...")
            self.app.sign_tx(tx, password, on_success, on_failure)
        else:
            self.app.tx_dialog(tx)

    def broadcast(self, tx, pr=None):
        def on_complete(ok, tx):
            if ok:
                #self.app.show_info(_('Payment sent.'))
                self.app.show_info(_('Conversion commit.'))
                self.amount = ''
                self.destroy_commit(tx)
            else:
                msg = msg or ''
                self.show_error(msg)
                return 
                
        self.app.broadcast_conversion(tx, on_complete, pr)

    def destroy_commit(self, tx):
        format_amount = self.app.format_amount_and_units
        tx_details = self.app.wallet.get_tx_info(tx)
        amount, fee = tx_details.amount, tx_details.fee
        txid = tx.txid()
        
        destroy_address = DESTROY_ADDRESS
        
        for item in tx.inputs():
            input_address = item['address']
            break
        
        response = self.app.client.post_conversion(txid, amount, fee, destroy_address, input_address)
        if response['code'] == 200:    
            self.app.show_info(_('Conversion finish.'))
        else:
            self.app.show_error(_('Conversion finish.'))
            
