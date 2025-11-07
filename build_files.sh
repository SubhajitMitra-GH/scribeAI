#!/bin/bash

# 1. Enable the EPEL (Extra Packages) repository
amazon-linux-extras install epel -y

# 2. Now that the repository is added, install ffmpeg
yum install -y ffmpeg
