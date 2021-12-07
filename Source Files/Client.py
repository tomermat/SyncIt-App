import socket
import threading
import pickle
from command import Command
import os
import json
import shutil
from myFileTransfer import *
import time
import util
from notifier import Notifier

# this class is responsible for the clients comunication actions - it will send and receive commands
# and will handle them (meaning create folders, rename , move , delete, receive and send files )


class Client():

    IP_ADD = "127.0.0.1"  # deafult ip if not given other
    # this sets header size for a message - inside of it will be the message size
    HEADER_SIZE = 64
    PORT = 5151
    ADDR = (IP_ADD, PORT)
    FORMAT = 'utf-8'  # messages will be encoded and decoded with this format
    DISCONNECT_MSG = "%DISCONNECT%"
    monitorCom = None  # this will be the object for comunicating with the main monitor object
    connected = False  # holding connected status
    # is it the first time connecting in current run or reconnection
    isInitialConnection = True
    watingForServer=False # when we are wating on the server to give us response
    # notification object
    notify = None

    def __init__(self, monitorCom):
        self.monitorCom = monitorCom
        self.notify = Notifier("images.png")  # create a notifier object
        if(os.path.isfile("connectionSettings.txt")):  # if connection settings file exists
            f = open("connectionSettings.txt", 'r')
            conf = json.load(f)
            # get ip address of the server from the file
            self.IP_ADD = conf['server_ip']
            self.ADDR = (self.IP_ADD, self.PORT)
            f.close()
        else:  # create the file with deafult settings
            f = open("connectionSettings.txt", 'w')
            f.write("{\"server_ip\":\""+self.IP_ADD+"\",\"is_Server?\":\"no\"}")
            f.close

        self.connect()

    # connection to the server
    def connect(self):
        util.printToLog("trying to connect...")
        try:
            # this socket will be used to get and send command messages
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.connect(self.ADDR)
            self.startClient()
            self.connected = True
            util.printToLog("connected!")
            self.notify.notify("Connected!", "We are now connected to the server", 2)
            # will run only if its not the first connection(meaning its a reconnection)
            if(not self.isInitialConnection):
                self.watingForServer=True
                syncedDir = self.monitorCom.getSyncedDirPath()
                # this method sends a reconnect message to sync changes that has been made while client was away
                command = Command("RECONNECTED", None,
                                  syncedDir, None, None, None, None)
                self.sendCommand(command)
            self.isInitialConnection = False
        except Exception as e:
            # if we are not connected, we wait 5 seconds and try to reconnect
            util.printToLog(e)
            time.sleep(5)
            self.connect()

    def startClient(self):
        # start a thread for messages comunication with server
        thread = threading.Thread(target=self.getMassage)
        thread.daemon = True
        thread.start()

    # this function is used to send a command object (containing all of the command info)
    def sendCommand(self, command):
        # first we pickle the object - meaning we convert it to a sendable form
        message = pickle.dumps(command)
        # we first send the message length (padded with spaces up to HEADER_SIZE length - 64) and then the actual message
        msgLen = len(message)
        sendLen = str(msgLen).encode(self.FORMAT).strip()
        sendLen += b' '*(self.HEADER_SIZE-len(sendLen))
        try:
            self.client.send(sendLen)
            self.client.send(message)
        except Exception:  # cant send meaning we disconnected - try to reconnect
            self.connected = False
            util.printToLog("connection to server lost...")
            self.connect()

    # this function runs a separate thread to receive messages from the server and send them to the handelCommand function to be executed
    def getMassage(self):
        self.connected = True
        keepAliveCounter = 1000
        while(self.connected):
            # this "keep alive" message is sent just to see if we are still connected - it is not handeld by the other side
            if(keepAliveCounter <= 0):
                command = Command("KEEP_ALIVE", None, None,
                                  None, None, None, None)
                self.sendCommand(command)
                keepAliveCounter = 1000
            else:
                keepAliveCounter -= 1
            try:
                msgLen = self.client.recv(self.HEADER_SIZE).decode(
                    self.FORMAT)  # getting the message length
            except Exception:
                pass
            try:
                if(msgLen):
                    msgLen = int(msgLen)
                    # getting the actual message
                    msg = self.client.recv(msgLen)
                    # converting it back to a command object
                    command = pickle.loads(msg)
                    # send it to the handelCommand function to be executed
                    self.handelCommand(command)
            except Exception:
                pass
        self.client.close()

    # this is the function that handels the commands received by the server
    def handelCommand(self, command):
        util.printToLog(f"got {command.command} command.")
        if(command.command == "MKDIR"):  # create folder command
            # we adjust the path to our clients synced dir path
            path = self.monitorCom.getSyncedDirPath() + command.path
            try:
                os.makedirs(path)  # create the folder
                self.notify.notify("New Folder Created", path, 2)
                info = os.stat(path)  # get folder info
                # extarct the name from the path
                name = self.getFileNameFromPath(command.path)
                self.monitorCom.insertToDataSet(
                    name, True, path, info, command.recordID)  # update our dataset (so we wont mark it as new in the next files scan)
                util.printToLog(f"folder {path} has been created.")
            except FileExistsError:
                util.printToLog("folder already exists")
        elif(command.command == "RENAME"):  # rename file command
            oldPath = self.monitorCom.getSyncedDirPath() + command.path
            newPath = self.monitorCom.getSyncedDirPath() + command.renameTo
            try:
                os.rename(oldPath, newPath)  # rename the file
                self.notify.notify("File Renamed", oldPath+" -> "+ newPath, 2)
                info = os.stat(newPath)
                name = self.getFileNameFromPath(command.path)
                self.monitorCom.updateFileInDataSet(
                    oldPath, newPath, name, info)  # update dataset
                util.printToLog(
                    f"file {oldPath} has been renamed to {newPath}.")
            except FileNotFoundError:
                pass
        elif(command.command == "MOVE"):  # move file command
            oldPath = self.monitorCom.getSyncedDirPath() + command.path
            newPath = self.monitorCom.getSyncedDirPath() + command.moveTo
            try:
                os.rename(oldPath, newPath)
                self.notify.notify("File Moved", oldPath+" -> "+ newPath, 2)
                info = os.stat(newPath)
                name = self.getFileNameFromPath(command.path)
                self.monitorCom.updateFileInDataSet(
                    oldPath, newPath, name, info)
                util.printToLog(f"file {oldPath} has been moved to {newPath}.")
            except FileNotFoundError:
                pass
        # delete file command (handeled different from deleting a folder)
        elif(command.command == "DELETE"):
            path = self.monitorCom.getSyncedDirPath() + command.path
            try:
                os.remove(path)  # remove the file
                self.notify.notify("File Deleted", path, 2)
                util.printToLog(
                    f"file {path} has been deleted by command from the server.")
                self.monitorCom.deleteFromDataSet(path)  # remove from dataset
            except FileNotFoundError:
                util.printToLog(f"{path} already deleted")
        elif(command.command == "DELETE_DIR"):  # delete folder command
            path = self.monitorCom.getSyncedDirPath() + command.path
            try:
                # deleting the folder (and all of its children)
                shutil.rmtree(path)
                self.notify.notify("Folder Deleted", path, 2)
                util.printToLog(
                    f"folder {path} has been deleted by command from the server.")
                # os.rmdir(path)
                self.monitorCom.deleteFromDataSet(path)  # remove from dataset
            except FileNotFoundError:
                util.printToLog(f"{path} already deleted")
        elif(command.command == "CLIENT_GET_FILE"):  # server is sending us a file
            port = command.port
            path = path = self.monitorCom.getSyncedDirPath() + command.path
            # see if its a new file or a modified one
            exists = self.monitorCom.existsInDataSet(path)    
            self.notify.notify("Receiving File..", path, 2)
            self.watingForServer = True
            # create a ClientFileReceive object which receives the file in a new thread
            getFile = ClientFileReceive(self.IP_ADD, port, path)
            while(not getFile.getIsDone()):  # wait until finished receiving the file
                    pass
            self.notify.notify("File Received!", path, 2)
            info = os.stat(path)  # get file info
            name = self.getFileNameFromPath(command.path)
            # if this is an existing file (mening modified) we update the dataset, and if its new we insert it to dataset
            if(exists):
                self.monitorCom.updateFileInDataSet(path, path, name, info)
            else:
                self.monitorCom.insertToDataSet(
                    name, False, path, info, command.recordID)
            self.watingForServer = False
        # this command tells us that server has opened a comunication channel for receiving a file and we can send it
        elif(command.command == "CLIENT_SEND_FILE"):
            port = command.port
            path = self.monitorCom.getSyncedDirPath() + command.path
            sendFile = ClientFileSend(self.IP_ADD, port, path)
        # send command tells us that server has opened a comunication channel for receiving our dataset and we can send it
        elif(command.command == "CLIENT_SEND_DATASET"):
            port = command.port
            sendFile = ClientDatasetSend(self.IP_ADD, port)
            self.watingForServer=False
        

    # extracts a files name from its path
    def getFileNameFromPath(self, path):
        return path.rsplit('/', 1)[-1]

    # returns servers ip address
    def getIP(self):
        return self.IP_ADD
