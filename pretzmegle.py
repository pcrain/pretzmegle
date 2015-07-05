#!/usr/bin/python2
# -*- coding: utf-8 -*-

  # PretzMegle ~ A Linux Omegle client for the terminal
  #
  # Author: Patrick Crain (Captain Pretzel)
  # Version: 1.0 (June 28, 2015)
  #
  # Usage: Optionally configure your settings below, and
  #   run "python2 pretzmegle.py" from the command line.
  #   If you have any interests, PretzMegle will search
  #   until at least one match is found; otherwise,
  #   you will be connected to a random stranger. Press
  #   Control+C during a chat to disconnect, or at any
  #   other time to close PretzMegle completely. Enjoy!
  #
  # Requirements:
  #   Linux
  #   Python 2
  #   An openable web browser (only for ReCaptchas)
  #
  # Features:
  #   Works from the terminal!
  #   Automatically saves logs, with optional timestamps.
  #   Optional sound effects when sending / receiving a
  #     message.
  #   Solve ReCaptchas straight from the command line.
  #   Never connects to any stranger without at least one
  #     matching interest (unless you don't list any).
  #   Color-coded for ease on the eyes!
  #   Uses only standard Python2 libraries.
  #   Runs without an X server (unless ReCaptchas need
  #     to be solved).
  #
  # ToDo:
  #   Get this thing working on Windows / OS X
  #   Download ReCaptchas to eliminate browser completely
  #
  # Known Bugs
  #   <none known>

##################################
### USER CONFIGURATION OPTIONS ###
##################################

PLAYSOUND=True                     # Whether to play sounds
TIMESTAMPS=True                    # Whether to record timestamps in logs
AUTOOPEN=True                      # Whether to automatically open captchas
LOGDIR='~/documents/logs/omegle/'  # Folder for chat logs
INTERESTS=[                    # List of your interests
  "linux",
  "omegle",
  "Python",
  "programming",
]
# INTERESTS=[]                # Uncomment for no interests

#########################################################
### MESS WITH THINGS BELOW THIS LINE AT YOUR OWN RISK ###
#########################################################

# Imports
import urllib2 as url
import httplib as http
import urllib, sys, time, os, threading, json, re, string, math, random
import readline, subprocess, webbrowser

# Constants
SERVER=random.choice([
  'http://front1.omegle.com','http://front2.omegle.com',
  'http://front3.omegle.com','http://front4.omegle.com',
  'http://front5.omegle.com','http://front6.omegle.com',
])
GOOGLE_KEY="AIzaSyBpFGt7-C95n9rW-7ZrGcMTTm3p0XiY4Rc"

# Global variables
global _canType, _canSend, _talkThread, _talkThreadRunning, _typing, _logfile
global _newid, _typeThreadRunning, _typeThread

# Colors / terminal column escape codes
class col:
  BLN      ='\033[0m'            # Blank
  UND      ='\033[1;4m'          # Underlined
  INV      ='\033[1;7m'          # Inverted
  CRT      ='\033[1;41m'         # Critical
  BLK      ='\033[1;30m'         # Black
  RED      ='\033[1;31m'         # Red
  GRN      ='\033[1;32m'         # Green
  YLW      ='\033[1;33m'         # Yellow
  BLU      ='\033[1;34m'         # Blue
  MGN      ='\033[1;35m'         # Magenta
  CYN      ='\033[1;36m'         # Cyan
  WHT      ='\033[1;37m'         # White
  C_UP     = '\x1b[1A'           # Up one row
  C_DOWN   = '\x1b[1B'           # Down one rom
  C_HOME   = '\x1b[100D'         # Start of row
  CLR_LINE = '\x1b[2K'           # Clear row
  UP_CLR   = C_UP+CLR_LINE       # Go up and clear
  FRESH    = CLR_LINE+C_HOME+BLN # Completely refresh row

# Prompt specifcations
class pr:
  IN_PROMPT         = '> '            # Prompt for input (no special formatting allowed)
  SND_PROMPT        = col.CYN + '> '  # Prompt for sent input
  RCV_PROMPT        = col.MGN + '< '  # Prompt for received input
  BAD_PROMPT        = col.RED + '@ '  # Prompt for unsendably input
  INT_PROMPT        = col.GRN + '* '  # Prompt for interests
  NOTE_PROMPT       = col.YLW + '# '  # Prompt for notifications
  WARN_PROMPT       = col.RED + '! '  # Prompt for warnings

