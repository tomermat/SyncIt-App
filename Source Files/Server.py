import socket
import threading
import os ,sys
import json
import pickle
import shutil
from myFileTransfer import *
from command import Command
from notifier import Notifier
import util

# this class is responsible for the servers comunication actions - it will send and receive commands
# and will handle them (meaning create folders, rename , move , delete, receive and send files )
# the server holds a list of all client connections and talk to each of them


class Server():

    IP_ADD = "127.0.0.1"  # deafult ip if not given other
    # this sets header size for a message - inside of it will be the message size

    HEADER_SIZE = 64
    PORT = 5151
    ADDR = (IP_ADD, PORT)
    FORMAT = 'utf-8'  # messages will be encoded and decoded with this format
    DISCONNECT_MSG = "%DISCONNECT%"
    watingForClient = False # when we are wating on a client to give us response
    connections = []  # list of all client connections
    # notification object
    notify = None

    def __init__(self, monitorCom):
        if(os.path.isfile("connectionSettings.txt")):  # if connection settings file exists
            f = open("connectionSettings.txt", 'r')
            conf = json.load(f)
            # get ip address of the server from the file
            self.IP_ADD = conf['server_ip']
            self.ADDR = (self.IP_ADD, self.PORT)
            f.close()
        else:
            f = open("connectionSettings.txt", 'w')
            f.write("{\"server_ip\":\""+self.IP_ADD +
                    "\",\"is_Server?\":\"yes\"}")
            f.close
        # create the socket with ipv4 over TCP
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(self.ADDR)
        # create the notifications object
        self.notify = Notifier("images.png")
        util.printToLog(f"[STARTING] server is starting...")
        # this is the object that is responsible for the communication with the monitor
        self.monitorCom = monitorCom
        # start a thread that listens to incoming connections from clients
        thread = threading.Thread(target=self.startServer)
        thread.daemon = True
        thread.start()

    # this function is used to send a command object (containing all of the command info)
    # the command is sent to all connected clients
    def sendCommand(self, command):
        # first we pickle the object - meaning we convert it to a sendable form
        message = pickle.dumps(command)
        # we first send the message length (padded with spaces up to HEADER_SIZE length - 64) and then the actual message
        msgLen = len(message)
        sendLen = str(msgLen).encode(self.FORMAT).strip()
        sendLen += b' '*(self.HEADER_SIZE-len(sendLen))
        for connection in self.connections:
            try:
                connection.send(sendLen)
                connection.send(message)
            except BrokenPipeError:  # cant send meaning we disconnected - remove this client from connected list
                self.connections.remove(connection)

    # same as sendCommand but only to an individual client
    def sendCommandToIndClient(self, command, conn):
        message = pickle.dumps(command)
        msgLen = len(message)
        sendLen = str(msgLen).encode(self.FORMAT).strip()
        sendLen += b' '*(self.HEADER_SIZE-len(sendLen))
        conn.send(sendLen)
        conn.send(message)

    # this function is executed as a new thread for each new client connecting and is responsible for
    # receiving messages from the client and send them to the handelCommand function to be executed
    def newConnection(self, conn, addr):
        util.printToLog(f"[NEW CONNECTION] {addr} is now connected.")
        self.notify.notify("New Client Connected!", f"{addr} connected to the server", 2)
        connected = True
        keepAliveCounter=1000
        while(connected):
            # this "keep alive" message is sent just to see if we are still connected - it is not handeld by the other side
            nonLenRecvd=False
            if(keepAliveCounter<=0):
                command = Command("KEEP_ALIVE", None, None, None, None, None, None)
                try:
                    self.sendCommandToIndClient(command, conn)
                    keepAliveCounter=1000
                except Exception:
                    util.printToLog("connection lost - keep alive message failed.")
                    break
            else:
                keepAliveCounter-=1
            try:
                msgLen = conn.recv(self.HEADER_SIZE) # receive message containing message length 
                try:
                    msgLen = msgLen.decode(self.FORMAT)  # getting the message length
                except Exception:
                    nonLenRecvd = True # if we couldn't decode it means it wasn't valid 
            except Exception as e:
                util.printToLog("connection lost - receiving header failed.")
                break
            try:
                if(msgLen and not nonLenRecvd):
                    msgLen = int(msgLen)
                    # getting the actual message
                    msg = conn.recv(msgLen)
                    # converting it back to a command object
                    command = pickle.loads(msg)
                    # send it to the handelCommand function to be executed
                    self.handelCommand(command, conn)
            except Exception as e:
                self.errHandl()
                break
        conn.close()
        self.connections.remove(conn)

    def errHandl(self):
        exception_type, exception_object, exception_traceback = sys.exc_info()
        filename = exception_traceback.tb_frame.f_code.co_filename
        line_number = exception_traceback.tb_lineno
        print("Exception type: ", exception_type)
        print("File name: ", filename)
        print("Line number: ", line_number)

    # this is the function that handels the commands received by the client
    # all actions performed by a command from a client is then sent to all
    # other clients to be executed and keeps everything in sync
    def handelCommand(self, command, conn):
        try:
            util.printToLog(f"got {command.command} command.")
            if(command.command == "MKDIR"):  # create folder command
                # we adjust the path to our clients synced dir path
                path = self.monitorCom.getSyncedDirPath() + command.path
                try:
                    os.makedirs(path)  # create the folder
                    self.notify.notify("New Folder Created", path, 2)
                    info = os.stat(path)  # get folder info
                    name = self.getFileNameFromPath(command.path)
                    util.printToLog(f"folder {path} has been created.")
                    self.monitorCom.insertToDataSet(
                        name, True, path, info, command.recordID)  # update our dataset (so we wont mark it as new in the next files scan)
                    tmpConnections = self.connections.copy()  # copy connections list
                    # remove origin connection so we wont send the command to whom we received it from
                    tmpConnections.remove(conn)
                    for newConn in tmpConnections:  # send the command to all other clients
                        command = Command("MKDIR", name, command.path,
                                        command.recordID, None, None, None)
                        self.sendCommandToIndClient(command, newConn)
                except FileExistsError:
                    util.printToLog("already exists")
            elif(command.command == "SENDALL"):  # this message is received when a new client with no dataset at all (brand new client) has connected and we need to pass everything to it
                self.monitorCom.sendAllRequested(conn)
            # this message is received when a client is reconnected and we need to update each other
            elif(command.command == "RECONNECTED"):
                # create a ServerDatasetReceive object which open a new channel of comunication and receives the dataset in a new thread
                # after opening the channel we send to the client a command to start sending us the file
                # with the new sockets details.
                getFile = ServerDatasetReceive(self.IP_ADD)
                port = getFile.getPort()
                newCommand = Command(
                    "CLIENT_SEND_DATASET", None, None, None, port, None, None)  # send to the client the command to start sending us the file
                self.sendCommandToIndClient(newCommand, conn)
                self.watingForClient = True
                while(not getFile.getIsDone()):  # wait until finished receiving the file
                    pass
                self.watingForClient = False
                datasetRcvd = getFile.getDataset()
                self.monitorCom.sendUpdateRequested(
                    conn, datasetRcvd, command.path)
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
                    util.printToLog(f"file {oldPath} has been renamed to {newPath}.")
                    # send to all other clients
                    tmpConnections = self.connections.copy()
                    tmpConnections.remove(conn)
                    for newConn in tmpConnections:
                        command = Command("RENAME", None, command.path,
                                        command.recordID, None, None, command.renameTo)
                        self.sendCommandToIndClient(command, newConn)
                except FileNotFoundError:
                    util.printToLog("file already renamed")
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
                    # send to all other clients
                    tmpConnections = self.connections.copy()
                    tmpConnections.remove(conn)
                    for newConn in tmpConnections:
                        command = Command("MOVE", None, command.path,
                                        command.recordID, None, command.moveTo, None)
                        self.sendCommandToIndClient(command, newConn)
                except FileNotFoundError:
                    util.printToLog("file already moved")
            # delete file command (handeled different from deleting a folder)
            elif(command.command == "DELETE"):
                path = self.monitorCom.getSyncedDirPath() + command.path
                try:
                    os.remove(path)  # remove the file
                    self.notify.notify("File Deleted", path, 2)
                    util.printToLog(
                        f"file {path} has been deleted by command from the Client.")
                    self.monitorCom.deleteFromDataSet(path)  # remove from dataset
                    # send to all other clients
                    tmpConnections = self.connections.copy()
                    tmpConnections.remove(conn)
                    for newConn in tmpConnections:
                        command = Command("DELETE", None, command.path,
                                        command.recordID, None, None, None)
                        self.sendCommandToIndClient(command, newConn)
                except FileNotFoundError:
                    util.printToLog("already deleted")
            elif(command.command == "DELETE_DIR"):  # delete folder command
                path = self.monitorCom.getSyncedDirPath() + command.path
                try:
                    # deleting the folder (and all of its children)
                    shutil.rmtree(path)
                    self.notify.notify("Folder Deleted", path, 2)
                    util.printToLog(
                        f"folder {path} has been deleted by command from the Client.")
                    # remove from dataset
                    self.monitorCom.deleteFromDataSet(path)
                    # send to all other clients
                    tmpConnections = self.connections.copy()
                    tmpConnections.remove(conn)
                    for newConn in tmpConnections:
                        command = Command(
                            "DELETE_DIR", None, command.path, command.recordID, None, None, None)
                        self.sendCommandToIndClient(command, newConn)
                except FileNotFoundError:
                    util.printToLog("already deleted")
            elif(command.command == "SERVER_GET_FILE"):  # client is sending us a file
                path = self.monitorCom.getSyncedDirPath() + command.path
                # check if the file is new or modified
                isExists = self.monitorCom.existsInDataSet(path)
                # create a ServerFileReceive object which open a new channel of comunication and receives the file in a new thread
                # after opening the channel we send to the client a command to start sending us the file
                # with the new sockets details.
                self.watingForClient = True
                getFile = ServerFileReceive(self.IP_ADD, path)
                port = getFile.getPort()
                newCommand = Command(
                    "CLIENT_SEND_FILE", command.aboutFile, command.path, None, port, None, None)  # send to the client the command to start sending us the file
                self.sendCommandToIndClient(newCommand, conn)
                self.notify.notify("Receiving File..",path,2)
                while(not getFile.getIsDone()):  # wait until finished receiving the file
                    pass
                self.notify.notify("File Received!",path,2)
                util.printToLog("done getting file")
                name = self.getFileNameFromPath(command.path)
                info = os.stat(path)  # get files info
                # if this is an existing file (mening modified) we update the dataset, and if its new we insert it to dataset
                if(isExists):
                    self.monitorCom.updateFileInDataSet(path, path, name, info)
                else:
                    self.monitorCom.insertToDataSet(
                        name, False, path, info, command.recordID)
                self.watingForClient = False
                # send the file to all other clients
                tmpConnections = self.connections.copy()
                tmpConnections.remove(conn)
                for newConn in tmpConnections:
                    sendFile = ServerFileSend(self.IP_ADD, path)
                    newPort = sendFile.getPort()
                    newCommand = Command(
                        "CLIENT_GET_FILE", None, command.path, command.recordID, newPort, None, None)
                    self.sendCommandToIndClient(newCommand, newConn)
        except Exception as e:
            print(e)
                
    # extracts a files name from its path
    def getFileNameFromPath(self, path):
        return path.rsplit('/', 1)[-1]

    # returns servers ip address
    def getIP(self):
        return self.IP_ADD

    # returns the list of clients connections
    def getConnections(self):
        return self.connections

    # runs as a thread that listens to incoming connections from clients
    def startServer(self):
        self.server.listen()
        util.printToLog(
            f"[LISTENING] server is now listening on {self.IP_ADD} with port {self.PORT}.")
        while(True):
            conn, addr = self.server.accept()
            self.connections.append(conn)  # add new connection to list
            thread = threading.Thread(
                target=self.newConnection, args=(conn, addr))  # open new thread for messages between server and client
            thread.daemon = True
            thread.start()
