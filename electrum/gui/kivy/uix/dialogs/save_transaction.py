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
<SaveTransactionDialog@Popup>:
    title: _('Save transaction')
    id: popup
    path: ''
    BoxLayout:
        orientation: 'vertical'
        padding: '10dp'        
        BoxLayout:
            orientation: 'horizontal'
            size_hint: 1, None
            Label:
                text: _('Filename:')
                size_hint: 0.4, None
                height: '35dp'
                pos_hint: {'center_y':.5}
                halign: 'left'
                multiline: False
                font_size: '16dp'
            TextInput:
                id: filename
                padding: '5dp'
                size_hint: 0.6, None
                height: '35dp'
                pos_hint: {'center_y':.5}
                text:''
                multiline: False
                background_normal: 'atlas://electrum/gui/kivy/theming/light/textinput_disabled'
                background_active: 'atlas://electrum/gui/kivy/theming/light/textinput_active'
                hint_text_color: self.foreground_color
                foreground_color: 1, 1, 1, 1
                font_size: '16dp'
                focus: True
        Widget
            size_hint_y: 0.05                
        FileChooserListView:
            id: transaction_selector
            dirselect: True
            filter_dirs: False
            filters: ['*.txn']
            path: root.path
            rootpath: root.path
            size_hint_y: 0.5
            height: '48dp'
            on_selection: root.file_on_selection()             
        Widget
            size_hint_y: 0.1
        GridLayout:
            cols: 4
            size_hint_y: 0.1
            Button:
                id: save_button
                size_hint: 0.1, None
                height: '48dp'
                text: _('Save transaction')
                on_release:
                    root.save_transaction()
            Button:
                id: close_button
                size_hint: 0.1, None
                height: '48dp'
                text: _('Close')
                on_release:
                    popup.dismiss()
''')

class SaveTransactionDialog(Factory.Popup):    
    def init(self, app, path, tx):
        self.app = app
        if path is None:
            self.path = os.path.dirname(app.get_wallet_path()) + '/../..'
        else:
            self.path = path
        self.tx = tx
        self.ids.filename.text = 'signed_%s' % (tx.txid()[0:8]) if self.tx.is_complete() else 'unsigned'
            
    def save_transaction(self):
        if len(self.ids.filename.text) == 0:
            self.app.show_error(_('The file name cannot be empty!'))
            return        
        try:
            fileName =  self.ids.transaction_selector.selection[0] 
            if os.path.isdir(fileName):            
                fileName +=  "/" + self.ids.filename.text + '.txn'
            else:
                fileName =  os.path.dirname(fileName) + "/" + self.ids.filename.text + '.txn'
                
            self.app.save_transaction(fileName, self.tx)
            self.dismiss()
        except Exception as e:
            self.app.show_error(str(e))
    
    def file_on_selection(self):
        try:
            fileName =  self.ids.transaction_selector.selection[0] 
            if os.path.isfile(fileName):            
                fileName =  os.path.basename(fileName) 
                pos = fileName.find('.txn')
                self.ids.filename.text = fileName[:pos]
        except Exception as e:
            self.app.show_error("k8:" + str(e))