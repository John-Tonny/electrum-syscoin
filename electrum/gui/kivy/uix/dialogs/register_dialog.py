from kivy.app import App
from kivy.factory import Factory
from kivy.properties import ObjectProperty
from kivy.lang import Builder
from decimal import Decimal
from kivy.clock import Clock

from electrum.util import InvalidPassword
from electrum.gui.kivy.i18n import _

Builder.load_string('''

<RegisterDialog@Popup>
    id: popup
    title: 'Electrum'
    message: ''
    mode: True
    BoxLayout:
        size_hint: 1, 1
        orientation: 'vertical'
        Widget:
            size_hint: 1, 0.05
        Label:
            font_size: '20dp'
            text: root.message
            text_size: self.width, None
            size: self.texture_size
        Widget:
            size_hint: 1, 0.05
        Label:
            id: a
            font_size: '50dp'
            text: kb.mobilephone + '-'*(11-len(kb.mobilephone)) if root.mode else ('*'*len(kb.password) + '-'*(6-len(kb.password)))
            size: self.texture_size
        Widget:
            size_hint: 1, 0.05
        GridLayout:
            id: kb
            size_hint: 1, None
            height: self.minimum_height
            update_amount: popup.update_password if not root.mode else popup.update_mobilephone 
            password: ''
            mobilephone: ''
            on_password: popup.on_password(self.password)
            on_mobilephone: popup.on_mobilephone(self.mobilephone)
            spacing: '2dp'
            cols: 3
            KButton:
                text: '1'
            KButton:
                text: '2'
            KButton:
                text: '3'
            KButton:
                text: '4'
            KButton:
                text: '5'
            KButton:
                text: '6'
            KButton:
                text: '7'
            KButton:
                text: '8'
            KButton:
                text: '9'
            KButton:
                text: 'Clear'
            KButton:
                text: '0'
            KButton:
                text: '<'
''')


class RegisterDialog(Factory.Popup):

    def init(self, app, wallet, message, on_success, on_failure, is_change=0):
        self.app = app
        self.wallet = wallet
        self.message = message
        self.mode = True
        self.on_success = on_success
        self.on_failure = on_failure
        self.ids.kb.password = ''
        self.success = False
        self.is_change = is_change
        self.mobilephone = None
        self.pw = None
        self.new_password = None
        self.title = _('Account Login') if is_change==0 else _('Account Register')
        
    def check_login(self):
        register_info = self.wallet.storage.get('user_register')
        if register_info is None:
            return False
        password, address = register_info.get(self.mobilephone)
        if password == self.pw:
            return True
        return False

    def on_dismiss(self):
        if not self.success:
            if self.on_failure:
                self.on_failure()
            else:
                # keep dialog open
                return True
        else:
            if self.on_success:
                args = (self.mobilephone, self.pw, self.new_password) if self.is_change>4 else (self.mobilephone, self.pw,)
                Clock.schedule_once(lambda dt: self.on_success(*args), 0.1)

    def update_password(self, c):
        kb = self.ids.kb
        text = kb.password
        if c == '<':
            text = text[:-1]
        elif c == 'Clear':
            text = ''
        else:
            text += c
        kb.password = text

    def on_password(self, pw):
        if len(pw) == 6:
            if self.is_change == 1:
                self.success = True
                self.pw = pw
                if self.check_login():
                    self.message = _('Please wait...')
                    self.dismiss()
                else:
                    self.message = _('Enter your mobile phone')
                    self.is_change = 0
                    self.ids.kb.password = ''
                    self.mode = True
                    self.app.show_error(_('Wrong mobile and password'))
            elif self.is_change == 3:
                self.pw = pw
                self.message = _('Confirm new password')
                self.ids.kb.password = ''
                self.is_change = 4
            elif self.is_change == 4:
                self.new_password = pw
                self.success = (self.pw == self.new_password)
                self.message = _('Please wait...')                
                self.dismiss()                

    def update_mobilephone(self, c):
        kb = self.ids.kb
        text = kb.mobilephone
        if c == '<':
            text = text[:-1]
        elif c == 'Clear':
            text = ''
        else:
            text += c
        kb.mobilephone = text

    def on_mobilephone(self, mobilephone):
        if len(mobilephone) == 11:
            if self.is_change == 0:
                self.mobilephone = mobilephone
                self.message = _('Enter new password')
                self.ids.kb.password = ''
                self.mode = False
            elif self.is_change == 2:
                self.mobilephone = mobilephone 
                self.message = _('Enter new password')
                self.ids.kb.password = ''
                self.mode = False
                self.is_change = 3
