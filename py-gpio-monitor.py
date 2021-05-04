#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import paho.mqtt.client as mqtt
import time
import datetime
import configparser
import sys
import getopt
import pigpio


# client, user and device details
serverUrl = "localhost"
username = "<<username>>"
password = "<<password>>"

devId = "pyGPIOmon"  # device id, also used as mqtt client id and mqtt base topic

logfile = "./py-gpio-monitor.log"
logLevel = Logger.LOG_INFO
gpios = []  # array of monitored gpios
gpiosSet = []  # array of settable gpios
configFile = './py-gpio-monitor.ini'
qos = 1


def cli_help():
    print('Usage: '+sys.argv[0] +
          ' -c <configfile> -v <verbose level> -l <logfile>')
    print()
    print('  -c | --config: ini-style configuration file, default is '+configFile)
    print('  -v | --verbose: 0-fatal, 1-error, 2-warning, 3-info, 4-debug')
    print('  -l | --logfile: log file name,default is '+logfile)
    print()
    print('Example: '+sys.argv[0] +
          ' -c /etc/monitor.ini -v 2 -l /var/log/monitor.log')


def getOptions(argv):
    try:
        opts, args = getopt.getopt(
            argv, "hc:v:l:", ["config=", "verbose=", "logfile="])
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
            loglevel = int(arg)
        elif opt in ("-l", "--logfile"):
            logfile = arg


def getConfig(cf):
    print('Using configuration file ', cf)
    config = configparser.ConfigParser()
    config.read(cf)

    try:
        seccfg = config['pygpiomon']
    except KeyError:
        print('Error: configuration file is not correct or missing')
        exit(1)

    serverUrl = seccfg.get('host', 'localhost')
    username = seccfg.get('username')
    password = seccfg.get('password')
    devId = seccfg.get('id', 'pyGPIOmon')
    qos = seccfg.get('qos', 1)
    a = seccfg.get('gpios_monitor')
    for g in a.split(','):
        gpios.append(int(g))
    a = seccfg.get('gpios_set')
    for g in a.split(','):
        gpiosSet.append(int(g))


class Logger:
    LogLevels = ["A", "F", "E", "W", "I", "D"]

    LOG_ALL = 0
    LOG_FATAL = 1
    LOG_ERROR = 2
    LOG_WARN = 3
    LOG_INFO = 4
    LOG_DEBUG = 5

    def __init__(self, *, filename="", console=False, level=self.LOG_INFO):
        self._f = 0
        self._console = console
        self.logLevel = level

        if filename != "":
            try:
                self._f = open(filename, "a")
            except FileNotFoundError:
                print("Error opening log file", filename)
                exit(1)

        if self._f == 0:
            self._console = True

    def warn(self, *args):
        self.log(args, level=self.LOG_WARN)

    def err(self, *args):
        self.log(args, level=self.LOG_ERROR)

    def debug(self, *args):
        self.log(args, level=self.LOG_DEBUG)

    def info(self, *args):
        self.log(args, level=self.LOG_INFO)

    def all(self, *args):
        self.log(args, level=self.LOG_ALL)

    def log(self, *args, level=self.LOG_WARN):
        if level > self.logLevel:
            return
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        line = ts + "  " + self.LogLevels[level]
        for a in args:
            line += " ".join(a)
        if self._f:
            self._f.write(line + "\n")
        if self._console:
            print(line)


