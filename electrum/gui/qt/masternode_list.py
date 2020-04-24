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
from electrum.bitcoin import public_key_to_p2pkh

import time, datetime

STATUS_ICONS = [
    "unconfirmed.png",
    "warning.png",
    "unconfirmed.png",
    "offline_tx.png",
    "clock1.png",
    "clock2.png",
    "clock3.png",
    "confirmed.png",
]

class MasternodeList(MyTreeView):

    class Columns(IntEnum):
        NAME = 0
        STATUS = 1
        COLLATERAL = 2
        UTXO = 3
        LASTSEEN = 4
        ACTIVESECONDS = 5
        DELEGATE = 6
        ADDRESS = 7

    headers = {
        Columns.NAME: _('Name'),
        Columns.STATUS: _('Status'),
        Columns.COLLATERAL: _('Collateral Key'),
        Columns.UTXO: _('Collateral Utxo'),
        Columns.LASTSEEN: _('Lastseen'),
        Columns.ACTIVESECONDS: _('Activeseconds'),
        Columns.DELEGATE: _('Masternode Private Key'),
        Columns.ADDRESS: _('Address'),        
    }
    filter_columns = [Columns.NAME, Columns.COLLATERAL]
    
    def __init__(self, parent):
        super().__init__(parent, self.create_menu,
                         stretch_column=self.Columns.NAME,
                         editable_columns=[self.Columns.NAME], tv=self)
        self.setModel(QStandardItemModel(self))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSortingEnabled(True)
        self.update()

    def on_edited(self, idx, user_role, text):
        mn = self.parent.masternode_manager.masternodes[user_role]
        mn.alias = text        
        self.parent.masternode_manager.save()
        self.update()

    def create_menu(self, position):
        menu = QMenu()
        idx = self.indexAt(position)
        column = idx.column() or self.Columns.UTXO
        selected_keys = []
        for s_idx in self.selected_in_column(self.Columns.UTXO):
            sel_key = self.model().itemFromIndex(s_idx).data(Qt.UserRole)
            selected_keys.append(sel_key)
        if selected_keys and idx.isValid():
            column_title = self.model().horizontalHeaderItem(column).text()
            column_data = '\n'.join(self.model().itemFromIndex(s_idx).text()
                                    for s_idx in self.selected_in_column(column))
            menu.addAction(_("Copy {}").format(column_title), lambda: self.parent.app.clipboard().setText(column_data))
            if column in self.editable_columns:
                item = self.model().itemFromIndex(idx)
                if item.isEditable():
                    # would not be editable if openalias
                    persistent = QPersistentModelIndex(idx)
                    menu.addAction(_("Edit {}").format(column_title), lambda p=persistent: self.edit(QModelIndex(p)))
            menu.addAction(_("Masternode Remove"), lambda: self.parent.masternode_remove(selected_keys))
            menu.addAction(_("Masternode Activate"), lambda: self.parent.masternode_activate(selected_keys))
            URLs = [block_explorer_URL(self.config, 'addr', key) for key in filter(is_address, selected_keys)]
            if URLs:
                menu.addAction(_("View on block explorer"), lambda: [webbrowser.open(u) for u in URLs])

        run_hook('create_contact_menu', menu, selected_keys)
        menu.exec_(self.viewport().mapToGlobal(position))

    def update(self):
        current_key = self.current_item_user_role(col=self.Columns.NAME)
        self.model().clear()
        self.update_headers(self.__class__.headers)
        set_current = None
        
        for key in self.parent.masternode_manager.masternodes.keys():
            mn = self.parent.masternode_manager.masternodes[key]
            utxo = mn.vin['prevout_hash'] + '-' + str(mn.vin['prevout_n'])  
            if mn.collateral_key == '':
                collateral = ''
            else:
                collateral = public_key_to_p2pkh(bfh(mn.collateral_key))
            delegate = self.parent.wallet.get_delegate_private_key(mn.delegate_key)
            if mn.lastseen > 0:
                lastseen = datetime.datetime.fromtimestamp(int(mn.lastseen)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                lastseen = ''
            address = str(mn.addr)
            items = [QStandardItem(x) for x in (mn.alias, mn.status, collateral, utxo, lastseen, mn.activeseconds, delegate, address)]
            items[self.Columns.NAME].setEditable(True)
            items[self.Columns.STATUS].setEditable(False)
            items[self.Columns.UTXO].setData(utxo, Qt.UserRole)
            row_count = self.model().rowCount()
            self.model().insertRow(row_count, items)
            self.disable_editability()            
            
            self.set_frozen_masternode(mn.vin['prevout_hash'], str(mn.vin['prevout_n']), True)
        
        self.set_current_idx(set_current)
        # FIXME refresh loses sort order; so set "default" here:
        self.sortByColumn(self.Columns.NAME, Qt.AscendingOrder)
        self.filter()
        run_hook('update_masternode_tab', self)

    def on_clicked(self, idx):
        alias = self.model().index(idx.row(),0).data()
        collateral = self.model().index(idx.row(),2).data()
        utxo = self.model().index(idx.row(),3).data()
        txid, index = utxo.split('-')
        delegate = self.model().index(idx.row(),6).data()
        ip, port = self.model().index(idx.row(),7).data().split(':')
        self.parent.alias_e.setText(alias)
        self.parent.address_e.setText(collateral)
        self.parent.txid_e.setText(txid)
        self.parent.index_e.setText(index)
        self.parent.delegate_e.setText(delegate)  
        self.parent.ip_e.setText(ip)
        self.parent.port_e.setText(port)
        self.parent.masternode_select(ip + ':' + port)
        if len(delegate) > 0:
            self.parent.masternode_combo.setDisabled(True)
        else:
            self.parent.masternode_combo.setDisabled(False)
            #self.parent.masternode_reset_frozen_masternodefresh()
            
    def set_frozen_masternode(self, txid , index, frozen=True):
        '''
        key = txid + ":" + index        
        coin = self.parent.utxo_list.utxo_dict.get(key)
        if not coin is None:
            self.parent.set_frozen_state_of_coins([coin], frozen)
        '''
        utxos = {'prevout_hash': txid, 'prevout_n': int(index)}
        self.parent.set_frozen_state_of_coins([utxos], frozen)