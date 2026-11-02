# gunicorn.conf.py – production configuration for ETICMONT

bind = "0.0.0.0:8000"
workers = 3              # 2×CPU+1 is the rule of thumb; adjust on server
threads = 2
timeout = 120
accesslog = "-"          # stdout → captured by Docker logs
errorlog = "-"
loglevel = "info"
