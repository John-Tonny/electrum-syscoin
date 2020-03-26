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
    id: settings
    title: _('Electrum Settings')
    disable_pin: False
    use_encryption: False
    BoxLayout:
        orientation: 'vertical'
        Button:
            background_color: 0, 0, 0, 0
            text: 'pppp-bbbbb'
            markup: True
            color: .9, .9, .9, 1
            font_size: '30dp'
            bold: True
            size_hint: 1, 0.25
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
