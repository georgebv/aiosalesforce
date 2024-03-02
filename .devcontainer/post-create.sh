#!/bin/bash

set -ex

printf "\nalias ll='ls -lahSr --color=auto'\n" >> ~/.bashrc
rye sync
