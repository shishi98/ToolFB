import requests, sys, getopt, getpass, json
import logging
import logging.config
from requests.auth import HTTPBasicAuth
from builtins import str

""" Global Variables
    Defaults are set from configuration file via processArgs()
"""
xmodURL = None
authUser = None
authPassword = None
outDirectory = None
outFilename = None
outFile = None
dirSep = "/"
niceNames = None
basicAuth = None
logger = None

def configure_logger(name: str, log_path: str):
    logging.config.dictConfig({
        'version': 1,
        'formatters': {
            'default': {'format': '%(asctime)s - %(levelname)s - %(message)s', 'datefmt': '%Y-%m-%d %H:%M:%S'}
        },
        'handlers': {
            'console': {
                'level': 'INFO',
                'class': 'logging.StreamHandler',
                'formatter': 'default',
                'stream': 'ext://sys.stdout'
            },
            'file': {
                'level': 'INFO',
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'default',
                'filename': log_path,
                'maxBytes': (10*1024*1024),
                'backupCount': 3
            }
        },
        'loggers': {
            'default': {
                'level': 'INFO',
                'handlers': ['file']
            }
        },
        'disable_existing_loggers': False
    })
    return logging.getLogger(name)

def logAndExit(url, response):
    global logger
    json = response.json()
    logger.error("Error %d on initial request to %s.\nPlease verify" +\
                 " instance address, user, and password\n",
                 response.status_code, url)
    logger.error("Response - code: %d, reason: %s, message: %s", 
                 json['code'], str(json['reason']), str(json['message']))
    sys.exit()

def usage(errMsg: str = None):
    global logger
    print("getGroupMembers.py -p <password> | --password=<password> | -P " +
          "(prompt for password)\n\
            \t[-i <xMatters Instance> | --instance=<xMatters Instance>] \n\
            \t[-u <user> | --user=<user>] \n\
            \t[-n <true|1|false|0> | --nicenames=<true|1|false|0> or -N (-n 1)] \n\
            \t[-d <outputDirectory> | --dir=<outputDirectory>] \n\
            \t[-f <outputFilename> | --ofile=<outputFilename>]\n\n\
            Any values in square brackets may be defaulted by setting an " +
            "equivalent value in the defaults.json file.\n"
         )
    if (errMsg != None):
        print(errMsg)
        logger.error(errMsg)
        
def processArgs(argv: list):
    global xmodURL, authUser, authPassword, outDirectory, outFilename, \
           basicAuth, niceNames, logger, dirSep
           
    # First try to read in the defaults from defaults.json
    cfg = json.load(open('defaults.json'))
    if (cfg['instance'] != ''):
        xmodURL = cfg['instance']
    if (cfg['user'] != ''):
        authUser = cfg['user']
    if (cfg['password'] != ''):
        authPassword = cfg['password']
    if (cfg['nicenames'] != ''):
        niceNames = ((cfg['nicenames'].lower() == "true") or
                     (cfg['nicenames'] == "1"))
    if (cfg['odir'] != ''):
        outDirectory = cfg['odir']
    if (cfg['ofile'] != ''):
        outFilename = cfg['ofile']
    if (cfg['dirsep'] != ''):
        dirSep = cfg['dirsep']
    
    # Process the input arguments
    try:
        opts, _ = getopt.getopt(argv,"hi:u:p:Pn:Nd:f:",
                             ["help","instance=","user=","password=",
                              "nicenames=","odir=","ofile="])
    except getopt.GetoptError:
        usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-i", "--instance"):
            xmodURL = arg
        elif opt in ("-u", "--user"):
            authUser = arg
        elif opt in ("-p", "--password"):
            authPassword = arg
        elif opt in ("-n", "--nicenames"):
            niceNames = ((arg.lower() == "true") or (arg == "1"))
        elif (opt == "-N"):
            niceNames = True
        elif opt in ("-d", "--odir"):
            outDirectory = arg
        elif opt in ("-f", "--ofile"):
            outFilename = arg
        elif (opt == "-P"):
            authPassword = getpass.getpass();
    if (xmodURL is None):
        usage("-i or --instance was not specified.")
        sys.exit(3)
    else:
        logger.info ('Instance is: %s', xmodURL)
    if (authUser is None):
        usage("-u or --user was not specified.")
        sys.exit(3)
    else:
        logger.info ('User is: %s', authUser)
    if (authPassword is None):
        usage("-p, --password, or -P was not specified.")
        sys.exit(3)
    else:
        logger.info ('Password len is: %d', len(authPassword))
    if (outDirectory is None):
        usage("-d or --odir was not specified.")
        sys.exit(3)
    else:
        logger.info ('Output directory is: %s', outDirectory)
    if (outFilename is None):
        usage("-f or --ofile was not specified.")
        sys.exit(3)
    else:
        logger.info ('Output file is: %s', outFilename)

    # Setup the basic auth object for subsequent REST calls
    basicAuth = HTTPBasicAuth(authUser, authPassword)

