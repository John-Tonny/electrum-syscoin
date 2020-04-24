from kivy.app import App
from kivy.factory import Factory
from kivy.properties import ObjectProperty
from kivy.lang import Builder

Builder.load_string('''
<LoginDialog@Popup>
    id: popup
    title: _('Account Login')
    size_hint: 0.8, 0.3
    pos_hint: {'top':0.9}
    BoxLayout:
        orientation: 'vertical'
        Widget:
            size_hint: 1, 0.2
        TextInput:
            id:mobile
            padding: '5dp'
            size_hint: 1, None
            height: '27dp'
            pos_hint: {'center_y':.5}
            text:''
            multiline: False
            background_normal: 'atlas://electrum/gui/kivy/theming/light/tab_btn'
            background_active: 'atlas://electrum/gui/kivy/theming/light/textinput_active'
            hint_text_color: self.foreground_color
            foreground_color: 1, 1, 1, 1
            font_size: '16dp'
            focus: True
        TextInput:
            id:password
            padding: '5dp'
            size_hint: 1, None
            height: '27dp'
            pos_hint: {'center_y':.5}
            text:''
            multiline: False
            background_normal: 'atlas://electrum/gui/kivy/theming/light/tab_btn'
            background_active: 'atlas://electrum/gui/kivy/theming/light/textinput_active'
            hint_text_color: self.foreground_color
            foreground_color: 1, 1, 1, 1
            font_size: '16dp'
            focus: False
        Widget:
            size_hint: 1, 0.2
        BoxLayout:
            orientation: 'horizontal'
            size_hint: 1, 0.5
            Button:
                text: _('Cancel')
                size_hint: 0.5, None
                height: '48dp'
                on_release: popup.dismiss()
            Button:
                text: _('OK')
                size_hint: 0.5, None
                height: '48dp'
                on_release:
                    root.callback(popup.title, mobile.text, password.text)
                    popup.dismiss()
''')

class LoginDialog(Factory.Popup):

    def __init__(self, title, callback):
        Factory.Popup.__init__(self)
        self.ids.mobile.text = ''
        self.ids.password.text = ''
        self.callback = callback
        self.title = title
