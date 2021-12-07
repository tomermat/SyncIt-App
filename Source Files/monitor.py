import os
import time
import hashlib
import sys
import threading
import pickle
import json
from myFileTransfer import *
from tkinter import filedialog
import tkinter as tk
from FileRecord import FileRecord
from Server import Server
from Client import Client
from command import Command
from tray import Tray
from notifier import Notifier
import util
from tkinter import messagebox

# holds synced directory path
syncedDir = ""
# this is the database of files information that are in the synced dir
dirDataSet = []
# a lock for controling access to the dataset
lock = threading.Lock()
# reference to this monitor for calling functions from other objects and classes
comMngr = None
# boolean that flags if this script runs as a server or a client
isServer = True
# notification object
notify = None
# servers ip address
ipAddr = ""
# holds list of "suspect" files to be deleted from database - they be deleted only in the second pass
suspects = []

# this object will be sent to the server and client classes for comunicating with the monitor functions
class MonitorCom():
    # print current dataset
    def printDataSet(self):
        printAllDataset()

    # returns synced directory's path
    def getSyncedDirPath(self):
        return syncedDir

    # returns a copy of the dataset
    def getDataSet(self):
        return dirDataSet.copy()

    # this function is executed when a fresh new client is connecting and wants the server to send it all of it data and files
    def sendAllRequested(self, conn):
        # first send all make-folder commands to create the folders
        # for each file record in our database
        for fileRecord in reversed(dirDataSet):
            if(fileRecord.isDir):
                # fix path will remove our leading dir path so it will be relative to other computer dir paths
                fixedPath = fixPath(fileRecord.filePath)
                command = Command("MKDIR", fileRecord.fileName,
                                  fixedPath, fileRecord.recordID, None, None, None)
                comMngr.sendCommandToIndClient(command, conn)
        # after creating the folders - we send the files
        for fileRecord in dirDataSet:
            if(not fileRecord.isDir):
                # create object for the file sending
                sendFile = ServerFileSend(ipAddr, fileRecord.filePath)
                newPort = sendFile.getPort()  # get the port
                command = Command("CLIENT_GET_FILE", None, fixPath(
                    fileRecord.filePath), fileRecord.recordID, newPort, None, None)  # send to the client the command to receive the file
                comMngr.sendCommandToIndClient(command, conn)

    # this function is executed when a client is reconnecting and wants the server to update it
    def sendUpdateRequested(self, conn, dataSet, otherPath):
        tmpDataSet = dirDataSet.copy()  # copy the database     
        toDelete = []  # will hold files that needs to be deleted
        toModify = []  # will hold files that needs to be modified
        toRename = []  # will hold files that needs to be renamed
        toMove = []  # will hold files that needs to be moved
        toInsert = []  # will hold files that needs to be sent to the client
        for clientFile in dataSet:  # for each file in the clients database - try to find a match
            found = False
            otherFixedPath = clientFile.filePath.replace(otherPath, "")
            for myFile in tmpDataSet:  # go through all our database
                if(myFile.recordID == clientFile.recordID):
                    found = True
                    myFixedPath = fixPath(myFile.filePath)
                    # if we found the file - we check if its modified by the files hash
                    if(otherFixedPath == myFixedPath):
                        if(myFile.fileHash == clientFile.fileHash):  # if not modified - ignore it
                            tmpDataSet.remove(myFile)
                        else:
                            # if modified - insert to modify list
                            toModify.append(myFile)
                            tmpDataSet.remove(myFile)
                    else:  # found the file but not in the same path - moved or renamed
                        if(myFile.fileName == clientFile.fileName):  # name is the same - its moved
                            myFile.moveFile = otherFixedPath
                            toMove.append(myFile)
                            tmpDataSet.remove(myFile)
                        else:  # renamed
                            myFile.renameFile = otherFixedPath
                            toRename.append(myFile)
                            tmpDataSet.remove(myFile)
            if(not found):  # we didn't find the file - meaning its deleted
                clientFile.filePath = clientFile.filePath.replace(
                    otherPath, "")  # clear client path - make it relative
                toDelete.append(clientFile)  # add to delete list
        toInsert = tmpDataSet.copy()  # all thats left needs to be sent to client
        # sending all of the command by the lists - delete , rename, move etc..
        for item in toDelete:
            if(not item.isDir):
                command = Command("DELETE", None, fixPath(
                    item.filePath), item.recordID, None, None, None)  # delete command
                comMngr.sendCommandToIndClient(command, conn)
            else:
                command = Command("DELETE_DIR", None, fixPath(
                    item.filePath), item.recordID, None, None, None)  # delete directory command
                comMngr.sendCommandToIndClient(command, conn)
        # create new directories (need to go first so we wont get errors with changing/sending files)
        for item in toInsert:
            if(item.isDir):
                command = Command("MKDIR", item.fileName, fixPath(
                    item.filePath), item.recordID, None, None, None)  # create dir command
                comMngr.sendCommandToIndClient(command, conn)
        for item in toRename:
            command = Command("RENAME", None, item.renameFile,
                              item.recordID, None, None, fixPath(item.filePath))  # rename command
            comMngr.sendCommandToIndClient(command, conn)
        for item in toMove:
            command = Command("MOVE", None, item.moveFile,
                              item.recordID, None, fixPath(item.filePath), None)  # move command
            comMngr.sendCommandToIndClient(command, conn)
        # sending missing files
        for item in toInsert:
            if(not item.isDir):
                sendFile = ServerFileSend(ipAddr, item.filePath)
                newPort = sendFile.getPort()
                command = Command("CLIENT_GET_FILE", None, fixPath(
                    item.filePath), item.recordID, newPort, None, None)
                comMngr.sendCommandToIndClient(command, conn)
        # files that needs to be modified are first deleted and then resent
        for item in toModify:
            command = Command("DELETE", None, fixPath(
                item.filePath), item.recordID, None, None, None)  # first delete
            comMngr.sendCommandToIndClient(command, conn)
            sendFile = ServerFileSend(ipAddr, item.filePath)
            newPort = sendFile.getPort()
            command = Command("CLIENT_GET_FILE", None, fixPath(
                item.filePath), item.recordID, newPort, None, None)  # then resend
            comMngr.sendCommandToIndClient(command, conn)

    # this function inserts a new file record to our database
    def insertToDataSet(self, name, isDir, path, info, recordID):
        if not isDir:
            fileHash = md5checksum(path)  # create the file hash
        else:
            fileHash = "Is_A_Dir"
        newRecordset = FileRecord(
            name, isDir, path, fileHash, info.st_size, info.st_mtime, info.st_ctime, info.st_ino)  # create a new fileRecord object with the file details
        newRecordset.recordID = recordID  # keep the original files recordID
        lock.acquire()  # lock access to database
        dirDataSet.append(newRecordset)  # insert to database
        saveDataSet()  # save to file
        lock.release()  # release lock

    # this function returns True if a given path exists in our database
    def existsInDataSet(self, path):
        for fileRecord in dirDataSet:
            if(fileRecord.filePath == path):
                return True
        return False

    # this function is called when we update an existing file (like rename or move)
    def updateFileInDataSet(self, aboutFile, path, name, info):
        lock.acquire()  # lock access to database
        for fileRecord in dirDataSet:  # find it
            if(fileRecord.filePath == aboutFile):
                if not fileRecord.isDir:
                    fileHash = md5checksum(path)  # rehash it
                else:
                    fileHash = "Is_A_Dir"
                fileRecord.fileHash = fileHash
                fileRecord.filePath = path  # update path
                fileRecord.fileName = name  # update name
                fileRecord.filemTime = info.st_mtime  # update modification time
                fileRecord.filecTime = info.st_ctime  # update metadata change time
                saveDataSet()  # save to file
        lock.release()  # release lock

    # deletes a file record from database
    def deleteFromDataSet(self, aboutFile):
        lock.acquire()  # lock access to database
        for fileRecord in dirDataSet:  # find it
            if(fileRecord.filePath == aboutFile):
                dirDataSet.remove(fileRecord)
                saveDataSet()  # save to file
        lock.release()  # release lock

    # this function prompts an "are you sure?" message for changing the synced directory and if the answer is yes deletes the database from file
    # and the synced dir saved path  and exits the program for the user to reopen and choose a new folder
    def changeDir(self):
        root = tk.Tk()
        root.withdraw()
        a = messagebox.askquestion(title="Are you sure??", message="Changing the folder deletes current database and closes the program,\nyou will need to re-open the program and choose a new folder (your files in the current folder wont be deleted) \ncontinue?")
        if(a == "yes"):
            try:
                os.remove("config.txt")
                os.remove("dataset.pckl")
                root.destroy()
                return True
            except Exception as e:
                print(e)
        root.destroy()
        return False

