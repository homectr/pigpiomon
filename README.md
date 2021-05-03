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
    ```/var/log/py-gpgio-monitor.log {
      size 5M
      rotate 3
      missingok
      dateext
      copytruncate
      compress
      delaycompress
    }```
 1. restart logrotate service

# Configuration file
Script reads configuration from ini file located in the script folder or from location provided as command line argument -cFile
```
[mqtt]
url= 
username= 
password=
clientid=pyGPIOmon
```

* url - ip address or host name of MQTT server
* username - username used to authenticate to MQTT server
* password - password for username
* clientid - MQTT client identifier - should be unique

# MQTT channels
Publishing "ON"/"OFF" status on channels `{clientId}/{gpio}`
Publishing alive status as ISO date on channel `{clientId}/alive`

# Usage
1. check service status
   `sudo systemctl status py-gpgio-monitor`
1. restart service
   `sudo systemctl restart py-gpgio-monitor`
