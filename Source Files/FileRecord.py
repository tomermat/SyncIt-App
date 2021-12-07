import time
from datetime import datetime
import hashlib

# this is a FileRecord object that is created for each file we have - all filerecords are save in the main dataset and new files attributes are compared to them


class FileRecord:
    def __init__(self, file_Name, is_a_dir, file_Path, file_Hash, file_Size, file_mTime, file_cTime, file_inod_add):
        self.fileName = file_Name
        self.filePath = file_Path
        self.fileHash = file_Hash
        self.fileSize = file_Size
        self.filemTime = file_mTime
        self.filecTime = file_cTime
        self.isDir = is_a_dir
        self.fileInodAddr = file_inod_add
        hash = hashlib.md5()
        hash.update(str(datetime.now()).encode('utf-8'))
        hash = hash.hexdigest()
        self.recordID = hash

    def printData(self):
        print("file path: "+self.filePath)
        print("file name "+self.fileName)
        print("Is A Directory: "+str(self.isDir))
        print("file hash: "+self.fileHash)
        print("file mod time: "+str(time.ctime(self.filemTime)))
        print("file headr time: "+str(time.ctime(self.filecTime)))
        print("file size: "+str(self.fileSize) + "B")
        print("file inode address: "+str(self.fileInodAddr))
        print("file recordID: "+str(self.recordID))
        print()