# this function removes the leading path of our synced dir - making it relative
def fixPath(path):
    return path.replace(syncedDir, "")

# save database to file
def saveDataSet():
    pick_file = open("dataset.pckl", 'wb')  # open file for writing
    pickle.dump(dirDataSet, pick_file)  # write it with pickle convertion
    pick_file.close()  # close file

# this function opens the saved database from file and reconverts (pickle) it to an array
# if the file doesn't exists - we return false
def openDataSet():
    global dirDataSet
    # check if the file exists and if its size isn't 0
    if(os.path.isfile("dataset.pckl") and not os.path.getsize("dataset.pckl") == 0):
        pick_file = open("dataset.pckl", 'rb')  # read the file
        dirDataSet = pickle.load(pick_file)  # reconverts it back to an array
        pick_file.close()  # close the file
        return True  # return that it exists
    else:
        return False  # file doesnt exists

# this function generats a hash from all of the files bytes
def md5checksum(fname):
    md5 = hashlib.md5()  # using hashlib module
    f = open(fname, "rb")  # open the file
    while(True):
        chunk = f.read(4096)  # read the file in chunks of 4k
        if(not chunk):
            break
        md5.update(chunk)  # update our hash generator
    return md5.hexdigest()  # return the hash

# this function is called on first operation of the application - it scans the folder and
# inserts to the database all of the files details. this creates the base database
# that we keep maintaining with the "scanFolderForChanges" function
def addFilesInDirs(dirPath):
    # use os.scandir to scan the folder
    with os.scandir(dirPath) as dir_entries:
        for entry in dir_entries:  # for each file/directory
            isDir = entry.is_dir()  # is the file a directory
            if isDir:
                # recursively go through all sub folders
                addFilesInDirs(entry.path)
            info = os.stat(entry.path)  # get file stats
            if not isDir:  # if its not a folder - create an hash for it
                fileHash = md5checksum(entry.path)
            else:
                fileHash = "Is_A_Dir"
            newRecordset = FileRecord(entry.name, isDir, entry.path, fileHash,
                                      info.st_size, info.st_mtime, info.st_ctime, info.st_ino)
            dirDataSet.append(newRecordset)  # save to our database
            saveDataSet()  # save database to file
    dir_entries.close()

