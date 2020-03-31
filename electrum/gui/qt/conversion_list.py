#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2015 Thomas Voegtlin
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

import webbrowser
from enum import IntEnum

from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt, QPersistentModelIndex, QModelIndex
from PyQt5.QtWidgets import (QAbstractItemView, QMenu)

from electrum.i18n import _
from electrum.bitcoin import is_address
from electrum.util import block_explorer_URL
from electrum.plugin import run_hook

from .util import MyTreeView, import_meta_gui, export_meta_gui

from electrum.util import bfh, bh2u
from electrum.bitcoin import public_key_to_p2pkh, COIN

import time, datetime

STATUS_ICONS = [
    "unconfirmed.png",
    "confirmed.png",
]

class ConversionList(MyTreeView):

    class Columns(IntEnum):
        STATUS = 0
        CDATE = 1
        TXID = 2
        PAYWAY = 3
        PAYNAME = 4
        PAYACCOUNT = 5
        PAYBANK = 6
        AMOUNT = 7
        MONEY = 8

    headers = {
        Columns.STATUS: _('Status'),
        Columns.CDATE: _('Date'),
        Columns.TXID: _('TxId'),
        Columns.PAYWAY: _('PayWay'),
        Columns.PAYNAME: _('PayName'),
        Columns.PAYACCOUNT: _('PayAccount'),
        Columns.PAYBANK: _('PayBank'),
        Columns.AMOUNT: _('Amount'),        
        Columns.MONEY: _('CashMoney'),        
    }
    filter_columns = [Columns.CDATE, Columns.TXID]    
    
    def __init__(self, parent):
        super().__init__(parent, self.create_menu,
                         stretch_column=self.Columns.CDATE,
                         editable_columns=[self.Columns.CDATE], tv=self)
        self.setModel(QStandardItemModel(self))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSortingEnabled(True)
        self.update()

    def on_edited(self, idx, user_role, text):
        self.update()

    def create_menu(self, position):
        menu = QMenu()
        idx = self.indexAt(position)
        column = idx.column() or self.Columns.TXID
        selected_keys = []
        for s_idx in self.selected_in_column(self.Columns.TXID):
            sel_key = self.model().itemFromIndex(s_idx).data(Qt.UserRole)
            selected_keys.append(sel_key)
        if selected_keys and idx.isValid():
            column_title = self.model().horizontalHeaderItem(column).text()
            column_data = '\n'.join(self.model().itemFromIndex(s_idx).text()
                                    for s_idx in self.selected_in_column(column))
            menu.addAction(_("Copy {}").format(column_title), lambda: self.parent.app.clipboard().setText(column_data))
            #menu.addAction(_("Conversion Commit"), lambda: self.parent.conversion_activate(selected_keys))

        run_hook('create_conversion_menu', menu, selected_keys)
        menu.exec_(self.viewport().mapToGlobal(position))

    def update(self):
        current_key = self.current_item_user_role(col=self.Columns.TXID)
        self.model().clear()
        self.update_headers(self.__class__.headers)
        set_current = None
        
        conversion_txid = ''
        is_commit = False
        if not self.parent.client is None:
            is_commit, conversion_data = self.parent.client.get_conversion_commit()
            if is_commit:
                conversion_txid = conversion_data.get('txId') if not conversion_data.get('txId') is None else ''                        
        
        conversion_list = self.parent.get_conversion_list()
        if len(conversion_list) > 0:
            start = (self.parent.client.conversion_cur_page-1) * self.parent.client.conversion_page_size 
            stop = start + self.parent.client.conversion_page_size
            conversion_list = conversion_list[start:stop]
        for data in conversion_list:
            status = data.get('txFlag') if not data.get('txFlag') is None else ''
            sdate = data.get('createTime') if not data.get('createTime') is None else ''
            txId = data.get('txId') if not data.get('txId') is None else ''
            payWay = data.get('payWay') if not data.get('payWay') is None else ''
            payName = data.get('payName') if not data.get('payName') is None else ''
            payAccount = data.get('payAccount') if not data.get('payAccount') is None else ''
            payBank = data.get('payBank') if not data.get('payBank') is None else ''
            payBankSub = data.get('payBankSub', '') if not data.get('payBankSub') is None else ''
            payBank += payBankSub
            amount = str(data.get('amount')/COIN) if not data.get('amount') is None else ''
            money = str(data.get('cashMoney')/COIN) if not data.get('cashMoney') is None else ''
            
            if is_commit:
                if txId == conversion_txid:
                    is_commit = False
                    self.parent.wallet.storage.put('conversion_masternode', {})
            
            items = [QStandardItem(x) for x in (status, sdate, txId, payWay, payName, payAccount, payBank, amount, money)]
            items[self.Columns.TXID].setEditable(False)
            items[self.Columns.TXID].setData(txId, Qt.UserRole)
            row_count = self.model().rowCount()
            self.model().insertRow(row_count, items)
            self.disable_editability()            
            
        if is_commit:
            status = conversion_data.get('txFlag') if not conversion_data.get('txFlag') is None else ''
            sdate = conversion_data.get('createTime') if not conversion_data.get('createTime') is None else ''
            txId = conversion_data.get('txId') if not conversion_data.get('txId') is None else ''
            payWay = conversion_data.get('payWay') if not conversion_data.get('payWay') is None else ''
            payName = conversion_data.get('payName') if not conversion_data.get('payName') is None else ''
            payAccount = conversion_data.get('payAccount') if not conversion_data.get('payAccount') is None else ''
            payBank = conversion_data.get('payBank') if not conversion_data.get('payBank') is None else ''
            payBankSub = conversion_data.get('payBankSub', '') if not conversion_data.get('payBankSub') is None else ''
            payBank += payBankSub
            amount = str(conversion_data.get('amount')/COIN) if not conversion_data.get('amount') is None else ''
            money = ''
            
            items = [QStandardItem(x) for x in (status, sdate, txId, payWay, payName, payAccount, payBank, amount, money)]
            items[self.Columns.TXID].setEditable(False)
            items[self.Columns.TXID].setData(txId, Qt.UserRole)
            row_count = self.model().rowCount()
            self.model().insertRow(row_count, items)
            self.disable_editability()            
            
        
        self.set_current_idx(set_current)
        # FIXME refresh loses sort order; so set "default" here:
        self.sortByColumn(self.Columns.CDATE, Qt.DescendingOrder)
        self.filter()
        run_hook('update_conversion_tab', self)

    def on_clicked(self, idx):
        #alias = self.model().index(idx.row(),0).data()
        pass
        