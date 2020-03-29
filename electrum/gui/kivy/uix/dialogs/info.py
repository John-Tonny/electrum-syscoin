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

from electrum.constants import DESTROY_ADDRESS

Builder.load_string('''
#:import partial functools.partial
#:import _ electrum.gui.kivy.i18n._

<InfoDialog@Popup>
    id: info
    title: _('Electrum Info')
    disable_pin: False
    use_encryption: False
    BoxLayout:
        orientation: 'vertical'
        ScrollView:
            GridLayout:
                id: scrollviewlayout
                cols:1
                size_hint: 1, None
                height: self.minimum_height
                padding: '10dp'
                SettingsItem:
                    title: _('Destroy Address')
                    description: root.get_destroy_address()
                    action: partial(root.do_action)
                CardSeparator
                SettingsItem:
                    title: _('Account')
                    description: self.app.get_mobile_phone()
                    action: partial(root.do_action)
                CardSeparator
                SettingsItem:
                    title: _('Profit Address') 
                    description: root.get_profit_address()
                    action: partial(root.do_action)
                    
                
''')



class InfoDialog(Factory.Popup):

    def __init__(self, app):
        self.app = app
        Factory.Popup.__init__(self)
        layout = self.ids.scrollviewlayout
        layout.bind(minimum_height=layout.setter('height'))
        
    def update(self):
        pass

    def get_profit_address(self):
        return self.app.client.get_profit_address()
        '''
        register_info = self.app.wallet.storage.get('masternoderegister')        
        if register_info is None:        
            return ''
        for key in register_info.keys():
            password, profit_address = register_info[key]
            return profit_address
        '''
        
    def get_destroy_address(self):
        return DESTROY_ADDRESS

    def do_action(self, item):
        pass