# return the number of record in our database
def fileCount():
    return len(dirDataSet)

# this function is used to re-call the folder scaning function as a thread every 5 seconds
# it calls the "scanFolderForChanges" and after its done it calls "scanForDeleted" to complete the folder scaning
# then it calls itself with a delay timer of 5 seconds
def recallScan(theDir):
    # call "scanFolderForChanges" in new thread
    t = threading.Thread(target=scanFolderForChanges, args=(theDir,))
    t.daemon = True
    t.start()
    t.join()  # block calling thread from continuing while not finished
    # call "scanForDeleted" in new thread
    t1 = threading.Thread(target=scanForDeleted)
    t1.daemon = True
    t1.start()
    t1.join()  # block calling thread from continuing while not finished
    t2 = threading.Timer(5.0, recallScan, [theDir])  # recall itself
    t2.daemon = True
    t2.start()


# this function is the first part of scaning the folder for changes - it scans for differences in files vs the database
# the second part is to scan the other way for differences between database and the actual files and see what files have been deleted
# this happanes in the next function "scanForDeleted"
def scanFolderForChanges(dirPath):
    global comMngr
    if(not isServer):
        if(not comMngr.connected or comMngr.watingForServer):  # if we are a client and we are not connected - don't scan for changes and return - this will prevent un-syncing problems
            return
    else:
        if(comMngr.watingForClient): # same for server if wating on client
            return
    try:
        # scan all files and folders in the dir
        with os.scandir(dirPath) as dir_entries:
            for entry in dir_entries:
                isDir = entry.is_dir()
                if isDir:
                    # recursively go through aal sub-folders
                    scanFolderForChanges(entry.path)
                info = os.stat(entry.path)  # get files info
                # lock.acquire()
                for fileRecord in dirDataSet:  # go through the database
                    matched = False  # will be true if we found the file , will stay false if its a new one
                    if(entry.path == fileRecord.filePath):  # if it has same path and name
                        # if it has same modified time or its a folder (meaning nothing changed inside)
                        if(info.st_mtime == fileRecord.filemTime or fileRecord.isDir):
                            matched = True
                            break
                        else:  # file has been modified
                            if(not fileRecord.isDir):
                                util.printToLog(
                                    f"file {fileRecord.fileName} has been modified")
                                notify.notify("File Modified", fileRecord.filePath, 2)
                                fileRecord.filemTime = info.st_mtime  # update modified time
                                fileHash = md5checksum(
                                    entry.path)  # create new hash
                                fileRecord.fileHash = fileHash  # update the hash
                                fileRecord.filecTime = info.st_ctime  # update c-time
                                saveDataSet()  # save database to file
                                # send to others modification command - meaning delete and receive again
                                command = Command("DELETE", None, fixPath(
                                    fileRecord.filePath), fileRecord.recordID, None, None, None)  # first delete
                                comMngr.sendCommand(command)
                                if(isServer):
                                    connList = comMngr.getConnections()
                                    for conn in connList:  # for all connections
                                        sendFile = ServerFileSend(
                                            ipAddr, entry.path)  # create file sending object
                                        newPort = sendFile.getPort()
                                        command = Command("CLIENT_GET_FILE", None, fixPath(
                                            entry.path), fileRecord.recordID, newPort, None, None)  # send the client a command to start receiving the file
                                        comMngr.sendCommandToIndClient(
                                            command, conn)
                                else:  # if we are a client
                                    command = Command("SERVER_GET_FILE", entry.name, fixPath(
                                        entry.path), fileRecord.recordID, None, None, None)  # tell server we have a file for it
                                    comMngr.sendCommand(command)
                                matched = True
                                break
                    # if we have same inode but different path or name (meaning file has been moved or renamed)
                    elif(info.st_ino == fileRecord.fileInodAddr and info.st_ino != 0):
                        # have same modified time - only path or  name changed
                        if(info.st_mtime == fileRecord.filemTime):
                            # same name different path - file moved
                            if(entry.name == fileRecord.fileName):
                                util.printToLog(
                                    f"file {fileRecord.fileName} has been moved to {entry.path}")
                                notify.notify("File Moved", fileRecord.filePath+"->"+entry.path, 2)
                                command = Command("MOVE", None, fixPath(
                                    fileRecord.filePath), fileRecord.recordID, None, fixPath(entry.path), None)  # send move command
                                fileRecord.filePath = entry.path  # update the path
                                saveDataSet()  # save database to file
                                comMngr.sendCommand(command)
                                matched = True
                                break
                            else:  # same path different name - file renamed
                                util.printToLog(
                                    f"file {fileRecord.fileName} has been renamed to {entry.name}")
                                notify.notify("File Renamed", fileRecord.filePath+"->"+entry.path, 2)
                                command = Command("RENAME", None, fixPath(
                                    fileRecord.filePath), fileRecord.recordID, None, None, fixPath(entry.path))  # send rename command
                                fileRecord.fileName = entry.name  # update name
                                fileRecord.filePath = entry.path  # update path
                                saveDataSet()  # save database to file
                                comMngr.sendCommand(command)
                                matched = True
                                break
                if(len(dirDataSet) == 0 or not matched):  # new file or folder found
                    if not isDir:  # its a file
                        util.printToLog("new file found : "+entry.path)
                        notify.notify("New File Found!", entry.path, 2)
                        fileHash = md5checksum(entry.path)  # create hash
                        if(isServer):
                            connList = comMngr.getConnections()
                            newRecordset = FileRecord(
                                entry.name, isDir, entry.path, fileHash, info.st_size, info.st_mtime, info.st_ctime, info.st_ino)  # create a new file record for our database
                            dirDataSet.append(newRecordset)  # add it
                            saveDataSet()  # save database to file
                            for conn in connList:  # send the file to all the clients
                                # create file sending object
                                sendFile = ServerFileSend(ipAddr, entry.path)
                                newPort = sendFile.getPort()  # get the port that was opened (its random)
                                command = Command("CLIENT_GET_FILE", None, fixPath(
                                    entry.path), newRecordset.recordID, newPort, None, None)  # send command with details
                                comMngr.sendCommandToIndClient(command, conn)
                        else:
                            newRecordset = FileRecord(
                                entry.name, isDir, entry.path, fileHash, info.st_size, info.st_mtime, info.st_ctime, info.st_ino)  # create a new file record for our database
                            dirDataSet.append(newRecordset)  # add it
                            saveDataSet()  # save database to file
                            command = Command("SERVER_GET_FILE", entry.name, fixPath(
                                entry.path), newRecordset.recordID, None, None, None)  # tell server we have a file for it
                            comMngr.sendCommand(command)
                    else:  # its a new folder
                        util.printToLog("new folder found : "+entry.path)
                        notify.notify("New Folder Found!", entry.path, 2)
                        fileHash = "Is_A_Dir"
                        newRecordset = FileRecord(
                            entry.name, isDir, entry.path, fileHash, info.st_size, info.st_mtime, info.st_ctime, info.st_ino)  # create a new file record for our database
                        dirDataSet.append(newRecordset)  # add it
                        saveDataSet()  # save database to file
                        command = Command("MKDIR", entry.name, fixPath(
                            entry.path), newRecordset.recordID, None, None, None)  # send a create folder command
                        comMngr.sendCommand(command)
                saveDataSet()  # save database to file
                # lock.release()
        dir_entries.close()
    except Exception as e:
        util.printToLog(e)
    # now go the other way to see if files were deleted (separate functions)