def getUserProperties(targetName: str) -> dict:
    """ Get the detailed properties for the user defined by targetName.
    """
    global xmodURL, basicAuth, logger
    
    # Set our resource URI
    url = xmodURL + '/api/xm/1/people/' + targetName
    
    # Get the member
    response = requests.get (url, auth=basicAuth)
    json = response.json()
    userProperties = {}

    # Did we find the user?
    if (response.status_code == 200):
        userProperties['firstName'] = json['firstName']
        userProperties['lastName'] = json['lastName']
    elif (response.status_code == 404):
        userProperties['firstName'] = "User Not Found"
        userProperties['lastName'] = "User Not Found"
    else:
        logAndExit(url, response)

    return userProperties

def getAndWriteMembers(targetName: str):
    """ Based on the targetName of the group being supplied, query for and
        put the names of the members into the output file. 
    """
    global xmodURL, basicAuth, outFile, niceNames, logger

    # Set our resource URI
    target = targetName
    if ('/' in target): # Convert embedded slash to encoded value
        target = target.replace("/","%2f")
    baseURL = xmodURL + '/api/xm/1/groups/' + target + '/members'
    url = baseURL + '?offset=0&limit=100'
    
    # Initialize loop with first request
    response = requests.get (url, auth=basicAuth)
    # If first request fails, then terminate
    if (response.status_code == 404):
        logger.error('getAndWriteMembers - Group not found: ' + targetName)
        # Group went away after we had started the process
    elif (response.status_code != 200):
        logAndExit(url, response)
    cnt = 0
    nMembers = 1
    
    # Continue until we exhaust the group list
    while ((cnt < nMembers) and (response.status_code == 200)):
        
        # Iterate through the result set
        json = response.json()
        nMembers = json['total']
        for d in json['data']:
            cnt += 1
            if (niceNames):
                userProps = getUserProperties(d['member']['targetName'])
                outFile.write('"' + targetName + '","' + \
                              d['member']['targetName'] + \
                              '","' + d['member']['recipientType'] + \
                              '","' + userProps['firstName'] + \
                              '","' + userProps['lastName'] + '"\n')
            else:
                outFile.write('"' + targetName + '","' + \
                              d['member']['targetName'] + \
                              '","' + d['member']['recipientType'] + \
                              '","",""\n')
        
        # If there are more users to get, then request the next page
        if (cnt < nMembers):
            getLimit = str(100 if (nMembers - cnt) >= 100 \
                           else (nMembers - cnt))
            logger.info ("Getting next %d Users.", getLimit)
            offset = '?offset=' + str(cnt) + '&limit=' + getLimit
            url = baseURL + offset
            response = requests.get (url, auth=basicAuth)
    
    else:
        logger.info ("Retrieved a total of %d from a possible %d" + \
                     " group members.", cnt, nMembers)    

def processGroups():
    """ Request the list of group names from this instance.
        Iterate through the groups and request the member list to be
        written to the output file.
    """
    global basicAuth, outFile, logger

    # Set our resource URLs
    baseURL = xmodURL + '/api/xm/1/groups'
    url = baseURL + '?offset=0&limit=100'
    
    # Initialize loop with first request
    cnt = 0
    nGroups = 1
    response = requests.get (url, auth=basicAuth)
    # If the initial response fails, then just terminate the process
    if (response.status_code != 200):
        logAndExit(url, response)

    # Continue until we exhaust the group list
    while ((cnt < nGroups) and (response.status_code == 200)):
        
        # Iterate through the result set
        json = response.json()
        nGroups = json['total']
        strNGroups = str(json['total'])
        logger.info ("Retrieved a batch of %d groups from a total of %d groups.",
                     json['count'], json['total'])
        for d in json['data']:
            cnt += 1
            logger.info('Processing group #' + str(cnt) + ' of ' + strNGroups + \
                  ': "' + d['targetName'] + '"')
            getAndWriteMembers(d['targetName'])
        
        # If there are more groups to get, then request the next page
        if (cnt < nGroups):
            getLimit = str(100 if (nGroups - cnt) >= 100 else (nGroups - cnt))
            logger.info ("Getting next " + getLimit + " groups, starting at " + \
                    str(cnt) + ".")
            offset = '?offset=' + str(cnt) + '&limit=' + getLimit
            url = baseURL + offset
            response = requests.get (url, auth=basicAuth)
    
    else:
        logger.info ("Retrieved a total of %d from a possible %d groups.", 
                     cnt, nGroups)
            
def main(argv: list):
    global outFile, logger, dirSep
    
    # Initialize logging
    logger = configure_logger('default', 'getGroupMembers.log')
    logger.info('getGroupMembers Started.')
    
    # Process the input arguments
    processArgs(argv)
    
    # Create the output file, overwriting existing file if any
    outFile = open(outDirectory + dirSep + outFilename, 'w')
    
    # Write out the header row
    outFile.write('"Group Name","Member ID","Member Type","First Name","Last Name"\n')
    
    # Begin the process
    processGroups()
    
    logger.info('getGroupMembers Finished.')
    
if __name__ == "__main__":
    main(sys.argv[1:])