def _main():
  global _talkThreadRunning, _canSend, _typeThreadRunning
  _talkThreadRunning = _canSend = _typeThreadRunning = False
  while True:
    try:
      omegleConnect()
    except KeyboardInterrupt:
      omegleInterrupt()
    except:
      freshLine(pr.WARN_PROMPT + 'UNKNOWN EXCEPTION')

def captchaLink(captchaid):
  fetchUrl = ('http://www.google.com/recaptcha/api/challenge?k=' + captchaid)
  site = url.urlopen(fetchUrl)
  sstring = site.read()
  cpos = sstring.find("challenge :")
  challenge = sstring[cpos+13:sstring.find('timeout',cpos)-7]
  return challenge

def checkTyping():
  global _typeThreadRunning
  meTyping = False
  _typeThreadRunning = True
  lastbuffer = 0
  while True:
    time.sleep(0.5)
    if not _typeThreadRunning:
      break
    newbuffer = readline.get_line_buffer().__len__()
    if newbuffer == 0:
      continue
    if newbuffer != lastbuffer:
      lastbuffer = newbuffer
      if not meTyping:
        meTyping = True
        msgReq = url.urlopen(SERVER+'/typing', '&id='+_newid)
        msgReq.close()
    else:
      if meTyping:
        meTyping = False
        msgReq = url.urlopen(SERVER+'/stoppedtyping', '&id='+_newid)
        msgReq.close()

def clearToBuffer():
  dellines = (readline.get_line_buffer().__len__()+2)/termWidth()
  for _ in range(0, dellines):
    sys.stdout.write(col.C_DOWN)
  for _ in range(0, dellines):
    sys.stdout.write(col.UP_CLR)

def closeGracefully():
  try:
    joinTalkThread()
    freshLine(pr.WARN_PROMPT + 'Chat terminated.')
    time.sleep(1)
    sys.exit(0)
  except KeyboardInterrupt:
    sys.exit(0)

def datestamp():
  return time.strftime("%Y-%m-%d_%H-%M-%S")

def exactLineBuffer():
  blen = readline.get_line_buffer().__len__()+pr.IN_PROMPT.__len__()
  return ((blen % termWidth()) == 0)

def exactlyOneLineBuffer():
  blen = readline.get_line_buffer().__len__()+pr.IN_PROMPT.__len__()
  return (blen == termWidth())

def extractMessage(rec):
  msgbeg = rec.find("gotMessage")+13
  msgend = rec.find("],[",msgbeg)-1
  if (msgend < 0):
    msgend = len( rec ) - 3
  return myDecode(rec[msgbeg:msgend])

def freshLine(prntstr):
  print(col.FRESH + prntstr + col.BLN)

def getLikes(chkstr):
  lpos = chkstr.find("commonLikes")
  if lpos >= 0:
    lpos2 = chkstr.find("]",lpos)+1
    common = chkstr[lpos+13:lpos2]
    common = re.sub('[\[\]\"]', '', common)
    common = re.sub(',', ', ', common)
    return common
  return ''

def hidePrompt():
  dellines = (readline.get_line_buffer().__len__()+2)/termWidth()
  for _ in range(0, dellines):
    sys.stdout.write(col.UP_CLR)

def joinTalkThread():
  global _talkThreadRunning, _canSend, _talkThread, _canType
  if _talkThreadRunning:
    _talkThreadRunning = _canType = False
    _canSend = True
    _talkThread.join()

def joinTypeThread():
  global _typeThreadRunning, _typeThread
  if _typeThreadRunning:
    _typeThreadRunning = False
    _typeThread.join()

def listenServer( id, req ):
  global _newid, _typeThread, _typeThreadRunning, _typing, _canType, _canSend
  _typing = False;
  while True:
    site = url.urlopen(req)
    rec = site.read()
    if 'waiting' in rec:
      freshLine(pr.NOTE_PROMPT + 'Looking for partner...')
    elif 'strangerDisconnected' in rec:
      _canSend = False
      _newid = None
      freshLine(pr.NOTE_PROMPT + 'Stranger disconnected')
      stopLogging()
      joinTypeThread()
      time.sleep(1)
      break
    elif 'connected' in rec:
      hidePrompt()
      refreshPrompt()
      startNewChat(rec)
    elif 'gotMessage' in rec:
      recmsg = extractMessage(rec)
      hidePrompt()
      if _typing:
        _typing = False
        sys.stdout.write(col.C_UP)
      if exactLineBuffer():
        sys.stdout.write(col.C_DOWN)
      freshLine(pr.RCV_PROMPT + recmsg)
      refreshPrompt()
      logMessage(myEncode("Stranger: " + recmsg + "\n"))
      sound("msg.mp3")
    elif 'stoppedTyping' in rec:
      if _typing:
        if exactLineBuffer():
          sys.stdout.write(col.C_DOWN)
        clearToBuffer()
        hidePrompt()
        sys.stdout.write(col.FRESH + col.C_UP + col.FRESH)
        refreshPrompt()
        if exactLineBuffer():
          sys.stdout.write(col.C_DOWN + col.C_HOME)
        _typing = False;
    elif 'typing' in rec:
      if not _typing:
        sys.stdout.write(col.FRESH)
        hidePrompt()
        if exactLineBuffer():
          sys.stdout.write(col.C_HOME)
        freshLine(pr.NOTE_PROMPT + 'Stranger is typing...')
        refreshPrompt()
        _typing = True;

