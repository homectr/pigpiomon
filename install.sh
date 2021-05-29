#!/bin/bash
set -x
echo "Installing pigpiomon script"

function check_installed {
    echo "here"
    local status=$?
    if [ $status -ne 0 ]; then
        echo "error: not installed"
        exit 1
    fi
    echo "ok"
}

function check_running {
    echo "here2"
    local cnt=`ps aux | grep -c ${1}`
    # assuming running if at least two lines found in ps result
    if [ $cnt -gt 1 ]; then
        echo "ok"
        return 0
    fi
    echo "error: not running"
}

echo -n "Checking if pigpio is installed... "
pigpiod -v > /dev/null
check_installed

echo "Checking if pigpiod is running"
check_running "pigpiod"

echo "Checking if python3 is installed"
python3 --version > /dev/null
check_installed

echo "Checking if pip is installed"
python3 -m pip --version > /dev/null
check_installed

echo "Installing required python packages"
python3 -m pip install pigpio paho-mqtt

echo "Copying script to /opt/pigpiomon folder"
sudo mkdir /opt/pigpiomon
sudo cp ./pigpiomon.py /opt/pigpiomon

echo "Copying default configuration to /etc"
sudo cp ./pigpiomon.cfg /etc

echo "Creating log file and configuring logrotate"
sudo touch /var/log/pigpiomon.log
sudo cp ./pigpiomon.logrotate /etc/logrotate.d/pigpiomon
sudo systemctl restart logrotate

echo "Creating service"
sudo cp ./pigpiomon.service /lib/systemd/system
sudo systemctl daemon-reload
sudo systemctl enable pigpiomon.service

echo "Starting service"
sudo systemctl start pigpiomon.service

echo "Installation complete"
echo "Modify script configuration in /etc/pigpiomon.cfg"
echo "Restart script service using: sudo systemctl restart pigpiomon"
echo "Check service status using: sudo systemctl status pigpiomon"