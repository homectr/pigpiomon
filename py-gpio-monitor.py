#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import paho.mqtt.client as mqtt
import time
import datetime
import configparser
import sys
import getopt
import pigpio


class Config:
    # client, user and device details
    def __init__(self, argv):
        self.serverUrl = "localhost"
        self.username = "<<username>>"
        self.password = "<<password>>"

        self.devId = "pyGPIOmon"  # device id, also used as mqtt client id and mqtt base topic

        self.logfile = "./py-gpio-monitor.log"
        self.logLevel = Logger.LOG_INFO
        self.gpios = []  # array of monitored gpios
        self.gpiosSet = []  # array of settable gpios
        self.configFile = './py-gpio-monitor.ini'
        self.qos = 1

        self.parseArgs(argv)

        if len(self.configFile) > 0:
            self.readConfig(self.configFile)

    def help(self):
        print('Usage: '+sys.argv[0] +
              ' -c <configfile> -v <verbose level> -l <logfile>')
        print()
        print('  -c | --config: ini-style configuration file, default is '+self.configFile)
        print('  -v | --verbose: 0-fatal, 1-error, 2-warning, 3-info, 4-debug')
        print('  -l | --logfile: log file name,default is '+self.logfile)
        print()
        print('Example: '+sys.argv[0] +
              ' -c /etc/monitor.ini -v 2 -l /var/log/monitor.log')

    def parseArgs(self, argv):
        try:
            opts, args = getopt.getopt(
                argv, "hc:v:l:", ["config=", "verbose=", "logfile="])
        except getopt.GetoptError:
            print("Command line argument error")
            self.help()
            sys.exit(2)

        for opt, arg in opts:
            if opt == '-h':
                self.help()
                sys.exit()
            elif opt in ("-c", "--config"):
                self.configFile = arg
            elif opt in ("-v", "--verbose"):
                self.logLevel = int(arg)
            elif opt in ("-l", "--logfile"):
                self.logfile = arg

    def readConfig(self, cf):
        print('Using configuration file ', cf)
        config = configparser.ConfigParser()
        config.read(cf)

        try:
            seccfg = config['pygpiomon']
        except KeyError:
            print('Error: configuration file is not correct or missing')
            exit(1)

        self.serverUrl = seccfg.get('host', 'localhost')
        self.username = seccfg.get('username')
        self.password = seccfg.get('password')
        self.devId = seccfg.get('id', 'pyGPIOmon')
        self.qos = int(seccfg.get('qos', "1"))
        a = seccfg.get('gpios_monitor')
        for g in a.split(','):
            self.gpios.append(int(g))
        a = seccfg.get('gpios_set')
        for g in a.split(','):
            self.gpiosSet.append(int(g))


class Logger:
    LogLevels = ["A", "F", "E", "W", "I", "D"]

    LOG_ALL = 0
    LOG_FATAL = 1
    LOG_ERROR = 2
    LOG_WARN = 3
    LOG_INFO = 4
    LOG_DEBUG = 5

    def __init__(self, *, filename="", console=False, level=4):
        self._f = 0
        self._console = console
        self.logLevel = level
        self.enabled = True

        print("Logging to", filename, "level=", level)

        if filename != "":
            try:
                self._f = open(filename, "a")
            except FileNotFoundError:
                print("Error opening log file", filename)
                exit(1)

        if self._f == 0:
            self._console = True

    def warn(self, *args):
        self._log(args, level=self.LOG_WARN)

    def err(self, *args):
        self._log(args, level=self.LOG_ERROR)

    def debug(self, *args):
        self._log(args, level=self.LOG_DEBUG)

    def info(self, *args):
        self._log(args, level=self.LOG_INFO)

    def all(self, *args):
        self._log(args, level=self.LOG_ALL)

    def _log(self, args, level=4):
        if not self.enabled:
            return
        if level > self.logLevel:
            return
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        line = ts + "  " + self.LogLevels[level]
        for a in args:
            line += (" "+str(a))
        if self._f:
            self._f.write(line + "\n")
        if self._console:
            print(line)

    def stop(self):
        self._f.close()
        self.enabled = False


