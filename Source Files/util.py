from datetime import datetime

# this function inserst a string to the log file - it records the current time and adds it to the start of the string
def printToLog(string):
    try:
        f = open('Log.txt', 'a')
        t = datetime.now().strftime("%d-%b-%Y %H:%M:%S")  # get time formatted nicely
        f.write("["+t+"]: "+string+"\n")
        f.close()
    except Exception:
        pass
