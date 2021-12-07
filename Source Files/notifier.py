import time
import os
import gi
gi.require_version('Notify', '0.7')
from gi.repository import Notify, GdkPixbuf

# this is a class for creating a notifier object to display messages to the user nicely


class Notifier():

    notification = None
    currentPath = ""

    def __init__(self, iconFileName):
        Notify.init("notifier")
        self.currentPath = os.path.dirname(
            os.path.realpath(__file__))  # get our current path
        self.notification = Notify.Notification.new(
            "hello")  # create basic notification object
        image = GdkPixbuf.Pixbuf.new_from_file(
            self.currentPath+"/"+iconFileName)  # set notification image
        self.notification.set_image_from_pixbuf(image)

    # this function displays a notification on screen with the deafult image
    # we set the notification title, message and display time
    def notify(self, title, message, displayTimeSec):
        self.notification.update(title, message)  # update title and message
        self.notification.show()  # display
        time.sleep(displayTimeSec)  # wait
        self.notification.close()  # close notification

    # same as "notify" but with changing the notification image
    def notifyChangeIcon(self, title, message, displayTimeSec, iconFileName):
        self.notification.update(
            title, message, self.currentPath+"/"+iconFileName)
        self.notification.show()
        time.sleep(displayTimeSec)
        self.notification.close()