class App:
    def __init__(self, id, mqttClient, logger):
        self.id = id
        self.log = logger
        self._mqtt = mqttClient
        self._mqtt_reconnect = 0  # reconnect count

        self._mqtt.on_message = self._on_mqtt_message
        self._mqtt.on_publish = self._on_mqtt_publish
        self._mqtt.on_connect = self._on_mqtt_connect
        self._mqtt.on_disconnect = self._on_mqtt_disconnect

        self.log.all("subscribing to MQTT channel", "cmd/"+self.id)
        self._mqtt.subscribe("cmd/"+self.id, 1)

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        self.mqtt_connected = rc
        self._mqtt_reconnect = 0
        if rc != 0:
            self.log.err("MQTT connection returned result="+rc)
            self._mqtt_reconnect += 1
            if self._mqtt_reconnect > 12:
                self._mqtt_reconnect = 12
            self.mqtt_reconnect_delay = 2**self._mqtt_reconnect
        else:
            self.log.info("Connected to MQTT broker.")

    def _on_mqtt_disconnect(self, client, userdata, rc):
        self._mqtt_reconnect = 1
        if rc != 0:
            self.log.err("MQTT unexpected disconnection.")
            self._mqtt_reconnect += 1
            self.mqtt_reconnect_delay = 10

    # display all incoming messages
    def _on_mqtt_message(self, client, userdata, message):
        self.log.debug("MQTT message="+str(message.payload))
        print("MQTT message="+str(message.payload))

    def _on_mqtt_publish(self, client, userdata, mid):
        self.log.debug("MQTT received=", mid)

    def loop(self):
        if self._mqtt_reconnect > 0:
            self.log.warn("MQTT Reconnecting...")
            self._mqtt.reconnect()


class PyGPIOmon:
    GPIOStatesStrings = "on ON 1 off OFF 0"
    GPIOStatesStringsPositive = 7

    def __init__(self, id, pi, mqttClient, *, qos=1, gpios=[], gpios_set=[], logger=Logger()):

        self._id = id
        self._pi = pi  # pigpio instance
        self._mqtt = mqttClient  # mqtt client
        self.log = logger
        self._qos = qos

        self._gpios = {}
        for g in gpios:
            # object constaining gpio statuses
            self._gpios[g] = {'t': 0, 's': 0, 'u': False}

        self._gSet = gpios_set
        print(gpios_set)
        for g in gpios_set:
            c = "cmd/"+id+"/gpio/"+str(g)
            print("print", c, g)

            self.log.all("subscribing to MQTT channel", c)
            self._mqtt.subscribe(c, 1)

            self._mqtt.message_callback_add(
                c,
                lambda client, userdata, message:
                    self.on_mqtt_gpio_set(g, str(message.payload.decode()))
            )

        self._aliveTime = 0

    def stop(self):
        self.log.all("*** PyGPIOmon Shutting down", self._id)
        for g in self._gpios:
            self._gpios[g]['cb'].cancel()

    def start(self):
        self.log.all("*** PyGPIOmon Starting", self._id)

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
            self.log.all("pyGPIOmon=", self._id, " is alive")
            self.publish('alive', ts, self._qos, retain=True)

    def on_mqtt_gpio_set(self, gpio, payload):
        i = self.GPIOStatesStrings.find(payload)
        self.log.debug("GPIO ", gpio, "received", payload, i)

        if i < 0:
            return
        on = 1 if i <= self.GPIOStatesStringsPositive else 0
        self.log.info("GPIO ", gpio, "set to", on)
        pi.write(gpio, on)

    # publish a message
    def publish(self, topic, message, qos=1, retain=False):
        self.log.info("publishing topic=", self._id +
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


def on_message(client, userdata, message):
    print("MESSAGE", message.payload.decode())


# -------------------------------------------------------
pi = pigpio.pi()  # connect to pigpio daemon

if not pi.connected:
    print("Error: Failed connecting to pigpiod. Installed and running?")
    exit(3)

# parse commandline aruments and read config file if specified
cfg = Config(sys.argv[1:])

if len(cfg.gpios) == 0:
    print("Error: no gpios specified")
    cfg.help()
    exit(1)

log = Logger(filename=cfg.logfile, level=cfg.logLevel, console=True)

print("Going to monitor gpios=", cfg.gpios)
print("Going to set gpios=", cfg.gpiosSet)

# connect the client to MQTT broker and register a device
print("Creating MQTT client for", cfg.serverUrl)
mqttc = mqtt.Client(cfg.devId)
mqttc.username_pw_set(cfg.username, cfg.password)
mqttc.connect(cfg.serverUrl)

app = App(cfg.devId, mqttc, log)

print("Creating PyGPIOmon device as", cfg.devId)
device = PyGPIOmon(cfg.devId, pi, mqttc,
                   qos=cfg.qos,
                   logger=log,
                   gpios=cfg.gpios,
                   gpios_set=cfg.gpiosSet)
device.start()
mqttc.loop_start()

try:
    while True:
        time.sleep(1)
        app.loop()
        device.loop()

except KeyboardInterrupt:
    print("\nTidying up")

device.stop()
log.stop()
mqttc.disconnect()
mqttc.loop_stop()
pi.stop()
