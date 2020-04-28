#!/bin/bash

sudo docker run -it          --name electrum-android-builder-cont1         -v $PWD:/home/user/wspace/electrum         -v ~/.keystore:/home/user/.keystore         --workdir /home/user/wspace/electrum         electrum-syscoin:v1.2       /bin/bash
