#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import paho.mqtt.client as mqtt
import time, ssl, random
import datetime
import configparser
import sys, getopt
import pigpio

LOG_FATAL = 0
LOG_ERROR = 1
LOG_WARN  = 2
LOG_INFO  = 3
LOG_DEBUG = 4

# client, user and device details
serverUrl   = "localhost"
username    = "<<username>>"
password    = "<<password>>"

clientId    = "pyGPIOmon"
deviceName  = "PyGPIO Monitor"
LOGFILE     = "./py-gpio-monitor.log"
LOG_LEVEL   = LOG_INFO
gpios       = []
configFile  = './py-gpio-monitor.ini'

def cli_help():
  print('Usage: '+sys.argv[0]+' -c <configfile> -g <gpios> -v <verbose level> -l <logfile>')
  print()
  print('  -c | --config: ini-style configuration file, default is '+configFile)
  print('  -g | --gpios: comma separated list of gpios to monitor')
  print('  -v | --verbose: 0-fatal, 1-error, 2-warning, 3-info, 4-debug')
  print('  -l | --logfile: log file name,default is '+LOGFILE)  
  print()
  print('Example: '+sys.argv[0]+' -c /etc/monitor.ini -g13,24,25 -v 2 -l /var/log/monitor.log')

def getOptions(argv):
  try:
    opts, args = getopt.getopt(argv,"hg:c:v:l:",["config=","verbose=", "logfile=","gpios="])
  except getopt.GetoptError:
    print("Command line argument error")
    help()
    sys.exit(2)

  for opt, arg in opts:
    if opt == '-h':
      help()
      sys.exit()
    elif opt in ("-c", "--config"):
      configFile = arg
    elif opt in ("-v", "--verbose"):
      LOG_LEVEL = int(arg)
    elif opt in ("-l", "--logfile"):
      LOGFILE = arg
    elif opt in ("-g", "--gpios"):
      for g in arg.split(','):
        gpios.append(int(g))

def getConfig(cf):
  print('Using configuration file ', cf)
  config = configparser.ConfigParser()
  config.read(cf)

  try:
    secServer = config['mqtt']
  except KeyError:
    print('Error: configuration file is not correct or missing')
    exit(1)

  serverUrl = secServer.get('url','localhost')
  username = secServer.get('username')
  password = secServer.get('password')
  clientId = secServer.get('clientid','pyGPIOmon')

def console(msg):
  ts = datetime.datetime.now().isoformat(timespec="seconds")
  print(ts,msg)

