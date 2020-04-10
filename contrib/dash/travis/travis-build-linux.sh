#!/bin/bash
set -ev

<<'COMMIT'

if [[ -z $TRAVIS_TAG ]]; then
  echo TRAVIS_TAG unset, exiting
  exit 1
fi

BUILD_REPO_URL=https://github.com/John-Tonny/electrum-vds.git

cd build

git clone --branch $TRAVIS_TAG $BUILD_REPO_URL electrum-vds


mkdir -p electrum-vds/dist

COMMIT

wget -O electrum-vds/dist/tor-proxy-setup.exe \
    https://github.com/zebra-lucky/tor-proxy/releases/download/0.3.5.8/tor-proxy-0.3.5.8-setup.exe

docker run --rm \
    -v $(pwd):/opt \
    -w /opt/electrum-vds \
    -t zebralucky/electrum-dash-winebuild:LinuxPy36 /opt/electrum-vds/build_linux.sh

sudo find . -name '*.po' -delete
sudo find . -name '*.pot' -delete


docker run --rm \
    -v $(pwd):/opt \
    -w /opt/electrum-vds/contrib/dash/travis \
    -t zebralucky/electrum-dash-winebuild:LinuxAppImage /opt/electrum-vds/build_appimage.sh


export WINEARCH=win32
export WINEPREFIX=/root/.wine-32
export PYHOME=$WINEPREFIX/drive_c/Python36

wget https://github.com/zebra-lucky/zbarw/releases/download/20180620/zbarw-zbarcam-0.10-win32.zip
unzip zbarw-zbarcam-0.10-win32.zip 
#&& rm zbarw-zbarcam-0.10-win32.zip

wget https://github.com/zebra-lucky/x11_hash/releases/download/1.4.1/x11_hash-1.4.1-win32.zip
unzip x11_hash-1.4.1-win32.zip 
#&& rm x11_hash-1.4.1-win32.zip

wget https://github.com/zebra-lucky/secp256k1/releases/download/0.1/libsecp256k1-0.1-win32.zip
unzip libsecp256k1-0.1-win32.zip 
#&& rm libsecp256k1-0.1-win32.zip

docker run --rm \
    -e WINEARCH=$WINEARCH \
    -e WINEPREFIX=$WINEPREFIX \
    -e PYHOME=$PYHOME \
    -v $(pwd):/opt \
    -v $(pwd)/electrum-vds/:$WINEPREFIX/drive_c/electrum-vds \
    -w /opt/electrum-vds \
    -t zebralucky/electrum-dash-winebuild:WinePy36 /opt/electrum-vds/build_wine.sh

export WINEARCH=win64
export WINEPREFIX=/root/.wine-64
export PYHOME=$WINEPREFIX/drive_c/Python36

wget https://github.com/zebra-lucky/zbarw/releases/download/20180620/zbarw-zbarcam-0.10-win64.zip
unzip zbarw-zbarcam-0.10-win64.zip 
#&& rm zbarw-zbarcam-0.10-win64.zip

wget https://github.com/zebra-lucky/x11_hash/releases/download/1.4.1/x11_hash-1.4.1-win64.zip
unzip x11_hash-1.4.1-win64.zip 
#&& rm x11_hash-1.4.1-win64.zip

wget https://github.com/zebra-lucky/secp256k1/releases/download/0.1/libsecp256k1-0.1-win64.zip
unzip libsecp256k1-0.1-win64.zip
#&& rm libsecp256k1-0.1-win64.zip

docker run --rm \
    -e WINEARCH=$WINEARCH \
    -e WINEPREFIX=$WINEPREFIX \
    -e PYHOME=$PYHOME \
    -v $(pwd):/opt \
    -v $(pwd)/electrum-vds/:$WINEPREFIX/drive_c/electrum-vds \
    -w /opt/electrum-vds \
    -t zebralucky/electrum-dash-winebuild:WinePy36 /opt/electrum-vds/build_wine.sh
