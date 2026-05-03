# Kind Project

The intention of this project is to install kind on Ubuntu so that I remember the process and the settings for doing so.

[This is the reference I am referring to in this readme](https://kind.sigs.k8s.io/docs/user/quick-start/#installing-from-release-binaries)

# Installation on Macos: 
## for Intel Macs
[ $(uname -m) = x86_64 ]&& curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.15.0/kind-darwin-amd64
## for M1 / ARM Macs
[ $(uname -m) = arm64 ] && curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.15.0/kind-darwin-arm64
chmod 0555 kind
mv kind /usr/local/bin

# Installlation on Linux 

chmod +x ./kind
mv ./kind /some-dir-in-your-PATH/kind
Installation on linux will begin through the following code:
```
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.14.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind
```