# check if a file exists in the suspect list
def existsInSuspectList(path):
    for item in suspects:
        if(path==item):
            return True
    return False

# second part of scaning folder for changes - see if we have records in our database that doesn't exists
def scanForDeleted():
    global suspects
    global comMngr
    if(not isServer):
        if(not comMngr.connected or comMngr.watingForServer):  # if we are a client and we are not connected - don't scan for changes and return - this will prevent un-syncing problems
            return
    else:
        if(comMngr.watingForClient): # same for server if wating on client
            return
    for fileRecord in dirDataSet:  # go through all the records
        if(fileRecord.isDir):  # folder record
            # if it doesn't exist - remove it from records and send to others
            if(not os.path.isdir(fileRecord.filePath)):
                # see if it is on the suspect list - if it is - remove it - if not add it
                if(existsInSuspectList(fileRecord.filePath)):
                    lock.acquire()
                    try:
                        dirDataSet.remove(fileRecord)  # remove it
                        suspects.remove(fileRecord.filePath) # remove from suspects
                        util.printToLog(
                            f"folder {fileRecord.fileName} has been deleted")
                        notify.notify("Folder Deleted", fileRecord.filePath, 2)
                        command = Command("DELETE_DIR", None, fixPath(
                            fileRecord.filePath), fileRecord.recordID, None, None, None)  # send to others to remove it
                        comMngr.sendCommand(command)
                    except:
                        pass
                    saveDataSet()  # save database to file
                    lock.release()
                else:
                    suspects.append(fileRecord.filePath)
            else: # does exist - check if it was in suspect list and if it was remove from suspects
                if(existsInSuspectList(fileRecord.filePath)):
                    suspects.remove(fileRecord.filePath)

        else:  # its a file
            # if it doesn't exist - remove it from records and send to others
            if(not os.path.isfile(fileRecord.filePath)):
                # see if it is on the suspect list - if it is - remove it - if not add it
                if(existsInSuspectList(fileRecord.filePath)):
                    lock.acquire()
                    try:
                        dirDataSet.remove(fileRecord)  # remove it
                        suspects.remove(fileRecord.filePath) # remove from suspects
                        util.printToLog(
                            f"file {fileRecord.fileName} has been deleted")
                        notify.notify("File Deleted", fileRecord.filePath, 2)
                        command = Command("DELETE", None, fixPath(
                            fileRecord.filePath), fileRecord.recordID, None, None, None)  # send to others to remove it
                        comMngr.sendCommand(command)
                    except:
                        pass
                    saveDataSet()  # save database to file
                    lock.release()
                else:
                    suspects.append(fileRecord.filePath)
            else: # does exist - check if it was in suspect list and if it was remove from suspects
                if(existsInSuspectList(fileRecord.filePath)):
                    suspects.remove(fileRecord.filePath)


