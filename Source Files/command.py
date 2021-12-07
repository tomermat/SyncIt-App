
# this is a Command object that represents a coomand and all the details needed to keep files in sync
class Command():
    def __init__(self, command, aboutFile, path, recordID, port, moveTo, renameTo):
        self.command = command
        self.aboutFile = aboutFile
        self.path = path
        self.moveTo = moveTo
        self.renameTo = renameTo
        self.recordID = recordID
        self.port = port

    def printCommand(self):
        print(f"command: {self.command}")
        print(f"about file: {self.aboutFile}")
        print(f"path: {self.path}")
        print(f"move to: {self.moveTo}")
        print(f"rename to: {self.renameTo}")
        print(f"file recordID: {self.recordID}")
        print(f"port: {self.port}")
