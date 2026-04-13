#FROM python:3.12
#recup img python officielle du docker hub
FROM python
#image  python se base sur ubuntu, on met à jour ubuntu
RUN apt-get update 
RUN apt-get install -y python3-pip

COPY requirements.txt /etc/requirements.txt
RUN pip install -r /etc/requirements.txt

COPY templates /etc/templates
COPY static /etc/static
COPY app-docker.py /etc/app-docker.py

#RUN python3 /etc/app.py  
ENTRYPOINT ["python3", "/etc/app-docker.py"] 

