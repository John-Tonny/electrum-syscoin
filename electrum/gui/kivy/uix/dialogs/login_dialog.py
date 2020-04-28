from kivy.app import App
from kivy.factory import Factory
from kivy.properties import ObjectProperty
from kivy.lang import Builder
from kivy.clock import Clock
from electrum.gui.kivy.i18n import _

Builder.load_string('''
<LoginDialog@Popup>
    id: popup
    title: _('Account Login')
    info: ''
    size_hint: 0.8, 0.4
    pos_hint: {'top':0.9}
    BoxLayout:
        orientation: 'vertical'
        Widget:
            size_hint: 1, 0.1
        BoxLayout:
            orientation: 'horizontal'
            size_hint: 1, None
            Label:
                text: _('Mobile:')
                size_hint: 0.4, None
                height: '35dp'
                pos_hint: {'center_y':.5}
                halign: 'left'
                multiline: False
                font_size: '16dp'
            TextInput:
                id: mobilephone
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
        Widget:
            size_hint: 1, 0.1
        BoxLayout:
            orientation: 'horizontal'
            size_hint: 1, None
            Label:
                text: _('Checkcode:')
                size_hint: 0.4, None
                height: '35dp'
                halign: 'left'
                multiline: False
                font_size: '16dp'
                pos_hint: {'center_y':.5}
            TextInput:
                id: password
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
                focus: False
        BoxLayout:
            orientation: 'horizontal'
            size_hint: 1, None
            Label:
                text: root.info
                size_hint: 1, None
                height: '32dp'
                multiline: False
                font_size: '24dp'
        Widget:
            size_hint: 1, 0.1
        BoxLayout:
            orientation: 'horizontal'
            size_hint: 1, 0.5
            Button:
                text: _('Cancel')
                size_hint: 0.33, None
                height: '48dp'
                on_release: popup.dismiss()
            Button:
                text: _('Get checkcode')
                size_hint: 0.34, None
                height: '48dp'
                on_release: Clock.schedule_once(lambda dt: root.do_checkcode()) #root.checkback(mobilephone.text)
            Button:
                text: _('OK')
                size_hint: 0.33, None
                height: '48dp'
                on_release: Clock.schedule_once(lambda dt: root.do_Ok())
                    #root.callback(mobilephone.text, password.text)
                    #popup.dismiss()
''')

class LoginDialog(Factory.Popup):

    def __init__(self, app):# mobilephone, password, callback, checkback):
        Factory.Popup.__init__(self) 
        
        self.app = app
        self.ids.mobilephone.text = ''
        self.ids.password.text = ''
        #self.callback = callback
        #self.checkback = checkback
        
    def do_Ok(self):
        mobilephone = self.ids.mobilephone.text        
        if len(mobilephone) != 11:
            self.app.show_error(_('Mobile must be 11 digits!'))                   
            return
        try:
            intMobilephone = int(mobilephone)
        except Exception as e:
            self.app.show_error(_('Mobile must be numeric!'))                                   
            return
        
        password = self.ids.password.text  
        if len(password) == 0:
            self.app.show_error(_('Checkcode cannot be empty!'))                    
            return
        
        self.info = _('Please wait') + '...'
        Clock.schedule_once(lambda dt: self._do_Ok(mobilephone, password))

    def _do_Ok(self, mobilephone, password):
        try:
            address = self.app.wallet.create_new_address(False)
            status = self.app.client.post_register(mobilephone, address, password)    
            self.info = ''
            if not status :                        
                self.app.show_error(_("Account Login failed!"))
                return
            self.app.wallet.storage.put('user_register', {mobilephone:(password, address)})
            self.app.show_info(_('Account Login successful!'))
            self.dismiss()
        except Exception as e:
            self.app.show_error("ppp:" +str(e))
        
    def do_checkcode(self):
        mobilephone = self.ids.mobilephone.text
        if len(mobilephone) != 11:
            self.app.show_error(_('Mobile must be 11 digits!'))                 
            return
        try:
            intMobilephone = int(mobilephone)
        except Exception as e:
            self.app.show_error(_('Mobile must be numeric!'))                                    
            return
        
        self.info = _('Please wait') + '...'
        Clock.schedule_once(lambda dt: self._do_checkcode(mobilephone))
        
    def _do_checkcode(self, mobilephone):
        status = self.app.client.post_mobilephone_checkcode(mobilephone)                
        self.info = ''
        if not status:                        
            self.app.show_error(_("Get checkcode sent failed!"))
            return
        self.app.show_info(_('Get checkcode send successful!'))
        