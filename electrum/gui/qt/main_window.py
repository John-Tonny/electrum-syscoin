#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@gitorious
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import sys
import time
import threading
import os
import traceback
import json
import shutil
import weakref
import webbrowser
import csv
from decimal import Decimal
import base64
from functools import partial
import queue
import asyncio
from typing import Optional
###john
import secrets

from PyQt5.QtGui import QPixmap, QKeySequence, QIcon, QCursor
from PyQt5.QtCore import Qt, QRect, QStringListModel, QSize, pyqtSignal, QTimer
from PyQt5.QtWidgets import (QMessageBox, QComboBox, QSystemTrayIcon, QTabWidget,
                             QSpinBox, QMenuBar, QFileDialog, QCheckBox, QLabel,
                             QVBoxLayout, QGridLayout, QLineEdit, QTreeWidgetItem,
                             QHBoxLayout, QPushButton, QScrollArea, QTextEdit,
                             QShortcut, QMainWindow, QCompleter, QInputDialog,
                             QWidget, QMenu, QSizePolicy, QStatusBar, QRadioButton)
import electrum
from electrum import (keystore, simple_config, ecc, constants, util, bitcoin, commands,
                      coinchooser, paymentrequest)
from electrum.bitcoin import COIN, is_address, TYPE_ADDRESS
from electrum.plugin import run_hook
from electrum.i18n import _
from electrum.util import (format_time, format_satoshis, format_fee_satoshis,ADDRESS_PREFIX,
                           format_satoshis_plain, NotEnoughFunds, PrintError,
                           UserCancelled, NoDynamicFeeEstimates, profiler,
                           export_meta, import_meta, bh2u, bfh, InvalidPassword,
                           base_units, base_units_list, base_unit_name_to_decimal_point,
                           decimal_point_to_base_unit_name, quantize_feerate,
                           UnknownBaseUnit, DECIMAL_POINT_DEFAULT, UserFacingException,
                           get_new_wallet_name, send_exception_to_crash_reporter,
                           InvalidBitcoinURI, AlreadyHaveAddress, USE_COLLATERAL_DEFAULT, use_collateral_list, USE_RBF_DEFAULT)
from electrum.transaction import Transaction, TxOutput
from electrum.address_synchronizer import AddTransactionException
from electrum.wallet import (Multisig_Wallet, CannotBumpFee, Abstract_Wallet,
                             sweep_preparations, InternalAddressCorruption)
from electrum.version import ELECTRUM_VERSION
from electrum.network import Network, TxBroadcastError, BestEffortRequestFailed
from electrum.exchange_rate import FxThread
from electrum.simple_config import SimpleConfig
from electrum.logging import Logger
from electrum.paymentrequest import PR_PAID

from .exception_window import Exception_Hook
from .amountedit import AmountEdit, BTCAmountEdit, MyLineEdit, FeerateEdit
from .qrcodewidget import QRCodeWidget, QRDialog
from .qrtextedit import ShowQRTextEdit, ScanQRTextEdit
from .transaction_dialog import show_transaction
from .fee_slider import FeeSlider
from .util import (read_QIcon, ColorScheme, text_dialog, icon_path, WaitingDialog,
                   WindowModalDialog, ChoicesLayout, HelpLabel, FromList, Buttons,
                   OkButton, InfoButton, WWLabel, TaskThread, CancelButton, EnterParamsButton,
                   CloseButton, HelpButton, MessageBoxMixin, EnterButton, expiration_values,
                   ButtonsLineEdit, CopyCloseButton, import_meta_gui, export_meta_gui,
                   filename_field, address_field)
from .installwizard import WIF_HELP_TEXT
from .history_list import HistoryList, HistoryModel
from .update_checker import UpdateCheck, UpdateCheckThread
from .masternode_list import MasternodeList
from .conversion_list import ConversionList

###john
from electrum.masternode_manager import MasternodeManager, parse_masternode_conf, MASTERNODE_MIN_CONFIRMATIONS
from electrum.masternode import MasternodeAnnounce, NetworkAddress, MasternodePing
from electrum.client import Client
import base58
import copy
from electrum.crypto import sha256d
from electrum.transaction import SerializationError
from electrum.keystore import Xpub
import re
from electrum.gui.qt.paytoedit import RE_ALIAS

class StatusBarButton(QPushButton):
    def __init__(self, icon, tooltip, func):
        QPushButton.__init__(self, icon, '')
        self.setToolTip(tooltip)
        self.setFlat(True)
        self.setMaximumWidth(25)
        self.clicked.connect(self.onPress)
        self.func = func
        self.setIconSize(QSize(25,25))
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def onPress(self, checked=False):
        '''Drops the unwanted PyQt5 "checked" argument'''
        self.func()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Return:
            self.func()