class PyGPIOmon:
  def __init__(self, clientId, name, mqttClient, gpios, pi, logFile):
    print("Initializing")
    self._clientId = clientId
    self._name = name
    self._running = True
    self._mqtt = mqttClient # mqtt client
    self._gpios = {}
    for g in gpios: 
      self._gpios[g]={'t':0, 's':0, 'u':False} # object constaining gpio statuses
    print('initialized', self._gpios)
    self._logF = logFile # log file name
    self._pi = pi  # pigpio instance
    self._f = 0  # logfile
    self._mqtt.on_message = self.on_message
    self._mqtt.on_publish = self.on_publish
    self._mqtt.on_connect = self.on_mqtt_connect
    self._mqtt_reconnect = 0

  def stop(self):
    for g in self._gpios:
      self._gpios[g]['cb'].cancel()
  
  def start(self):
    print("Starting " + self._name)
    print("Opening log file " + self._logF)

    try:
      self._f = open(self._logF, "a")
    except FileNotFoundError:
      print("Error opening log file.")
      exit(1)

    self.logI("*** PyGPIOmon Starting")
    self.logI("Starting MQTT client")
    self._mqtt.loop_start()
    self._mqtt.subscribe("cmd/"+self._clientId)

    print("Connecting to gpios")
    # register callback function for interrupts
    t = pi.get_current_tick()
    for g in self._gpios:
      print("g=",g)
      self._gpios[g]['cb'] = pi.callback(g, pigpio.EITHER_EDGE, self.cbf)
      self._gpios[g]['t'] = t
    
    print("GPIO monitor started.")
    
  def loop(self):
    if self._running:
      if self._mqtt_reconnect > 0:
        self.logW("MQTT Reconnecting...")
        self._mqtt.reconnect()
      t = pi.get_current_tick()  
      for g in self._gpios:
        if (pigpio.tickDiff(self._gpios[g]['t'],t) > 50000 and self._gpios[g]['u'] == True ):  # announce change only after some stable period
          print('Sending ',g)
          self._gpios[g]['u'] = False
          if self._gpios[g]['s'] == 1:
            self.publish('GPIO:'+str(g),"ON")
          else:
            self.publish('GPIO:'+str(g),"OFF")

  def logW(self, msg):
    self.log(msg, level=LOG_WARN)

  def logE(self, msg):
    self.log(msg, level=LOG_ERROR)

  def logD(self, msg):
    self.log(msg, level=LOG_DEBUG)

  def logI(self, msg):
    self.log(msg, level=LOG_INFO)  
  
  def log(self, msg, level=LOG_WARN):
    if level > LOG_LEVEL: 
      return
    l = ["F","E","W","I","D"]
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    print(ts + "  " + l[level] + "  " + msg)
    self._f.write(ts + "  " + l[level] + "  " + msg + "\n")
   
  # display all incoming messages
  def on_message(self, userdata, message):
    self.logI("MQTT received msg="+str(message.payload))
  
  def on_publish(self, userdata, mid):
    self.receivedMessages.append(mid)
  
  def on_mqtt_connect(self, client, userdata, flags, rc):
    self.mqtt_connected = rc
    self._mqtt_reconnect = 0
    if rc != 0:
      self.logE("MQTT connection returned result="+rc)
      self._mqtt_reconnect += 1
      if self._mqtt_reconnect > 12: self._mqtt_reconnect = 12
      self.mqtt_reconnect_delay = 2**self._mqtt_reconnect
    else:
      self.logI("Connected to MQTT broker.")
  
  def on_mqtt_disconnect(self, client, userdata, rc):
    self._mqtt_reconnect = 1
    if rc != 0:
      self.logE("MQTT unexpected disconnection.")
      self._mqtt_reconnect = True
      self.mqtt_reconnect_delay = 10
  
  # publish a message
  def publish(self, topic, message, waitForAck = False):
    mid = self._mqtt.publish(topic, message, 1)[1]
    if (waitForAck):
        while mid not in self.receivedMessages:
            time.sleep(0.25)

  # callback for interrupts
  def cbf(self, GPIO, level, tick):
    print("GPIO status changed",GPIO,level)
    self._gpios[GPIO]['t'] = tick
    self._gpios[GPIO]['u'] = True
    if level == pigpio.RISING_EDGE:
      self._gpios[GPIO]['s'] = 1
    else:
      self._gpios[GPIO]['s'] = 0

#-------------------------------------------------------
getOptions(sys.argv[1:])
getConfig(configFile)

if len(gpios) == 0:
  print("Error: no gpios specified")
  cli_help()
  exit(1)

print("Going to monitor gpios=", gpios)

pi = pigpio.pi()

if not pi.connected:
  print("Error: Failed connecting to pigpiod. Installed and running?")
  exit(3)

# connect the client to MQTT broker and register a device
print("Creating MQTT client for",serverUrl)
mqtt = mqtt.Client(clientId)
mqtt.username_pw_set(username, password)
mqtt.connect_async(serverUrl)

print("Creating PyGPIOmon device as",clientId)
mon = PyGPIOmon(clientId, deviceName, mqtt, gpios, pi, LOGFILE)
mon.start()

try:
  t=time.time()
  while True:
    if time.time()-t > 30:
      console("PyGPIOmon is alive")
      t=time.time()
    time.sleep(1)
    mon.loop()
except KeyboardInterrupt:
  print("\nTidying up")
  mon.stop()

pi.stop()
