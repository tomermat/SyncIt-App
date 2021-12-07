import socket
import threading
from random import randint
import util
import os
import pickle

# this classes are responsible for server and clients file transfer :
# the main idea is that for each file and for each client  a separate socket on a random port is opened by the server
# in which the is sent through. after completing the transfer the socket is closed.
# when a client wants to send a file to the server - it ask for the server to open a socket, the server opens one and sends its details
# to the client and then the files is transferred


# this object is for the servers file receiving
class ServerFileReceive():
    # we get the servers ip address and the path where the file needs to be saved
    def __init__(self, ipAddr, filePath):
        self.file = filePath
        self.ip = ipAddr
        # create a new socket with a timeout of 60 secondes for the client to connect to
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.settimeout(60)
        # generate a random port in the range of 30,000 - 40,000 and try to bind it
        # keep trying if the port is not available
        foundPort = False
        while(not foundPort):
            self.port = randint(30000, 40000)
            try:
                self.s.bind((ipAddr, self.port))
                foundPort = True
            except:
                pass
        # open a new thread to listen to to clients connection
        thread = threading.Thread(target=self.startServer)
        thread.start()

    # return the generated port number
    def getPort(self):
        return self.port

    # runs as a thread to listen to to clients connection
    def startServer(self):
        self.s.listen()
        util.printToLog(
            f"[LISTENING] server is now listening on {self.ip} with port {self.port}.")
        try:
            conn, addr = self.s.accept()
            # open a new thread for the file transfer
            thread = threading.Thread(
                target=self.newConnection, args=(conn, addr))
            thread.start()
        except socket.timeout:
            util.printToLog(f"socket on port {self.port} closed because of timeout")

    isDone = False

    # this runs as a thread to receive a file from the client
    def newConnection(self, conn, addr):
        # create a random file name to save locally (this prevent big files discovering as new while still receiving them)
        randName = str(randint(0, 100000))+".tmp"
        while (os.path.isfile(randName)): # see that it doesn't already exist (low chance but can happen)
            randName = str(randint(0, 100000))+".tmp"
        file = open(randName, "wb")  # open the file for writing
        while(True):
            chunk = conn.recv(2048)  # receive the file in 2048B chunks
            while(chunk):
                file.write(chunk)  # write to the file
                chunk = conn.recv(2048)  # receive next chunk
            util.printToLog("File received!")
            file.close()
            break
        os.rename(randName,self.file)
        self.isDone = True

    # returns true if file transfer  is done, false otherwise
    def getIsDone(self):
        return self.isDone

# this object is for the servers file sending


class ServerFileSend():
    # we get the servers ip address and the path where the file we send is at
    def __init__(self, ipAddr, filePath):
        self.file = filePath
        self.ip = ipAddr
        # create a new socket with a timeout of 60 secondes for the client to connect to
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.settimeout(60)
        # generate a random port in the range of 30,000 - 40,000 and try to bind it
        # keep trying if the port is not available
        foundPort = False
        while(not foundPort):
            self.port = randint(30000, 40000)
            try:
                self.s.bind((ipAddr, self.port))
                foundPort = True
            except:
                pass
        # open a new thread to listen to to clients connection
        thread = threading.Thread(target=self.startServer)
        thread.start()

    # return the generated port number
    def getPort(self):
        return self.port

    # runs as a thread to listen to to clients connection
    def startServer(self):
        self.s.listen()
        util.printToLog(
            f"[LISTENING] server is now listening on {self.ip} with port {self.port}.")
        try:
            conn, addr = self.s.accept()
            # open a new thread for the file transfer
            thread = threading.Thread(
                target=self.newConnection, args=(conn, addr))
            thread.start()
        except socket.timeout:
            util.printToLog(f"socket on port {self.port} closed because of timeout")

    # this runs as a thread to send a file to the client
    def newConnection(self, conn, addr):
        util.printToLog(f"Sending {self.file}...")
        file = open(self.file, "rb")  # open the file for reading
        chunk = file.read(2048)  # read the file in 2048B chunks
        while(chunk):
            conn.send(chunk)  # send the chunk
            chunk = file.read(2048)  # read next chunk
        file.close()
        conn.close()
        util.printToLog(f"File {self.file} Sent!")

# this object is for the clients file sending


