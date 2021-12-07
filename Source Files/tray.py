import gobject
import subprocess
import time
import os
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk as gtk, AppIndicator3 as appindicator
from tkinter import messagebox
import tkinter as tk


# this class is for creating the tray icon and menu for the user functions
# this it basically our only GUI on the project
class Tray():
    indicator = None
    currentPath = ""
    monCom = None

    # constructor receiving reference to the monitor
    def __init__(self, monitorRef):
        self.monCom = monitorRef
        self.currentPath = os.path.dirname(
            os.path.realpath(__file__))  # get current path
        self.indicator = appindicator.Indicator.new(
            "a", self.currentPath+"/icon.png", appindicator.IndicatorCategory.APPLICATION_STATUS)  # create the tray icon
        self.indicator.set_status(
            appindicator.IndicatorStatus.ACTIVE)  # set status to active
        # attach a menu returned by the "menu" function
        self.indicator.set_menu(self.menu())
        self.indicator.set_icon_full(
            self.currentPath+"/icon.png", "SyncIt")  # set icon with description bubble text
        gtk.main()  # start the tray menu

    # returns a menu to attach to the tray icon
    def menu(self):
        menu = gtk.Menu()
        # zero menu item (added later ;) ) - open the synced folder
        command_zero = gtk.MenuItem(label='Open Synced Folder')
        # attach menu item to the currect function
        command_zero.connect('activate', self.openSyncedFolder)
        menu.append(command_zero)        
        # first menu item - open the log file
        command_one = gtk.MenuItem(label='Open Log File')
        # attach menu item to the currect function
        command_one.connect('activate', self.openLog)
        menu.append(command_one)
        # second menu item - change folder
        command_two = gtk.MenuItem(label='Change Synced Folder')
        # attach menu item to the currect function
        command_two.connect('activate', self.changeDir)
        menu.append(command_two)
        # first menu item - quiting the app
        exittray = gtk.MenuItem(label='Quit App')
        # attach menu item to the currect function
        exittray.connect('activate', self.quit)
        menu.append(exittray)

        menu.show_all()
        return menu

    # opens the log file
    def openLog(self, menuItem):
        try:
            subprocess.call(["xdg-open", "Log.txt"])
        except Exception as e:
            print(e)

    # opens the log file
    def openSyncedFolder(self, menuItem):
        try:
            subprocess.call(["xdg-open", self.monCom.getSyncedDirPath()])
        except Exception as e:
            print(e)
            
    # quiting
    def quit(self, menuItem):
        gtk.main_quit()

    # prompt an "are you sure?" message
    def changeDir(self,menuItem):
        if(self.monCom.changeDir()): # they said yes , database has been deleted , close program..
            gtk.main_quit()