class PyGPIOmon:
    def __init__(self, id, pi, mqttClient, *, qos=1, gpios=[], gpios_set=[], logger=Logger()):

        self._id = id
        self._pi = pi  # pigpio instance
        self._mqtt = mqttClient  # mqtt client

        self._gpios = {}
        for g in gpios:
            # object constaining gpio statuses
            self._gpios[g] = {'t': 0, 's': 0, 'u': False}

        self._gSet = gpios_set
        self.log = logger
        self._qos = qos

        self._f = 0  # logfile
        self._mqtt.on_message = self.on_message
        self._mqtt.on_publish = self.on_publish
        self._mqtt.on_connect = self.on_mqtt_connect
        self._mqtt_reconnect = 0
        self._aliveTime = 0

    def stop(self):
        for g in self._gpios:
            self._gpios[g]['cb'].cancel()

    def start(self):
        self.log.all("*** PyGPIOmon Starting", self._id)
        self.log.info("Starting MQTT client")

        self._mqtt.loop_start()
        self._mqtt.subscribe("cmd/"+self._id)

        self.log.debug("Monitoring gpios")
        # register callback function for interrupts
        t = pi.get_current_tick()
        for g in self._gpios:
            self.log.debug(" g=", g)
            self._gpios[g]['cb'] = pi.callback(
                g, pigpio.EITHER_EDGE, self.gpioCbf)
            self._gpios[g]['t'] = t

        print("\nGPIO monitor started.")
        print("Settable gpios", self._gSet)

    def loop(self):
        if self._mqtt_reconnect > 0:
            self.log.warn("MQTT Reconnecting...")
            self._mqtt.reconnect()
        t = pi.get_current_tick()
        for g in self._gpios:
            # announce change only after some stable period
            if (pigpio.tickDiff(self._gpios[g]['t'], t) > 50000 and self._gpios[g]['u'] == True):
                self.log.debug('MQTT Sending', g)
                self._gpios[g]['u'] = False
                if self._gpios[g]['s'] == 1:
                    self.publish('gpio/'+str(g), "ON", self._qos)
                else:
                    self.publish('gpio/'+str(g), "OFF", self._qos)
        if time.time() - self._aliveTime > 30:
            ts = datetime.datetime.now().isoformat(timespec="seconds")
            self._aliveTime = time.time()
            self.log.all("pyGPIOmon=", self.id, " is alive")
            self.publish('alive', ts, self._qos, retain=True)

    # display all incoming messages

    def on_message(self, client, userdata, message):
        self.log.debug("MQTT received msg="+str(message.payload))

    def on_publish(self, client, userdata, mid):
        self.log.debug("MQTT received=", mid)
        # self.receivedMessages.append(mid)

    def on_mqtt_connect(self, client, userdata, flags, rc):
        self.mqtt_connected = rc
        self._mqtt_reconnect = 0
        if rc != 0:
            self.logE("MQTT connection returned result="+rc)
            self._mqtt_reconnect += 1
            if self._mqtt_reconnect > 12:
                self._mqtt_reconnect = 12
            self.mqtt_reconnect_delay = 2**self._mqtt_reconnect
        else:
            self.log.info("Connected to MQTT broker.")

    def on_mqtt_disconnect(self, client, userdata, rc):
        self._mqtt_reconnect = 1
        if rc != 0:
            self.log.err("MQTT unexpected disconnection.")
            self._mqtt_reconnect = True
            self.mqtt_reconnect_delay = 10

    # publish a message
    def publish(self, topic, message, qos=1, retain=False):
        self.log.debug("publishing topic=", self._id +
                       '/'+topic, "message=", message)
        mid = self._mqtt.publish(self._id+'/'+topic, message, qos, retain)[1]

    # callback for interrupts
    def gpioCbf(self, GPIO, level, tick):
        self._gpios[GPIO]['t'] = tick
        self._gpios[GPIO]['u'] = True
        if level == 1:
            self._gpios[GPIO]['s'] = 1
        else:
            self._gpios[GPIO]['s'] = 0
        self.log.debug("GPIO status changed", GPIO, level, self._gpios[GPIO])


# -------------------------------------------------------
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
print("Creating MQTT client for", serverUrl)
mqtt = mqtt.Client(devId)
mqtt.username_pw_set(username, password)
mqtt.connect_async(serverUrl)

print("Creating PyGPIOmon device as", devId)
mon = PyGPIOmon(devId, pi, mqtt,
                qos=qos,
                logger=Logger(filename=logfile, level=loglevel),
                gpios=gpios,
                gpios_set=gpiosSet)
mon.start()

try:
    while True:
        time.sleep(1)
        mon.loop()
except KeyboardInterrupt:
    print("\nTidying up")
    mon.stop()

pi.stop()
