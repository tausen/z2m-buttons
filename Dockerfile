FROM python:3.12-alpine

# this installs a version that seems to be for python 3.12, thus basing on python 3.12 image
RUN apk add --no-cache py3-paho-mqtt

# the directory where the package is installed is not in PYTHONPATH by default, though, so:
ENV PYTHONPATH /usr/lib/python3.12/site-packages

RUN apk add --no-cache py3-yaml

# default to running our python script which runs until stopped
ADD z2m-buttons.py /
CMD ["python", "z2m-buttons.py"]
