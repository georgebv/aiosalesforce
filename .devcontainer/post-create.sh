#!/bin/bash

set -ex

printf "\nalias ll='ls -lahSr --color=auto'\n" >> ~/.bashrc
rye sync
rye run pre-commit install