def logMessage(message):
  global _logfile
  if TIMESTAMPS:
    _logfile.write("["+timestamp()+"] "+message)
  else:
    _logfile.write(message)

def myDecode(chkstr):
  try:
    return urlUnescape(chkstr.decode('UTF-8').decode('unicode-escape'))
  except:
    return urlUnescape(chkstr)

def myEncode(chkstr):
  try:
    return chkstr.encode("utf8", "replace")
  except:
    return chkstr

def obtainId(resp):
  idpos = resp.find("shard2")
  if idpos < 0:
    idpos = resp.find("central2")
  return resp[idpos:resp.find('"',idpos)]

def omegleConnect():
  global _talkThreadRunning, _typeThread, _talkThread, _newid

  joinTypeThread()
  _typeThread = threading.Thread(target = checkTyping)

  if _talkThreadRunning:
    freshLine(pr.NOTE_PROMPT + 'Enter for new chat; Ctrl+C -> Enter to quit.')
    joinTalkThread()
  _talkThread = threading.Thread(target = talk)

  sstring = url.urlopen(SERVER+'/start?rcs=1&firstevents=1&spid=&randid='+randid()+'&'+parseInterests()+'&lang=en').read()
  _newid = obtainId(sstring)
  events = url.Request(SERVER+'/events', urllib.urlencode( {'id':_newid}))

  if sstring.find("recaptcha") >= 0:
    sstring = solveCaptchaPrompt(sstring,events)

  if sstring.find("connected") >= 0:
    startNewChat(sstring)
  elif sstring.find("waiting") >= 0:
    freshLine(pr.NOTE_PROMPT + 'Looking for partner...')
  else:
    freshLine(pr.WARN_PROMPT + 'UNKNOWN EVENT: ' + sstring)

  listenServer(_newid,events)

def omegleInterrupt():
  try:
    global _typeThreadRunning, _talkThread, _canType, _newid
    if _newid and _typeThreadRunning:
      dc = url.Request(SERVER+'/disconnect', urllib.urlencode( {'id':_newid}))
      site = url.urlopen(dc)
      rec = site.read()
      freshLine(pr.NOTE_PROMPT + 'You disconnected.')
      stopLogging()
      joinTypeThread()
      try:
        time.sleep(1)
      except KeyboardInterrupt:
        closeGracefully()
    else:
      closeGracefully()
  except KeyboardInterrupt:
    os._exit(0)
  except SystemExit:
    os._exit(0)

def openBrowser(urlstr):
   webbrowser.get().open(urlstr)

def parseInterests():
  ints = str(INTERESTS).replace("'", '"').replace(" ", '_').replace(",_", ',')
  return urllib.urlencode( {'topics':ints}).translate(None, "+").replace("_","%20")

def playfile(audio_file_path):
  subprocess.call(["ffplay", "-nodisp", "-autoexit", "-loglevel","quiet", audio_file_path],stdout=open(os.devnull, 'wb'))

def randid():
  RANDID_SELECTION = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
  randid = ''
  for _ in range(0, 8):
      c = int(math.floor(32 * random.random()))
      randid += RANDID_SELECTION[c]
  return randid

def refreshPrompt():
  global _canSend
  if _talkThreadRunning:
    if _canSend or (readline.get_line_buffer().__len__() < 1):
      _canSend = _canType = True
      sys.stdout.write(pr.IN_PROMPT+readline.get_line_buffer())
    else:
      sys.stdout.write(pr.BAD_PROMPT)
    sys.stdout.flush()