def main():
    global comMngr
    global syncedDir
    global isServer
    global ipAddr
    global notify

    # if we have a config file  - holding our synced dir path - get the path from there
    if(os.path.isfile("config.txt")):
        f = open("config.txt", 'r')
        syncedDir = f.read(2048)
        f.close()
    else:  # open a folder pick dialog to choose our synced folder
        root = tk.Tk()
        root.withdraw()
        folder_selected = filedialog.askdirectory()  # open dialog
        if folder_selected == "":  # if canceled - exit the program
            sys.exit("EXITING - you must choose a folder")
        # write our selected path to the config file
        f = open("config.txt", 'w')
        f.write(folder_selected)
        f.close
        syncedDir = folder_selected
    # object for communicating with this monitor (will be sent to other objects)
    monCom = MonitorCom()
    # check if we have a connection setting file and if so check there if we are a server
    if(os.path.isfile("connectionSettings.txt")):
        f = open("connectionSettings.txt", 'r')
        conf = json.load(f)
        isServer = conf['is_Server?']
        if(isServer == "yes"):
            isServer = True
        else:
            isServer = False
        f.close()
    else:  # if the file doesn't exist - assume we are a server
        isServer = True
    if(not openDataSet()):  # check if we have a database file save and if so import the database, if not create it
        if(isServer): # if its a server we add exiting files first, for the client they will be added later after getting al of the stuff from the server
            addFilesInDirs(syncedDir)
        saveDataSet()
    if(isServer):
        comMngr = Server(monCom)  # if we are a server - create a server object
    else:
        comMngr = Client(monCom)  # create a client object

    ipAddr = comMngr.getIP()  # get servers ip address
    if(not isServer and (len(dirDataSet) == 0)):
        # if we don't have anything in our database (meaning first connection)  - ask the server to send us all
        command = Command("SENDALL", None, None, None, None, None, None)
        comMngr.sendCommand(command)
    elif(not isServer and (len(dirDataSet) > 0)):
        # if we have somthing in our database - send a reconnected command to server with our database
        tmpDataSet = dirDataSet.copy()
        command = Command("RECONNECTED", None,
                          syncedDir, None, None, None, None)
        comMngr.sendCommand(command)
        comMngr.watingForServer = True
    recallScan(syncedDir)  # start re-calling scan folder functions
    notify = Notifier("images.png")  # create a notifier object
    # say hello
    notify.notify("Welcome", "SyncIt By Moti Fransis & Tomer Matityahu", 4)
    tray = Tray(monCom)  # create a tray icon object


# print our database to stdout


def printAllDataset():
    for fileRecord in dirDataSet:
        fileRecord.printData()


if __name__ == '__main__':
    main()