class ClientFileSend():
    # we get the servers ip address, the port and the path where the file we send is at
    def __init__(self, ipAddr, port, path):
        util.printToLog(f"need to send {path} to {ipAddr} on port {port}")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # connect to the server
        s.connect((ipAddr, port))
        # start sending the file
        util.printToLog(f"Sending {path} ...")
        file = open(path, "rb")  # open the file for reading       
        chunk = file.read(2048)  # read the file in 2048B chunks
        while(chunk):
            s.send(chunk)  # send the chunk
            chunk = file.read(2048)  # read next chunk
        file.close()
        s.close()
        util.printToLog(f"File {path} Sent!")

# this object is for the clients file receiving


class ClientFileReceive():
    isDone = False
    # we get the servers ip address, the port and the path where the file needs to be saved
    def __init__(self, ipAddr, port, path):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # connect to the server
        s.connect((ipAddr, port))
        # create a random file name to save locally (this prevent big files discovering as new while still receiving them)
        randName = str(randint(0, 100000))+".tmp"
        while (os.path.isfile(randName)): # see that it doesn't already exist (low chance but can happen)
            randName = str(randint(0, 100000))+".tmp"
        file = open(randName, "wb")  # open the file for writing
        while(True):
            chunk = s.recv(2048)  # receive the file in 2048B chunks
            while(chunk):
                file.write(chunk)  # write to the file
                chunk = s.recv(2048)  # receive next chunk
            util.printToLog(f"File {path} received!")
            file.close()
            break
        os.rename(randName,path)
        self.isDone = True

    # returns true if file transfer  is done, false otherwise
    def getIsDone(self):
        return self.isDone

# this function is for getting a dataset from a client in order to compare it 
class ServerDatasetReceive():
    rcvdDataSet=None
    # we get the servers ip address and the path where the file needs to be saved
    def __init__(self, ipAddr):
        self.ip = ipAddr
        # create a new socket with a timeout of 60 secondes for the client to connect to
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.settimeout(60)
        # generate a random port in the range of 30,000 - 40,000 and try to bind it
        # keep trying if the port is not available
        foundPort = False
        while(not foundPort):
            self.port = randint(30000, 40000)
            try:
                self.s.bind((ipAddr, self.port))
                foundPort = True
            except:
                pass
        # open a new thread to listen to to clients connection
        thread = threading.Thread(target=self.startServer)
        thread.start()

    # return the generated port number
    def getPort(self):
        return self.port
    
    # return the received dataset
    def getDataset(self):
        return self.rcvdDataSet

    # runs as a thread to listen to to clients connection
    def startServer(self):
        self.s.listen()
        util.printToLog(
            f"[LISTENING] server is now listening on {self.ip} with port {self.port} for dataset.")
        try:
            conn, addr = self.s.accept()
            # open a new thread for the file transfer
            thread = threading.Thread(
                target=self.newConnection, args=(conn, addr))
            thread.start()
        except socket.timeout:
            util.printToLog(f"socket on port {self.port} closed because of timeout")

    isDone = False
    # this runs as a thread to receive a file from the client
    def newConnection(self, conn, addr):
        # create a random file name to save locally (this prevent big files discovering as new while still receiving them)
        randName = "datasetRcvd"+str(randint(0, 100))+".tmp"
        while (os.path.isfile(randName)): # see that it doesn't already exist (low chance but can happen)
            randName = "datasetRcvd"+str(randint(0, 100))+".tmp"
        file = open(randName, "wb")  # open the file for writing
        while(True):
            chunk = conn.recv(2048)  # receive the file in 2048B chunks
            while(chunk):
                file.write(chunk)  # write to the file
                chunk = conn.recv(2048)  # receive next chunk
            util.printToLog(f"Dataset received from {addr}")
            file.close()
            break
        pick_file = open(randName, 'rb')  # read the file
        self.rcvdDataSet = pickle.load(pick_file)  # reconverts it back to an object
        pick_file.close()  # close the file
        self.isDone = True
        os.remove(randName)

    # returns true if file transfer  is done, false otherwise
    def getIsDone(self):
        return self.isDone

class ClientDatasetSend():
    # we get the servers ip address, the port and the path where the file we send is at
    def __init__(self, ipAddr, port):
        util.printToLog(f"need to send dataset to {ipAddr} on port {port}")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # connect to the server
        s.connect((ipAddr, port))
        # start sending the file
        util.printToLog(f"Sending dataset ...")
        file = open("dataset.pckl", "rb")  # open the file for reading       
        chunk = file.read(2048)  # read the file in 2048B chunks
        while(chunk):
            s.send(chunk)  # send the chunk
            chunk = file.read(2048)  # read next chunk
        file.close()
        s.close()
        util.printToLog(f"dataset Sent!")