def sendCaptchaResponse(captcha,response):
  srv = SERVER+'/recaptcha'
  header = urllib.urlencode( {'id':_newid,'challenge':captcha,'response':response} )
  reply = url.Request(srv, header)
  site = url.urlopen(reply)
  return site.read()

def shortenUrl(urlstr):
  post_url = 'https://www.googleapis.com/urlshortener/v1/url?key=' + GOOGLE_KEY
  postdata = {'longUrl':urlstr,'key':GOOGLE_KEY}
  headers = {'Content-Type':'application/json'}
  req = url.Request(post_url, json.dumps(postdata), headers)
  ret = url.urlopen(req).read()
  return json.loads(ret)['id']

def solveCaptchaPrompt(resp,events):
  cpos = resp.find("recaptchaRequired")
  captcha = resp[cpos+20:resp.find('"]',cpos)]
  while True:
    challenge = captchaLink(captcha)
    captchaurl = "http://www.google.com/recaptcha/api/image?c=" + challenge
    captchaurl = shortenUrl(captchaurl)
    freshLine(pr.WARN_PROMPT + 'ReCaptcha required: ' + col.GRN + captchaurl)
    if AUTOOPEN:
      openBrowser(captchaurl)
    answer = str(raw_input(pr.IN_PROMPT))
    sys.stdout.write(col.UP_CLR + col.CYN + "> " + answer + ": " + col.BLN)
    sendCaptchaResponse(challenge,answer)
    ev = url.urlopen(events).read()
    if ev.find("recaptcha") >= 0:
      print(col.RED + 'rejected.' + col.BLN)
      continue
    print(col.GRN + 'accepted!' + col.BLN)
    return ev

def sound(fpath):
  if PLAYSOUND:
    here = os.path.dirname(os.path.realpath(sys.argv[0])) + "/"
    _sThread = threading.Thread(target = playfile,args=(here+fpath,))
    _sThread.start()

def startLogging():
  global _logfile
  logdir = os.path.expanduser(LOGDIR)
  if not os.path.exists(logdir):
    os.makedirs(logdir)
  _logfile = open(logdir+'omegle-'+datestamp(),'wb',0)

def startNewChat(likestr):
  global _talkThreadRunning, _typeThreadRunning, _talkThread, _typeThread, _canSend
  startLogging()
  freshLine(pr.NOTE_PROMPT + 'New chat started')
  if ('commonLikes' in likestr):
    hidePrompt()
    freshLine(pr.INT_PROMPT + 'Common interests: ' + getLikes(likestr))
    refreshPrompt()
  if not _talkThreadRunning:
    _talkThreadRunning = True
    _talkThread.start()
  elif (readline.get_line_buffer().__len__() > 0):
    _canSend = False
    sys.stdout.write(col.FRESH + pr.BAD_PROMPT)
    sys.stdout.flush()
  if not _typeThreadRunning:
    _typeThread.start()

def stopLogging():
  global _logfile
  _logfile.close()

def talk():
  global _canType, _canSend, _logfile, _newid, _typing
  while True:
    _canType = _canSend = True
    msg = ''
    while _canType and _canSend and (not msg):
      sys.stdout.write(col.FRESH)
      msg = str(raw_input(pr.IN_PROMPT))
      if not msg:
        sys.stdout.write(col.UP_CLR)
        sys.stdout.flush()
    if _typing:
      sys.stdout.write(col.UP_CLR)
      _typing = False
    if not _canSend:
      sys.stdout.write(col.UP_CLR)
      sys.stdout.flush()
      freshLine(pr.WARN_PROMPT + 'Old buffer cleared. Please retype message.')
    elif _canType and msg:
      logMessage("Me: " + msg + "\n")
      for _ in range(0, (msg.__len__()+1)/termWidth()):
        sys.stdout.write(col.UP_CLR)
      print(col.UP_CLR + pr.SND_PROMPT + msg + col.BLN)
      msgReq = url.urlopen(SERVER+'/send', '&msg='+urlEscape(msg)+'&id='+_newid)
      msgReq.close()
      sound("msg.mp3")
    else:
      break

def timestamp():
  return time.strftime("%H:%M:%S")

def termWidth():
  th, tw = os.popen('stty size', 'r').read().split()
  tw = int(tw)
  return tw

def urlEscape(chkstr):
  return chkstr.replace("&","%26").replace("+","%2B").replace(";","%3B").replace("]","%5D")

def urlUnescape(chkstr):
  return chkstr.replace("\/","/")

if __name__ == "__main__":
  _main()
