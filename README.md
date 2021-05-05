# py-gpgio-monitor

Python GPIO monitor MQTT client

# Installation

1. install Python 3
1. install Python libs\
   `pip install paho-mqtt pigpio`
1. copy script and configuration ini file to any directory, e.g. user home
1. prepare empty log file\
   `sudo touch /var/log/py-gpio-monitor.log`\
   `sudo chown openhabian /var/log/py-gpio-monitor.log`
1. copy `py-gpio-monitor.service` to `/lib/systemd/system`
1. modify service file as needed
1. make systemctl daemon aware of new service, run\
   `sudo systemctl daemon-reload`
1. enable and start service\
   `sudo systemctl enable py-gpgio-monitor.service`\
   `sudo systemctl start py-gpgio-monitor.service`
1. create empty logrotate configuration in /etc/logrotate.d/py-gpgio-monitor
1. copy-paste following configuration\
   ````/var/log/py-gpgio-monitor.log {
     size 5M
     rotate 3
     missingok
     dateext
     copytruncate
     compress
     delaycompress
   }```
   ````
1. restart logrotate service

# Configuration file

Script reads configuration from ini file located in the script folder or from location provided as command line argument -cFile

```
[pygpiomon]
host=myqtt.server.com
username=myusername
password=mysecretpassword
id=pyGPIOmon
qos=1
gpios_set=13,24
gpios_mon=23
```

- host - ip address or host name of MQTT server. Default is `localhost`.
- username - username used to authenticate to MQTT server. Default is none.
- password - password for username. Default is none.
- id - MQTT client identifier - should be unique. Default is `pyGPIOmon`
- qos - MQTT QOS for publishing gpio statuses. Default is `1`.
- gpios_set - comma-separated list of gpios which will be set by MQTT
- gpios_mon - comma-separated list of gpios which will be monitored and their statuses published on MQTT

# MQTT channels

Publishing "ON"/"OFF" status on channels `{clientId}/{gpio}`
Publishing alive status as ISO date on channel `{clientId}/alive`
Accepting gpio status changes "ON/OFF" or "1/0" on channels `{clientid}/cmd/{gpio}`

# Usage

1. getting help on commandline options
   `python3 py-gpio-monitor.py -h`
1. check service status
   `sudo systemctl status py-gpgio-monitor`
1. restart service
   `sudo systemctl restart py-gpgio-monitor`
