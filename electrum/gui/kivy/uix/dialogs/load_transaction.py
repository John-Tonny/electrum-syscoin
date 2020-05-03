import os

from kivy.app import App
from kivy.factory import Factory
from kivy.properties import ObjectProperty
from kivy.lang import Builder

from electrum.util import base_units

from ...i18n import _
from .label_dialog import LabelDialog

Builder.load_string('''
#:import os os
<LoadTransactionDialog@Popup>:
    title: _('Load transaction')
    id: popup
    path: ''
    BoxLayout:
        orientation: 'vertical'
        padding: '10dp'
        FileChooserListView:
            id: transaction_selector
            #dirselect: True
            filter_dirs: False
            filters: ['*.txn']
            path: root.path
            rootpath: root.path
            size_hint_y: 0.5
            height: '48dp'
        Widget
            size_hint_y: 0.1
        GridLayout:
            cols: 4
            size_hint_y: 0.1
            Button:
                id: open_button
                size_hint: 0.1, None
                height: '48dp'
                text: _('Load transaction')
                disabled: not transaction_selector.selection
                on_release:
                    popup.dismiss()
                    root.open_transaction()
            Button:
                id: close_button
                size_hint: 0.1, None
                height: '48dp'
                text: _('Close')
                on_release:
                    popup.dismiss()
''')

class LoadTransactionDialog(Factory.Popup):
    
    def init(self, app, path):
        self.app = app
        if path is None:
            self.path = os.path.dirname(app.get_wallet_path()) + '/../..'
        else:
            self.path = path
            
    def open_transaction(self):
        fileName = self.ids.transaction_selector.selection[0]
        self.app.do_process_from_file(fileName)
    