###john
class ElectrumWindow(QMainWindow, MessageBoxMixin, PrintError):

    payment_request_ok_signal = pyqtSignal()
    payment_request_error_signal = pyqtSignal()
    new_fx_quotes_signal = pyqtSignal()
    new_fx_history_signal = pyqtSignal()
    network_signal = pyqtSignal(str, object)
    alias_received_signal = pyqtSignal()
    computing_privkeys_signal = pyqtSignal()
    show_privkeys_signal = pyqtSignal()

    def __init__(self, gui_object, wallet: Abstract_Wallet):
        QMainWindow.__init__(self)
        
        self.gui_object = gui_object
        self.config = config = gui_object.config  # type: SimpleConfig
        self.gui_thread = gui_object.gui_thread
        
        ###john
        self.masternode_manager = MasternodeManager(None, self.config)
        self.client = None
        self.feerounding_text = ''
        self.conversion_retrys = 0
        self.conversion_data = {}
        self.aggregation_nums = 0
        self.aggregation_password = None

        self.setup_exception_hook()

        self.network = gui_object.daemon.network  # type: Network
        assert wallet, "no wallet"
        self.wallet = wallet
        self.fx = gui_object.daemon.fx  # type: FxThread
        self.invoices = wallet.invoices
        self.contacts = wallet.contacts
        self.tray = gui_object.tray
        self.app = gui_object.app
        self.cleaned_up = False
        self.payment_request = None  # type: Optional[paymentrequest.PaymentRequest]
        self.asset_payment_request = None
        self.checking_accounts = False
        self.qr_window = None
        self.not_enough_funds = False
        self.pluginsdialog = None
        self.require_fee_update = False
        self.tl_windows = []
        self.tx_external_keypairs = {}

        self.tx_notification_queue = queue.Queue()
        self.tx_notification_last_time = 0

        self.create_status_bar()
        self.need_update = threading.Event()

        self.decimal_point = config.get('decimal_point', DECIMAL_POINT_DEFAULT)
        try:
            decimal_point_to_base_unit_name(self.decimal_point)
        except UnknownBaseUnit:
            self.decimal_point = DECIMAL_POINT_DEFAULT
        self.num_zeros = int(config.get('num_zeros', 0))

        self.completions = QStringListModel()

        self.tabs = tabs = QTabWidget(self)
        self.send_tab = self.create_send_tab()
        self.receive_tab = self.create_receive_tab()
        self.addresses_tab = self.create_addresses_tab()
        self.utxo_tab = self.create_utxo_tab()
        self.console_tab = self.create_console_tab()
        self.contacts_tab = self.create_contacts_tab()
        
        ###john
        self.masternode_tab = self.create_masternode_tab()
        self.conversion_tab = self.create_conversion_tab()
                
        tabs.addTab(self.create_history_tab(), read_QIcon("tab_history.png"), _('History'))
        tabs.addTab(self.send_tab, read_QIcon("tab_send.png"), _('Send'))
        tabs.addTab(self.receive_tab, read_QIcon("tab_receive.png"), _('Receive'))

        def add_optional_tab(tabs, tab, icon, description, name):
            tab.tab_icon = icon
            tab.tab_description = description
            tab.tab_pos = len(tabs)
            tab.tab_name = name
            if self.config.get('show_{}_tab'.format(name), False):
                tabs.addTab(tab, icon, description.replace("&", ""))

        add_optional_tab(tabs, self.addresses_tab, read_QIcon("tab_addresses.png"), _("&Addresses"), "addresses")
        add_optional_tab(tabs, self.utxo_tab, read_QIcon("tab_coins.png"), _("Co&ins"), "utxo")
        add_optional_tab(tabs, self.contacts_tab, read_QIcon("tab_contacts.png"), _("Con&tacts"), "contacts")
        add_optional_tab(tabs, self.console_tab, read_QIcon("tab_console.png"), _("Con&sole"), "console")
        ###john
        add_optional_tab(tabs, self.masternode_tab, read_QIcon("tab_console.png"), _("&Masternode"), "masternode")
        add_optional_tab(tabs, self.conversion_tab, read_QIcon("tab_console.png"), _("Con&version"), "conversion")

        tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCentralWidget(tabs)

        if self.config.get("is_maximized"):
            self.showMaximized()

        self.setWindowIcon(read_QIcon("electrum.png"))
        self.init_menubar()

        wrtabs = weakref.proxy(tabs)
        QShortcut(QKeySequence("Ctrl+W"), self, self.close)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)
        QShortcut(QKeySequence("Ctrl+R"), self, self.update_wallet)
        QShortcut(QKeySequence("F5"), self, self.update_wallet)
        QShortcut(QKeySequence("Ctrl+PgUp"), self, lambda: wrtabs.setCurrentIndex((wrtabs.currentIndex() - 1)%wrtabs.count()))
        QShortcut(QKeySequence("Ctrl+PgDown"), self, lambda: wrtabs.setCurrentIndex((wrtabs.currentIndex() + 1)%wrtabs.count()))
        
        for i in range(wrtabs.count()):
            QShortcut(QKeySequence("Alt+" + str(i + 1)), self, lambda i=i: wrtabs.setCurrentIndex(i))

        self.payment_request_ok_signal.connect(self.payment_request_ok)
        self.payment_request_error_signal.connect(self.payment_request_error)
        self.history_list.setFocus(True)

        # network callbacks
        if self.network:
            self.network_signal.connect(self.on_network_qt)
            interests = ['wallet_updated', 'network_updated', 'blockchain_updated',
                         'new_transaction', 'status',
                         'banner', 'verified', 'fee', 'fee_histogram']
            # To avoid leaking references to "self" that prevent the
            # window from being GC-ed when closed, callbacks should be
            # methods of this class only, and specifically not be
            # partials, lambdas or methods of subobjects.  Hence...
            self.network.register_callback(self.on_network, interests)
            # set initial message
            self.console.showMessage(self.network.banner)
            self.network.register_callback(self.on_quotes, ['on_quotes'])
            self.network.register_callback(self.on_history, ['on_history'])
            self.new_fx_quotes_signal.connect(self.on_fx_quotes)
            self.new_fx_history_signal.connect(self.on_fx_history)

        # update fee slider in case we missed the callback
        self.fee_slider.update()
        self.load_wallet(wallet)
        gui_object.timer.timeout.connect(self.timer_actions)
        self.fetch_alias()

        # If the option hasn't been set yet
        if config.get('check_updates') is None:
            choice = self.question(title="Electrum - " + _("Enable update check"),
                                   msg=_("For security reasons we advise that you always use the latest version of Electrum.") + " " +
                                       _("Would you like to be notified when there is a newer version of Electrum available?"))
            config.set_key('check_updates', bool(choice), save=True)

        if config.get('check_updates', False):
            # The references to both the thread and the window need to be stored somewhere
            # to prevent GC from getting in our way.
            def on_version_received(v):
                if UpdateCheck.is_newer(v):
                    self.update_check_button.setText(_("Update to Electrum {} is available").format(v))
                    self.update_check_button.clicked.connect(lambda: self.show_update_check(v))
                    self.update_check_button.show()
            self._update_check_thread = UpdateCheckThread(self)
            self._update_check_thread.checked.connect(on_version_received)
            self._update_check_thread.start()
        ###john
        self.assets_inited = None
            

    def on_history(self, b):
        self.wallet.clear_coin_price_cache()
        self.new_fx_history_signal.emit()

    def setup_exception_hook(self):
        Exception_Hook(self)

    def on_fx_history(self):
        self.history_model.refresh('fx_history')
        self.address_list.update()

    def on_quotes(self, b):
        self.new_fx_quotes_signal.emit()

    def on_fx_quotes(self):
        self.update_status()
        # Refresh edits with the new rate
        edit = self.fiat_send_e if self.fiat_send_e.is_last_edited else self.amount_e
        edit.textEdited.emit(edit.text())
        edit = self.fiat_receive_e if self.fiat_receive_e.is_last_edited else self.receive_amount_e
        edit.textEdited.emit(edit.text())
        # History tab needs updating if it used spot
        if self.fx.history_used_spot:
            self.history_model.refresh('fx_quotes')
        self.address_list.update()

    def toggle_tab(self, tab):
        show = not self.config.get('show_{}_tab'.format(tab.tab_name), False)
        if tab.tab_name == 'masternode' or tab.tab_name == 'conversion':
            if show:
                if not self.check_register():
                    return
        
                
        self.config.set_key('show_{}_tab'.format(tab.tab_name), show)
        item_text = (_("Hide {}") if show else _("Show {}")).format(tab.tab_description)
        tab.menu_action.setText(item_text)
        if show:
            # Find out where to place the tab
            index = len(self.tabs)
            for i in range(len(self.tabs)):
                try:
                    if tab.tab_pos < self.tabs.widget(i).tab_pos:
                        index = i
                        break
                except AttributeError:
                    pass
            self.tabs.insertTab(index, tab, tab.tab_icon, tab.tab_description.replace("&", ""))
        else:
            i = self.tabs.indexOf(tab)
            self.tabs.removeTab(i)

    def push_top_level_window(self, window):
        '''Used for e.g. tx dialog box to ensure new dialogs are appropriately
        parented.  This used to be done by explicitly providing the parent
        window, but that isn't something hardware wallet prompts know.'''
        self.tl_windows.append(window)

    def pop_top_level_window(self, window):
        self.tl_windows.remove(window)

    def top_level_window(self, test_func=None):
        '''Do the right thing in the presence of tx dialog windows'''
        override = self.tl_windows[-1] if self.tl_windows else None
        if override and test_func and not test_func(override):
            override = None  # only override if ok for test_func
        return self.top_level_window_recurse(override, test_func)

    def diagnostic_name(self):
        #return '{}:{}'.format(self.__class__.__name__, self.wallet.diagnostic_name())
        return self.wallet.diagnostic_name()

    def is_hidden(self):
        return self.isMinimized() or self.isHidden()

    def show_or_hide(self):
        if self.is_hidden():
            self.bring_to_top()
        else:
            self.hide()

    def bring_to_top(self):
        self.show()
        self.raise_()

    def on_error(self, exc_info):
        e = exc_info[1]
        if isinstance(e, UserCancelled):
            pass
        elif isinstance(e, UserFacingException):
            self.show_error(str(e))
        else:
            try:
                traceback.print_exception(*exc_info)
            except OSError:
                pass  # see #4418
            self.show_error(str(e))

    def on_network(self, event, *args):
        if event == 'wallet_updated':
            wallet = args[0]
            if wallet == self.wallet:
                self.need_update.set()
        elif event == 'network_updated':
            # TODO: hella stupid move to the right place when I find it
            if self.wallet.network and self.wallet.network.is_connected() \
                    and len(self.wallet.get_addresses()) > 0: # and self.assets_inited is None:
                #self.assets_inited = True
                #self.update_assets()
                pass
            self.gui_object.network_updated_signal_obj.network_updated_signal \
                .emit(event, args)
            self.network_signal.emit('status', None)
            
        elif event == 'blockchain_updated':
            # to update number of confirmations in history
            self.need_update.set()
        elif event == 'new_transaction':
            wallet, tx = args
            if wallet == self.wallet:
                self.tx_notification_queue.put(tx)
        elif event in ['status', 'banner', 'verified', 'fee', 'fee_histogram']:
            # Handle in GUI thread
            self.network_signal.emit(event, args)
        else:
            self.print_error("unexpected network message:", event, args)

    def on_network_qt(self, event, args=None):
        # Handle a network message in the GUI thread
        if event == 'status':
            self.update_status()
        elif event == 'banner':
            self.console.showMessage(args[0])
        elif event == 'verified':
            wallet, tx_hash, tx_mined_status = args
            if wallet == self.wallet:
                self.history_model.update_tx_mined_status(tx_hash, tx_mined_status)
        elif event == 'fee':
            if self.config.is_dynfee():
                self.fee_slider.update()
                self.do_update_fee('send')
                self.fee_slider.update()
                self.do_update_fee('conversion')
        elif event == 'fee_histogram':
            if self.config.is_dynfee():
                self.fee_slider.update()
                self.do_update_fee('send')
                self.fee_slider.update()
                self.do_update_fee('conversion')
            self.history_model.on_fee_histogram()
        else:
            self.print_error("unexpected network_qt signal:", event, args)

    def fetch_alias(self):
        self.alias_info = None
        alias = self.config.get('alias')
        if alias:
            alias = str(alias)
            def f():
                self.alias_info = self.contacts.resolve_openalias(alias)
                self.alias_received_signal.emit()
            t = threading.Thread(target=f)
            t.setDaemon(True)
            t.start()

    def close_wallet(self):
        if self.wallet:
            self.print_error('close_wallet', self.wallet.storage.path)
        run_hook('close_wallet', self.wallet)

    @profiler
    def load_wallet(self, wallet):
        wallet.thread = TaskThread(self, self.on_error)
        ###john
        self.masternode_manager.set_wallet(self.wallet)
        self.client = Client(self.wallet)
        self.client.payaccount_load()
        self.get_account_combo()
        
        self.update_recently_visited(wallet.storage.path)
        self.need_update.set()
        # Once GUI has been initialized check if we want to announce something since the callback has been called before the GUI was initialized
        # update menus
        self.seed_menu.setEnabled(self.wallet.has_seed())
        self.update_lock_icon()
        self.update_buttons_on_seed()
        self.update_console()
        self.clear_receive_tab()
        self.request_list.update()
        self.tabs.show()
        self.init_geometry()
        if self.config.get('hide_gui') and self.gui_object.tray.isVisible():
            self.hide()
        else:
            self.show()
        self.watching_only_changed()
        run_hook('load_wallet', wallet, self)
        try:
            wallet.try_detecting_internal_addresses_corruption()
        except InternalAddressCorruption as e:
            self.show_error(str(e))
            send_exception_to_crash_reporter(e)

    def init_geometry(self):
        winpos = self.wallet.storage.get("winpos-qt")
        try:
            screen = self.app.desktop().screenGeometry()
            assert screen.contains(QRect(*winpos))
            self.setGeometry(*winpos)
        except:
            self.print_error("using default geometry")
            self.setGeometry(100, 100, 840, 400)

    def watching_only_changed(self):
        name = "Electrum Testnet" if constants.net.TESTNET else "Electrum"
        title = '%s %s  -  %s' % (name, ELECTRUM_VERSION,
                                        self.wallet.basename())
        extra = [self.wallet.storage.get('wallet_type', '?')]
        if self.wallet.is_watching_only():
            extra.append(_('watching only'))
        title += '  [%s]'% ', '.join(extra)
        self.setWindowTitle(title)
        self.password_menu.setEnabled(self.wallet.may_have_password())
        self.import_privkey_menu.setVisible(self.wallet.can_import_privkey())
        self.import_address_menu.setVisible(self.wallet.can_import_address())
        self.export_menu.setEnabled(self.wallet.can_export())

    def warn_if_watching_only(self):
        if self.wallet.is_watching_only():
            msg = ' '.join([
                _("This wallet is watching-only."),
                _("This means you will not be able to spend Bitcoins with it."),
                _("Make sure you own the seed phrase or the private keys, before you request Bitcoins to be sent to this wallet.")
            ])
            self.show_warning(msg, title=_('Watch-only wallet'))

    def warn_if_testnet(self):
        if not constants.net.TESTNET:
            return
        # user might have opted out already
        if self.config.get('dont_show_testnet_warning', False):
            return
        # only show once per process lifecycle
        if getattr(self.gui_object, '_warned_testnet', False):
            return
        self.gui_object._warned_testnet = True
        msg = ''.join([
            _("You are in testnet mode."), ' ',
            _("Testnet coins are worthless."), '\n',
            _("Testnet is separate from the main Bitcoin network. It is used for testing.")
        ])
        cb = QCheckBox(_("Don't show this again."))
        cb_checked = False
        def on_cb(x):
            nonlocal cb_checked
            cb_checked = x == Qt.Checked
        cb.stateChanged.connect(on_cb)
        self.show_warning(msg, title=_('Testnet'), checkbox=cb)
        if cb_checked:
            self.config.set_key('dont_show_testnet_warning', True)

    def open_wallet(self):
        try:
            wallet_folder = self.get_wallet_folder()
        except FileNotFoundError as e:
            self.show_error(str(e))
            return
        filename, __ = QFileDialog.getOpenFileName(self, "Select your wallet file", wallet_folder)
        if not filename:
            return
        self.gui_object.new_window(filename)

    def backup_wallet(self):
        path = self.wallet.storage.path
        wallet_folder = os.path.dirname(path)
        filename, __ = QFileDialog.getSaveFileName(self, _('Enter a filename for the copy of your wallet'), wallet_folder)
        if not filename:
            return
        new_path = os.path.join(wallet_folder, filename)
        if new_path != path:
            try:
                shutil.copy2(path, new_path)
                self.show_message(_("A copy of your wallet file was created in")+" '%s'" % str(new_path), title=_("Wallet backup created"))
            except BaseException as reason:
                self.show_critical(_("Electrum was unable to copy your wallet file to the specified location.") + "\n" + str(reason), title=_("Unable to create backup"))

    def update_recently_visited(self, filename):
        recent = self.config.get('recently_open', [])
        try:
            sorted(recent)
        except:
            recent = []
        if filename in recent:
            recent.remove(filename)
        recent.insert(0, filename)
        recent = [path for path in recent if os.path.exists(path)]
        recent = recent[:5]
        self.config.set_key('recently_open', recent)
        self.recently_visited_menu.clear()
        for i, k in enumerate(sorted(recent)):
            b = os.path.basename(k)
            def loader(k):
                return lambda: self.gui_object.new_window(k)
            self.recently_visited_menu.addAction(b, loader(k)).setShortcut(QKeySequence("Ctrl+%d"%(i+1)))
        self.recently_visited_menu.setEnabled(len(recent))

    def get_wallet_folder(self):
        return os.path.dirname(os.path.abspath(self.config.get_wallet_path()))

    def new_wallet(self):
        try:
            wallet_folder = self.get_wallet_folder()
        except FileNotFoundError as e:
            self.show_error(str(e))
            return
        filename = get_new_wallet_name(wallet_folder)
        full_path = os.path.join(wallet_folder, filename)
        self.gui_object.start_new_window(full_path, None)

    def init_menubar(self):
        menubar = QMenuBar()

        file_menu = menubar.addMenu(_("&File"))
        self.recently_visited_menu = file_menu.addMenu(_("&Recently open"))
        file_menu.addAction(_("&Open"), self.open_wallet).setShortcut(QKeySequence.Open)
        file_menu.addAction(_("&New/Restore"), self.new_wallet).setShortcut(QKeySequence.New)
        file_menu.addAction(_("&Save backup"), self.backup_wallet).setShortcut(QKeySequence.SaveAs)
        file_menu.addAction(_("Delete"), self.remove_wallet)
        file_menu.addSeparator()
        file_menu.addAction(_("&Quit"), self.close)

        wallet_menu = menubar.addMenu(_("&Wallet"))
        wallet_menu.addAction(_("&Information"), self.show_master_public_keys)
        wallet_menu.addSeparator()
        self.password_menu = wallet_menu.addAction(_("&Password"), self.change_password_dialog)
        self.seed_menu = wallet_menu.addAction(_("&Seed"), self.show_seed_dialog)
        self.private_keys_menu = wallet_menu.addMenu(_("&Private keys"))
        self.private_keys_menu.addAction(_("&Sweep"), self.sweep_key_dialog)
        self.import_privkey_menu = self.private_keys_menu.addAction(_("&Import"), self.do_import_privkey)
        self.export_menu = self.private_keys_menu.addAction(_("&Export"), self.export_privkeys_dialog)
        self.import_address_menu = wallet_menu.addAction(_("Import addresses"), self.import_addresses)
        wallet_menu.addSeparator()

        addresses_menu = wallet_menu.addMenu(_("&Addresses"))
        addresses_menu.addAction(_("&Filter"), lambda: self.address_list.toggle_toolbar(self.config))
        labels_menu = wallet_menu.addMenu(_("&Labels"))
        labels_menu.addAction(_("&Import"), self.do_import_labels)
        labels_menu.addAction(_("&Export"), self.do_export_labels)
        history_menu = wallet_menu.addMenu(_("&History"))
        history_menu.addAction(_("&Filter"), lambda: self.history_list.toggle_toolbar(self.config))
        history_menu.addAction(_("&Summary"), self.history_list.show_summary)
        history_menu.addAction(_("&Plot"), self.history_list.plot_history_dialog)
        history_menu.addAction(_("&Export"), self.history_list.export_history_dialog)
        contacts_menu = wallet_menu.addMenu(_("Contacts"))
        contacts_menu.addAction(_("&New"), self.new_contact_dialog)
        contacts_menu.addAction(_("Import"), lambda: self.contact_list.import_contacts())
        contacts_menu.addAction(_("Export"), lambda: self.contact_list.export_contacts())
        invoices_menu = wallet_menu.addMenu(_("Invoices"))
        invoices_menu.addAction(_("Import"), lambda: self.invoice_list.import_invoices())
        invoices_menu.addAction(_("Export"), lambda: self.invoice_list.export_invoices())

        wallet_menu.addSeparator()
        wallet_menu.addAction(_("Find"), self.toggle_search).setShortcut(QKeySequence("Ctrl+F"))

        def add_toggle_action(view_menu, tab):
            is_shown = self.config.get('show_{}_tab'.format(tab.tab_name), False)
            item_name = (_("Hide") if is_shown else _("Show")) + " " + tab.tab_description
            tab.menu_action = view_menu.addAction(item_name, lambda: self.toggle_tab(tab))

        view_menu = menubar.addMenu(_("&View"))
        add_toggle_action(view_menu, self.addresses_tab)
        add_toggle_action(view_menu, self.utxo_tab)
        add_toggle_action(view_menu, self.contacts_tab)
        add_toggle_action(view_menu, self.console_tab)
        ###john
        add_toggle_action(view_menu, self.masternode_tab)
        add_toggle_action(view_menu, self.conversion_tab)

        tools_menu = menubar.addMenu(_("&Tools"))

        # Settings / Preferences are all reserved keywords in macOS using this as work around
        tools_menu.addAction(_("Electrum preferences") if sys.platform == 'darwin' else _("Preferences"), self.settings_dialog)
        tools_menu.addAction(_("&Network"), lambda: self.gui_object.show_network_dialog(self))
        tools_menu.addAction(_("&Plugins"), self.plugins_dialog)
        tools_menu.addSeparator()
        tools_menu.addAction(_("&Sign/verify message"), self.sign_verify_message)
        tools_menu.addAction(_("&Encrypt/decrypt message"), self.encrypt_message)
        tools_menu.addSeparator()

        paytomany_menu = tools_menu.addAction(_("&Pay to many"), self.paytomany)

        raw_transaction_menu = tools_menu.addMenu(_("&Load transaction"))
        raw_transaction_menu.addAction(_("&From file"), self.do_process_from_file)
        raw_transaction_menu.addAction(_("&From text"), self.do_process_from_text)
        raw_transaction_menu.addAction(_("&From the blockchain"), self.do_process_from_txid)
        raw_transaction_menu.addAction(_("&From QR code"), self.read_tx_from_qrcode)
        self.raw_transaction_menu = raw_transaction_menu
        run_hook('init_menubar_tools', self, tools_menu)

        help_menu = menubar.addMenu(_("&Help"))
        help_menu.addAction(_("&About"), self.show_about)
        help_menu.addAction(_("&Check for updates"), self.show_update_check)
        help_menu.addAction(_("&Official website"), lambda: webbrowser.open("http://www.90qkl.cn"))
        #help_menu.addSeparator()
        #help_menu.addAction(_("&Documentation"), lambda: webbrowser.open("http://docs.electrum.org/")).setShortcut(QKeySequence.HelpContents)
        #help_menu.addAction(_("&Report Bug"), self.show_report_bug)
        #help_menu.addSeparator()
        #help_menu.addAction(_("&Donate to server"), self.donate_to_server)

        self.setMenuBar(menubar)

    def donate_to_server(self):
        d = self.network.get_donation_address()
        if d:
            host = self.network.get_parameters().host
            self.pay_to_URI(ADDRESS_PREFIX + '%s?message=donation for %s'%(d, host))
        else:
            self.show_error(_('No donation address for this server'))

    def show_about(self):
        QMessageBox.about(self, "Electrum",
                          (_("Version")+" %s" % ELECTRUM_VERSION + "\n\n" +
                           _("Electrum's focus is speed, with low resource usage and simplifying Syscoin.") + " " +
                           _("You do not need to perform regular backups, because your wallet can be "
                              "recovered from a secret phrase that you can memorize or write on paper.") + " " +
                           _("Startup times are instant because it operates in conjunction with high-performance "
                              "servers that handle the most complicated parts of the Syscoin system.") + "\n\n" +
                           _("Uses icons from the Icons8 icon pack (icons8.com).")))

    def show_update_check(self, version=None):
        self.gui_object._update_check = UpdateCheck(self, version)

    def show_report_bug(self):
        msg = ' '.join([
            _("Please report any bugs as issues on github:<br/>"),
            "<a href=\"https://github.com/spesmilo/electrum/issues\">https://github.com/spesmilo/electrum/issues</a><br/><br/>",
            _("Before reporting a bug, upgrade to the most recent version of Electrum (latest release or git HEAD), and include the version number in your report."),
            _("Try to explain not only what the bug is, but how it occurs.")
         ])
        self.show_message(msg, title="Electrum - " + _("Reporting Bugs"), rich_text=True)

    def notify_transactions(self):
        if self.tx_notification_queue.qsize() == 0:
            return
        if not self.wallet.up_to_date:
            return  # no notifications while syncing
        now = time.time()
        rate_limit = 20  # seconds
        if self.tx_notification_last_time + rate_limit > now:
            return
        self.tx_notification_last_time = now
        self.print_error("Notifying GUI about new transactions")
        txns = []
        while True:
            try:
                txns.append(self.tx_notification_queue.get_nowait())
            except queue.Empty:
                break
        # Combine the transactions if there are at least three
        if len(txns) >= 3:
            total_amount = 0
            for tx in txns:
                is_relevant, is_mine, v, fee = self.wallet.get_wallet_delta(tx)
                if not is_relevant:
                    continue
                total_amount += v
            self.notify(_("{} new transactions: Total amount received in the new transactions {}")
                        .format(len(txns), self.format_amount_and_units(total_amount)))
        else:
            for tx in txns:
                is_relevant, is_mine, v, fee = self.wallet.get_wallet_delta(tx)
                if not is_relevant:
                    continue
                self.notify(_("New transaction: {}").format(self.format_amount_and_units(v)))

    def notify(self, message):
        if self.tray:
            try:
                # this requires Qt 5.9
                self.tray.showMessage("Electrum", message, read_QIcon("electrum_dark_icon"), 20000)
            except TypeError:
                self.tray.showMessage("Electrum", message, QSystemTrayIcon.Information, 20000)



    # custom wrappers for getOpenFileName and getSaveFileName, that remember the path selected by the user
    def getOpenFileName(self, title, filter = ""):
        directory = self.config.get('io_dir', os.path.expanduser('~'))
        fileName, __ = QFileDialog.getOpenFileName(self, title, directory, filter)
        if fileName and directory != os.path.dirname(fileName):
            self.config.set_key('io_dir', os.path.dirname(fileName), True)
        return fileName

    def getSaveFileName(self, title, filename, filter = ""):
        directory = self.config.get('io_dir', os.path.expanduser('~'))
        path = os.path.join( directory, filename )
        fileName, __ = QFileDialog.getSaveFileName(self, title, path, filter)
        if fileName and directory != os.path.dirname(fileName):
            self.config.set_key('io_dir', os.path.dirname(fileName), True)
        return fileName

    def timer_actions(self):
        # Note this runs in the GUI thread
        if self.need_update.is_set():
            self.need_update.clear()
            self.update_wallet()
        elif not self.wallet.up_to_date:
            # this updates "synchronizing" progress
            self.update_status()
        # resolve aliases
        # FIXME this is a blocking network call that has a timeout of 5 sec
        self.payto_e.resolve()
        # update fee
        if self.require_fee_update:
            self.do_update_fee('send')
            self.do_update_fee('conversion')
            self.require_fee_update = False
        self.notify_transactions()
        if self.aggregation_button.text() == _('Stop aggregation'):
            self.aggregation_timer_actions()
    
    ###john               
    def do_aggregation(self):
        msg=[]        
        if self.aggregation_button.text() == _('Stop aggregation'):
            reply = QMessageBox.question(self, _('Aggregation'), _("Are you sure you want to stop aggregation?"), QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.No:
                return
            
            self.aggregation_button.setText(_('Start aggregation'))
            self.aggregation_nums = 0
            self.aggregation_password = None
        else:
            reply = QMessageBox.question(self, _('Message'), _("Are you sure you want to start aggregation?"), QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.No:
                return
            self.aggregation_start()
    
    def aggregation_timer_actions(self):
        self.aggregation_nums += 1
        if (self.aggregation_nums % constants.AGGREGATION_INTERVAL_TIME) == 0:
            #self.show_message("aggregation")
            aggregation_height = self.wallet.storage.get('aggregation_height')
            amount = 0
            nums = 0
            coins = self.wallet.get_spendable_coins(None, self.config)
            coins.sort(key=lambda k: (k.get('height', 0)))
            acoins = []
            for coin in coins:
                baggregation = True
                if not aggregation_height is None:
                    if  coin['height'] < aggregation_height:
                        baggregation = False
                if coin['value'] < constants.AGGREGATION_MIN_COIN * bitcoin.COIN and baggregation:
                    amount += coin['value']
                    acoins.append(coin)
                    nums += 1
                    if nums >= constants.AGGREGATION_MAX_INPUTS:
                        self.send_aggregation(acoins)
                        return
                    if amount >= constants.AGGREGATION_MAX_COIN * bitcoin.COIN:
                        self.send_aggregation(acoins)
                        return 
            self.aggregation_finish()
                
    def send_aggregation(self, acoins):
        self.do_send(mode='send', acoins = acoins)    
    
    def aggregation_finish(self):
        self.aggregation_password = None
        self.aggregation_nums = 0
        self.aggregation_button.setText(_('Start aggregation'))
        self.show_message(_('Aggregation finish!'), title=_('Info'))                
    
    def parse_script(self, x):
        script = ''
        for word in x.split():
            if word[0:3] == 'OP_':
                opcode_int = opcodes[word]
                assert opcode_int < 256  # opcode is single-byte
                script += bitcoin.int_to_hex(opcode_int)
            else:
                bfh(word)  # to test it is hex data
                script += push_script(word)
        return script

    def parse_address(self, line):
        r = line.strip()
        m = re.match('^'+RE_ALIAS+'$', r)
        address = str(m.group(2) if m else r)
        assert bitcoin.is_address(address)
        return address    

    def format_amount(self, x, is_diff=False, whitespaces=False):
        return format_satoshis(x, self.num_zeros, self.decimal_point, is_diff=is_diff, whitespaces=whitespaces)

    def format_amount_and_units(self, amount):
        text = self.format_amount(amount) + ' '+ self.base_unit()
        x = self.fx.format_amount_and_units(amount) if self.fx else None
        if text and x:
            text += ' (%s)'%x
        return text

    def format_fee_rate(self, fee_rate):
        # fee_rate is in sat/kB
        return format_fee_satoshis(fee_rate/1000, num_zeros=self.num_zeros) + ' sat/byte'

    def get_decimal_point(self):
        return self.decimal_point

    def base_unit(self):
        return decimal_point_to_base_unit_name(self.decimal_point)

    def connect_fields(self, window, btc_e, fiat_e, fee_e):

        def edit_changed(edit):
            if edit.follows:
                return
            edit.setStyleSheet(ColorScheme.DEFAULT.as_stylesheet())
            fiat_e.is_last_edited = (edit == fiat_e)
            amount = edit.get_amount()
            rate = self.fx.exchange_rate() if self.fx else Decimal('NaN')
            if rate.is_nan() or amount is None:
                if edit is fiat_e:
                    btc_e.setText("")
                    if fee_e:
                        fee_e.setText("")
                else:
                    fiat_e.setText("")
            else:
                if edit is fiat_e:
                    btc_e.follows = True
                    btc_e.setAmount(int(amount / Decimal(rate) * COIN))
                    btc_e.setStyleSheet(ColorScheme.BLUE.as_stylesheet())
                    btc_e.follows = False
                    if fee_e:
                        window.update_fee()
                else:
                    fiat_e.follows = True
                    fiat_e.setText(self.fx.ccy_amount_str(
                        amount * Decimal(rate) / COIN, False))
                    fiat_e.setStyleSheet(ColorScheme.BLUE.as_stylesheet())
                    fiat_e.follows = False

        btc_e.follows = False
        fiat_e.follows = False
        fiat_e.textChanged.connect(partial(edit_changed, fiat_e))
        btc_e.textChanged.connect(partial(edit_changed, btc_e))
        fiat_e.is_last_edited = False

    def update_status(self):
        if not self.wallet:
            return

        if self.network is None:
            text = _("Offline")
            icon = read_QIcon("status_disconnected.png")

        elif self.network.is_connected():
            ###john
            #self.masternode_manager.send_subscriptions()
            self.masternode_manager.update_masternodes_status()
            
            server_height = self.network.get_server_height()
            server_lag = self.network.get_local_height() - server_height
            fork_str = "_fork" if len(self.network.get_blockchains())>1 else ""
            # Server height can be 0 after switching to a new server
            # until we get a headers subscription request response.
            # Display the synchronizing message in that case.
            if not self.wallet.up_to_date or server_height == 0:
                text = _("Synchronizing...")
                icon = read_QIcon("status_waiting.png")
            elif server_lag > 1:
                text = _("Server is lagging ({} blocks)").format(server_lag)
                icon = read_QIcon("status_lagging%s.png"%fork_str)
            else:
                c, u, x = self.wallet.get_balance()
                text =  _("Balance" ) + ": %s "%(self.format_amount_and_units(c))
                if u:
                    text +=  " [%s "%(self.format_amount(u, is_diff=True).strip())
                    text += _('unconfirmed') + "]"
                if x:
                    text +=  " [%s "%(self.format_amount(x, is_diff=True).strip())
                    text +=  _('unmatured') + "]"
                    
                if self.client.money_ratio > 0:
                    text +=  " [" + _('Convertible proportion') + ":"
                    text +=  "%f "%(self.client.money_ratio) + "]"
                
                # append fiat balance and price
                if self.fx.is_enabled():
                    text += self.fx.get_fiat_status_text(c + u + x,
                        self.base_unit(), self.get_decimal_point()) or ''
                if not self.network.proxy:
                    icon = read_QIcon("status_connected%s.png"%fork_str)
                else:
                    icon = read_QIcon("status_connected_proxy%s.png"%fork_str)
        else:
            if self.network.proxy:
                text = "{} ({})".format(_("Not connected"), _("proxy enabled"))
            else:
                text = _("Not connected")
            icon = read_QIcon("status_disconnected.png")

        self.tray.setToolTip("%s (%s)" % (text, self.wallet.basename()))
        self.balance_label.setText(text)
        self.status_button.setIcon( icon )

    def update_wallet(self):
        self.update_status()
        if self.wallet.up_to_date or not self.network or not self.network.is_connected():
            self.update_tabs()

    def update_tabs(self, wallet=None):
        if wallet is None:
            wallet = self.wallet
        if wallet != self.wallet:
            return
        self.history_model.refresh('update_tabs')
        self.request_list.update()
        self.address_list.update()
        self.utxo_list.update()
        self.contact_list.update()
        self.invoice_list.update()
        
        ###john
        self.masternode_list.update()
        
        self.update_completions()

    def create_history_tab(self):
        self.history_model = HistoryModel(self)
        self.history_list = l = HistoryList(self, self.history_model)
        self.history_model.set_view(self.history_list)
        l.searchable_list = l
        toolbar = l.create_toolbar(self.config)
        toolbar_shown = self.config.get('show_toolbar_history', False)
        l.show_toolbar(toolbar_shown)
        return self.create_list_tab(l, toolbar)

    def show_address(self, addr):
        from . import address_dialog
        d = address_dialog.AddressDialog(self, addr)
        d.exec_()

    def show_transaction(self, tx, tx_desc = None):
        '''tx_desc is set only for txs created in the Send tab'''
        show_transaction(tx, self, tx_desc)

    def create_receive_tab(self):
        # A 4-column grid layout.  All the stretch is in the last column.
        # The exchange rate plugin adds a fiat widget in column 2
        self.receive_grid = grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(3, 1)

        self.receive_address_e = ButtonsLineEdit()
        self.receive_address_e.addCopyButton(self.app)
        self.receive_address_e.setReadOnly(True)
        msg = _('Bitcoin address where the payment should be received. Note that each payment request uses a different Bitcoin address.')
        self.receive_address_label = HelpLabel(_('Receiving address'), msg)
        self.receive_address_e.textChanged.connect(self.update_receive_qr)
        self.receive_address_e.textChanged.connect(self.update_receive_address_styling)
        self.receive_address_e.setFocusPolicy(Qt.ClickFocus)
        grid.addWidget(self.receive_address_label, 0, 0)
        grid.addWidget(self.receive_address_e, 0, 1, 1, -1)
                
        self.receive_message_e = QLineEdit()
        grid.addWidget(QLabel(_('Description')), 1, 0)
        grid.addWidget(self.receive_message_e, 1, 1, 1, -1)
        self.receive_message_e.textChanged.connect(self.update_receive_qr)

        self.receive_amount_e = BTCAmountEdit(self.get_decimal_point)
        grid.addWidget(QLabel(_('Requested amount')), 2, 0)
        grid.addWidget(self.receive_amount_e, 2, 1)
        self.receive_amount_e.textChanged.connect(self.update_receive_qr)

        self.fiat_receive_e = AmountEdit(self.fx.get_currency if self.fx else '')
        if not self.fx or not self.fx.is_enabled():
            self.fiat_receive_e.setVisible(False)
        grid.addWidget(self.fiat_receive_e, 2, 2, Qt.AlignLeft)
        self.connect_fields(self, self.receive_amount_e, self.fiat_receive_e, None)

        self.expires_combo = QComboBox()
        self.expires_combo.addItems([i[0] for i in expiration_values])
        self.expires_combo.setCurrentIndex(3)
        self.expires_combo.setFixedWidth(self.receive_amount_e.width())
        msg = ' '.join([
            _('Expiration date of your request.'),
            _('This information is seen by the recipient if you send them a signed payment request.'),
            _('Expired requests have to be deleted manually from your list, in order to free the corresponding Bitcoin addresses.'),
            _('The bitcoin address never expires and will always be part of this electrum wallet.'),
        ])
        grid.addWidget(HelpLabel(_('Request expires'), msg), 3, 0)
        grid.addWidget(self.expires_combo, 3, 1)
        self.expires_label = QLineEdit('')
        self.expires_label.setReadOnly(1)
        self.expires_label.setFocusPolicy(Qt.NoFocus)
        self.expires_label.hide()
        grid.addWidget(self.expires_label, 3, 1)

        self.save_request_button = QPushButton(_('Save'))
        self.save_request_button.clicked.connect(self.save_payment_request)

        self.new_request_button = QPushButton(_('New'))
        self.new_request_button.clicked.connect(self.new_payment_request)

        self.receive_qr = QRCodeWidget(fixedSize=200)
        self.receive_qr.mouseReleaseEvent = lambda x: self.toggle_qr_window()
        self.receive_qr.enterEvent = lambda x: self.app.setOverrideCursor(QCursor(Qt.PointingHandCursor))
        self.receive_qr.leaveEvent = lambda x: self.app.setOverrideCursor(QCursor(Qt.ArrowCursor))

        self.receive_buttons = buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.save_request_button)
        buttons.addWidget(self.new_request_button)
        grid.addLayout(buttons, 4, 1, 1, 2)

        self.receive_requests_label = QLabel(_('Requests'))

        from .request_list import RequestList
        self.request_list = RequestList(self)

        # layout
        vbox_g = QVBoxLayout()
        vbox_g.addLayout(grid)
        vbox_g.addStretch()

        hbox = QHBoxLayout()
        hbox.addLayout(vbox_g)
        hbox.addWidget(self.receive_qr)

        w = QWidget()
        w.searchable_list = self.request_list
        vbox = QVBoxLayout(w)
        vbox.addLayout(hbox)
        vbox.addStretch(1)
        vbox.addWidget(self.receive_requests_label)
        vbox.addWidget(self.request_list)
        vbox.setStretchFactor(self.request_list, 1000)

        return w


    def delete_payment_request(self, addr):
        self.wallet.remove_payment_request(addr, self.config)
        self.request_list.update()
        self.clear_receive_tab()

    def get_request_URI(self, addr):
        req = self.wallet.receive_requests[addr]
        message = self.wallet.labels.get(addr, '')
        amount = req['amount']
        extra_query_params = {}
        if req.get('time'):
            extra_query_params['time'] = str(int(req.get('time')))
        if req.get('exp'):
            extra_query_params['exp'] = str(int(req.get('exp')))
        if req.get('name') and req.get('sig'):
            sig = bfh(req.get('sig'))
            sig = bitcoin.base_encode(sig, base=58)
            extra_query_params['name'] = req['name']
            extra_query_params['sig'] = sig
        uri = util.create_bip21_uri(addr, amount, message, extra_query_params=extra_query_params)
        return str(uri)


    def sign_payment_request(self, addr):
        alias = self.config.get('alias')
        alias_privkey = None
        if alias and self.alias_info:
            alias_addr, alias_name, validated = self.alias_info
            if alias_addr:
                if self.wallet.is_mine(alias_addr):
                    msg = _('This payment request will be signed.') + '\n' + _('Please enter your password')
                    password = None
                    if self.wallet.has_keystore_encryption():
                        password = self.password_dialog(msg)
                        if not password:
                            return
                    try:
                        self.wallet.sign_payment_request(addr, alias, alias_addr, password)
                    except Exception as e:
                        self.show_error(str(e))
                        return
                else:
                    return

    def save_payment_request(self):
        addr = str(self.receive_address_e.text())
        amount = self.receive_amount_e.get_amount()
        message = self.receive_message_e.text()
        if not message and not amount:
            self.show_error(_('No message or amount'))
            return False
        i = self.expires_combo.currentIndex()
        expiration = list(map(lambda x: x[1], expiration_values))[i]
        req = self.wallet.make_payment_request(addr, amount, message, expiration)
        try:
            self.wallet.add_payment_request(req, self.config)
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            self.show_error(_('Error adding payment request') + ':\n' + str(e))
        else:
            self.sign_payment_request(addr)
            self.save_request_button.setEnabled(False)
        finally:
            self.request_list.update()
            self.address_list.update()

    def view_and_paste(self, title, msg, data):
        dialog = WindowModalDialog(self, title)
        vbox = QVBoxLayout()
        label = QLabel(msg)
        label.setWordWrap(True)
        vbox.addWidget(label)
        pr_e = ShowQRTextEdit(text=data)
        vbox.addWidget(pr_e)
        vbox.addLayout(Buttons(CopyCloseButton(pr_e.text, self.app, dialog)))
        dialog.setLayout(vbox)
        dialog.exec_()

    def export_payment_request(self, addr):
        r = self.wallet.receive_requests.get(addr)
        pr = paymentrequest.serialize_request(r).SerializeToString()
        name = r['id'] + '.bip70'
        fileName = self.getSaveFileName(_("Select where to save your payment request"), name, "*.bip70")
        if fileName:
            with open(fileName, "wb+") as f:
                f.write(util.to_bytes(pr))
            self.show_message(_("Request saved successfully"))
            self.saved = True

    def new_payment_request(self):
        addr = self.wallet.get_unused_address()
        if addr is None:
            if not self.wallet.is_deterministic():
                msg = [
                    _('No more addresses in your wallet.'),
                    _('You are using a non-deterministic wallet, which cannot create new addresses.'),
                    _('If you want to create new addresses, use a deterministic wallet instead.')
                   ]
                self.show_message(' '.join(msg))
                return
            if not self.question(_("Warning: The next address will not be recovered automatically if you restore your wallet from seed; you may need to add it manually.\n\nThis occurs because you have too many unused addresses in your wallet. To avoid this situation, use the existing addresses first.\n\nCreate anyway?")):
                return
            addr = self.wallet.create_new_address(False)
        self.set_receive_address(addr)
        self.expires_label.hide()
        self.expires_combo.show()
        self.new_request_button.setEnabled(False)
        self.receive_message_e.setFocus(1)

    def set_receive_address(self, addr):
        self.receive_address_e.setText(addr)
        self.receive_message_e.setText('')
        self.receive_amount_e.setAmount(None)

    def clear_receive_tab(self):
        try:
            addr = self.wallet.get_receiving_address() or ''
        except InternalAddressCorruption as e:
            self.show_error(str(e))
            addr = ''
        self.receive_address_e.setText(addr)
        self.receive_message_e.setText('')
        self.receive_amount_e.setAmount(None)
        self.expires_label.hide()
        self.expires_combo.show()

    def toggle_qr_window(self):
        from . import qrwindow
        if not self.qr_window:
            self.qr_window = qrwindow.QR_Window(self)
            self.qr_window.setVisible(True)
            self.qr_window_geometry = self.qr_window.geometry()
        else:
            if not self.qr_window.isVisible():
                self.qr_window.setVisible(True)
                self.qr_window.setGeometry(self.qr_window_geometry)
            else:
                self.qr_window_geometry = self.qr_window.geometry()
                self.qr_window.setVisible(False)
        self.update_receive_qr()

    def show_send_tab(self):
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.send_tab))

    def show_receive_tab(self):
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.receive_tab))

    def receive_at(self, addr):
        if not bitcoin.is_address(addr):
            return
        self.show_receive_tab()
        self.receive_address_e.setText(addr)
        self.new_request_button.setEnabled(True)

    def update_receive_qr(self):
        addr = str(self.receive_address_e.text())
        amount = self.receive_amount_e.get_amount()
        message = self.receive_message_e.text()
        self.save_request_button.setEnabled((amount is not None) or (message != ""))
        uri = util.create_bip21_uri(addr, amount, message)
        self.receive_qr.setData(uri)
        if self.qr_window and self.qr_window.isVisible():
            self.qr_window.qrw.setData(uri)

    def update_receive_address_styling(self):
        addr = str(self.receive_address_e.text())
        if self.wallet.is_used(addr):
            self.receive_address_e.setStyleSheet(ColorScheme.RED.as_stylesheet(True))
            self.receive_address_e.setToolTip(_("This address has already been used. "
                                                "For better privacy, do not reuse it for new payments."))
        else:
            self.receive_address_e.setStyleSheet("")
            self.receive_address_e.setToolTip("")

    def set_feerounding_text(self, num_satoshis_added):
        self.feerounding_text = (_('Additional {} satoshis are going to be added.')
                                 .format(num_satoshis_added))

    def create_send_tab(self):
        # A 4-column grid layout.  All the stretch is in the last column.
        # The exchange rate plugin adds a fiat widget in column 2
        self.send_grid = grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(3, 1)

        from .paytoedit import PayToEdit
        self.amount_e = BTCAmountEdit(self.get_decimal_point)
        self.payto_e = PayToEdit(self)
        msg = _('Recipient of the funds.') + '\n\n'\
              + _('You may enter a Bitcoin address, a label from your list of contacts (a list of completions will be proposed), or an alias (email-like address that forwards to a Bitcoin address)')
        payto_label = HelpLabel(_('Pay to'), msg)
        grid.addWidget(payto_label, 1, 0)
        grid.addWidget(self.payto_e, 1, 1, 1, -1)

        completer = QCompleter()
        completer.setCaseSensitivity(False)
        self.payto_e.set_completer(completer)
        completer.setModel(self.completions)

        msg = _('Description of the transaction (not mandatory).') + '\n\n'\
              + _('The description is not sent to the recipient of the funds. It is stored in your wallet file, and displayed in the \'History\' tab.')
        description_label = HelpLabel(_('Description'), msg)
        grid.addWidget(description_label, 2, 0)
        self.message_e = MyLineEdit()
        grid.addWidget(self.message_e, 2, 1, 1, -1)

        self.from_label = QLabel(_('From'))
        grid.addWidget(self.from_label, 3, 0)
        self.from_list = FromList(self, self.from_list_menu)
        grid.addWidget(self.from_list, 3, 1, 1, -1)
        self.set_pay_from([])

        msg = _('Amount to be sent.') + '\n\n' \
              + _('The amount will be displayed in red if you do not have enough funds in your wallet.') + ' ' \
              + _('Note that if you have frozen some of your addresses, the available funds will be lower than your total balance.') + '\n\n' \
              + _('Keyboard shortcut: type "!" to send all your coins.')
        amount_label = HelpLabel(_('Amount'), msg)
        grid.addWidget(amount_label, 4, 0)
        grid.addWidget(self.amount_e, 4, 1)

        self.fiat_send_e = AmountEdit(self.fx.get_currency if self.fx else '')
        if not self.fx or not self.fx.is_enabled():
            self.fiat_send_e.setVisible(False)
        grid.addWidget(self.fiat_send_e, 4, 2)
        self.amount_e.frozen.connect(
            lambda: self.fiat_send_e.setFrozen(self.amount_e.isReadOnly()))

        self.max_button = EnterButton(_("Max"), self.spend_max)
        self.max_button.setFixedWidth(140)
        self.max_button.setCheckable(True)
        grid.addWidget(self.max_button, 4, 3)
        hbox = QHBoxLayout()
        hbox.addStretch(1)
        grid.addLayout(hbox, 4, 4)

        msg = _('Bitcoin transactions are in general not free. A transaction fee is paid by the sender of the funds.') + '\n\n'\
              + _('The amount of fee can be decided freely by the sender. However, transactions with low fees take more time to be processed.') + '\n\n'\
              + _('A suggested fee is automatically added to this field. You may override it. The suggested fee increases with the size of the transaction.')
        self.fee_e_label = HelpLabel(_('Fee'), msg)

        def fee_cb(dyn, pos, fee_rate):
            if dyn:
                if self.config.use_mempool_fees():
                    self.config.set_key('depth_level', pos, False)
                else:
                    self.config.set_key('fee_level', pos, False)
            else:
                self.config.set_key('fee_per_kb', fee_rate, False)

            if fee_rate:
                fee_rate = Decimal(fee_rate)
                self.feerate_e.setAmount(quantize_feerate(fee_rate / 1000))
            else:
                self.feerate_e.setAmount(None)
            self.fee_e.setModified(False)

            self.fee_slider.activate()
            self.spend_max() if self.max_button.isChecked() else self.update_fee()

        self.fee_slider = FeeSlider(self, self.config, fee_cb)
        self.fee_slider.setFixedWidth(140)

        def on_fee_or_feerate(edit_changed, editing_finished):
            edit_other = self.feerate_e if edit_changed == self.fee_e else self.fee_e
            if editing_finished:
                if edit_changed.get_amount() is None:
                    # This is so that when the user blanks the fee and moves on,
                    # we go back to auto-calculate mode and put a fee back.
                    edit_changed.setModified(False)
            else:
                # edit_changed was edited just now, so make sure we will
                # freeze the correct fee setting (this)
                edit_other.setModified(False)
            self.fee_slider.deactivate()
            self.update_fee()

        class TxSizeLabel(QLabel):
            def setAmount(self, byte_size):
                self.setText(('x   %s bytes   =' % byte_size) if byte_size else '')

        self.size_e = TxSizeLabel()
        self.size_e.setAlignment(Qt.AlignCenter)
        self.size_e.setAmount(0)
        self.size_e.setFixedWidth(140)
        self.size_e.setStyleSheet(ColorScheme.DEFAULT.as_stylesheet())

        self.feerate_e = FeerateEdit(lambda: 0)
        self.feerate_e.setAmount(self.config.fee_per_byte())
        self.feerate_e.textEdited.connect(partial(on_fee_or_feerate, self.feerate_e, False))
        self.feerate_e.editingFinished.connect(partial(on_fee_or_feerate, self.feerate_e, True))

        self.fee_e = BTCAmountEdit(self.get_decimal_point)
        self.fee_e.textEdited.connect(partial(on_fee_or_feerate, self.fee_e, False))
        self.fee_e.editingFinished.connect(partial(on_fee_or_feerate, self.fee_e, True))

        def feerounding_onclick():
            text = (self.feerounding_text + '\n\n' +
                    _('To somewhat protect your privacy, Electrum tries to create change with similar precision to other outputs.') + ' ' +
                    _('At most 100 satoshis might be lost due to this rounding.') + ' ' +
                    _("You can disable this setting in '{}'.").format(_('Preferences')) + '\n' +
                    _('Also, dust is not kept as change, but added to the fee.')  + '\n' +
                    _('Also, when batching RBF transactions, BIP 125 imposes a lower bound on the fee.'))
            self.show_message(title=_('Fee rounding'), msg=text)

        self.feerounding_icon = QPushButton(read_QIcon('info.png'), '')
        self.feerounding_icon.setFixedWidth(20)
        self.feerounding_icon.setFlat(True)
        self.feerounding_icon.clicked.connect(feerounding_onclick)
        self.feerounding_icon.setVisible(False)

        self.connect_fields(self, self.amount_e, self.fiat_send_e, self.fee_e)

        vbox_feelabel = QVBoxLayout()
        vbox_feelabel.addWidget(self.fee_e_label)
        vbox_feelabel.addStretch(1)
        grid.addLayout(vbox_feelabel, 5, 0)

        self.fee_adv_controls = QWidget()
        hbox = QHBoxLayout(self.fee_adv_controls)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.addWidget(self.feerate_e)
        hbox.addWidget(self.size_e)
        hbox.addWidget(self.fee_e)
        hbox.addWidget(self.feerounding_icon, Qt.AlignLeft)
        hbox.addStretch(1)

        vbox_feecontrol = QVBoxLayout()
        vbox_feecontrol.addWidget(self.fee_adv_controls)
        vbox_feecontrol.addWidget(self.fee_slider)

        grid.addLayout(vbox_feecontrol, 5, 1, 1, -1)

        if not self.config.get('show_fee', False):
            self.fee_adv_controls.setVisible(False)

        self.preview_button = EnterParamsButton(_("Preview"), self.do_preview, True, 'send')
        self.preview_button.setToolTip(_('Display the details of your transaction before signing it.'))
        self.send_button = EnterParamsButton(_("Send"), self.do_send, False, 'send')
        self.clear_button = EnterButton(_("Clear"), self.do_clear)
        self.aggregation_button = EnterButton(_("Start aggregation"), self.do_aggregation)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.aggregation_button)
        buttons.addWidget(self.clear_button)
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.send_button)
        grid.addLayout(buttons, 6, 1, 1, 3)

        self.amount_e.shortcut.connect(self.spend_max)
        self.payto_e.textChanged.connect(self.update_fee)
        self.amount_e.textEdited.connect(self.update_fee)

        def reset_max(text):
            self.max_button.setChecked(False)
            enable = not bool(text) and not self.amount_e.isReadOnly()
            self.max_button.setEnabled(enable)
        self.amount_e.textEdited.connect(reset_max)
        self.fiat_send_e.textEdited.connect(reset_max)

        def entry_changed():
            text = ""

            amt_color = ColorScheme.DEFAULT
            fee_color = ColorScheme.DEFAULT
            feerate_color = ColorScheme.DEFAULT

            if self.not_enough_funds:
                amt_color, fee_color = ColorScheme.RED, ColorScheme.RED
                feerate_color = ColorScheme.RED
                text = _("Not enough funds")
                c, u, x = self.wallet.get_frozen_balance()
                if c+u+x:
                    text += " ({} {} {})".format(
                        self.format_amount(c + u + x).strip(), self.base_unit(), _("are frozen")
                    )

            # blue color denotes auto-filled values
            elif self.fee_e.isModified():
                feerate_color = ColorScheme.BLUE
            elif self.feerate_e.isModified():
                fee_color = ColorScheme.BLUE
            elif self.amount_e.isModified():
                fee_color = ColorScheme.BLUE
                feerate_color = ColorScheme.BLUE
            else:
                amt_color = ColorScheme.BLUE
                fee_color = ColorScheme.BLUE
                feerate_color = ColorScheme.BLUE

            self.statusBar().showMessage(text)
            self.amount_e.setStyleSheet(amt_color.as_stylesheet())
            self.fee_e.setStyleSheet(fee_color.as_stylesheet())
            self.feerate_e.setStyleSheet(feerate_color.as_stylesheet())

        self.amount_e.textChanged.connect(entry_changed)
        self.fee_e.textChanged.connect(entry_changed)
        self.feerate_e.textChanged.connect(entry_changed)

        self.invoices_label = QLabel(_('Invoices'))
        from .invoice_list import InvoiceList
        self.invoice_list = InvoiceList(self)

        vbox0 = QVBoxLayout()
        vbox0.addLayout(grid)
        hbox = QHBoxLayout()
        hbox.addLayout(vbox0)
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.addLayout(hbox)
        vbox.addStretch(1)
        vbox.addWidget(self.invoices_label)
        vbox.addWidget(self.invoice_list)
        vbox.setStretchFactor(self.invoice_list, 1000)
        w.searchable_list = self.invoice_list
        run_hook('create_send_tab', grid)
        return w

    def spend_max(self):
        if run_hook('abort_send', self):
            return
        self.max_button.setChecked(True)
        self.do_update_fee(mode='send')

    def spend_conversion_max(self):
        if run_hook('abort_send', self):
            return
        self.max_conversion_button.setChecked(True)
        self.do_update_fee(mode='conversion')

    def update_fee(self):
        self.require_fee_update = True

    def get_payto_or_dummy(self):
        r = self.payto_e.get_recipient()
        if r:
            return r
        return (TYPE_ADDRESS, self.wallet.dummy_address())

    def do_update_fee(self, mode='send'):
        '''Recalculate the fee.  If the fee was manually input, retain it, but
        still build the TX to see if there are enough funds.
        '''        
        if mode == 'send':
            size_e = self.size_e
            fee_e = self.fee_e
            feerate_e = self.feerate_e
            amount_e = self.amount_e
            max_button = self.max_button   
            feerounding_icon = self.feerounding_icon
            fee_slider = self.fee_slider
        elif mode == 'conversion':
            size_e = self.size_conversion_e
            fee_e = self.fee_conversion_e
            feerate_e = self.feerate_conversion_e
            amount_e = self.amount_conversion_e
            max_button = self.max_conversion_button
            feerounding_icon = self.feerounding_conversion_icon
            fee_slider = self.fee_conversion_slider
        
        freeze_fee = self.is_send_fee_frozen(mode)
        freeze_feerate = self.is_send_feerate_frozen(mode)
        amount = '!' if max_button.isChecked() else amount_e.get_amount()
        if amount is None:
            if not freeze_fee:
                fee_e.setAmount(None)
            self.not_enough_funds = False
            self.statusBar().showMessage('')
            return

        outputs, fee_estimator, tx_desc, coins = self.read_send_tab(mode)
        if not outputs:
            _type, addr = self.get_payto_or_dummy()
            outputs = [TxOutput(_type, addr, amount)]
        is_sweep = bool(self.tx_external_keypairs)
        make_tx = lambda fee_est: \
            self.wallet.make_unsigned_transaction(
                coins, outputs, self.config,
                fixed_fee=fee_est, is_sweep=is_sweep)
        try:
            tx = make_tx(fee_estimator)
            self.not_enough_funds = False
        except (NotEnoughFunds, NoDynamicFeeEstimates) as e:
            if not freeze_fee:
                fee_e.setAmount(None)
            if not freeze_feerate:
                feerate_e.setAmount(None)
            self.feerounding_icon.setVisible(False)

            if isinstance(e, NotEnoughFunds):
                self.not_enough_funds = True
            elif isinstance(e, NoDynamicFeeEstimates):
                try:
                    tx = make_tx(0)
                    size = tx.estimated_size()
                    size_e.setAmount(size)
                except BaseException:
                    pass
            return
        except BaseException:
            self.print_error("")
            return

        size = tx.estimated_size()
        size_e.setAmount(size)

        fee = tx.get_fee()
        fee = None if self.not_enough_funds else fee

        # Displayed fee/fee_rate values are set according to user input.
        # Due to rounding or dropping dust in CoinChooser,
        # actual fees often differ somewhat.
        if freeze_feerate or fee_slider.is_active():
            displayed_feerate = feerate_e.get_amount()
            if displayed_feerate is not None:
                displayed_feerate = quantize_feerate(displayed_feerate)
            else:
                # fallback to actual fee
                displayed_feerate = quantize_feerate(fee / size) if fee is not None else None
                feerate_e.setAmount(displayed_feerate)
            displayed_fee = round(displayed_feerate * size) if displayed_feerate is not None else None
            fee_e.setAmount(displayed_fee)
        else:
            if freeze_fee:
                displayed_fee = fee_e.get_amount()
            else:
                # fallback to actual fee if nothing is frozen
                displayed_fee = fee
                fee_e.setAmount(displayed_fee)
            displayed_fee = displayed_fee if displayed_fee else 0
            displayed_feerate = quantize_feerate(displayed_fee / size) if displayed_fee is not None else None
            feerate_e.setAmount(displayed_feerate)

        # show/hide fee rounding icon
        feerounding = (fee - displayed_fee) if fee else 0
        self.set_feerounding_text(int(feerounding))
        feerounding_icon.setToolTip(self.feerounding_text)
        feerounding_icon.setVisible(abs(feerounding) >= 1)
        
        if max_button.isChecked():
            amount = tx.output_value()
            __, x_fee_amount = run_hook('get_tx_extra_fee', self.wallet, tx) or (None, 0)
            amount_after_all_fees = amount - x_fee_amount
            amount_e.setAmount(amount_after_all_fees)
            if mode == 'conversion':
                amounts = round((amount_after_all_fees * self.client.money_ratio)/bitcoin.COIN, 2)
                self.estimation_e.setText(str(amounts))
            

    def from_list_delete(self, item):
        i = self.from_list.indexOfTopLevelItem(item)
        self.pay_from.pop(i)
        self.redraw_from_list()
        self.update_fee()

    def from_list_menu(self, position):
        item = self.from_list.itemAt(position)
        menu = QMenu()
        menu.addAction(_("Remove"), lambda: self.from_list_delete(item))
        menu.exec_(self.from_list.viewport().mapToGlobal(position))

    def set_pay_from(self, coins):
        self.pay_from = list(coins)
        self.redraw_from_list()

    def redraw_from_list(self):
        self.from_list.clear()
        self.from_label.setHidden(len(self.pay_from) == 0)
        self.from_list.setHidden(len(self.pay_from) == 0)

        def format(x):
            h = x.get('prevout_hash')
            return h[0:10] + '...' + h[-10:] + ":%d"%x.get('prevout_n') + u'\t' + "%s"%x.get('address')

        for item in self.pay_from:
            self.from_list.addTopLevelItem(QTreeWidgetItem( [format(item), self.format_amount(item['value']) ]))

    def get_contact_payto(self, key):
        _type, label = self.contacts.get(key)
        return label + '  <' + key + '>' if _type == 'address' else key

    def update_completions(self):
        l = [self.get_contact_payto(key) for key in self.contacts.keys()]
        self.completions.setStringList(l)

    def protected(func):
        '''Password request wrapper.  The password is passed to the function
        as the 'password' named argument.  "None" indicates either an
        unencrypted wallet, or the user cancelled the password request.
        An empty input is passed as the empty string.'''
        def request_password(self, *args, **kwargs):
            parent = self.top_level_window()
            password = None
            while self.wallet.has_keystore_encryption():
                password = self.password_dialog(parent=parent)
                if password is None:
                    # User cancelled password input
                    return
                try:
                    self.wallet.check_password(password)
                    break
                except Exception as e:
                    self.show_error(str(e), parent=parent)
                    continue

            kwargs['password'] = password
            return func(self, *args, **kwargs)
        return request_password

    def is_send_fee_frozen(self, mode='send'):
        if mode == 'send':
            fee_e = self.fee_e
        elif mode == 'conversion':
            fee_e = self.fee_conversion_e
            
        return fee_e.isVisible() and fee_e.isModified() \
               and (fee_e.text() or fee_e.hasFocus())
            
    def is_send_feerate_frozen(self, mode='send'):
        if mode == 'send':
            feerate_e = self.feerate_e
        elif mode == 'conversion':
            feerate_e = self.feerate_conversion_e        
            
        return feerate_e.isVisible() and feerate_e.isModified() \
               and (feerate_e.text() or feerate_e.hasFocus())

    def get_send_fee_estimator(self, mode='send'):
        if mode == 'send':
            fee_e = self.fee_e
            feerate_e = self.feerate_e        
        elif mode == 'conversion':
            fee_e = self.fee_conversion_e
            feerate_e = self.feerate_conversion_e        
        
        if self.is_send_fee_frozen(mode):
            fee_estimator = fee_e.get_amount()
        elif self.is_send_feerate_frozen(mode):
            amount = feerate_e.get_amount()  # sat/byte feerate
            amount = 0 if amount is None else amount * 1000  # sat/kilobyte feerate
            fee_estimator = partial(
                simple_config.SimpleConfig.estimate_fee_for_feerate, amount)
        else:
            fee_estimator = None
        return fee_estimator

    def read_send_tab(self, mode='send'):
        if mode == 'send':
            max_button = self.max_button        
            label = self.message_e.text()

            if self.payment_request:
                outputs = self.payment_request.get_outputs()
            else:
                outputs = self.payto_e.get_outputs(max_button.isChecked())
        elif mode == 'conversion':
            max_button = self.max_conversion_button
            label = ''
            outputs = self.payee_conversion_e.get_outputs(max_button.isChecked())
            
        fee_estimator = self.get_send_fee_estimator(mode)
        coins = self.get_coins()                
        return outputs, fee_estimator, label, coins

    def check_send_tab_outputs_and_show_errors(self, outputs) -> bool:
        """Returns whether there are errors with outputs.
        Also shows error dialog to user if so.
        """
        pr = self.payment_request
        if pr:
            if pr.has_expired():
                self.show_error(_('Payment request has expired'))
                return True

        if not pr:
            errors = self.payto_e.get_errors()
            if errors:
                self.show_warning(_("Invalid Lines found:") + "\n\n" + '\n'.join([ _("Line #") + str(x[0]+1) + ": " + x[1] for x in errors]))
                return True

            if self.payto_e.is_alias and self.payto_e.validated is False:
                alias = self.payto_e.toPlainText()
                msg = _('WARNING: the alias "{}" could not be validated via an additional '
                        'security check, DNSSEC, and thus may not be correct.').format(alias) + '\n'
                msg += _('Do you wish to continue?')
                if not self.question(msg):
                    return True

        if not outputs:
            self.show_error(_('No outputs'))
            return True

        for o in outputs:
            if o.address is None:
                self.show_error(_('Bitcoin Address is None'))
                return True
            if o.type == TYPE_ADDRESS and not bitcoin.is_address(o.address):
                self.show_error(_('Invalid Bitcoin Address'))
                return True
            if o.value is None:
                self.show_error(_('Invalid Amount'))
                return True

        return False  # no errors

    def do_preview(self, preview=True, mode='send'):
        self.do_send(preview, mode= mode)

    def do_send(self, preview = False, mode = 'send', acoins = []):
        if run_hook('abort_send', self):
            return
        
        if mode == 'send':
            max_button = self.max_button
            
        elif mode == 'conversion':
            max_button = self.max_conversion_button
        
        if (mode == 'send' or mode == 'conversion') and len(acoins) == 0:
            outputs, fee_estimator, tx_desc, coins = self.read_send_tab(mode)
        else:
            if len(acoins) == 0:
                return
            
            coins = acoins
            amount = '!'
            #for coin in coins:
            #    amount += coin['value']
            
            new_address = self.wallet.create_new_address(for_change=True)
            try:
                address = self.parse_address(new_address)
                _type , addr = bitcoin.TYPE_ADDRESS, address
            except:
                script = self.parse_script(new_address)
                _type, addr = bitcoin.TYPE_SCRIPT, script
            
            outputs = [TxOutput(_type, addr, amount)]
            fee_estimator = self.get_send_fee_estimator('send')
            tx_desc = _('Aggregation')
            
        if self.check_send_tab_outputs_and_show_errors(outputs):
            return
        try:
            is_sweep = bool(self.tx_external_keypairs)
            tx = self.wallet.make_unsigned_transaction(
                coins, outputs, self.config, fixed_fee=fee_estimator,
                is_sweep=is_sweep)
        except (NotEnoughFunds, NoDynamicFeeEstimates) as e:
            self.show_message(str(e))
            return
        except InternalAddressCorruption as e:
            self.show_error(str(e))
            raise
        except BaseException as e:
            traceback.print_exc(file=sys.stdout)
            self.show_message(str(e))
            return

        amount = tx.output_value() if max_button.isChecked() else sum(map(lambda x:x[2], outputs))
        fee = tx.get_fee()

        use_rbf = self.config.get('use_rbf', USE_RBF_DEFAULT)
        if use_rbf:
            tx.set_rbf(True)

        if fee < self.wallet.relayfee() * tx.estimated_size() / 1000:
            self.show_error('\n'.join([
                _("This transaction requires a higher fee, or it will not be propagated by your current server"),
                _("Try to raise your transaction fee, or use a server with a lower relay fee.")
            ]))
            return

        if preview:
            self.show_transaction(tx, tx_desc)
            return

        if not self.network:
            self.show_error(_("You can't broadcast a transaction without a live network connection."))
            return
                
        ###john
        for in1 in tx.inputs():
            if in1['value'] == constants.COLLATERAL_COINS * bitcoin.COIN:
                reply = QMessageBox.question(self, _('Message'), _("Are you sure to spend the collateral coins of masternode?"), QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if reply == QMessageBox.Yes:
                    break
                else:
                    return
         
        # confirmation dialog
        msg = [
            _("Amount to be sent") + ": " + self.format_amount_and_units(amount),
            _("Mining fee") + ": " + self.format_amount_and_units(fee),
        ]

        x_fee = run_hook('get_tx_extra_fee', self.wallet, tx)
        if x_fee:
            x_fee_address, x_fee_amount = x_fee
            msg.append( _("Additional fees") + ": " + self.format_amount_and_units(x_fee_amount) )

        feerate_warning = simple_config.FEERATE_WARNING_HIGH_FEE
        if fee > feerate_warning * tx.estimated_size() / 1000:
            msg.append(_('Warning') + ': ' + _("The fee for this transaction seems unusually high."))
            
        if len(coins) ==0 and not (self.aggregation_password is None):
            if self.wallet.has_keystore_encryption():
                msg.append("")
                msg.append(_("Enter your password to proceed"))
                password = self.password_dialog('\n'.join(msg))
                if not password:
                    return
            else:
                msg.append(_('Proceed?'))
                password = None
                if not self.question('\n'.join(msg)):
                    return
        else:
            password = self.aggregation_password

        def sign_done(success):
            if success:
                if not tx.is_complete():
                    self.show_transaction(tx)
                    self.do_clear()
                else:
                    self.broadcast_transaction(tx, tx_desc, mode)
        self.sign_tx_with_password(tx, sign_done, password)

    @protected
    def sign_tx(self, tx, callback, password):
        self.sign_tx_with_password(tx, callback, password)

    def sign_tx_with_password(self, tx, callback, password):
        '''Sign the transaction in a separate thread.  When done, calls
        the callback with a success code of True or False.
        '''
        aaa = time.time()
        def on_success(result):
            bbb = time.time() - aaa
            self.show_message(str(bbb), title='sign time')
            callback(True)
        def on_failure(exc_info):
            self.on_error(exc_info)
            callback(False)
        on_success = run_hook('tc_sign_wrapper', self.wallet, tx, on_success, on_failure) or on_success
        if self.tx_external_keypairs:
            # can sign directly
            task = partial(Transaction.sign, tx, self.tx_external_keypairs)
        else:
            task = partial(self.wallet.sign_transaction, tx, password)
        msg = _('Signing transaction...') + '-' + str(len(tx.inputs()))
        
        WaitingDialog(self, msg, task, on_success, on_failure)

    def broadcast_transaction(self, tx, tx_desc, mode='send'):
        def broadcast_thread():
            # non-GUI thread
            pr = self.payment_request
            if pr and pr.has_expired():
                self.payment_request = None
                return False, _("Payment request has expired")
            status = False
            try:
                self.network.run_from_another_thread(self.network.broadcast_transaction(tx))
            except TxBroadcastError as e:
                msg = e.get_message_for_gui()
            except BestEffortRequestFailed as e:
                msg = repr(e)
            else:
                status, msg = True, tx.txid()
            if pr and status is True:
                self.invoices.set_paid(pr, tx.txid())
                self.invoices.save()
                self.payment_request = None
                refund_address = self.wallet.get_receiving_address()
                coro = pr.send_payment_and_receive_paymentack(str(tx), refund_address)
                fut = asyncio.run_coroutine_threadsafe(coro, self.network.asyncio_loop)
                ack_status, ack_msg = fut.result(timeout=20)
                self.print_error(f"Payment ACK: {ack_status}. Ack message: {ack_msg}")
            return status, msg

        # Capture current TL window; override might be removed on return
        parent = self.top_level_window(lambda win: isinstance(win, MessageBoxMixin))

        def broadcast_done(result):
            # GUI thread
            if result:
                status, msg = result
                if status:
                    if tx_desc is not None and tx.is_complete():
                        self.wallet.set_label(tx.txid(), tx_desc)
                    if mode == 'conversion':
                        self.conversion_list_update(tx)
                    else:
                        parent.show_message(_('Payment sent.') + '\n' + msg)
                    self.invoice_list.update()
                    self.do_clear()
                else:
                    msg = msg or ''
                    parent.show_error(msg)

        WaitingDialog(self, _('Broadcasting transaction...'),
                      broadcast_thread, broadcast_done, self.on_error)

    def query_choice(self, msg, choices):
        # Needed by QtHandler for hardware wallets
        dialog = WindowModalDialog(self.top_level_window())
        clayout = ChoicesLayout(msg, choices)
        vbox = QVBoxLayout(dialog)
        vbox.addLayout(clayout.layout())
        vbox.addLayout(Buttons(OkButton(dialog)))
        if not dialog.exec_():
            return None
        return clayout.selected_index()

    def lock_amount(self, b):
        self.amount_e.setFrozen(b)
        self.max_button.setEnabled(not b)

    def prepare_for_payment_request(self):
        self.show_send_tab()
        self.payto_e.is_pr = True
        for e in [self.payto_e, self.message_e]:
            e.setFrozen(True)
        self.lock_amount(True)
        self.payto_e.setText(_("please wait..."))
        return True

    def delete_invoice(self, key):
        self.invoices.remove(key)
        self.invoice_list.update()

    def payment_request_ok(self):
        pr = self.payment_request
        if not pr:
            return
        key = self.invoices.add(pr)
        status = self.invoices.get_status(key)
        self.invoice_list.update()
        if status == PR_PAID:
            self.show_message("invoice already paid")
            self.do_clear()
            self.payment_request = None
            return
        self.payto_e.is_pr = True
        if not pr.has_expired():
            self.payto_e.setGreen()
        else:
            self.payto_e.setExpired()
        self.payto_e.setText(pr.get_requestor())
        self.amount_e.setText(format_satoshis_plain(pr.get_amount(), self.decimal_point))
        self.message_e.setText(pr.get_memo())
        # signal to set fee
        self.amount_e.textEdited.emit("")

    def payment_request_error(self):
        pr = self.payment_request
        if not pr:
            return
        self.show_message(pr.error)
        self.payment_request = None
        self.do_clear()

    def on_pr(self, request):
        self.payment_request = request
        if self.payment_request.verify(self.contacts):
            self.payment_request_ok_signal.emit()
        else:
            self.payment_request_error_signal.emit()

    def pay_to_URI(self, URI):
        if not URI:
            return
        try:
            out = util.parse_URI(URI, self.on_pr)
        except InvalidBitcoinURI as e:
            self.show_error(_("Error parsing URI") + f":\n{e}")
            return
        self.show_send_tab()
        r = out.get('r')
        sig = out.get('sig')
        name = out.get('name')
        if r or (name and sig):
            self.prepare_for_payment_request()
            return
        address = out.get('address')
        amount = out.get('amount')
        label = out.get('label')
        message = out.get('message')
        # use label as description (not BIP21 compliant)
        if label and not message:
            message = label
        if address:
            self.payto_e.setText(address)
        if message:
            self.message_e.setText(message)
        if amount:
            self.amount_e.setAmount(amount)
            self.amount_e.textEdited.emit("")


    def do_clear(self):
        self.max_conversion_button.setChecked(False)
        self.amount_conversion_e.setText('')
        self.size_conversion_e.setText('')
        self.estimation_e.setText('')
        self.amount_conversion_e.setFrozen(False)
        
        self.max_button.setChecked(False)
        self.not_enough_funds = False
        self.payment_request = None
        self.payto_e.is_pr = False
        for e in [self.payto_e, self.message_e, self.amount_e, self.fiat_send_e,
                  self.fee_e, self.feerate_e]:
            e.setText('')
            e.setFrozen(False)
        self.fee_slider.activate()
        self.feerate_e.setAmount(self.config.fee_per_byte())
        self.size_e.setAmount(0)
        self.feerounding_icon.setVisible(False)
        self.set_pay_from([])
        self.tx_external_keypairs = {}
        self.update_status()
        run_hook('do_clear', self)

    def set_frozen_state_of_addresses(self, addrs, freeze: bool):
        self.wallet.set_frozen_state_of_addresses(addrs, freeze)
        self.address_list.update()
        self.utxo_list.update()
        self.update_fee()

    def set_frozen_state_of_coins(self, utxos, freeze: bool):
        self.wallet.set_frozen_state_of_coins(utxos, freeze)
        self.utxo_list.update()
        self.update_fee()

    def create_list_tab(self, l, toolbar=None):
        w = QWidget()
        w.searchable_list = l
        vbox = QVBoxLayout()
        w.setLayout(vbox)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        if toolbar:
            vbox.addLayout(toolbar)
        vbox.addWidget(l)
        return w

    def create_addresses_tab(self):
        from .address_list import AddressList
        self.address_list = l = AddressList(self)
        toolbar = l.create_toolbar(self.config)
        toolbar_shown = self.config.get('show_toolbar_addresses', False)
        l.show_toolbar(toolbar_shown)
        return self.create_list_tab(l, toolbar)

    def create_utxo_tab(self):
        from .utxo_list import UTXOList
        self.utxo_list = l = UTXOList(self)
        return self.create_list_tab(l)

    def create_contacts_tab(self):
        from .contact_list import ContactList
        self.contact_list = l = ContactList(self)
        return self.create_list_tab(l)

    def remove_address(self, addr):
        if self.question(_("Do you want to remove {} from your wallet?").format(addr)):
            self.wallet.delete_address(addr)
            self.need_update.set()  # history, addresses, coins
            self.clear_receive_tab()

    def get_coins(self):
        if self.pay_from:
            return self.pay_from
        else:
            return self.wallet.get_spendable_coins(None, self.config)

    def spend_coins(self, coins):
        self.set_pay_from(coins)
        self.show_send_tab()
        self.update_fee()

    def paytomany(self):
        self.show_send_tab()
        self.payto_e.paytomany()
        msg = '\n'.join([
            _('Enter a list of outputs in the \'Pay to\' field.'),
            _('One output per line.'),
            _('Format: address, amount'),
            _('You may load a CSV file using the file icon.')
        ])
        self.show_message(msg, title=_('Pay to many'))

    def payto_contacts(self, labels):
        paytos = [self.get_contact_payto(label) for label in labels]
        self.show_send_tab()
        if len(paytos) == 1:
            self.payto_e.setText(paytos[0])
            self.amount_e.setFocus()
        else:
            text = "\n".join([payto + ", 0" for payto in paytos])
            self.payto_e.setText(text)
            self.payto_e.setFocus()

    def set_contact(self, label, address):
        if not is_address(address):
            self.show_error(_('Invalid Address'))
            self.contact_list.update()  # Displays original unchanged value
            return False
        self.contacts[address] = ('address', label)
        self.contact_list.update()
        self.history_list.update()
        self.update_completions()
        return True

    def delete_contacts(self, labels):
        if not self.question(_("Remove {} from your list of contacts?")
                             .format(" + ".join(labels))):
            return
        for label in labels:
            self.contacts.pop(label)
        self.history_list.update()
        self.contact_list.update()
        self.update_completions()

    def show_invoice(self, key):
        pr = self.invoices.get(key)
        if pr is None:
            self.show_error('Cannot find payment request in wallet.')
            return
        pr.verify(self.contacts)
        self.show_pr_details(pr)

    def show_pr_details(self, pr):
        key = pr.get_id()
        d = WindowModalDialog(self, _("Invoice"))
        vbox = QVBoxLayout(d)
        grid = QGridLayout()
        grid.addWidget(QLabel(_("Requestor") + ':'), 0, 0)
        grid.addWidget(QLabel(pr.get_requestor()), 0, 1)
        grid.addWidget(QLabel(_("Amount") + ':'), 1, 0)
        outputs_str = '\n'.join(map(lambda x: self.format_amount(x[2])+ self.base_unit() + ' @ ' + x[1], pr.get_outputs()))
        grid.addWidget(QLabel(outputs_str), 1, 1)
        expires = pr.get_expiration_date()
        grid.addWidget(QLabel(_("Memo") + ':'), 2, 0)
        grid.addWidget(QLabel(pr.get_memo()), 2, 1)
        grid.addWidget(QLabel(_("Signature") + ':'), 3, 0)
        grid.addWidget(QLabel(pr.get_verify_status()), 3, 1)
        if expires:
            grid.addWidget(QLabel(_("Expires") + ':'), 4, 0)
            grid.addWidget(QLabel(format_time(expires)), 4, 1)
        vbox.addLayout(grid)
        def do_export():
            name = str(key) + '.bip70'
            fn = self.getSaveFileName(_("Save invoice to file"), name, filter="*.bip70")
            if not fn:
                return
            with open(fn, 'wb') as f:
                data = f.write(pr.raw)
            self.show_message(_('Invoice saved as' + ' ' + fn))
        exportButton = EnterButton(_('Save'), do_export)
        def do_delete():
            if self.question(_('Delete invoice?')):
                self.invoices.remove(key)
                self.history_list.update()
                self.invoice_list.update()
                d.close()
        deleteButton = EnterButton(_('Delete'), do_delete)
        vbox.addLayout(Buttons(exportButton, deleteButton, CloseButton(d)))
        d.exec_()

    def do_pay_invoice(self, key):
        pr = self.invoices.get(key)
        self.payment_request = pr
        self.prepare_for_payment_request()
        pr.error = None  # this forces verify() to re-run
        if pr.verify(self.contacts):
            self.payment_request_ok()
        else:
            self.payment_request_error()

    def create_console_tab(self):
        from .console import Console
        self.console = console = Console()
        return console

    def update_console(self):
        console = self.console
        console.history = self.config.get("console-history",[])
        console.history_index = len(console.history)

        console.updateNamespace({
            'wallet': self.wallet,
            'network': self.network,
            'plugins': self.gui_object.plugins,
            'window': self,
            'config': self.config,
            'electrum': electrum,
            'daemon': self.gui_object.daemon,
            'util': util,
            'bitcoin': bitcoin,
        })

        c = commands.Commands(self.config, self.wallet, self.network, lambda: self.console.set_json(True))
        methods = {}
        def mkfunc(f, method):
            return lambda *args: f(method, args, self.password_dialog)
        for m in dir(c):
            if m[0]=='_' or m in ['network','wallet','config']: continue
            methods[m] = mkfunc(c._run, m)

        console.updateNamespace(methods)

    def create_status_bar(self):

        sb = QStatusBar()
        sb.setFixedHeight(35)

        self.balance_label = QLabel("Loading wallet...")
        self.balance_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.balance_label.setStyleSheet("""QLabel { padding: 0 }""")
        sb.addWidget(self.balance_label)

        self.search_box = QLineEdit()
        self.search_box.textChanged.connect(self.do_search)
        self.search_box.hide()
        sb.addPermanentWidget(self.search_box)

        self.update_check_button = QPushButton("")
        self.update_check_button.setFlat(True)
        self.update_check_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.update_check_button.setIcon(read_QIcon("update.png"))
        self.update_check_button.hide()
        sb.addPermanentWidget(self.update_check_button)

        self.password_button = StatusBarButton(QIcon(), _("Password"), self.change_password_dialog )
        sb.addPermanentWidget(self.password_button)

        sb.addPermanentWidget(StatusBarButton(read_QIcon("preferences.png"), _("Preferences"), self.settings_dialog ) )
        self.seed_button = StatusBarButton(read_QIcon("seed.png"), _("Seed"), self.show_seed_dialog )
        sb.addPermanentWidget(self.seed_button)
        self.status_button = StatusBarButton(read_QIcon("status_disconnected.png"), _("Network"), lambda: self.gui_object.show_network_dialog(self))
        sb.addPermanentWidget(self.status_button)
        run_hook('create_status_bar', sb)
        self.setStatusBar(sb)

    def update_lock_icon(self):
        icon = read_QIcon("lock.png") if self.wallet.has_password() else read_QIcon("unlock.png")
        self.password_button.setIcon(icon)

    def update_buttons_on_seed(self):
        self.seed_button.setVisible(self.wallet.has_seed())
        self.password_button.setVisible(self.wallet.may_have_password())
        self.send_button.setVisible(not self.wallet.is_watching_only())

    def change_password_dialog(self):
        from electrum.storage import STO_EV_XPUB_PW
        if self.wallet.get_available_storage_encryption_version() == STO_EV_XPUB_PW:
            from .password_dialog import ChangePasswordDialogForHW
            d = ChangePasswordDialogForHW(self, self.wallet)
            ok, encrypt_file = d.run()
            if not ok:
                return

            try:
                hw_dev_pw = self.wallet.keystore.get_password_for_storage_encryption()
            except UserCancelled:
                return
            except BaseException as e:
                traceback.print_exc(file=sys.stderr)
                self.show_error(str(e))
                return
            old_password = hw_dev_pw if self.wallet.has_password() else None
            new_password = hw_dev_pw if encrypt_file else None
        else:
            from .password_dialog import ChangePasswordDialogForSW
            d = ChangePasswordDialogForSW(self, self.wallet)
            ok, old_password, new_password, encrypt_file = d.run()

        if not ok:
            return
        try:
            self.wallet.update_password(old_password, new_password, encrypt_file)
        except InvalidPassword as e:
            self.show_error(str(e))
            return
        except BaseException:
            traceback.print_exc(file=sys.stdout)
            self.show_error(_('Failed to update password'))
            return
        msg = _('Password was updated successfully') if self.wallet.has_password() else _('Password is disabled, this wallet is not protected')
        self.show_message(msg, title=_("Success"))
        self.update_lock_icon()

    def toggle_search(self):
        tab = self.tabs.currentWidget()
        #if hasattr(tab, 'searchable_list'):
        #    tab.searchable_list.toggle_toolbar()
        #return
        self.search_box.setHidden(not self.search_box.isHidden())
        if not self.search_box.isHidden():
            self.search_box.setFocus(1)
        else:
            self.do_search('')

    def do_search(self, t):
        tab = self.tabs.currentWidget()
        if hasattr(tab, 'searchable_list'):
            tab.searchable_list.filter(t)

    def new_contact_dialog(self):
        d = WindowModalDialog(self, _("New Contact"))
        vbox = QVBoxLayout(d)
        vbox.addWidget(QLabel(_('New Contact') + ':'))
        grid = QGridLayout()
        line1 = QLineEdit()
        line1.setFixedWidth(280)
        line2 = QLineEdit()
        line2.setFixedWidth(280)
        grid.addWidget(QLabel(_("Address")), 1, 0)
        grid.addWidget(line1, 1, 1)
        grid.addWidget(QLabel(_("Name")), 2, 0)
        grid.addWidget(line2, 2, 1)
        vbox.addLayout(grid)
        vbox.addLayout(Buttons(CancelButton(d), OkButton(d)))
        if d.exec_():
            self.set_contact(line2.text(), line1.text())

    def show_master_public_keys(self):
        dialog = WindowModalDialog(self, _("Wallet Information"))
        dialog.setMinimumSize(500, 100)
        mpk_list = self.wallet.get_master_public_keys()
        vbox = QVBoxLayout()
        wallet_type = self.wallet.storage.get('wallet_type', '')
        if self.wallet.is_watching_only():
            wallet_type += ' [{}]'.format(_('watching-only'))
        seed_available = _('True') if self.wallet.has_seed() else _('False')
        keystore_types = [k.get_type_text() for k in self.wallet.get_keystores()]
        grid = QGridLayout()
        basename = os.path.basename(self.wallet.storage.path)
        grid.addWidget(QLabel(_("Wallet name")+ ':'), 0, 0)
        grid.addWidget(QLabel(basename), 0, 1)
        grid.addWidget(QLabel(_("Wallet type")+ ':'), 1, 0)
        grid.addWidget(QLabel(wallet_type), 1, 1)
        grid.addWidget(QLabel(_("Script type")+ ':'), 2, 0)
        grid.addWidget(QLabel(self.wallet.txin_type), 2, 1)
        grid.addWidget(QLabel(_("Seed available") + ':'), 3, 0)
        grid.addWidget(QLabel(str(seed_available)), 3, 1)
        if len(keystore_types) <= 1:
            grid.addWidget(QLabel(_("Keystore type") + ':'), 4, 0)
            ks_type = str(keystore_types[0]) if keystore_types else _('No keystore')
            grid.addWidget(QLabel(ks_type), 4, 1)
        vbox.addLayout(grid)
        if self.wallet.is_deterministic():
            mpk_text = ShowQRTextEdit()
            ###john
            mpk_text.setMaximumHeight(150)
            mpk_text.addCopyButton(self.app)
            def show_mpk(index):
                mpk_text.setText(mpk_list[index])
            # only show the combobox in case multiple accounts are available
            if len(mpk_list) > 1:
                def label(key):
                    if isinstance(self.wallet, Multisig_Wallet):
                        return _("cosigner") + f' {key+1} ( keystore: {keystore_types[key]} )'
                    return ''
                labels = [label(i) for i in range(len(mpk_list))]
                on_click = lambda clayout: show_mpk(clayout.selected_index())
                labels_clayout = ChoicesLayout(_("Master Public Keys"), labels, on_click)
                vbox.addLayout(labels_clayout.layout())
            else:
                vbox.addWidget(QLabel(_("Master Public Key")))
            show_mpk(0)
            vbox.addWidget(mpk_text)
        vbox.addStretch(1)
        vbox.addLayout(Buttons(CloseButton(dialog)))
        dialog.setLayout(vbox)
        dialog.exec_()

    def remove_wallet(self):
        if self.question('\n'.join([
                _('Delete wallet file?'),
                "%s"%self.wallet.storage.path,
                _('If your wallet contains funds, make sure you have saved its seed.')])):
            self._delete_wallet()

    ###john
    @protected
    def aggregation_start(self, password):
        self.aggregation_password = password        
        self.aggregation_button.setText(_('Stop aggregation'))
        self.aggregation_nums = constants.AGGREGATION_INTERVAL_TIME - 2        
        

    @protected
    def _delete_wallet(self, password):
        wallet_path = self.wallet.storage.path
        basename = os.path.basename(wallet_path)
        r = self.gui_object.daemon.delete_wallet(wallet_path)
        self.close()
        if r:
            self.show_error(_("Wallet removed: {}").format(basename))
        else:
            self.show_error(_("Wallet file not found: {}").format(basename))

    @protected
    def show_seed_dialog(self, password):
        if not self.wallet.has_seed():
            self.show_message(_('This wallet has no seed'))
            return
        keystore = self.wallet.get_keystore()
        try:
            seed = keystore.get_seed(password)
            passphrase = keystore.get_passphrase(password)
        except BaseException as e:
            self.show_error(str(e))
            return
        from .seed_dialog import SeedDialog
        d = SeedDialog(self, seed, passphrase)
        d.exec_()

    def show_qrcode(self, data, title = _("QR code"), parent=None):
        if not data:
            return
        d = QRDialog(data, parent or self, title)
        d.exec_()

    @protected
    def show_private_key(self, address, password):
        if not address:
            return
        try:
            pk, redeem_script = self.wallet.export_private_key(address, password)
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            self.show_message(str(e))
            return
        xtype = bitcoin.deserialize_privkey(pk)[0]
        d = WindowModalDialog(self, _("Private key"))
        d.setMinimumSize(600, 150)
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel(_("Address") + ': ' + address))
        vbox.addWidget(QLabel(_("Script type") + ': ' + xtype))
        vbox.addWidget(QLabel(_("Private key") + ':'))
        keys_e = ShowQRTextEdit(text=pk)
        keys_e.addCopyButton(self.app)
        vbox.addWidget(keys_e)
        if redeem_script:
            vbox.addWidget(QLabel(_("Redeem Script") + ':'))
            rds_e = ShowQRTextEdit(text=redeem_script)
            rds_e.addCopyButton(self.app)
            vbox.addWidget(rds_e)
        vbox.addLayout(Buttons(CloseButton(d)))
        d.setLayout(vbox)
        d.exec_()

    msg_sign = _("Signing with an address actually means signing with the corresponding "
                "private key, and verifying with the corresponding public key. The "
                "address you have entered does not have a unique public key, so these "
                "operations cannot be performed.") + '\n\n' + \
               _('The operation is undefined. Not just in Electrum, but in general.')

    @protected
    def do_sign(self, address, message, signature, password):
        address  = address.text().strip()
        message = message.toPlainText().strip()
        if not bitcoin.is_address(address):
            self.show_message(_('Invalid Bitcoin address.'))
            return
        if self.wallet.is_watching_only():
            self.show_message(_('This is a watching-only wallet.'))
            return
        if not self.wallet.is_mine(address):
            self.show_message(_('Address not in wallet.'))
            return
        txin_type = self.wallet.get_txin_type(address)
        if txin_type not in ['p2pkh', 'p2wpkh', 'p2wpkh-p2sh']:
            self.show_message(_('Cannot sign messages with this type of address:') + \
                              ' ' + txin_type + '\n\n' + self.msg_sign)
            return
        task = partial(self.wallet.sign_message, address, message, password)

        def show_signed_message(sig):
            try:
                signature.setText(base64.b64encode(sig).decode('ascii'))
            except RuntimeError:
                # (signature) wrapped C/C++ object has been deleted
                pass

        self.wallet.thread.add(task, on_success=show_signed_message)

    def do_verify(self, address, message, signature):
        address  = address.text().strip()
        message = message.toPlainText().strip().encode('utf-8')
        if not bitcoin.is_address(address):
            self.show_message(_('Invalid Bitcoin address.'))
            return
        try:
            # This can throw on invalid base64
            sig = base64.b64decode(str(signature.toPlainText()))
            verified = ecc.verify_message_with_address(address, sig, message)
        except Exception as e:
            verified = False
        if verified:
            self.show_message(_("Signature verified"))
        else:
            self.show_error(_("Wrong signature"))

    def sign_verify_message(self, address=''):
        d = WindowModalDialog(self, _('Sign/verify Message'))
        d.setMinimumSize(610, 290)

        layout = QGridLayout(d)

        message_e = QTextEdit()
        message_e.setAcceptRichText(False)
        layout.addWidget(QLabel(_('Message')), 1, 0)
        layout.addWidget(message_e, 1, 1)
        layout.setRowStretch(2,3)

        address_e = QLineEdit()
        address_e.setText(address)
        layout.addWidget(QLabel(_('Address')), 2, 0)
        layout.addWidget(address_e, 2, 1)

        signature_e = QTextEdit()
        signature_e.setAcceptRichText(False)
        layout.addWidget(QLabel(_('Signature')), 3, 0)
        layout.addWidget(signature_e, 3, 1)
        layout.setRowStretch(3,1)

        hbox = QHBoxLayout()

        b = QPushButton(_("Sign"))
        b.clicked.connect(lambda: self.do_sign(address_e, message_e, signature_e))
        hbox.addWidget(b)

        b = QPushButton(_("Verify"))
        b.clicked.connect(lambda: self.do_verify(address_e, message_e, signature_e))
        hbox.addWidget(b)

        b = QPushButton(_("Close"))
        b.clicked.connect(d.accept)
        hbox.addWidget(b)
        layout.addLayout(hbox, 4, 1)
        d.exec_()

    @protected
    def do_decrypt(self, message_e, pubkey_e, encrypted_e, password):
        if self.wallet.is_watching_only():
            self.show_message(_('This is a watching-only wallet.'))
            return
        cyphertext = encrypted_e.toPlainText()
        task = partial(self.wallet.decrypt_message, pubkey_e.text(), cyphertext, password)

        def setText(text):
            try:
                message_e.setText(text.decode('utf-8'))
            except RuntimeError:
                # (message_e) wrapped C/C++ object has been deleted
                pass

        self.wallet.thread.add(task, on_success=setText)

    def do_encrypt(self, message_e, pubkey_e, encrypted_e):
        message = message_e.toPlainText()
        message = message.encode('utf-8')
        try:
            public_key = ecc.ECPubkey(bfh(pubkey_e.text()))
        except BaseException as e:
            traceback.print_exc(file=sys.stdout)
            self.show_warning(_('Invalid Public key'))
            return
        encrypted = public_key.encrypt_message(message)
        encrypted_e.setText(encrypted.decode('ascii'))

    def encrypt_message(self, address=''):
        d = WindowModalDialog(self, _('Encrypt/decrypt Message'))
        d.setMinimumSize(610, 490)

        layout = QGridLayout(d)

        message_e = QTextEdit()
        message_e.setAcceptRichText(False)
        layout.addWidget(QLabel(_('Message')), 1, 0)
        layout.addWidget(message_e, 1, 1)
        layout.setRowStretch(2,3)

        pubkey_e = QLineEdit()
        if address:
            pubkey = self.wallet.get_public_key(address)
            pubkey_e.setText(pubkey)
        layout.addWidget(QLabel(_('Public key')), 2, 0)
        layout.addWidget(pubkey_e, 2, 1)

        encrypted_e = QTextEdit()
        encrypted_e.setAcceptRichText(False)
        layout.addWidget(QLabel(_('Encrypted')), 3, 0)
        layout.addWidget(encrypted_e, 3, 1)
        layout.setRowStretch(3,1)

        hbox = QHBoxLayout()
        b = QPushButton(_("Encrypt"))
        b.clicked.connect(lambda: self.do_encrypt(message_e, pubkey_e, encrypted_e))
        hbox.addWidget(b)

        b = QPushButton(_("Decrypt"))
        b.clicked.connect(lambda: self.do_decrypt(message_e, pubkey_e, encrypted_e))
        hbox.addWidget(b)

        b = QPushButton(_("Close"))
        b.clicked.connect(d.accept)
        hbox.addWidget(b)

        layout.addLayout(hbox, 4, 1)
        d.exec_()

    def password_dialog(self, msg=None, parent=None):
        from .password_dialog import PasswordDialog
        parent = parent or self
        d = PasswordDialog(parent, msg)
        return d.run()
    
    def register_dialog(self, msg=None, parent=None):
        from .password_dialog import RegisterDialog
        parent = parent or self
        d = RegisterDialog(parent, msg)
        return d.run()

    def login_dialog(self, msg=None, parent=None):
        from .password_dialog import LoginDialog
        parent = parent or self
        d = LoginDialog(parent, msg)
        return d.run() 
    
    def tx_from_text(self, txt):
        from electrum.transaction import tx_from_str
        try:
            tx = tx_from_str(txt)
            return Transaction(tx)
        except BaseException as e:
            self.show_critical(_("Electrum was unable to parse your transaction") + ":\n" + str(e))
            return

    def read_tx_from_qrcode(self):
        from electrum import qrscanner
        try:
            data = qrscanner.scan_barcode(self.config.get_video_device())
        except BaseException as e:
            self.show_error(str(e))
            return
        if not data:
            return
        # if the user scanned a bitcoin URI
        if str(data).startswith(ADDRESS_PREFIX):
            self.pay_to_URI(data)
            return
        # else if the user scanned an offline signed tx
        try:
            data = bh2u(bitcoin.base_decode(data, length=None, base=43))
        except BaseException as e:
            self.show_error((_('Could not decode QR code')+':\n{}').format(repr(e)))
            return
        tx = self.tx_from_text(data)
        if not tx:
            return
        self.show_transaction(tx)

    def read_tx_from_file(self):
        fileName = self.getOpenFileName(_("Select your transaction file"), "*.txn")
        if not fileName:
            return
        try:
            with open(fileName, "r") as f:
                file_content = f.read()
        except (ValueError, IOError, os.error) as reason:
            self.show_critical(_("Electrum was unable to open your transaction file") + "\n" + str(reason), title=_("Unable to read file or no transaction found"))
            return
        return self.tx_from_text(file_content)

    def do_process_from_text(self):
        text = text_dialog(self, _('Input raw transaction'), _("Transaction:"), _("Load transaction"))
        if not text:
            return
        tx = self.tx_from_text(text)
        if tx:
            self.show_transaction(tx)

    def do_process_from_file(self):
        tx = self.read_tx_from_file()
        if tx:
            self.show_transaction(tx)

    def do_process_from_txid(self):
        from electrum import transaction
        txid, ok = QInputDialog.getText(self, _('Lookup transaction'), _('Transaction ID') + ':')
        if ok and txid:
            txid = str(txid).strip()
            try:
                raw_tx = self.network.run_from_another_thread(
                    self.network.get_transaction(txid, timeout=10))
            except Exception as e:
                self.show_message(_("Error getting transaction from network") + ":\n" + str(e))
                return
            tx = transaction.Transaction(raw_tx)
            self.show_transaction(tx)

    @protected
    def export_privkeys_dialog(self, password):
        if self.wallet.is_watching_only():
            self.show_message(_("This is a watching-only wallet"))
            return

        if isinstance(self.wallet, Multisig_Wallet):
            self.show_message(_('WARNING: This is a multi-signature wallet.') + '\n' +
                              _('It cannot be "backed up" by simply exporting these private keys.'))

        d = WindowModalDialog(self, _('Private keys'))
        d.setMinimumSize(980, 300)
        vbox = QVBoxLayout(d)

        msg = "%s\n%s\n%s" % (_("WARNING: ALL your private keys are secret."),
                              _("Exposing a single private key can compromise your entire wallet!"),
                              _("In particular, DO NOT use 'redeem private key' services proposed by third parties."))
        vbox.addWidget(QLabel(msg))

        e = QTextEdit()
        e.setReadOnly(True)
        vbox.addWidget(e)

        defaultname = 'electrum-private-keys.csv'
        select_msg = _('Select file to export your private keys to')
        hbox, filename_e, csv_button = filename_field(self, self.config, defaultname, select_msg)
        vbox.addLayout(hbox)

        b = OkButton(d, _('Export'))
        b.setEnabled(False)
        vbox.addLayout(Buttons(CancelButton(d), b))

        private_keys = {}
        addresses = self.wallet.get_addresses()
        done = False
        cancelled = False
        def privkeys_thread():
            for addr in addresses:
                time.sleep(0.1)
                if done or cancelled:
                    break
                privkey = self.wallet.export_private_key(addr, password)[0]
                private_keys[addr] = privkey
                self.computing_privkeys_signal.emit()
            if not cancelled:
                self.computing_privkeys_signal.disconnect()
                self.show_privkeys_signal.emit()

        def show_privkeys():
            s = "\n".join( map( lambda x: x[0] + "\t"+ x[1], private_keys.items()))
            e.setText(s)
            b.setEnabled(True)
            self.show_privkeys_signal.disconnect()
            nonlocal done
            done = True

        def on_dialog_closed(*args):
            nonlocal done
            nonlocal cancelled
            if not done:
                cancelled = True
                self.computing_privkeys_signal.disconnect()
                self.show_privkeys_signal.disconnect()

        self.computing_privkeys_signal.connect(lambda: e.setText("Please wait... %d/%d"%(len(private_keys),len(addresses))))
        self.show_privkeys_signal.connect(show_privkeys)
        d.finished.connect(on_dialog_closed)
        threading.Thread(target=privkeys_thread).start()

        if not d.exec_():
            done = True
            return

        filename = filename_e.text()
        if not filename:
            return

        try:
            self.do_export_privkeys(filename, private_keys, csv_button.isChecked())
        except (IOError, os.error) as reason:
            txt = "\n".join([
                _("Electrum was unable to produce a private key-export."),
                str(reason)
            ])
            self.show_critical(txt, title=_("Unable to create csv"))

        except Exception as e:
            self.show_message(str(e))
            return

        self.show_message(_("Private keys exported."))

    def do_export_privkeys(self, fileName, pklist, is_csv):
        with open(fileName, "w+") as f:
            if is_csv:
                transaction = csv.writer(f)
                transaction.writerow(["address", "private_key"])
                for addr, pk in pklist.items():
                    transaction.writerow(["%34s"%addr,pk])
            else:
                f.write(json.dumps(pklist, indent = 4))

    def do_import_labels(self):
        def import_labels(path):
            def _validate(data):
                return data  # TODO

            def import_labels_assign(data):
                for key, value in data.items():
                    self.wallet.set_label(key, value)
            import_meta(path, _validate, import_labels_assign)

        def on_import():
            self.need_update.set()
        import_meta_gui(self, _('labels'), import_labels, on_import)

    def do_export_labels(self):
        def export_labels(filename):
            export_meta(self.wallet.labels, filename)
        export_meta_gui(self, _('labels'), export_labels)

    def sweep_key_dialog(self):
        d = WindowModalDialog(self, title=_('Sweep private keys'))
        d.setMinimumSize(600, 300)

        vbox = QVBoxLayout(d)

        hbox_top = QHBoxLayout()
        hbox_top.addWidget(QLabel(_("Enter private keys:")))
        hbox_top.addWidget(InfoButton(WIF_HELP_TEXT), alignment=Qt.AlignRight)
        vbox.addLayout(hbox_top)

        keys_e = ScanQRTextEdit(allow_multi=True)
        keys_e.setTabChangesFocus(True)
        vbox.addWidget(keys_e)

        addresses = self.wallet.get_unused_addresses()
        if not addresses:
            try:
                addresses = self.wallet.get_receiving_addresses()
            except AttributeError:
                addresses = self.wallet.get_addresses()
        h, address_e = address_field(addresses)
        vbox.addLayout(h)

        vbox.addStretch(1)
        button = OkButton(d, _('Sweep'))
        vbox.addLayout(Buttons(CancelButton(d), button))
        button.setEnabled(False)

        def get_address():
            addr = str(address_e.text()).strip()
            if bitcoin.is_address(addr):
                return addr

        def get_pk(*, raise_on_error=False):
            text = str(keys_e.toPlainText())
            return keystore.get_private_keys(text, raise_on_error=raise_on_error)

        def on_edit():
            valid_privkeys = False
            try:
                valid_privkeys = get_pk(raise_on_error=True) is not None
            except Exception as e:
                button.setToolTip(f'{_("Error")}: {str(e)}')
            else:
                button.setToolTip('')
            button.setEnabled(get_address() is not None and valid_privkeys)
        on_address = lambda text: address_e.setStyleSheet((ColorScheme.DEFAULT if get_address() else ColorScheme.RED).as_stylesheet())
        keys_e.textChanged.connect(on_edit)
        address_e.textChanged.connect(on_edit)
        address_e.textChanged.connect(on_address)
        on_address(str(address_e.text()))
        if not d.exec_():
            return
        # user pressed "sweep"
        addr = get_address()
        try:
            self.wallet.check_address(addr)
        except InternalAddressCorruption as e:
            self.show_error(str(e))
            raise
        try:
            coins, keypairs = sweep_preparations(get_pk(), self.network)
        except Exception as e:  # FIXME too broad...
            #traceback.print_exc(file=sys.stderr)
            self.show_message(str(e))
            return
        self.do_clear()
        self.tx_external_keypairs = keypairs
        self.spend_coins(coins)
        self.payto_e.setText(addr)
        self.spend_max()
        self.payto_e.setFrozen(True)
        self.amount_e.setFrozen(True)
        self.warn_if_watching_only()

    def _do_import(self, title, header_layout, func):
        text = text_dialog(self, title, header_layout, _('Import'), allow_multi=True)
        if not text:
            return
        keys = str(text).split()
        good_inputs, bad_inputs = func(keys)
        if good_inputs:
            msg = '\n'.join(good_inputs[:10])
            if len(good_inputs) > 10: msg += '\n...'
            self.show_message(_("The following addresses were added")
                              + f' ({len(good_inputs)}):\n' + msg)
        if bad_inputs:
            msg = "\n".join(f"{key[:10]}... ({msg})" for key, msg in bad_inputs[:10])
            if len(bad_inputs) > 10: msg += '\n...'
            self.show_error(_("The following inputs could not be imported")
                            + f' ({len(bad_inputs)}):\n' + msg)
        self.address_list.update()
        self.history_list.update()

    def import_addresses(self):
        if not self.wallet.can_import_address():
            return
        title, msg = _('Import addresses'), _("Enter addresses")+':'
        self._do_import(title, msg, self.wallet.import_addresses)

    @protected
    def do_import_privkey(self, password):
        if not self.wallet.can_import_privkey():
            return
        title = _('Import private keys')
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(_("Enter private keys")+':'))
        header_layout.addWidget(InfoButton(WIF_HELP_TEXT), alignment=Qt.AlignRight)
        self._do_import(title, header_layout, lambda x: self.wallet.import_private_keys(x, password))

    def update_fiat(self):
        b = self.fx and self.fx.is_enabled()
        self.fiat_send_e.setVisible(b)
        self.fiat_receive_e.setVisible(b)
        self.history_list.update()
        self.address_list.refresh_headers()
        self.address_list.update()
        self.update_status()

    def settings_dialog(self):
        self.need_restart = False
        d = WindowModalDialog(self, _('Preferences'))
        vbox = QVBoxLayout()
        tabs = QTabWidget()
        gui_widgets = []
        fee_widgets = []
        tx_widgets = []
        id_widgets = []

        # language
        lang_help = _('Select which language is used in the GUI (after restart).')
        lang_label = HelpLabel(_('Language') + ':', lang_help)
        lang_combo = QComboBox()
        from electrum.i18n import languages
        lang_combo.addItems(list(languages.values()))
        lang_keys = list(languages.keys())
        lang_cur_setting = self.config.get("language", '')
        try:
            index = lang_keys.index(lang_cur_setting)
        except ValueError:  # not in list
            index = 0
        lang_combo.setCurrentIndex(index)
        if not self.config.is_modifiable('language'):
            for w in [lang_combo, lang_label]: w.setEnabled(False)
        def on_lang(x):
            lang_request = list(languages.keys())[lang_combo.currentIndex()]
            if lang_request != self.config.get('language'):
                self.config.set_key("language", lang_request, True)
                self.need_restart = True
        lang_combo.currentIndexChanged.connect(on_lang)
        gui_widgets.append((lang_label, lang_combo))

        nz_help = _('Number of zeros displayed after the decimal point. For example, if this is set to 2, "1." will be displayed as "1.00"')
        nz_label = HelpLabel(_('Zeros after decimal point') + ':', nz_help)
        nz = QSpinBox()
        nz.setMinimum(0)
        nz.setMaximum(self.decimal_point)
        nz.setValue(self.num_zeros)
        if not self.config.is_modifiable('num_zeros'):
            for w in [nz, nz_label]: w.setEnabled(False)
        def on_nz():
            value = nz.value()
            if self.num_zeros != value:
                self.num_zeros = value
                self.config.set_key('num_zeros', value, True)
                self.history_list.update()
                self.address_list.update()
        nz.valueChanged.connect(on_nz)
        gui_widgets.append((nz_label, nz))

        msg = '\n'.join([
            _('Time based: fee rate is based on average confirmation time estimates'),
            _('Mempool based: fee rate is targeting a depth in the memory pool')
            ]
        )
        fee_type_label = HelpLabel(_('Fee estimation') + ':', msg)
        fee_type_combo = QComboBox()
        fee_type_combo.addItems([_('Static'), _('ETA'), _('Mempool')])
        fee_type_combo.setCurrentIndex((2 if self.config.use_mempool_fees() else 1) if self.config.is_dynfee() else 0)
        def on_fee_type(x):
            self.config.set_key('mempool_fees', x==2)
            self.config.set_key('dynamic_fees', x>0)
            self.fee_slider.update()
        fee_type_combo.currentIndexChanged.connect(on_fee_type)
        fee_widgets.append((fee_type_label, fee_type_combo))

        feebox_cb = QCheckBox(_('Edit fees manually'))
        feebox_cb.setChecked(self.config.get('show_fee', False))
        feebox_cb.setToolTip(_("Show fee edit box in send tab."))
        def on_feebox(x):
            self.config.set_key('show_fee', x == Qt.Checked)
            self.fee_adv_controls.setVisible(bool(x))
            ###john
            self.show_conversion_fee(bool(x))            
        feebox_cb.stateChanged.connect(on_feebox)
        fee_widgets.append((feebox_cb, None))

        use_rbf = self.config.get('use_rbf', USE_RBF_DEFAULT)
        use_rbf_cb = QCheckBox(_('Use Replace-By-Fee'))
        use_rbf_cb.setChecked(use_rbf)
        use_rbf_cb.setToolTip(
            _('If you check this box, your transactions will be marked as non-final,') + '\n' + \
            _('and you will have the possibility, while they are unconfirmed, to replace them with transactions that pay higher fees.') + '\n' + \
            _('Note that some merchants do not accept non-final transactions until they are confirmed.'))
        def on_use_rbf(x):
            self.config.set_key('use_rbf', bool(x))
            batch_rbf_cb.setEnabled(bool(x))
        use_rbf_cb.stateChanged.connect(on_use_rbf)
        fee_widgets.append((use_rbf_cb, None))

        batch_rbf_cb = QCheckBox(_('Batch RBF transactions'))
        batch_rbf_cb.setChecked(self.config.get('batch_rbf', False))
        batch_rbf_cb.setEnabled(use_rbf)
        batch_rbf_cb.setToolTip(
            _('If you check this box, your unconfirmed transactions will be consolidated into a single transaction.') + '\n' + \
            _('This will save fees.'))
        def on_batch_rbf(x):
            self.config.set_key('batch_rbf', bool(x))
        batch_rbf_cb.stateChanged.connect(on_batch_rbf)
        fee_widgets.append((batch_rbf_cb, None))

        msg = _('OpenAlias record, used to receive coins and to sign payment requests.') + '\n\n'\
              + _('The following alias providers are available:') + '\n'\
              + '\n'.join(['https://cryptoname.co/', 'http://xmr.link']) + '\n\n'\
              + 'For more information, see https://openalias.org'
        alias_label = HelpLabel(_('OpenAlias') + ':', msg)
        alias = self.config.get('alias','')
        alias_e = QLineEdit(alias)
        def set_alias_color():
            if not self.config.get('alias'):
                alias_e.setStyleSheet("")
                return
            if self.alias_info:
                alias_addr, alias_name, validated = self.alias_info
                alias_e.setStyleSheet((ColorScheme.GREEN if validated else ColorScheme.RED).as_stylesheet(True))
            else:
                alias_e.setStyleSheet(ColorScheme.RED.as_stylesheet(True))
        def on_alias_edit():
            alias_e.setStyleSheet("")
            alias = str(alias_e.text())
            self.config.set_key('alias', alias, True)
            if alias:
                self.fetch_alias()
        set_alias_color()
        self.alias_received_signal.connect(set_alias_color)
        alias_e.editingFinished.connect(on_alias_edit)
        id_widgets.append((alias_label, alias_e))

        # SSL certificate
        msg = ' '.join([
            _('SSL certificate used to sign payment requests.'),
            _('Use setconfig to set ssl_chain and ssl_privkey.'),
        ])
        if self.config.get('ssl_privkey') or self.config.get('ssl_chain'):
            try:
                SSL_identity = paymentrequest.check_ssl_config(self.config)
                SSL_error = None
            except BaseException as e:
                SSL_identity = "error"
                SSL_error = str(e)
        else:
            SSL_identity = ""
            SSL_error = None
        SSL_id_label = HelpLabel(_('SSL certificate') + ':', msg)
        SSL_id_e = QLineEdit(SSL_identity)
        SSL_id_e.setStyleSheet((ColorScheme.RED if SSL_error else ColorScheme.GREEN).as_stylesheet(True) if SSL_identity else '')
        if SSL_error:
            SSL_id_e.setToolTip(SSL_error)
        SSL_id_e.setReadOnly(True)
        id_widgets.append((SSL_id_label, SSL_id_e))

        units = base_units_list
        msg = (_('Base unit of your wallet.')
               + '\n1 BTC = 1000 mBTC. 1 mBTC = 1000 bits. 1 bit = 100 sat.\n'
               + _('This setting affects the Send tab, and all balance related fields.'))
        unit_label = HelpLabel(_('Base unit') + ':', msg)
        unit_combo = QComboBox()
        unit_combo.addItems(units)
        unit_combo.setCurrentIndex(units.index(self.base_unit()))
        def on_unit(x, nz):
            unit_result = units[unit_combo.currentIndex()]
            if self.base_unit() == unit_result:
                return
            edits = self.amount_e, self.fee_e, self.receive_amount_e
            amounts = [edit.get_amount() for edit in edits]
            self.decimal_point = base_unit_name_to_decimal_point(unit_result)
            self.config.set_key('decimal_point', self.decimal_point, True)
            nz.setMaximum(self.decimal_point)
            self.history_list.update()
            self.request_list.update()
            self.address_list.update()
            for edit, amount in zip(edits, amounts):
                edit.setAmount(amount)
            self.update_status()
        unit_combo.currentIndexChanged.connect(lambda x: on_unit(x, nz))
        gui_widgets.append((unit_label, unit_combo))

        block_explorers = sorted(util.block_explorer_info().keys())
        msg = _('Choose which online block explorer to use for functions that open a web browser')
        block_ex_label = HelpLabel(_('Online Block Explorer') + ':', msg)
        block_ex_combo = QComboBox()
        block_ex_combo.addItems(block_explorers)
        block_ex_combo.setCurrentIndex(block_ex_combo.findText(util.block_explorer(self.config)))
        def on_be(x):
            be_result = block_explorers[block_ex_combo.currentIndex()]
            self.config.set_key('block_explorer', be_result, True)
        block_ex_combo.currentIndexChanged.connect(on_be)
        gui_widgets.append((block_ex_label, block_ex_combo))

        from electrum import qrscanner
        system_cameras = qrscanner._find_system_cameras()
        qr_combo = QComboBox()
        qr_combo.addItem("Default","default")
        for camera, device in system_cameras.items():
            qr_combo.addItem(camera, device)
        #combo.addItem("Manually specify a device", config.get("video_device"))
        index = qr_combo.findData(self.config.get("video_device"))
        qr_combo.setCurrentIndex(index)
        msg = _("Install the zbar package to enable this.")
        qr_label = HelpLabel(_('Video Device') + ':', msg)
        qr_combo.setEnabled(qrscanner.libzbar is not None)
        on_video_device = lambda x: self.config.set_key("video_device", qr_combo.itemData(x), True)
        qr_combo.currentIndexChanged.connect(on_video_device)
        gui_widgets.append((qr_label, qr_combo))

        colortheme_combo = QComboBox()
        colortheme_combo.addItem(_('Light'), 'default')
        colortheme_combo.addItem(_('Dark'), 'dark')
        index = colortheme_combo.findData(self.config.get('qt_gui_color_theme', 'default'))
        colortheme_combo.setCurrentIndex(index)
        colortheme_label = QLabel(_('Color theme') + ':')
        def on_colortheme(x):
            self.config.set_key('qt_gui_color_theme', colortheme_combo.itemData(x), True)
            self.need_restart = True
        colortheme_combo.currentIndexChanged.connect(on_colortheme)
        gui_widgets.append((colortheme_label, colortheme_combo))

        updatecheck_cb = QCheckBox(_("Automatically check for software updates"))
        updatecheck_cb.setChecked(self.config.get('check_updates', False))
        def on_set_updatecheck(v):
            self.config.set_key('check_updates', v == Qt.Checked, save=True)
        updatecheck_cb.stateChanged.connect(on_set_updatecheck)
        gui_widgets.append((updatecheck_cb, None))

        filelogging_cb = QCheckBox(_("Write logs to file"))
        filelogging_cb.setChecked(bool(self.config.get('log_to_file', False)))
        def on_set_filelogging(v):
            self.config.set_key('log_to_file', v == Qt.Checked, save=True)
            self.need_restart = True
        filelogging_cb.stateChanged.connect(on_set_filelogging)
        filelogging_cb.setToolTip(_('Debug logs can be persisted to disk. These are useful for troubleshooting.'))
        gui_widgets.append((filelogging_cb, None))

        usechange_cb = QCheckBox(_('Use change addresses'))
        usechange_cb.setChecked(self.wallet.use_change)
        if not self.config.is_modifiable('use_change'): usechange_cb.setEnabled(False)
        def on_usechange(x):
            usechange_result = x == Qt.Checked
            if self.wallet.use_change != usechange_result:
                self.wallet.use_change = usechange_result
                self.wallet.storage.put('use_change', self.wallet.use_change)
                multiple_cb.setEnabled(self.wallet.use_change)
        usechange_cb.stateChanged.connect(on_usechange)
        usechange_cb.setToolTip(_('Using change addresses makes it more difficult for other people to track your transactions.'))
        tx_widgets.append((usechange_cb, None))

        def on_multiple(x):
            multiple = x == Qt.Checked
            if self.wallet.multiple_change != multiple:
                self.wallet.multiple_change = multiple
                self.wallet.storage.put('multiple_change', multiple)
        multiple_change = self.wallet.multiple_change
        multiple_cb = QCheckBox(_('Use multiple change addresses'))
        multiple_cb.setEnabled(self.wallet.use_change)
        multiple_cb.setToolTip('\n'.join([
            _('In some cases, use up to 3 change addresses in order to break '
              'up large coin amounts and obfuscate the recipient address.'),
            _('This may result in higher transactions fees.')
        ]))
        multiple_cb.setChecked(multiple_change)
        multiple_cb.stateChanged.connect(on_multiple)
        tx_widgets.append((multiple_cb, None))

        def fmt_docs(key, klass):
            lines = [ln.lstrip(" ") for ln in klass.__doc__.split("\n")]
            return '\n'.join([key, "", " ".join(lines)])

        choosers = sorted(coinchooser.COIN_CHOOSERS.keys())
        if len(choosers) > 1:
            chooser_name = coinchooser.get_name(self.config)
            msg = _('Choose coin (UTXO) selection method.  The following are available:\n\n')
            msg += '\n\n'.join(fmt_docs(*item) for item in coinchooser.COIN_CHOOSERS.items())
            chooser_label = HelpLabel(_('Coin selection') + ':', msg)
            chooser_combo = QComboBox()
            chooser_combo.addItems(choosers)
            i = choosers.index(chooser_name) if chooser_name in choosers else 0
            chooser_combo.setCurrentIndex(i)
            def on_chooser(x):
                chooser_name = choosers[chooser_combo.currentIndex()]
                self.config.set_key('coin_chooser', chooser_name)
            chooser_combo.currentIndexChanged.connect(on_chooser)
            tx_widgets.append((chooser_label, chooser_combo))

        def on_unconf(x):
            self.config.set_key('confirmed_only', bool(x))
        conf_only = self.config.get('confirmed_only', False)
        unconf_cb = QCheckBox(_('Spend only confirmed coins'))
        unconf_cb.setToolTip(_('Spend only confirmed inputs.'))
        unconf_cb.setChecked(conf_only)
        unconf_cb.stateChanged.connect(on_unconf)
        tx_widgets.append((unconf_cb, None))

        def on_outrounding(x):
            self.config.set_key('coin_chooser_output_rounding', bool(x))
        enable_outrounding = self.config.get('coin_chooser_output_rounding', False)
        outrounding_cb = QCheckBox(_('Enable output value rounding'))
        outrounding_cb.setToolTip(
            _('Set the value of the change output so that it has similar precision to the other outputs.') + '\n' +
            _('This might improve your privacy somewhat.') + '\n' +
            _('If enabled, at most 100 satoshis might be lost due to this, per transaction.'))
        outrounding_cb.setChecked(enable_outrounding)
        outrounding_cb.stateChanged.connect(on_outrounding)
        tx_widgets.append((outrounding_cb, None))

        '''
        use_collateral_label = QLabel(_('Use collateral coins') + ":")
        use_collateral_combo = QComboBox()
        use_collateral_combo.addItems(use_collateral_list)
        if self.config.get('use_collateral') == use_collateral_list[0]:
            use_collateral_combo.setCurrentIndex(0)
        elif self.config.get('use_collateral') == use_collateral_list[1]:
            use_collateral_combo.setCurrentIndex(1)
        else:
            use_collateral_combo.setCurrentIndex(2)        
        def on_use_collateral(x):
            self.config.set_key('use_collateral', x)
        use_collateral_combo.currentTextChanged.connect(on_use_collateral)
        tx_widgets.append((use_collateral_label, use_collateral_combo))
        '''

        # Fiat Currency
        hist_checkbox = QCheckBox()
        hist_capgains_checkbox = QCheckBox()
        fiat_address_checkbox = QCheckBox()
        ccy_combo = QComboBox()
        ex_combo = QComboBox()

        def update_currencies():
            if not self.fx: return
            currencies = sorted(self.fx.get_currencies(self.fx.get_history_config()))
            ccy_combo.clear()
            ccy_combo.addItems([_('None')] + currencies)
            if self.fx.is_enabled():
                ccy_combo.setCurrentIndex(ccy_combo.findText(self.fx.get_currency()))

        def update_history_cb():
            if not self.fx: return
            hist_checkbox.setChecked(self.fx.get_history_config())
            hist_checkbox.setEnabled(self.fx.is_enabled())

        def update_fiat_address_cb():
            if not self.fx: return
            fiat_address_checkbox.setChecked(self.fx.get_fiat_address_config())

        def update_history_capgains_cb():
            if not self.fx: return
            hist_capgains_checkbox.setChecked(self.fx.get_history_capital_gains_config())
            hist_capgains_checkbox.setEnabled(hist_checkbox.isChecked())

        def update_exchanges():
            if not self.fx: return
            b = self.fx.is_enabled()
            ex_combo.setEnabled(b)
            if b:
                h = self.fx.get_history_config()
                c = self.fx.get_currency()
                exchanges = self.fx.get_exchanges_by_ccy(c, h)
            else:
                exchanges = self.fx.get_exchanges_by_ccy('USD', False)
            ex_combo.blockSignals(True)
            ex_combo.clear()
            ex_combo.addItems(sorted(exchanges))
            ex_combo.setCurrentIndex(ex_combo.findText(self.fx.config_exchange()))
            ex_combo.blockSignals(False)

        def on_currency(hh):
            if not self.fx: return
            b = bool(ccy_combo.currentIndex())
            ccy = str(ccy_combo.currentText()) if b else None
            self.fx.set_enabled(b)
            self.fx.set_currency(ccy)
            update_history_cb()
            update_exchanges()
            self.update_fiat()

        def on_exchange(idx):
            exchange = str(ex_combo.currentText())
            if self.fx and self.fx.is_enabled() and exchange and exchange != self.fx.exchange.name():
                self.fx.set_exchange(exchange)

        def on_history(checked):
            if not self.fx: return
            self.fx.set_history_config(checked)
            update_exchanges()
            self.history_model.refresh('on_history')
            if self.fx.is_enabled() and checked:
                self.fx.trigger_update()
            update_history_capgains_cb()

        def on_history_capgains(checked):
            if not self.fx: return
            self.fx.set_history_capital_gains_config(checked)
            self.history_model.refresh('on_history_capgains')

        def on_fiat_address(checked):
            if not self.fx: return
            self.fx.set_fiat_address_config(checked)
            self.address_list.refresh_headers()
            self.address_list.update()

        update_currencies()
        update_history_cb()
        update_history_capgains_cb()
        update_fiat_address_cb()
        update_exchanges()
        ccy_combo.currentIndexChanged.connect(on_currency)
        hist_checkbox.stateChanged.connect(on_history)
        hist_capgains_checkbox.stateChanged.connect(on_history_capgains)
        fiat_address_checkbox.stateChanged.connect(on_fiat_address)
        ex_combo.currentIndexChanged.connect(on_exchange)

        fiat_widgets = []
        fiat_widgets.append((QLabel(_('Fiat currency')), ccy_combo))
        fiat_widgets.append((QLabel(_('Show history rates')), hist_checkbox))
        fiat_widgets.append((QLabel(_('Show capital gains in history')), hist_capgains_checkbox))
        fiat_widgets.append((QLabel(_('Show Fiat balance for addresses')), fiat_address_checkbox))
        fiat_widgets.append((QLabel(_('Source')), ex_combo))

        tabs_info = [
            (fee_widgets, _('Fees')),
            (tx_widgets, _('Transactions')),
            (gui_widgets, _('General')),
            ###john
            #(fiat_widgets, _('Fiat')),
            (id_widgets, _('Identity')),
        ]
        for widgets, name in tabs_info:
            tab = QWidget()
            grid = QGridLayout(tab)
            grid.setColumnStretch(0,1)
            for a,b in widgets:
                i = grid.rowCount()
                if b:
                    if a:
                        grid.addWidget(a, i, 0)
                    grid.addWidget(b, i, 1)
                else:
                    grid.addWidget(a, i, 0, 1, 2)
            tabs.addTab(tab, name)

        vbox.addWidget(tabs)
        vbox.addStretch(1)
        vbox.addLayout(Buttons(CloseButton(d)))
        d.setLayout(vbox)

        # run the dialog
        d.exec_()

        if self.fx:
            self.fx.trigger_update()

        self.alias_received_signal.disconnect(set_alias_color)

        run_hook('close_settings_dialog')
        if self.need_restart:
            self.show_warning(_('Please restart Electrum to activate the new GUI settings'), title=_('Success'))


    def closeEvent(self, event):
        # It seems in some rare cases this closeEvent() is called twice
        if not self.cleaned_up:
            self.cleaned_up = True
            self.clean_up()
        event.accept()
        ###john
        try:
            os._exit(5) 
        except Exception as e:
            print(e)        

    def clean_up(self):
        self.wallet.thread.stop()
        if self.network:
            self.network.unregister_callback(self.on_network)
            self.network.unregister_callback(self.on_quotes)
            self.network.unregister_callback(self.on_history)
        self.config.set_key("is_maximized", self.isMaximized())
        if not self.isMaximized():
            g = self.geometry()
            self.wallet.storage.put("winpos-qt", [g.left(),g.top(),
                                                  g.width(),g.height()])
        self.config.set_key("console-history", self.console.history[-50:],
                            True)
        if self.qr_window:
            self.qr_window.close()
        self.close_wallet()

        self.gui_object.timer.timeout.disconnect(self.timer_actions)
        self.gui_object.close_window(self)

    def plugins_dialog(self):
        self.pluginsdialog = d = WindowModalDialog(self, _('Electrum Plugins'))

        plugins = self.gui_object.plugins

        vbox = QVBoxLayout(d)

        # plugins
        scroll = QScrollArea()
        scroll.setEnabled(True)
        scroll.setWidgetResizable(True)
        scroll.setMinimumSize(400,250)
        vbox.addWidget(scroll)

        w = QWidget()
        scroll.setWidget(w)
        w.setMinimumHeight(plugins.count() * 35)

        grid = QGridLayout()
        grid.setColumnStretch(0,1)
        w.setLayout(grid)

        settings_widgets = {}

        def enable_settings_widget(p, name, i):
            widget = settings_widgets.get(name)
            if not widget and p and p.requires_settings():
                widget = settings_widgets[name] = p.settings_widget(d)
                grid.addWidget(widget, i, 1)
            if widget:
                widget.setEnabled(bool(p and p.is_enabled()))

        def do_toggle(cb, name, i):
            p = plugins.toggle(name)
            cb.setChecked(bool(p))
            enable_settings_widget(p, name, i)
            run_hook('init_qt', self.gui_object)

        for i, descr in enumerate(plugins.descriptions.values()):
            full_name = descr['__name__']
            prefix, _separator, name = full_name.rpartition('.')
            p = plugins.get(name)
            if descr.get('registers_keystore'):
                continue
            try:
                cb = QCheckBox(descr['fullname'])
                plugin_is_loaded = p is not None
                cb_enabled = (not plugin_is_loaded and plugins.is_available(name, self.wallet)
                              or plugin_is_loaded and p.can_user_disable())
                cb.setEnabled(cb_enabled)
                cb.setChecked(plugin_is_loaded and p.is_enabled())
                grid.addWidget(cb, i, 0)
                enable_settings_widget(p, name, i)
                cb.clicked.connect(partial(do_toggle, cb, name, i))
                msg = descr['description']
                if descr.get('requires'):
                    msg += '\n\n' + _('Requires') + ':\n' + '\n'.join(map(lambda x: x[1], descr.get('requires')))
                grid.addWidget(HelpButton(msg), i, 2)
            except Exception:
                self.print_msg("error: cannot display plugin", name)
                traceback.print_exc(file=sys.stdout)
        grid.setRowStretch(len(plugins.descriptions.values()), 1)
        vbox.addLayout(Buttons(CloseButton(d)))
        d.exec_()

    def cpfp(self, parent_tx, new_tx):
        total_size = parent_tx.estimated_size() + new_tx.estimated_size()
        parent_fee = self.wallet.get_tx_fee(parent_tx)
        if parent_fee is None:
            self.show_error(_("Can't CPFP: unknown fee for parent transaction."))
            return
        d = WindowModalDialog(self, _('Child Pays for Parent'))
        vbox = QVBoxLayout(d)
        msg = (
            "A CPFP is a transaction that sends an unconfirmed output back to "
            "yourself, with a high fee. The goal is to have miners confirm "
            "the parent transaction in order to get the fee attached to the "
            "child transaction.")
        vbox.addWidget(WWLabel(_(msg)))
        msg2 = ("The proposed fee is computed using your "
            "fee/kB settings, applied to the total size of both child and "
            "parent transactions. After you broadcast a CPFP transaction, "
            "it is normal to see a new unconfirmed transaction in your history.")
        vbox.addWidget(WWLabel(_(msg2)))
        grid = QGridLayout()
        grid.addWidget(QLabel(_('Total size') + ':'), 0, 0)
        grid.addWidget(QLabel('%d bytes'% total_size), 0, 1)
        max_fee = new_tx.output_value()
        grid.addWidget(QLabel(_('Input amount') + ':'), 1, 0)
        grid.addWidget(QLabel(self.format_amount(max_fee) + ' ' + self.base_unit()), 1, 1)
        output_amount = QLabel('')
        grid.addWidget(QLabel(_('Output amount') + ':'), 2, 0)
        grid.addWidget(output_amount, 2, 1)
        fee_e = BTCAmountEdit(self.get_decimal_point)
        # FIXME with dyn fees, without estimates, there are all kinds of crashes here
        combined_fee = QLabel('')
        combined_feerate = QLabel('')
        def on_fee_edit(x):
            out_amt = max_fee - fee_e.get_amount()
            out_amt_str = (self.format_amount(out_amt) + ' ' + self.base_unit()) if out_amt else ''
            output_amount.setText(out_amt_str)
            comb_fee = parent_fee + fee_e.get_amount()
            comb_fee_str = (self.format_amount(comb_fee) + ' ' + self.base_unit()) if comb_fee else ''
            combined_fee.setText(comb_fee_str)
            comb_feerate = comb_fee / total_size * 1000
            comb_feerate_str = self.format_fee_rate(comb_feerate) if comb_feerate else ''
            combined_feerate.setText(comb_feerate_str)
        fee_e.textChanged.connect(on_fee_edit)
        def get_child_fee_from_total_feerate(fee_per_kb):
            fee = fee_per_kb * total_size / 1000 - parent_fee
            fee = min(max_fee, fee)
            fee = max(total_size, fee)  # pay at least 1 sat/byte for combined size
            return fee
        suggested_feerate = self.config.fee_per_kb()
        if suggested_feerate is None:
            self.show_error(f'''{_("Can't CPFP'")}: {_('Dynamic fee estimates not available')}''')
            return
        fee = get_child_fee_from_total_feerate(suggested_feerate)
        fee_e.setAmount(fee)
        grid.addWidget(QLabel(_('Fee for child') + ':'), 3, 0)
        grid.addWidget(fee_e, 3, 1)
        def on_rate(dyn, pos, fee_rate):
            fee = get_child_fee_from_total_feerate(fee_rate)
            fee_e.setAmount(fee)
        fee_slider = FeeSlider(self, self.config, on_rate)
        fee_slider.update()
        grid.addWidget(fee_slider, 4, 1)
        grid.addWidget(QLabel(_('Total fee') + ':'), 5, 0)
        grid.addWidget(combined_fee, 5, 1)
        grid.addWidget(QLabel(_('Total feerate') + ':'), 6, 0)
        grid.addWidget(combined_feerate, 6, 1)
        vbox.addLayout(grid)
        vbox.addLayout(Buttons(CancelButton(d), OkButton(d)))
        if not d.exec_():
            return
        fee = fee_e.get_amount()
        if fee > max_fee:
            self.show_error(_('Max fee exceeded'))
            return
        new_tx = self.wallet.cpfp(parent_tx, fee)
        new_tx.set_rbf(True)
        self.show_transaction(new_tx)

    def bump_fee_dialog(self, tx):
        fee = self.wallet.get_tx_fee(tx)
        if fee is None:
            self.show_error(_("Can't bump fee: unknown fee for original transaction."))
            return
        tx_label = self.wallet.get_label(tx.txid())
        tx_size = tx.estimated_size()
        d = WindowModalDialog(self, _('Bump Fee'))
        vbox = QVBoxLayout(d)
        vbox.addWidget(WWLabel(_("Increase your transaction's fee to improve its position in mempool.")))
        vbox.addWidget(QLabel(_('Current fee') + ': %s'% self.format_amount(fee) + ' ' + self.base_unit()))
        vbox.addWidget(QLabel(_('New fee' + ':')))
        fee_e = BTCAmountEdit(self.get_decimal_point)
        fee_e.setAmount(fee * 1.5)
        vbox.addWidget(fee_e)

        def on_rate(dyn, pos, fee_rate):
            fee = fee_rate * tx_size / 1000
            fee_e.setAmount(fee)
        fee_slider = FeeSlider(self, self.config, on_rate)
        vbox.addWidget(fee_slider)
        cb = QCheckBox(_('Final'))
        vbox.addWidget(cb)
        vbox.addLayout(Buttons(CancelButton(d), OkButton(d)))
        if not d.exec_():
            return
        is_final = cb.isChecked()
        new_fee = fee_e.get_amount()
        delta = new_fee - fee
        if delta < 0:
            self.show_error("fee too low")
            return
        try:
            new_tx = self.wallet.bump_fee(tx, delta)
        except CannotBumpFee as e:
            self.show_error(str(e))
            return
        if is_final:
            new_tx.set_rbf(False)
        self.show_transaction(new_tx, tx_label)

    def save_transaction_into_wallet(self, tx):
        win = self.top_level_window()
        try:
            if not self.wallet.add_transaction(tx.txid(), tx):
                win.show_error(_("Transaction could not be saved.") + "\n" +
                               _("It conflicts with current history."))
                return False
        except AddTransactionException as e:
            win.show_error(e)
            return False
        else:
            self.wallet.storage.write()
            # need to update at least: history_list, utxo_list, address_list
            self.need_update.set()
            msg = (_("Transaction added to wallet history.") + '\n\n' +
                   _("Note: this is an offline transaction, if you want the network "
                     "to see it, you need to broadcast it."))
            win.msg_box(QPixmap(icon_path("offline_tx.png")), None, _('Success'), msg)
            return True

    def create_masternode_tab(self):
        # A 4-column grid layout.  All the stretch is in the last column.
        # The exchange rate plugin adds a fiat widget in column 2
        
        self.masternode_grid = grid = QGridLayout()
        grid.setSpacing(8)
        #grid.setColumnStretch(5, 1)

        self.alias_e = MyLineEdit()
        self.alias_label = QLabel(_('Alias'))
        grid.addWidget(self.alias_label, 1, 0)
        grid.addWidget(self.alias_e, 1, 1)
        
        self.ip_e = MyLineEdit()
        self.ip_label =QLabel(_('Address IP'))
        self.ip_e.setReadOnly(True)
        grid.addWidget(self.ip_label, 1, 2)
        grid.addWidget(self.ip_e, 1, 3)

        self.port_e = MyLineEdit()
        self.port_label = QLabel(_('Port'))
        self.port_e.setReadOnly(True)
        grid.addWidget(self.port_label, 1, 4)
        grid.addWidget(self.port_e, 1, 5)

        self.txid_e = MyLineEdit()
        self.txid_e.setReadOnly(True)
        self.txid_label = QLabel(_('Collateral Txid'))
        grid.addWidget(self.txid_label, 2, 0)
        grid.addWidget(self.txid_e, 2, 1, 1, -1)

        self.index_e = MyLineEdit()
        self.index_e.setReadOnly(True)
        self.index_label = QLabel(_('Collateral Index'))
        grid.addWidget(self.index_label, 3, 0)
        grid.addWidget(self.index_e, 3, 1)

        self.address_e = MyLineEdit()
        self.address_e.setReadOnly(True)
        self.address_label = QLabel(_('Collateral Key'))
        grid.addWidget(self.address_label, 3, 2)
        grid.addWidget(self.address_e, 3, 3, 1, -1)

        self.masternode_label = QLabel(_('Masternode'))
        self.masternode_combo = QComboBox()
        self.masternode_combo.addItem('None')        
        self.masternode_combo.currentIndexChanged.connect(
                                    lambda: self.masternode_change(self.masternode_combo.currentIndex()))        
        grid.addWidget(self.masternode_label, 4, 0)
        grid.addWidget(self.masternode_combo, 4, 1)
            
        self.delegate_e = MyLineEdit()
        self.delegate_e.setReadOnly(True)
        self.delegate_label = QLabel(_('Masternode Private Key'))
        grid.addWidget(self.delegate_label, 4, 2)
        grid.addWidget(self.delegate_e, 4, 3, 1, -1)

        self.masternode_hide_button = EnterButton(_("Hide"), self.masternode_hide)
        self.masternode_import_button = EnterButton(_("Import"), self.masternode_import)
        self.masternode_scan_button = EnterButton(_("Scan"), self.masternode_scan)
        self.masternode_scan_button.setToolTip(_('Display the details of your transaction before signing it.'))
        
        self.masternode_save_button = EnterButton(_("Save"), self.masternode_save)
        self.masternode_generate_button = EnterButton(_("Generate"), self.masternode_generate)
        self.masternode_activate_button = EnterButton(_("Activate"), self.masternode_do_activate)
        self.masternode_clear_button = EnterButton(_("Clear"), self.masternode_clear)
        self.masternode_remove_button = EnterButton(_("Remove"), self.masternode_do_remove)
        self.masternode_remove_all_button = EnterButton(_("Remove All"), self.masternode_remove_all)
        self.masternode_monit_button = EnterButton(_("Monit"), self.masternode_monit)
        buttons = QHBoxLayout()
        buttons.addWidget(self.masternode_hide_button)
        #buttons.addWidget(self.masternode_import_button)
        #buttons.addWidget(self.masternode_generate_button)
        buttons.addStretch(1)
        buttons.addWidget(self.masternode_scan_button)
        buttons.addWidget(self.masternode_save_button)        
        buttons.addWidget(self.masternode_clear_button)
        #buttons.addWidget(self.masternode_remove_button)
        buttons.addWidget(self.masternode_remove_all_button)
        buttons.addWidget(self.masternode_activate_button)
        #buttons.addWidget(self.masternode_monit_button)
        grid.addLayout(buttons, 5, 1, 1, -1)
                
        vbox0 = QVBoxLayout()
        vbox0.addLayout(grid)
        vbox1 = QVBoxLayout()
        hbox = QHBoxLayout()
        hbox.addLayout(vbox0)
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.addLayout(hbox)
        
        self.masternode_list = l = MasternodeList(self)
        vbox1.addWidget(l)
        vbox.addLayout(vbox1)                
        run_hook('create_masternode_tab', grid)
        return w
    
    def masternode_clear(self):
        self.alias_e.setText('')
        self.txid_e.setText('')
        self.index_e.setText('')
        self.address_e.setText('')
        self.delegate_e.setText('')
        self.ip_e.setText('')
        self.port_e.setText('')
    
    def masternode_scan(self):
        try:
            exclude_frozen = True
            coins = self.masternode_manager.get_masternode_outputs(exclude_frozen=exclude_frozen)        
            for coin in coins:
                if self.masternode_manager.is_used_masternode_from_coin(coin):
                    continue
                alias = self.masternode_manager.get_default_alias()                                  
                vin = {'prevout_hash': coin['prevout_hash'], 'prevout_n': coin['prevout_n']}                        
                try:
                    collateral = self.wallet.get_public_keys(coin['address'])[0]       
                except Exception as e:
                    self.app.show_error(_("InValid Collateral Key"))
                    collateral = ''
                
                delegate = ''
                mn = MasternodeAnnounce(alias=alias, vin=vin, addr=NetworkAddress(),
                                        collateral_key=collateral, delegate_key=delegate, sig='', sig_time=0,
                                        last_ping=MasternodePing(),
                                        status='', lastseen=0, activeseconds=0, announced=False)             
                self.masternode_manager.add_masternode(mn)
            self.masternode_refresh()
            self.masternode_list.update()           
        except Exception as e:
            self.show_error(str(e))
            
    def masternode_activate(self, collateral):
        self.sign_announce(collateral[0])
    
    def masternode_monit(self):        
        vin = {'prevout_hash': self.txid_e.text(), 'prevout_n': int(self.index_e.text())}                    
        
        try:
            delegate = self.masternode_manager.import_masternode_delegate(self.delegate_e.text())
        except Exception as e:
            self.show_error(str(e))
            return
        
        try:
            collateral = self.wallet.get_public_keys(self.address_e.text())[0]
        except Exception as e:
            self.show_error(_("InValid Collateral Key"))
            return
                
        mn = MasternodeAnnounce(alias=self.alias_e.text(), vin=vin, addr=NetworkAddress(),
                                collateral_key=collateral, delegate_key=delegate, sig='', sig_time=0,
                                protocol_version=31800, last_ping=MasternodePing(), status='', 
                                lastseen=0, activeseconds=0, announced=False)             
        try:
            self.masternode_manager.add_masternode(mn)
            self.masternode_list.update()
        except Exception as e:
            self.show_error(str(e))        
        
    def masternode_remove_all(self):
        reply = QMessageBox.question(self, _('Message'), _("Are you sure you want to remove all of them?"), QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            
            for key in self.masternode_manager.masternodes.keys():
                mn = self.masternode_manager.masternodes[key]            
                self.masternode_list.set_frozen_masternode(mn.vin['prevout_hash'], str(mn.vin['prevout_n']), False)                
            
            self.masternode_manager.masternodes = {}
            self.masternode_manager.save()
            self.masternode_list.update()
    
    def masternode_do_remove(self):
        pass

    def masternode_remove(self, collateral):
        reply = QMessageBox.question(self, _('Message'), _("Are you sure you want to remove it?"), QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            try:
                self.masternode_manager.remove_masternode(collateral[0])
                self.masternode_list.update()
                txid, index = collateral[0].split('-')
                self.masternode_list.set_frozen_masternode(txid, index, False)
            except Exception as e:
                self.show_error(str(e))
                
    def masternode_change(self, index):
        key = self.masternode_combo.currentText()
        if key == 'None' or key == '':
            self.delegate_e.setText('')
            self.ip_e.setText('')
            self.port_e.setText('')
            return
        self.delegate_e.setText(self.masternode_combo.itemData(index))
        ip, port = key.split(":")
        self.ip_e.setText(ip)
        self.port_e.setText(port)
    
    def masternode_select(self, host):
        for index in range(self.masternode_combo.count()):
            if self.masternode_combo.itemText(index) == host:
                self.masternode_combo.setCurrentIndex(index)
                return
        self.masternode_combo.setCurrentIndex(0)
    
    def masternode_refresh(self):
        
        def query_masternode_thread():            
            ret = self.client.get_masternodes()
            return ret
        
        def on_success(masternodes):
            self.masternode_combo.clear()
            self.masternode_combo.addItem('None')
            index = 0
            for key in masternodes.keys():
                if not self.masternode_manager.is_used_masternode_from_host(key):
                    index += 1
                    self.masternode_combo.addItem(key)
                    self.masternode_combo.setItemData(index, masternodes[key])
            self.masternode_combo.setCurrentIndex(0)
            
        def on_error(err):
            pass
    
        WaitingDialog(self, _('masternode query...'), query_masternode_thread, on_success, on_error)  
        
        
    
    def masternode_combo_remove(self,host):
        for index in range(self.masternode_combo.count()):
            if self.masternode_combo.itemText(index) == host:
                self.masternode_combo.removeItem(index)
                self.masternode_combo.setDisabled(True)
                break
        self.masternode_combo.setCurrentIndex(0)     
        
    
    def check_masternode_save(self, collateral=None):
        if len(self.alias_e.text()) == 0: 
            raise Exception(_('Alias is not specified'))        
        if len(self.address_e.text()) == 0:
            raise Exception(_('Collateral payment is not specified'))
        if len(self.delegate_e.text()) == 0:
            raise Exception(_('Masternode delegate key is not specified'))
        if len(self.ip_e.text()) == 0:
            raise Exception(_('Masternode has no IP address'))
                
        for key in self.masternode_manager.masternodes.keys():
            if not (collateral is None):
                if key == collateral:
                    continue
            mn = self.masternode_manager.masternodes[key]
            if mn.alias == self.alias_e.text():
                raise Exception(_('A masternode with alias "%s" already exists' % self.alias_e.text()))
            delegate = self.wallet.get_delegate_private_key(mn.delegate_key)            
            if delegate == self.delegate_e.text():
                raise Exception(_('A masternode with private key "%s" already exists' % self.delegate_e.text()))
            ipaddress, port = (self.ip_e.text(), self.port_e.text())
            if mn.addr.ip == ipaddress:
                raise Exception(_('A masternode with ip address "%s" already exists' % self.ip_e.text()))
        return True
    
    def masternode_save(self):
        key = self.txid_e.text() + '-' + self.index_e.text()
        mn = self.masternode_manager.get_masternode(key)
        if mn is None:
            key = None
            
        try:
            self.check_masternode_save(key)
        except Exception as e:
            self.show_error(str(e))
            return
        
        try:
            delegate_pub = self.masternode_manager.import_masternode_delegate(self.delegate_e.text())
        except Exception as e:
            self.show_error(str(e))
            pass
                
        try:
            txin_type, txin_key, is_compressed = bitcoin.deserialize_privkey(self.delegate_e.text())
            delegate_pub = ecc.ECPrivkey(txin_key).get_public_key_hex(compressed=is_compressed)
        except Exception as e:
            self.show_error(_('Invalid Masternode Private Key'))
            return
                       
        try:
            collateral_pub = self.wallet.get_public_keys(self.address_e.text())[0]            
        except Exception as e:
            self.show_error(_("InValid Collateral Key"))
            return 
        
        try:
            if mn is None:
                self.show_info("bbbbb1:" + str(key) + '-' + str(type(key)))
                return
            mn.alias = self.alias_e.text()
            mn.delegate_key = delegate_pub
            mn.collateral_key = collateral_pub
            ipaddress , port = (self.ip_e.text(), self.port_e.text())
            mn.addr.ip = ipaddress
            mn.addr.port = int(port)
            self.masternode_manager.save()
            self.masternode_list.update()     
            self.masternode_combo_remove(ipaddress + ':' + port)
        except Exception as e:
            self.show_error(str(e))        
    
    def masternode_generate(self):
        private_key = b'\x80' + os.urandom(32)
        checksum = sha256d(private_key)[0:4]
        wif = base58.b58encode(private_key + checksum)        
        self.delegate_e.setText(str(wif, encoding='utf-8'))
    
    def masternode_import(self):
        text = QFileDialog.getOpenFileName(None, _('Select a file to import'), '', '*.conf')
        filename, ext = text
        if filename !='' and len(text) == 2:
            self.import_masternode_conf(text[0])
            self.masternode_list.update()
    
    def import_masternode_conf(self, filename):
        """Import a masternode.conf file."""
        
        pw = None
        if self.wallet.has_password():
            pw = self.password_dialog(msg=_('Please enter your password to import Masternode information.'))
            if pw is None:
                return
        
        if not os.path.exists(filename):
            self.show_critical(_('File does not exist'), title=_('Error'))
            return
        with open(filename, 'r') as f:
            lines = f.readlines()

        # Show an error if the conf file is malformed.
        try:
            conf_lines = parse_masternode_conf(lines)
        except Exception as e:
            self.show_critical(str(e), title=_('Error'))
            return

        num = self.masternode_manager.import_masternode_conf_lines(conf_lines, pw)
        if not num:
            return self.show_warning(_('Could not import any masternode'
                                       ' configurations. Please ensure that'
                                       ' they are not already imported.'),
                                     title=_('Failed to Import'))
        # Grammar is important.
        configurations = 'configuration' if num == 1 else 'configurations'
        adjective = 'this' if num == 1 else 'these'
        noun = 'masternode' if num == 1 else 'masternodes'
        words = {'adjective': adjective, 'configurations': configurations, 'noun': noun, 'num': num,}
        msg = '{num} {noun} {configurations} imported.\n\nPlease wait for transactions involving {adjective} {configurations} to be retrieved before activating {adjective} {noun}.'.format(**words)
        self.show_message(_(msg), title=_('Success'))

    
    def masternode_do_activate(self):
        '''
        if self.check_status(obj):
            self.show_message('Masternode has already been activated')
            return
        if len(self.alias_e.text()) == 0:
            self.show_message(_("Please Enter Alias"))
            return
        if self.check_alias(self.screen.alias, obj):
            self.show_message(_('A masternode with alias "%s" already exists' % self.screen.alias))
            return
        
        if not self.check_delegate(self.screen.delegate):
            self.app.show_info(_("InValid Delegate Key"))
            return
        if not self.check_collateral(self.screen.collateral):
            self.app.show_info(_("Please First Scan"))
            return
        '''
        self.sign_announce()
                                
    def check_delegate(self, delegate_priv):
        try:
            txin_type, key, is_compressed = bitcoin.deserialize_privkey(delegate_priv)
            delegate_pub = ecc.ECPrivkey(key).get_public_key_hex(compressed=is_compressed)
            return True
        except:
            return False
        
    def check_collateral(self, collateral):
        if len(collateral) == 0:
            return False
        return True   

    def sign_announce(self, key=None):
        """Sign an announce for alias. This is called by SignAnnounceWidget."""
        
        if key is None:
            alias = self.alias_e.text()
            try:
                delegate = self.wallet.import_masternode_delegate(self.delegate_e.text())
            except AlreadyHaveAddress:
                txin_type, key, is_compressed = bitcoin.deserialize_privkey(self.delegate_e.text())
                delegate = ecc.ECPrivkey(key).get_public_key_hex(compressed=is_compressed)
            except Exception as e:
                self.show_error(_("InValid Deletate Key"))
                return
                    
            try:
                collateral = self.wallet.get_public_keys(self.address_e.text())[0]            
            except Exception as e:
                self.app.show_error(_("InValid Collateral Key"))
                return
            
            try:
                txid = self.txid_e.text()
                index = self.index_e.text()
                key = txid + "-" + str(index)
                vin = {'prevout_hash': txid, 'prevout_n': int(index)}    
                mn = MasternodeAnnounce(alias=alias, vin=vin, addr=NetworkAddress(),
                                        collateral_key=collateral, delegate_key=delegate, sig='', sig_time=0,
                                        protocol_version=31800, last_ping=MasternodePing(),announced=False)             
                #self.masternode_manager.add_masternode(mn, save=True)            
            except Exception as e:
                self.show_error(str(e))
                #self.app.masternode_manager.rename_masternode(mn)
                
            tx_height = self.wallet.get_tx_height(txid)
            if tx_height.conf < MASTERNODE_MIN_CONFIRMATIONS:
                self.show_error(_('Collateral payment must have at least %d confirmations (current: %d)' %(MASTERNODE_MIN_CONFIRMATIONS, tx_height.conf))) 
                return                    
        mn1 = self.masternode_manager.get_masternode(key)
        if not (mn1 is None):
            if mn1.status == 'PRE_ENABLED' or mn1.status == 'ENABLED':
                self.show_message(_('Masternode has already been activated')) 
                return
        
        pw = None
        if self.masternode_manager.wallet.has_password():
            pw = self.password_dialog(msg=_('Please enter your password to activate masternode "%s".') % alias)
            if pw is None:
                return
        
        mn = self.masternode_manager.get_masternode(key)
        
        def sign_thread():
            return self.masternode_manager.sign_announce(key, pw)

        def on_sign_successful(mn):
            self.print_msg('Successfully signed Masternode Announce.')
            self.send_announce(key)
        # Proceed to broadcasting the announcement, or re-enable the button.
        def on_sign_error(err):
            self.show_error('Error signing MasternodeAnnounce:')
            # Print traceback information to error log.
            self.print_error(''.join(traceback.format_tb(err[2])))
            self.print_error(''.join(traceback.format_exception_only(err[0],
                                                                      err[1])))

        WaitingDialog(self, _('Signing Masternode Announce...'), sign_thread, on_sign_successful, on_sign_error)

    def send_announce(self, key):
        """Send an announce for a masternode."""
        def send_thread():
            return self.masternode_manager.send_announce(key)

        def on_send_successful(result):
            errmsg, was_announced = result
            if errmsg:
                self.print_error(f'Failed to broadcast MasternodeAnnounce: '
                                  f'{errmsg}')
                self.show_critical(errmsg, title=_('Error Sending'))
            elif was_announced:
                self.print_msg(f'Successfully broadcasted '
                                 f'MasternodeAnnounce for "{key}"')
                self.show_message(_('Masternode activated successfully.'),
                                  title=_('Success'))            
            self.masternode_list.update()
            self.masternode_manager.update_masternodes_status(update=True)

        def on_send_error(err):
            self.print_error('Error sending Masternode Announce message:')
            # Print traceback information to error log.
            self.print_error(''.join(traceback.format_tb(err[2])))
            self.print_error(''.join(traceback.format_exception_only(err[0],
                                                                      err[1])))
            self.masternode_list.update()
            
        self.print_msg('Sending Masternode Announce message...')
        WaitingDialog(self, _('Broadcasting masternode...'), send_thread, on_send_successful, on_send_error)

    def masternode_hide(self):
        show = self.masternode_hide_button.text()
        if show == "Hide":
            self.masternode_hide_button.setText("Show")
            self.alias_e.hide()
            self.alias_label.hide()
            self.ip_e.hide()
            self.ip_label.hide()
            self.port_e.hide()
            self.port_label.hide()
            
            self.txid_e.hide()
            self.txid_label.hide()
            
            self.index_e.hide()
            self.index_label.hide()
            self.address_e.hide()
            self.address_label.hide()
            
            self.masternode_label.hide()
            self.masternode_combo.hide()
            self.delegate_e.hide()
            self.delegate_label.hide()
                        
            #self.masternode_refresh_button.hide()
            #self.masternode_import_button.hide()
            #self.masternode_generate_button.hide()
            self.masternode_save_button.hide()
            self.masternode_clear_button.hide()
            self.masternode_activate_button.hide()
            #self.masternode_monit_button.hide()
            self.masternode_scan_button.hide()
            #self.masternode_remove_button.hide()
        else:
            self.masternode_hide_button.setText("Hide")
            self.alias_e.show()
            self.alias_label.show()
            self.ip_e.show()
            self.ip_label.show()
            self.port_e.show()
            self.port_label.show()
            
            self.txid_e.hide()
            self.txid_label.hide()
            
            self.index_e.show()
            self.index_label.show()
            self.address_e.show()
            self.address_label.show()
            
            self.masternode_label.show()
            self.masternode_combo.show()
            self.delegate_e.show()
            self.delegate_label.show()

            #self.masternode_refresh_button.show()
            #self.masternode_import_button.show()
            #self.masternode_generate_button.show()
            self.masternode_save_button.show()
            self.masternode_clear_button.show()
            self.masternode_activate_button.show()
            #self.masternode_monit_button.show()
            self.masternode_scan_button.show()
            #self.masternode_remove_button.show()            

    def check_register(self):
        register_info = None #self.wallet.storage.get('user_register')
        try:
            if register_info is None:
                mobilephone, pw = self.login_dialog('')
                pw1 = pw
                if (pw is None) or (mobilephone is None) :
                    # User cancelled password input
                    return False
                if len(mobilephone) != 11:
                    self.show_message(_('Mobile must be 11 digits!'),
                                          title=_('Error'))                    
                    return False
                
                if pw != pw1:  
                    self.show_message(_('Password mismatch!'),
                                          title=_('Error'))                    
                    return False                
                
                if len(pw) < 6:
                    self.show_message(_('Password length not less than 6 digits!'),
                                          title=_('Error'))                    
                    return False
                
                bregister = True
            else:
                '''
                mobilephone, pw = self.login_dialog('')
                if (pw is None) or (mobilephone is None) :
                    # User cancelled password input
                    return False
                pw1 = None
                '''
                bregister = False                                
        except Exception as e:
            self.show_error(str(e))
            return False
            
        def register_thread():
            address = self.get_app_new_address()
            self.masternode_manager.check_register(register_info, mobilephone, pw, pw1, bregister, address)                    
            #return self.client.post_register(mobilephone, address, pw)
            return self.client.post_mobilephone_checkcode(mobilephone)
                        
        def on_success(status):
            if not status :                        
                self.show_message(_('Account Login failed!'), title=_('Error'))
            else:
                self.show_message(_('Account Login successful!'),
                                      title=_('Success'))
            
        def on_error(msg):
            self.show_message(_('Account Login failure'), title=_('Error'))
            
        if bregister:        
            WaitingDialog(self, _('Login...'), register_thread, on_success, on_error)  
        else:
            return True    
                        
    def paymode_state(self, btn):        
        if btn.text() == 'WeiXin' or btn.text() == 'ZhiFuBao':
            if btn.isChecked():
                self.payment_bank_e.hide()
                self.payment_bank_label.hide()
                
        if btn.text() == "Bank":
            if btn.isChecked():
                self.payment_bank_e.show()
                self.payment_bank_label.show()

    def create_conversion_tab(self):
        # A 4-column grid layout.  All the stretch is in the last column.
        # The exchange rate plugin adds a fiat widget in column 2
        
        self.conversion_grid = grid = QGridLayout()
        grid.setSpacing(8)

        self.payment_mode_label = QLabel(_('Payment mode'))
        self.btn_weixin = QRadioButton('WeiXin')
        self.btn_weixin.setChecked(True)
        self.btn_weixin.toggled.connect(lambda :self.paymode_state(self.btn_weixin))
        self.btn_zhifubao = QRadioButton('ZhiFuBao')
        self.btn_zhifubao.setChecked(False)
        self.btn_zhifubao.toggled.connect(lambda :self.paymode_state(self.btn_zhifubao))
        self.btn_bank = QRadioButton('Bank')
        self.btn_bank.setChecked(False)
        self.btn_bank.toggled.connect(lambda :self.paymode_state(self.btn_bank))                
        grid.addWidget(self.payment_mode_label, 1, 0)
        
        pay_controls = QWidget()
        pay_hbox = QHBoxLayout(pay_controls)
        pay_hbox.setContentsMargins(0, 0, 0, 0)
        pay_hbox.addWidget(self.btn_weixin)
        pay_hbox.addWidget(self.btn_zhifubao)
        pay_hbox.addWidget(self.btn_bank)
        pay_hbox.addStretch(1)
        grid.addWidget(pay_controls, 1, 1)
        
        self.account_combo_label = QLabel(_('Select Account'))
        self.account_combo = QComboBox()
        self.account_combo.currentIndexChanged.connect(
                                    lambda: self.account_change(self.account_combo.currentIndex()))        
        grid.addWidget(self.account_combo_label, 1, 2)
        grid.addWidget(self.account_combo, 1, 3, 1, -1)
        

        self.payment_name_e = MyLineEdit()
        self.payment_name_label = QLabel(_('Payee Name'))
        grid.addWidget(self.payment_name_label, 2, 0)
        grid.addWidget(self.payment_name_e, 2, 1)

        self.payment_bank_e = MyLineEdit()
        self.payment_bank_label = QLabel(_('Receiving Bank'))
        grid.addWidget(self.payment_bank_label, 2, 2)
        grid.addWidget(self.payment_bank_e, 2, 3, 1, -1)
        self.payment_bank_e.setVisible(False)
        self.payment_bank_label.setVisible(False)

        self.payment_account_e = MyLineEdit()
        self.payment_account_label = QLabel(_('Receiving Account'))
        grid.addWidget(self.payment_account_label, 3, 0)
        grid.addWidget(self.payment_account_e, 3, 1, 1, -1)

        from .paytoedit import PayToEdit
        self.payee_conversion_e = PayToEdit(self)
        self.payee_conversion_e.setReadOnly(True)
        self.payee_conversion_label = QLabel(_('Destroy Address'))
        grid.addWidget(self.payee_conversion_label, 4, 0)
        grid.addWidget(self.payee_conversion_e, 4, 1, 1, -1)
                  
        self.amount_conversion_e = BTCAmountEdit(self.get_decimal_point)
        msg = _('Amount to be sent.') + '\n\n' \
              + _('The amount will be displayed in red if you do not have enough funds in your wallet.') + ' ' \
              + _('Note that if you have frozen some of your addresses, the available funds will be lower than your total balance.') + '\n\n' \
              + _('Keyboard shortcut: type "!" to send all your coins.')
        self.amount_conversion_label = HelpLabel(_('Amount'), msg)
        grid.addWidget(self.amount_conversion_label, 5, 0)

        self.payee_conversion_e.setText(constants.DESTROY_ADDRESS)
        self.payee_conversion_e.setAmount(self.amount_conversion_e)

        self.fiat_send_conversion_e = AmountEdit(self.fx.get_currency if self.fx else '')
        if not self.fx or not self.fx.is_enabled():
            self.fiat_send_conversion_e.setVisible(False)
        self.amount_conversion_e.frozen.connect(
            lambda: self.fiat_send_conversion_e.setFrozen(self.amount_conversion_e.isReadOnly()))

        self.max_conversion_button = EnterButton(_("Max"), self.spend_conversion_max)
        self.max_conversion_button.setFixedWidth(140)
        self.max_conversion_button.setCheckable(True)
                
        amount_controls = QWidget()
        amount_hbox = QHBoxLayout(amount_controls)
        amount_hbox.setContentsMargins(0, 0, 0, 0)
        amount_hbox.addWidget(self.amount_conversion_e)
        amount_hbox.addWidget(self.fiat_send_conversion_e)
        amount_hbox.addWidget(self.max_conversion_button)
        amount_hbox.addStretch(1)
        grid.addWidget(amount_controls, 5, 1)
                
        self.estimation_e = MyLineEdit()
        self.estimation_e.setReadOnly(True)
        self.estimation_label = QLabel(_('Estimation'))
        grid.addWidget(self.estimation_label, 5, 2)
        grid.addWidget(self.estimation_e, 5, 3, 1, -1)            
        
        msg = _('Bitcoin transactions are in general not free. A transaction fee is paid by the sender of the funds.') + '\n\n'\
              + _('The amount of fee can be decided freely by the sender. However, transactions with low fees take more time to be processed.') + '\n\n'\
              + _('A suggested fee is automatically added to this field. You may override it. The suggested fee increases with the size of the transaction.')
        self.fee_conversion_label = HelpLabel(_('Fee'), msg)
        self.fee_conversion_label1 = HelpLabel(_('Fee'), msg)
        
        def fee_cb(dyn, pos, fee_rate):
            if dyn:
                if self.config.use_mempool_fees():
                    self.config.set_key('depth_level', pos, False)
                else:
                    self.config.set_key('fee_level', pos, False)
            else:
                self.config.set_key('fee_per_kb', fee_rate, False)

            if fee_rate:
                fee_rate = Decimal(fee_rate)
                self.feerate_conversion_e.setAmount(quantize_feerate(fee_rate / 1000))
            else:
                self.feerate_conversion_e.setAmount(None)
            self.fee_conversion_e.setModified(False)

            self.fee_conversion_slider.activate()
            self.spend_conversion_max() if self.max_conversion_button.isChecked() else self.update_fee()

        self.fee_conversion_slider = FeeSlider(self, self.config, fee_cb)
        self.fee_conversion_slider.setFixedWidth(140)

        def on_fee_or_feerate(edit_changed, editing_finished):
            edit_other = self.feerate_conversion_e if edit_changed == self.fee_conversion_e else self.fee_conversion_e
            if editing_finished:
                if edit_changed.get_amount() is None:
                    # This is so that when the user blanks the fee and moves on,
                    # we go back to auto-calculate mode and put a fee back.
                    edit_changed.setModified(False)
            else:
                # edit_changed was edited just now, so make sure we will
                # freeze the correct fee setting (this)
                edit_other.setModified(False)
            self.fee_conversion_slider.deactivate()
            self.update_fee()

        class TxSizeLabel(QLabel):
            def setAmount(self, byte_size):
                self.setText(('x   %s bytes   =' % byte_size) if byte_size else '')

        self.size_conversion_e = TxSizeLabel()
        self.size_conversion_e.setAlignment(Qt.AlignCenter)
        self.size_conversion_e.setAmount(0)
        self.size_conversion_e.setFixedWidth(140)
        self.size_conversion_e.setStyleSheet(ColorScheme.DEFAULT.as_stylesheet())

        self.feerate_conversion_e = FeerateEdit(lambda: 0)
        self.feerate_conversion_e.setAmount(self.config.fee_per_byte())
        self.feerate_conversion_e.textEdited.connect(partial(on_fee_or_feerate, self.feerate_conversion_e, False))
        self.feerate_conversion_e.editingFinished.connect(partial(on_fee_or_feerate, self.feerate_conversion_e, True))

        self.fee_conversion_e = BTCAmountEdit(self.get_decimal_point)
        self.fee_conversion_e.textEdited.connect(partial(on_fee_or_feerate, self.fee_conversion_e, False))
        self.fee_conversion_e.editingFinished.connect(partial(on_fee_or_feerate, self.fee_conversion_e, True))

        def feerounding_onclick():
            text = (self.feerounding_text + '\n\n' +
                    _('To somewhat protect your privacy, Electrum tries to create change with similar precision to other outputs.') + ' ' +
                    _('At most 100 satoshis might be lost due to this rounding.') + ' ' +
                    _("You can disable this setting in '{}'.").format(_('Preferences')) + '\n' +
                    _('Also, dust is not kept as change, but added to the fee.')  + '\n' +
                    _('Also, when batching RBF transactions, BIP 125 imposes a lower bound on the fee.'))
            self.show_message(title=_('Fee rounding'), msg=text)

        self.feerounding_conversion_icon = QPushButton(read_QIcon('info.png'), '')
        self.feerounding_conversion_icon.setFixedWidth(20)
        self.feerounding_conversion_icon.setFlat(True)
        self.feerounding_conversion_icon.clicked.connect(feerounding_onclick)
        self.feerounding_conversion_icon.setVisible(False)

        self.connect_fields(self, self.amount_conversion_e, self.fiat_send_conversion_e, self.fee_conversion_e)
        
        grid.addWidget(self.fee_conversion_label, 6, 0)                
        fee_controls = QWidget()
        fee_hbox = QHBoxLayout(fee_controls)
        fee_hbox.setContentsMargins(0, 0, 0, 0)
        fee_hbox.addWidget(self.feerate_conversion_e)
        fee_hbox.addWidget(self.size_conversion_e)
        fee_hbox.addWidget(self.fee_conversion_e)
        fee_hbox.addWidget(self.feerounding_conversion_icon)
        fee_hbox.addStretch(1)
        grid.addWidget(fee_controls, 6, 1)
        
        grid.addWidget(self.fee_conversion_label1, 7, 0)
        grid.addWidget(self.fee_conversion_slider, 7 ,1)
        
        if not self.config.get('show_fee', False):
            self.show_conversion_fee(False, True)

        self.conversion_hide_button = EnterButton(_("Hide"), self.conversion_hide)
        self.conversion_clear_button = EnterButton(_("Clear"), self.do_conversion_clear)
        self.conversion_preview_button = EnterParamsButton(_("Preview"), self.do_preview, True, 'conversion')
        self.conversion_preview_button.setToolTip(_('Display the details of your transaction before signing it.'))
        self.conversion_button = EnterButton(_("Conversion"), self.do_conversion_send) 
        self.conversion_search_button = EnterButton(_("Search"), self.do_conversion_search)
        self.conversion_back_button = EnterButton(_("Back Page"), self.do_conversion_back)
        self.conversion_next_button = EnterButton(_("Next Page"), self.do_conversion_next)
        self.conversion_back_button.setEnabled(False)
        self.conversion_next_button.setEnabled(False)
        
        buttons = QHBoxLayout()
        buttons.addWidget(self.conversion_hide_button)
        buttons.addWidget(self.conversion_clear_button)
        buttons.addWidget(self.conversion_preview_button)
        buttons.addWidget(self.conversion_button)
        buttons.addStretch(1)
        buttons.addWidget(self.conversion_back_button)
        buttons.addWidget(self.conversion_next_button)
        buttons.addWidget(self.conversion_search_button)
        grid.addLayout(buttons, 8, 1, 1, 3)

        self.amount_conversion_e.shortcut.connect(self.spend_conversion_max)
        self.amount_conversion_e.textEdited.connect(self.update_fee)

        def reset_max(text):
            self.max_conversion_button.setChecked(False)
            enable = not bool(text) and not self.amount_conversion_e.isReadOnly()
            self.max_conversion_button.setEnabled(enable)
        self.amount_conversion_e.textEdited.connect(reset_max)
        self.fiat_send_conversion_e.textEdited.connect(reset_max)

        def entry_changed():
            text = ""

            amt_color = ColorScheme.DEFAULT
            fee_color = ColorScheme.DEFAULT
            feerate_color = ColorScheme.DEFAULT

            if self.not_enough_funds:
                amt_color, fee_color = ColorScheme.RED, ColorScheme.RED
                feerate_color = ColorScheme.RED
                text = _("Not enough funds")
                c, u, x = self.wallet.get_frozen_balance()
                if c+u+x:
                    text += " ({} {} {})".format(
                        self.format_amount(c + u + x).strip(), self.base_unit(), _("are frozen")
                    )

            # blue color denotes auto-filled values
            elif self.fee_e.isModified():
                feerate_color = ColorScheme.BLUE
            elif self.feerate_e.isModified():
                fee_color = ColorScheme.BLUE
            elif self.amount_e.isModified():
                fee_color = ColorScheme.BLUE
                feerate_color = ColorScheme.BLUE
            else:
                amt_color = ColorScheme.BLUE
                fee_color = ColorScheme.BLUE
                feerate_color = ColorScheme.BLUE

            self.statusBar().showMessage(text)
            self.amount_conversion_e.setStyleSheet(amt_color.as_stylesheet())
            self.fee_conversion_e.setStyleSheet(fee_color.as_stylesheet())
            self.feerate_conversion_e.setStyleSheet(feerate_color.as_stylesheet())

        self.amount_conversion_e.textChanged.connect(entry_changed)
        self.fee_conversion_e.textChanged.connect(entry_changed)
        self.feerate_conversion_e.textChanged.connect(entry_changed)        
        
        vbox0 = QVBoxLayout()
        vbox0.addLayout(grid)
        vbox1 = QVBoxLayout()
        hbox = QHBoxLayout()
        hbox.addLayout(vbox0)
        
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.addLayout(hbox)
        
        self.conversion_list = l = ConversionList(self)
        vbox1.addWidget(l)
        vbox.addLayout(vbox1)                
        run_hook('create_conversion_tab', grid)
        return w

    def conversion_hide(self):
        show = self.conversion_hide_button.text()
        if show == "Hide":
            self.conversion_hide_button.setText("Show")
            self.payment_mode_label.hide()
            self.btn_weixin.hide()
            self.btn_zhifubao.hide()
            self.btn_bank.hide()
            self.account_combo_label.hide()
            self.account_combo.hide()
            
            self.payment_name_label.hide()
            self.payment_name_e.hide()
            self.payment_bank_label.hide()
            self.payment_bank_e.hide()
            self.payment_account_label.hide()
            self.payment_account_e.hide()
            
            self.payee_conversion_label.hide()
            self.payee_conversion_e.hide()
            
            self.amount_conversion_label.hide()
            self.amount_conversion_e.hide()
            self.max_conversion_button.hide()
            self.estimation_label.hide()
            self.estimation_e.hide()
                       
            self.show_conversion_fee(False, False)
            
            self.conversion_clear_button.hide()
            self.conversion_preview_button.hide()
            self.conversion_button.hide()            
        else:
            self.conversion_hide_button.setText("Hide")
            
            self.payment_mode_label.show()
            self.btn_weixin.show()
            self.btn_zhifubao.show()
            self.btn_bank.show()
            
            self.account_combo_label.show()
            self.account_combo.show()
            
            self.payment_name_label.show()
            self.payment_name_e.show()
            
            if self.btn_bank.isChecked():
                self.payment_bank_label.show()
                self.payment_bank_e.show()
            
            self.payment_account_label.show()
            self.payment_account_e.show()
            
            self.payee_conversion_label.show()
            self.payee_conversion_e.show()
            
            self.amount_conversion_label.show()
            self.amount_conversion_e.show()
            self.max_conversion_button.show()
            self.estimation_label.show()
            self.estimation_e.show()

            if not self.config.get('show_fee', False):            
                self.show_conversion_fee(False, True)
            else:
                self.show_conversion_fee(True, True)
            
            self.conversion_clear_button.show()
            self.conversion_preview_button.show()
            self.conversion_button.show()
            
    def do_conversion_clear(self):
        self.btn_weixin.setChecked(True)
        self.payment_name_e.setText('')
        self.payment_bank_e.setText('')
        self.payment_account_e.setText('')
        self.amount_conversion_e.setText('')
        self.estimation_e.setText('')
        self.size_conversion_e.setText('')
        self.estimation_e.setText('')
        self.feerate_conversion_e.setText('')
        
    def do_conversion_search(self):
        def search_thread():
            return self.client.do_search_conversion()
                        
        def on_success(response):
            self.search_state_update()
            self.conversion_list.update()
            
        def on_error(msg):
            self.show_message("conversion search fail")
            
        WaitingDialog(self, _('Conversion search...'), search_thread, on_success, on_error)        
        
    def do_conversion_back(self):
        def search_thread():
            return self.client.do_back_conversion()        
                        
        def on_success(response):
            self.search_state_update()
            self.conversion_list.update()
            
        def on_error(msg):
            self.show_message("conversion search fail")
            
        WaitingDialog(self, _('Conversion search...'), search_thread, on_success, on_error)        

    def do_conversion_next(self):
        def search_thread():
            return self.client.do_next_conversion()            
                        
        def on_success(response):
            self.search_state_update()
            self.conversion_list.update()
            
        def on_error(msg):
            self.show_message("conversion search fail")
            
        WaitingDialog(self, _('Conversion search...'), search_thread, on_success, on_error)        

    def do_conversion_send(self):
        if self.client is None:
            return
        if self.client.money_ratio == 0:
            self.show_message(_('Value not yet determined, please wait!'))
            return
        
        is_commit, self.conversion_data = self.client.get_conversion_commit()
        if is_commit:
            self.conversion_retrys = 0
            tx = self.wallet.db.get_transaction(self.conversion_data['txId'])    
            self.conversion_list_update(tx)
            return
                
        try:
            self.check_conversion()
        except Exception as e:
            self.show_error(str(e))
            return
                
        self.conversion_data ={}
        self.conversion_data['createTime'] = self.client.get_current_time() 
        self.conversion_data['phone'] = self.client.get_phone()
        self.conversion_data['dstAccount'] = constants.DESTROY_ADDRESS
        self.conversion_data['payWay'] = self.get_pay_mode()
        self.conversion_data['payName'] = self.payment_name_e.text()
        self.conversion_data['payAccount'] = self.payment_account_e.text()
        self.conversion_data['payBank'] = self.payment_bank_e.text()
        self.conversion_data['payBankSub'] = ''
        self.conversion_data['remark'] = ''        
        
        self.do_send(preview=False, mode='conversion')
    
    def search_state_update(self):
        if self.client is None:
            self.conversion_back_button.setEnabled(False)
            self.conversion_next_button.setEnabled(False)
        else:
            total_page = (self.client.conversion_total + (self.client.conversion_page_size -1))//self.client.conversion_page_size
            if total_page <= 1 :
                self.conversion_back_button.setEnabled(False)
                self.conversion_next_button.setEnabled(False)
            elif self.client.conversion_cur_page == 1:
                self.conversion_back_button.setEnabled(False)
                self.conversion_next_button.setEnabled(True)
            elif self.client.conversion_cur_page == total_page:
                self.conversion_back_button.setEnabled(True)
                self.conversion_next_button.setEnabled(False)
            elif self.client.conversion_cur_page < total_page:
                self.conversion_back_button.setEnabled(True)
                self.conversion_next_button.setEnabled(True)
                
    def do_get_conversion(self):
        response = self.client.get_conversion()
        pass
    
    def do_get_masternode(self):
        response = self.client.get_masternodes()
        pass
    
    def do_get_account(self):
        response = self.client.get_account()
        pass
    
    def conversion_list_update(self, tx):   
        tx = copy.deepcopy(tx)  # type: Transaction
        try:
            tx.deserialize()
        except BaseException as e:
            raise SerializationError(e)    
        
        format_amount = self.format_amount_and_units
        tx_details = self.wallet.get_tx_info(tx)
        amount, fee = tx_details.amount, tx_details.fee
        txid = tx.txid()
        
        destroy_address = constants.DESTROY_ADDRESS
        is_destroy = False
        amount = 0
        for output in tx.outputs():
            if output.address == destroy_address:
                amount = output.value
                is_destroy = True
                break
        if not is_destroy: 
            return
        
        for item in tx.inputs():
            input_address = item['address']
            break
                 
         
        payWay = self.conversion_data['payWay']
        payName = self.conversion_data['payName']
        payAccount = self.conversion_data['payAccount']
        payBank = self.conversion_data['payBank']
        payBankSub = 'sub'
        remark = ''
        def conversion_thread():
            return self.client.post_conversion(txid, amount, fee, destroy_address, input_address, payWay, payName, payAccount, payBank, payBankSub, remark)
            
        def on_success(response):
            if response['code'] == 200:    
                self.client.payaccount_add(payName, payAccount, payBank, payWay)
                self.get_account_combo()
                self.client.conversion_commit_send(response['data'])
                self.show_message(_('Conversion successful!'))
            elif response['code'] == 901:
                self.client.payaccount_add(payName, payAccount, payBank, payWay)
                self.wallet.storage.put('conversion_masternode', {})        
                self.get_account_combo()
                self.show_message(_('Conversion successful!'))
            else:
                self.conversion_data['txFlag'] = '-100'
                self.conversion_data['createTime'] = self.client.get_current_time() 
                self.conversion_data['txId'] = txid
                self.conversion_data['amount'] = amount
                self.conversion_data['fee'] = fee        
                
                self.wallet.storage.put('conversion_masternode', self.conversion_data)            
                self.show_error(response['pagePrompt'])
            
            self.conversion_list.update()
            
        def on_error(msg):
            self.show_error(msg)
        
        WaitingDialog(self, _('Convert...'),
                      conversion_thread, on_success, on_error)
                        
    def get_pay_mode(self):
        if self.btn_bank.isChecked():
            return "1"
        
        if self.btn_weixin.isChecked():
            return "2"
        
        if self.btn_zhifubao.isChecked():
            return "3"
    
    def set_pay_mode(self, text):
        if text == '1':
            self.btn_bank.setChecked(True)
            return 

        if text == '2':
            self.btn_weixin.setChecked(True)
            return 

        if text == '3':
            self.btn_zhifubao.setChecked(True)
            return 
        
    def get_conversion_list(self):
        if self.client is None:
            return []
        return self.client.conversion_list
            
    def check_conversion(self):
        if len(self.payment_name_e.text()) == 0:
            raise Exception("name is present")
        if len(self.payment_account_e.text()) == 0:            
            raise Exception("account is present")
        if self.btn_bank.isChecked():
            if len(self.payment_bank_e.text()) == 0:            
                raise Exception("bank is present")
        if len(self.amount_conversion_e.text()) == 0:
            raise Exception("amount is unpresent")

    def get_account_combo(self):
        self.account_combo.clear()
        index = 0
        for key in self.client.conversion_account.keys():
            name, bank, mode = self.client.conversion_account[key]
            self.account_combo.addItem(name + '-' + key)
            #self.account_combo.setItemData(index, (bank, mode))
        self.account_combo.setCurrentIndex(0)
                           
    def account_change(self, index):
        key = self.account_combo.currentText()
        if key == 'None' or key == '':
            return
        name, account = key.split("-")
        name, bank, mode = self.client.conversion_account[account]
        self.payment_name_e.setText(name)
        self.payment_account_e.setText(account)
        self.payment_bank_e.setText(bank)
        self.set_pay_mode(str(mode))
            
        
    def show_conversion_fee(self, fee_show, slide_show=True):
        if fee_show:
            self.fee_conversion_label.show()                
            self.size_conversion_e.show()
            self.feerate_conversion_e.show()
            self.fee_conversion_e.show()
            self.feerounding_conversion_icon.show()
            self.fee_conversion_label1.setText('')
        else:
            self.fee_conversion_label.hide()                
            self.size_conversion_e.hide()
            self.feerate_conversion_e.hide()
            self.fee_conversion_e.hide()
            self.feerounding_conversion_icon.hide()
            self.fee_conversion_label1.setText(_('Fee'))
        
        if slide_show:
            self.fee_conversion_label1.show()                
            self.fee_conversion_slider.show()
        else:
            self.fee_conversion_label1.hide()                
            self.fee_conversion_slider.hide()

    def get_app_new_address(self):
        if not self.wallet:
            return ''
        try:
            addr = self.wallet.get_unused_address()
            if addr is None:
                addr = self.wallet.get_receiving_address() or ''
        except InternalAddressCorruption as e:
            addr = ''
            self.show_error(str(e))
            send_exception_to_crash_reporter(e)
        return addr