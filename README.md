# Raspberry Pi GPIO monitor MQTT client

Python script which

- monitors specified GPIOS and sends changes to specified MQTT broker
- listens to MQTT channels and sets specified GPIOS accordingly

# Requires

1. `pigpio` daemon/package installed and running
1. `python3` and `pip`

# Installation

1. copy project files to your local folder
1. make script `install.sh` executable
   `chmod +x install.sh`
1. run install.sh
   `./install.sh`

# Configuration file

Script reads configuration from ini-style file located in the script folder or from location provided as command line argument.

```
[pigpiomon]
host=myqtt.server.com
username=myusername
password=mysecretpassword
id=pigpiomon
qos=1
gpios_set=13,24
gpios_mon=23
```

- host - ip address or host name of MQTT server. Default is `localhost`.
- username - username used to authenticate to MQTT server. Default is none.
- password - password for username. Default is none.
- id - MQTT client identifier - should be unique. Default is `pigpiomon`
- qos - MQTT QOS for publishing gpio statuses. Default is `1`.
- gpios_set - comma-separated list of gpios which will be set by MQTT
- gpios_mon - comma-separated list of gpios which will be monitored and their statuses published on MQTT

# MQTT channels

### Publishes to
- `{clientId}/{gpio}` - publishing "ON"/"OFF" status on channels 
- `{clientId}/alive` - ISO datetime updated every 30s

### Subscribes to
- `{clientid}/gpio/{gpio}/cmd` - gpio status changes "ON/OFF" or "1/0"

# Usage

1. getting help on commandline options
   `python3 pigpiomon.py -h`
1. check service status
   `sudo systemctl status pigpiomon`
1. restart service
   `sudo systemctl restart pigpiomon`
